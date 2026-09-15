"""user_invitations row-level security under the NOBYPASSRLS runtime role.

The ordinary test database is built with ``create_all`` and has no policies,
so these checks only mean something against a migrated database reached
through the least-privilege application role (``RLS_TEST_DATABASE_URL``).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import set_invitation_token_lookup, set_tenant_context
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.services import user_invitations as invitations


def _runtime_url() -> str:
    url = os.getenv("RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RLS_TEST_DATABASE_URL is required for runtime-role integration")
    return url


async def _seed_invitation(db_session, tenant: Tenant, email: str, token: str):
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=email,
        role="user",
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    invitation = UserInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        token_hash=invitations.hash_invite_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invitation)
    await db_session.commit()
    return user, invitation


@pytest.mark.asyncio
async def test_user_invitations_rls_isolates_firms_and_limits_token_lookup(
    db_session, test_tenant
):
    url = _runtime_url()
    other_tenant = Tenant(
        id=uuid.uuid4(),
        name="Other Firm",
        domain=f"other-{uuid.uuid4().hex[:8]}.example",
        billing_tier="payg",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.commit()
    token_a = f"firm-a-{uuid.uuid4().hex}"
    token_b = f"firm-b-{uuid.uuid4().hex}"
    _, invitation_a = await _seed_invitation(
        db_session, test_tenant, "a@testfirm.com", token_a
    )
    _, invitation_b = await _seed_invitation(
        db_session, other_tenant, "b@other.example", token_b
    )
    invitation_a_id, invitation_b_id = invitation_a.id, invitation_b.id

    engine = create_async_engine(url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as runtime_db:
            # No tenant and no presented token: nothing is visible.
            assert (
                await runtime_db.execute(select(UserInvitation.id))
            ).scalars().all() == []
            await runtime_db.rollback()

            # A firm sees only its own invitations.
            await set_tenant_context(runtime_db, str(other_tenant.id))
            visible = (
                (await runtime_db.execute(select(UserInvitation.id))).scalars().all()
            )
            assert visible == [invitation_b_id]
            await runtime_db.rollback()

            # Presenting a token reveals exactly that one row, and nothing else.
            await set_invitation_token_lookup(
                runtime_db, invitations.hash_invite_token(token_a)
            )
            visible = (
                (await runtime_db.execute(select(UserInvitation.id))).scalars().all()
            )
            assert visible == [invitation_a_id]
            # The lookup is read-only: it cannot revoke or accept the row.
            revoked = await runtime_db.execute(
                update(UserInvitation)
                .where(UserInvitation.id == invitation_a_id)
                .values(revoked_at=datetime.now(timezone.utc))
            )
            assert revoked.rowcount == 0
            await runtime_db.rollback()

            # Another firm's context plus a leaked token still cannot write it.
            await set_tenant_context(runtime_db, str(other_tenant.id))
            await set_invitation_token_lookup(
                runtime_db, invitations.hash_invite_token(token_a)
            )
            hijack = await runtime_db.execute(
                update(UserInvitation)
                .where(UserInvitation.id == invitation_a_id)
                .values(accepted_at=datetime.now(timezone.utc))
            )
            assert hijack.rowcount == 0
            await runtime_db.rollback()

            # The service path binds the invitation's own firm and can claim it.
            ctx = await invitations.resolve_invitation(runtime_db, token_a)
            assert ctx.tenant.id == test_tenant.id
            assert ctx.invitation.id == invitation_a_id
            await invitations.claim_invitation(
                runtime_db, ctx.invitation.id, "password"
            )
            await runtime_db.commit()
    finally:
        await engine.dispose()

    await db_session.refresh(invitation_a)
    await db_session.refresh(invitation_b)
    assert invitation_a.accepted_method == "password"
    assert invitation_b.accepted_at is None and invitation_b.revoked_at is None
