"""Runtime-role proof that both template-set tables are fail-closed under FORCE RLS.

The handlers are covered with a mocked session; this is the one test that
exercises the policies themselves, the gap the Clio-parity execution status
named first. It creates the runtime role and the policies migration 175
declares, then reads and writes as that role.
"""

import os
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import set_tenant_context
from app.models.document_template import DocumentTemplate
from app.models.document_template_set import DocumentTemplateSet, DocumentTemplateSetItem
from app.models.tenant import Tenant

_ROLE = "template_sets_rls_probe"
_PASSWORD = "template_sets_rls_probe_password"
_TABLES = ("document_template_sets", "document_template_set_items")
_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


@pytest.mark.asyncio
async def test_template_set_tables_are_fail_closed_and_tenant_scoped(db_session, test_tenant):
    database_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/legalapp_test"
    )
    tenant_b = Tenant(
        id=uuid.uuid4(),
        name="Sets RLS Tenant B",
        domain=f"sets-rls-{uuid.uuid4().hex}@example.test",
        is_active=True,
    )
    template_a = DocumentTemplate(tenant_id=test_tenant.id, title="A form", body="", format="pdf")
    template_b = DocumentTemplate(tenant_id=tenant_b.id, title="B form", body="", format="pdf")
    db_session.add_all([tenant_b, template_a, template_b])
    await db_session.flush()
    set_a = DocumentTemplateSet(tenant_id=test_tenant.id, title="Packet A")
    set_b = DocumentTemplateSet(tenant_id=tenant_b.id, title="Packet B")
    db_session.add_all([set_a, set_b])
    await db_session.flush()
    db_session.add_all(
        [
            DocumentTemplateSetItem(tenant_id=test_tenant.id, set_id=set_a.id, template_id=template_a.id, position=0),
            DocumentTemplateSetItem(tenant_id=tenant_b.id, set_id=set_b.id, template_id=template_b.id, position=0),
        ]
    )
    await db_session.commit()
    set_a_id, set_b_id, template_a_id = set_a.id, set_b.id, template_a.id

    admin_engine = create_async_engine(database_url, pool_pre_ping=True)
    role_url = (
        make_url(database_url).set(username=_ROLE, password=_PASSWORD).render_as_string(hide_password=False)
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
            for table in _TABLES:
                await connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                await connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
                await connection.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
                await connection.execute(
                    text(
                        f"CREATE POLICY tenant_isolation ON {table} "
                        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
                    )
                )
                await connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {_ROLE}"))
            await connection.execute(text(f"GRANT SELECT ON document_templates TO {_ROLE}"))
            await connection.execute(text(f"GRANT SELECT ON tenants TO {_ROLE}"))

        runtime_engine = create_async_engine(role_url, pool_pre_ping=True)
        maker = async_sessionmaker(runtime_engine, expire_on_commit=False)
        async with maker() as runtime_db:
            for table in _TABLES:
                flags = (
                    await runtime_db.execute(
                        text(
                            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                            f"WHERE oid = '{table}'::regclass"
                        )
                    )
                ).one()
                assert flags == (True, True), table
            # No tenant context: fail closed, both tables.
            assert (await runtime_db.scalar(select(func.count()).select_from(DocumentTemplateSet))) == 0
            assert (await runtime_db.scalar(select(func.count()).select_from(DocumentTemplateSetItem))) == 0
            # Tenant A sees only its own set and item.
            await set_tenant_context(runtime_db, str(test_tenant.id))
            visible = (await runtime_db.execute(select(DocumentTemplateSet.id))).scalars().all()
            assert visible == [set_a_id]
            items = (await runtime_db.execute(select(DocumentTemplateSetItem.set_id))).scalars().all()
            assert items == [set_a_id]
            assert await runtime_db.get(DocumentTemplateSet, set_b_id) is None
            # A write into another tenant's set is refused by the policy.
            runtime_db.add(
                DocumentTemplateSetItem(
                    tenant_id=tenant_b.id, set_id=set_b_id, template_id=template_a_id, position=5
                )
            )
            with pytest.raises(DBAPIError):
                await runtime_db.flush()
            await runtime_db.rollback()
    finally:
        if runtime_engine is not None:
            await runtime_engine.dispose()
        async with admin_engine.begin() as connection:
            for table in _TABLES:
                await connection.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
                await connection.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
                await connection.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        await admin_engine.dispose()
