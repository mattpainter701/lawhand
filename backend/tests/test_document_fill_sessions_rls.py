"""Runtime-role proof that document_fill_sessions is fail-closed under FORCE RLS.

The service tests cover the handlers through the ORM; this is the one test that
exercises migration 198's policy itself, the gap named for the set tables. It
creates a runtime role with the policy, then reads and writes as that role.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import set_tenant_context
from app.models.document_fill_session import DocumentFillSession
from app.models.tenant import Tenant
from app.models.user import User

_ROLE = "fill_sessions_rls_probe"
_PASSWORD = "fill_sessions_rls_probe_password"
_TABLE = "document_fill_sessions"
_POLICY = "document_fill_sessions_tenant_isolation"
_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


def _session(tenant_id, user_id):
    return DocumentFillSession(
        tenant_id=tenant_id,
        user_id=user_id,
        template_id=uuid.uuid4(),
        title="Probe",
        answers_sha256="a" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_document_fill_sessions_is_fail_closed_and_tenant_scoped(
    db_session, test_tenant, test_user
):
    database_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/legalapp_test"
    )
    tenant_b = Tenant(
        id=uuid.uuid4(),
        name="Fill session RLS Tenant B",
        domain=f"fill-rls-{uuid.uuid4().hex}@example.test",
        is_active=True,
    )
    user_b = User(
        id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        email=f"fill-rls-{uuid.uuid4().hex}@example.test",
        role="user",
        is_active=True,
    )
    db_session.add_all([tenant_b, user_b])
    await db_session.flush()
    session_a = _session(test_tenant.id, test_user.id)
    session_b = _session(tenant_b.id, user_b.id)
    db_session.add_all([session_a, session_b])
    await db_session.commit()
    session_a_id, session_b_id = session_a.id, session_b.id

    admin_engine = create_async_engine(database_url, pool_pre_ping=True)
    role_url = (
        make_url(database_url)
        .set(username=_ROLE, password=_PASSWORD)
        .render_as_string(hide_password=False)
    )
    runtime_engine = None
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    f"""
                    DO $$ BEGIN
                      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                        CREATE ROLE {_ROLE} LOGIN PASSWORD '{_PASSWORD}'
                          NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
                      END IF;
                    END $$;
                    """
                )
            )
            await connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {_ROLE}"))
            await connection.execute(
                text(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
            )
            await connection.execute(
                text(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
            )
            await connection.execute(
                text(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
            )
            await connection.execute(
                text(
                    f"CREATE POLICY {_POLICY} ON {_TABLE} "
                    f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
                )
            )
            await connection.execute(
                text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {_TABLE} TO {_ROLE}")
            )

        runtime_engine = create_async_engine(role_url, pool_pre_ping=True)
        maker = async_sessionmaker(runtime_engine, expire_on_commit=False)
        async with maker() as runtime_db:
            flags = (
                await runtime_db.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        f"WHERE oid = '{_TABLE}'::regclass"
                    )
                )
            ).one()
            assert flags == (True, True)
            # No tenant context: fail closed.
            assert (
                await runtime_db.scalar(
                    select(func.count()).select_from(DocumentFillSession)
                )
            ) == 0
            # Tenant A sees only its own session.
            await set_tenant_context(runtime_db, str(test_tenant.id))
            visible = (
                (await runtime_db.execute(select(DocumentFillSession.id)))
                .scalars()
                .all()
            )
            assert visible == [session_a_id]
            assert await runtime_db.get(DocumentFillSession, session_b_id) is None
            # A write attributed to another tenant is refused by the policy.
            runtime_db.add(_session(tenant_b.id, user_b.id))
            with pytest.raises(DBAPIError):
                await runtime_db.flush()
            await runtime_db.rollback()
    finally:
        if runtime_engine is not None:
            await runtime_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
            )
            await connection.execute(
                text(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
            )
            await connection.execute(
                text(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
            )
        await admin_engine.dispose()
