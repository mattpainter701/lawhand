"""Password reset is not a side door into invited or deactivated accounts.

Invitees get in through their invitation. Before, a forgot-password request
for an invitee's address would issue a reset link, and the reset would set a
password while leaving the account inactive, which looked like a broken login.
A deactivated person could also set a password with a link issued earlier.
"""

import uuid

import pytest
import pytest_asyncio

from app.models.user import User
from app.routers import auth as auth_router

GENERIC_MESSAGE = "If that email exists, a reset link has been sent."
NEW_PASSWORD = "correct-horse-battery-staple-42"


@pytest_asyncio.fixture(autouse=True)
async def _reset_auth_rate_limits(test_redis):
    for path in ("/api/auth/forgot-password", "/api/auth/reset-password"):
        async for key in test_redis.scan_iter(f"rate:auth:{path}:*"):
            await test_redis.delete(key)
    yield


@pytest.fixture
def dev_reset_tokens(monkeypatch):
    """Return reset tokens in the response instead of emailing them."""
    monkeypatch.setattr(auth_router.settings, "EMAIL_ENABLED", False)
    monkeypatch.setattr(auth_router.settings, "DEV_MODE", True)


async def _user(db_session, tenant, email, *, is_active, password_hash):
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=email,
        role="user",
        is_active=is_active,
        password_hash=password_hash,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_forgot_password_still_issues_link_for_active_password_user(
    client, db_session, test_tenant, dev_reset_tokens
):
    await _user(
        db_session,
        test_tenant,
        "active@testfirm.com",
        is_active=True,
        password_hash=auth_router._hash_password("an-existing-password-1"),
    )

    response = await client.post(
        "/api/auth/forgot-password", json={"email": "active@testfirm.com"}
    )

    assert response.status_code == 200
    assert response.json()["reset_token"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "is_active", "password_hash"),
    [
        ("invitee@testfirm.com", False, None),
        ("legacy-invitee@testfirm.com", False, "invite:legacy-token"),
        ("deactivated@testfirm.com", False, "$2b$12$placeholderplaceholderpl"),
    ],
)
async def test_forgot_password_sends_nothing_to_invitees_or_deactivated(
    client, db_session, test_tenant, dev_reset_tokens, email, is_active, password_hash
):
    await _user(
        db_session,
        test_tenant,
        email,
        is_active=is_active,
        password_hash=password_hash,
    )

    response = await client.post("/api/auth/forgot-password", json={"email": email})

    # Identical to the unknown-address response, so nothing is enumerable.
    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_MESSAGE, "reset_token": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "password_hash",
    ["invite:legacy-token", "$2b$12$placeholderplaceholderpl"],
)
async def test_reset_refuses_inactive_account_without_changing_it(
    client, db_session, test_tenant, test_redis, password_hash
):
    user = await _user(
        db_session,
        test_tenant,
        "inactive@testfirm.com",
        is_active=False,
        password_hash=password_hash,
    )
    token = f"issued-before-deactivation-{uuid.uuid4().hex}"
    await test_redis.setex(auth_router._reset_key(token), 600, user.email)

    response = await client.post(
        "/api/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired reset token"
    await db_session.refresh(user)
    assert user.is_active is False
    assert user.password_hash == password_hash


@pytest.mark.asyncio
async def test_reset_still_works_for_active_account(
    client, db_session, test_tenant, test_redis
):
    user = await _user(
        db_session,
        test_tenant,
        "resetting@testfirm.com",
        is_active=True,
        password_hash=auth_router._hash_password("an-existing-password-1"),
    )
    token = f"valid-reset-{uuid.uuid4().hex}"
    await test_redis.setex(auth_router._reset_key(token), 600, user.email)

    response = await client.post(
        "/api/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(user)
    assert auth_router._verify_password(NEW_PASSWORD, user.password_hash)
