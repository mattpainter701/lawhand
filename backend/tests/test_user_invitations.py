"""Staff invitations: hashed storage, admin lifecycle, and password acceptance.

Before this existed an invite stored its raw token in ``users.password_hash``
and emailed a link nothing could redeem, so invited people could not get in.
These tests pin the replacement: only a hash is stored, a link works once,
expired/revoked links fail closed, and one firm can never see, resend, revoke,
or accept another firm's invitation.
"""

import asyncio
import re
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from jose import jwt as jose_jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.database import set_tenant_context
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.services import email_admin
from app.services import user_invitations as invitations
from app.services.email import EmailDeliveryResult

settings = get_settings()

STRONG_PASSWORD = "correct-horse-battery-staple-42"
RATE_LIMITED_PATHS = (
    "/api/auth/invite/lookup",
    "/api/auth/invite/accept",
    "/api/auth/login",
)


@pytest_asyncio.fixture(autouse=True)
async def _reset_auth_rate_limits(test_redis):
    """Auth limits are per source IP and every test client shares one."""
    for path in RATE_LIMITED_PATHS:
        async for key in test_redis.scan_iter(f"rate:auth:{path}:*"):
            await test_redis.delete(key)
    yield


@pytest.fixture
def sent_invites(monkeypatch):
    sent: list[dict] = []

    async def fake_send(db, tenant_id, to_emails, subject, html_body):
        sent.append(
            {
                "tenant_id": str(tenant_id),
                "to": list(to_emails),
                "subject": subject,
                "html": html_body,
            }
        )
        return EmailDeliveryResult.SENT

    monkeypatch.setattr(email_admin, "send_admin_notification", fake_send)
    return sent


def _token_from_email(html: str) -> str:
    match = re.search(r"/accept-invite\?token=([^\"&\s<]+)", html)
    assert match, "invitation email must link to the accept page"
    return urllib.parse.unquote(match.group(1))


async def _invite(
    db_session,
    tenant: Tenant,
    email: str = "invitee@testfirm.com",
    *,
    full_name: str | None = "New Colleague",
    principal_type: str = "human",
) -> tuple[User, str]:
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=email,
        full_name=full_name,
        role="user",
        is_active=False,
        principal_type=principal_type,
    )
    db_session.add(user)
    await db_session.flush()
    await set_tenant_context(db_session, str(tenant.id))
    token = await invitations.create_invitation(
        db_session, tenant_id=tenant.id, user_id=user.id, created_by_user_id=None
    )
    await db_session.commit()
    return user, token


async def _open_invitation(db_session, user_id: uuid.UUID) -> UserInvitation | None:
    return await db_session.scalar(
        select(UserInvitation).where(
            UserInvitation.user_id == user_id,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
    )


async def _other_tenant_admin(db_session) -> tuple[Tenant, User, dict]:
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Other Firm",
        domain=f"other-{uuid.uuid4().hex[:8]}.example",
        billing_tier="payg",
        is_active=True,
    )
    admin = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="admin@other.example",
        full_name="Other Admin",
        role="admin",
        is_active=True,
    )
    db_session.add_all([tenant, admin])
    await db_session.commit()
    token = jose_jwt.encode(
        {
            "sub": str(admin.id),
            "tenant_id": str(tenant.id),
            "role": "admin",
            "email": admin.email,
            "billing_tier": "payg",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return tenant, admin, {"Authorization": f"Bearer {token}"}


# ── Admin invite ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invite_stores_only_token_hash_and_links_to_accept_page(
    client, db_session, test_tenant, sent_invites
):
    response = await client.post(
        "/api/admin/users/invite",
        json={
            "email": "  New.Colleague@TestFirm.com ",
            "full_name": "New Colleague",
            "role": "user",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "new.colleague@testfirm.com"
    user = await db_session.scalar(
        select(User).where(User.email == "new.colleague@testfirm.com")
    )
    assert user.is_active is False
    assert user.password_hash is None

    assert len(sent_invites) == 1
    assert sent_invites[0]["to"] == ["new.colleague@testfirm.com"]
    assert "reset-password" not in sent_invites[0]["html"]
    token = _token_from_email(sent_invites[0]["html"])

    invitation = await _open_invitation(db_session, user.id)
    assert invitation.token_hash == invitations.hash_invite_token(token)
    assert token not in invitation.token_hash
    lifetime = invitation.expires_at - invitation.created_at
    assert timedelta(days=6, hours=23) < lifetime <= timedelta(days=7)


@pytest.mark.asyncio
async def test_invite_duplicate_check_ignores_case(client, test_user, sent_invites):
    response = await client.post(
        "/api/admin/users/invite",
        json={"email": test_user.email.upper(), "role": "user"},
    )

    assert response.status_code == 409
    assert sent_invites == []


@pytest.mark.asyncio
async def test_invite_email_escapes_admin_typed_names(client, sent_invites):
    response = await client.post(
        "/api/admin/users/invite",
        json={
            "email": "escaped@testfirm.com",
            "full_name": "<script>alert(1)</script>",
            "role": "user",
        },
    )

    assert response.status_code == 200, response.text
    html = sent_invites[0]["html"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── Lookup ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lookup_describes_pending_invitation_without_consuming_it(
    client, db_session, test_tenant, caplog
):
    user, token = await _invite(db_session, test_tenant)

    first = await client.post("/api/auth/invite/lookup", json={"token": token})
    second = await client.post("/api/auth/invite/lookup", json={"token": token})

    assert first.status_code == 200, first.text
    assert second.status_code == 200
    body = first.json()
    assert body["email_masked"] == "i•••@testfirm.com"
    assert body["firm_name"] == test_tenant.name
    assert body["providers"]["password"] is True
    assert await _open_invitation(db_session, user.id) is not None
    assert token not in caplog.text
    assert user.email not in caplog.text


@pytest.mark.asyncio
async def test_lookup_of_unknown_token_is_refused_with_code(client):
    response = await client.post(
        "/api/auth/invite/lookup", json={"token": "not-a-real-invitation-token"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invite_invalid"


# ── Password acceptance ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_with_password_activates_and_signs_in(
    client, db_session, test_tenant
):
    user, token = await _invite(db_session, test_tenant)

    response = await client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": STRONG_PASSWORD},
    )

    assert response.status_code == 200, response.text
    assert response.json()["tenant_id"] == str(test_tenant.id)
    assert response.json()["email"] == user.email
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies

    await db_session.refresh(user)
    assert user.is_active is True
    assert user.password_hash.startswith("$2")
    accepted = await db_session.scalar(
        select(UserInvitation).where(UserInvitation.user_id == user.id)
    )
    assert accepted.accepted_at is not None
    assert accepted.accepted_method == "password"

    login = await client.post(
        "/api/auth/login", json={"email": user.email, "password": STRONG_PASSWORD}
    )
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_invitation_link_works_only_once(client, db_session, test_tenant):
    _, token = await _invite(db_session, test_tenant)
    payload = {"token": token, "password": STRONG_PASSWORD}

    first = await client.post("/api/auth/invite/accept", json=payload)
    second = await client.post("/api/auth/invite/accept", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 400
    assert second.json()["code"] == "invite_accepted"


@pytest.mark.asyncio
async def test_expired_invitation_is_refused_without_activating(
    client, db_session, test_tenant
):
    user, token = await _invite(db_session, test_tenant)
    await db_session.execute(
        update(UserInvitation)
        .where(UserInvitation.user_id == user.id)
        .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await db_session.commit()

    response = await client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": STRONG_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invite_expired"
    await db_session.refresh(user)
    assert user.is_active is False
    assert user.password_hash is None


@pytest.mark.asyncio
async def test_weak_password_is_rejected_without_consuming_invitation(
    client, db_session, test_tenant
):
    user, token = await _invite(db_session, test_tenant)

    response = await client.post(
        "/api/auth/invite/accept", json={"token": token, "password": "short"}
    )

    assert response.status_code == 422
    assert await _open_invitation(db_session, user.id) is not None
    still_valid = await client.post("/api/auth/invite/lookup", json={"token": token})
    assert still_valid.status_code == 200


@pytest.mark.asyncio
async def test_inactive_firm_cannot_accept(client, db_session, test_tenant):
    user, token = await _invite(db_session, test_tenant)
    test_tenant.is_active = False
    await db_session.commit()

    response = await client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": STRONG_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "tenant_inactive"
    await db_session.refresh(user)
    assert user.is_active is False


@pytest.mark.asyncio
async def test_invitation_for_service_principal_is_treated_as_invalid(
    client, db_session, test_tenant
):
    _, token = await _invite(
        db_session, test_tenant, "automation@testfirm.com", principal_type="service"
    )

    response = await client.post("/api/auth/invite/lookup", json={"token": token})

    assert response.status_code == 400
    assert response.json()["code"] == "invite_invalid"


@pytest.mark.asyncio
async def test_claim_is_single_use_under_concurrency(
    db_session, test_engine, test_tenant
):
    user, _ = await _invite(db_session, test_tenant)
    invitation_id = (await _open_invitation(db_session, user.id)).id
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def attempt() -> str:
        async with factory() as session:
            try:
                await invitations.claim_invitation(session, invitation_id, "password")
                await session.commit()
                return "claimed"
            except invitations.InvitationRefusal:
                await session.rollback()
                return "refused"

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(results) == ["claimed", "refused"]


# ── Admin lifecycle ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resend_replaces_previous_link(
    client, db_session, test_tenant, sent_invites
):
    user, old_token = await _invite(db_session, test_tenant)

    response = await client.post(f"/api/admin/users/{user.id}/invitation/resend")

    assert response.status_code == 200, response.text
    new_token = _token_from_email(sent_invites[-1]["html"])
    assert new_token != old_token
    old = await client.post("/api/auth/invite/lookup", json={"token": old_token})
    new = await client.post("/api/auth/invite/lookup", json={"token": new_token})
    assert old.status_code == 400 and old.json()["code"] == "invite_invalid"
    assert new.status_code == 200


@pytest.mark.asyncio
async def test_resend_refuses_someone_who_already_accepted(
    client, db_session, test_tenant, sent_invites
):
    user, token = await _invite(db_session, test_tenant)
    accepted = await client.post(
        "/api/auth/invite/accept", json={"token": token, "password": STRONG_PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    # Accepting signs the invitee in on this client; drop their cookies so the
    # next call is made as the administrator again.
    client.cookies.clear()

    response = await client.post(f"/api/admin/users/{user.id}/invitation/resend")

    assert response.status_code == 409
    assert sent_invites == []


@pytest.mark.asyncio
async def test_revoked_invitation_cannot_be_accepted(client, db_session, test_tenant):
    user, token = await _invite(db_session, test_tenant)

    revoked = await client.delete(f"/api/admin/users/{user.id}/invitation")
    again = await client.delete(f"/api/admin/users/{user.id}/invitation")
    response = await client.post(
        "/api/auth/invite/accept", json={"token": token, "password": STRONG_PASSWORD}
    )

    assert revoked.status_code == 204
    assert again.status_code == 404
    assert response.status_code == 400
    assert response.json()["code"] == "invite_invalid"


@pytest.mark.asyncio
async def test_deactivating_invitee_revokes_their_link(client, db_session, test_tenant):
    user, token = await _invite(db_session, test_tenant)

    response = await client.delete(f"/api/admin/users/{user.id}")

    assert response.status_code == 204, response.text
    lookup = await client.post("/api/auth/invite/lookup", json={"token": token})
    assert lookup.status_code == 400
    assert lookup.json()["code"] == "invite_invalid"


@pytest.mark.asyncio
async def test_reactivate_refuses_person_who_never_accepted(
    client, db_session, test_tenant
):
    user, _ = await _invite(db_session, test_tenant)

    response = await client.post(f"/api/admin/users/{user.id}/reactivate")

    assert response.status_code == 409
    await db_session.refresh(user)
    assert user.is_active is False


@pytest.mark.asyncio
async def test_reactivate_still_restores_deactivated_colleague(
    client, db_session, test_tenant
):
    colleague = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="former@testfirm.com",
        role="user",
        is_active=False,
    )
    db_session.add(colleague)
    await db_session.commit()

    response = await client.post(f"/api/admin/users/{colleague.id}/reactivate")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reactivated"


@pytest.mark.asyncio
async def test_user_list_reports_each_invitation_state(client, db_session, test_tenant):
    pending, _ = await _invite(db_session, test_tenant, "pending@testfirm.com")
    expired, _ = await _invite(db_session, test_tenant, "expired@testfirm.com")
    revoked, _ = await _invite(db_session, test_tenant, "revoked@testfirm.com")
    accepted, accepted_token = await _invite(
        db_session, test_tenant, "accepted@testfirm.com"
    )
    await db_session.execute(
        update(UserInvitation)
        .where(UserInvitation.user_id == expired.id)
        .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    await db_session.execute(
        update(UserInvitation)
        .where(UserInvitation.user_id == revoked.id)
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db_session.commit()
    joined = await client.post(
        "/api/auth/invite/accept",
        json={"token": accepted_token, "password": STRONG_PASSWORD},
    )
    assert joined.status_code == 200, joined.text
    client.cookies.clear()

    response = await client.get("/api/admin/users")

    assert response.status_code == 200, response.text
    by_email = {row["email"]: row for row in response.json()["users"]}
    assert by_email["pending@testfirm.com"]["invitation_status"] == "pending"
    assert by_email["pending@testfirm.com"]["invitation_expires_at"] is not None
    assert by_email["expired@testfirm.com"]["invitation_status"] == "expired"
    # Revoked but never accepted: still only reachable through a new invitation,
    # so the list must say so rather than show a plain inactive account.
    assert by_email["revoked@testfirm.com"]["invitation_status"] == "revoked"
    assert by_email["revoked@testfirm.com"]["invitation_expires_at"] is None
    assert by_email["accepted@testfirm.com"]["invitation_status"] is None
    assert by_email["attorney@testfirm.com"]["invitation_status"] is None


@pytest.mark.asyncio
async def test_create_invitation_leaves_one_open_row(db_session, test_tenant):
    user, first = await _invite(db_session, test_tenant)
    await set_tenant_context(db_session, str(test_tenant.id))
    second = await invitations.create_invitation(
        db_session, tenant_id=test_tenant.id, user_id=user.id, created_by_user_id=None
    )
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(UserInvitation).where(UserInvitation.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    open_rows = [r for r in rows if r.revoked_at is None and r.accepted_at is None]
    assert len(rows) == 2
    assert [r.token_hash for r in open_rows] == [invitations.hash_invite_token(second)]
    assert first != second


# ── Tenant isolation ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_other_firm_admin_cannot_see_resend_or_revoke_invitation(
    client, db_session, test_tenant, sent_invites
):
    user, token = await _invite(db_session, test_tenant)
    _, _, other_headers = await _other_tenant_admin(db_session)

    listing = await client.get("/api/admin/users", headers=other_headers)
    resend = await client.post(
        f"/api/admin/users/{user.id}/invitation/resend", headers=other_headers
    )
    revoke = await client.delete(
        f"/api/admin/users/{user.id}/invitation", headers=other_headers
    )

    assert listing.status_code == 200, listing.text
    assert user.email not in {row["email"] for row in listing.json()["users"]}
    assert resend.status_code == 404
    assert revoke.status_code == 404
    assert sent_invites == []
    assert await _open_invitation(db_session, user.id) is not None
    still_valid = await client.post("/api/auth/invite/lookup", json={"token": token})
    assert still_valid.status_code == 200


@pytest.mark.asyncio
async def test_acceptance_signs_into_the_inviting_firm_not_the_caller(
    client, db_session, test_tenant
):
    user, token = await _invite(db_session, test_tenant)
    other_tenant, _, other_headers = await _other_tenant_admin(db_session)

    response = await client.post(
        "/api/auth/invite/accept",
        json={"token": token, "password": STRONG_PASSWORD},
        headers=other_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["tenant_id"] == str(test_tenant.id)
    assert response.json()["tenant_id"] != str(other_tenant.id)
    assert response.json()["user_id"] == str(user.id)


def test_mask_email_hides_all_but_first_character():
    assert invitations.mask_email("jane.doe@firm.com") == "j•••@firm.com"
    assert invitations.mask_email("not-an-address") == "•••"
