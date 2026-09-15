"""Accepting a staff invitation by continuing with Google or Microsoft.

Linking requires both a valid, unused invitation token and the provider
reporting the address the invitation was sent to. Without an invitation,
Microsoft sign-in still never links by email; those tests live in
test_auth_oauth_existing_user.py and must keep passing unchanged.
"""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select, update

from app.database import set_tenant_context
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.routers import auth as auth_router
from app.services import user_invitations as invitations

INVITEE_EMAIL = "invitee@testfirm.com"


class _ProviderTokenResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"access_token": "provider-access-token", "id_token": "provider-id"}


def _mock_callback(monkeypatch, provider: str, claims: dict, *, invite: str | None):
    async def consume_state(_request, _state):
        state = {"signup": None, "nonce": "nonce", "pkce_verifier": "verifier"}
        if invite is not None:
            state["invite"] = invite
        return True, state

    async def provider_post(_self, _url, **_kwargs):
        return _ProviderTokenResponse()

    async def verify_token(_raw_token, **_kwargs):
        return claims

    async def issue_access_token(_db, _user, _tenant):
        return "application-jwt"

    async def save_replay(_request, _state, _code, _token, _return_to=None):
        return None

    async def save_callback_token(_request, _token, _return_to=None):
        return "one-time-callback-code"

    monkeypatch.setattr(auth_router, "_consume_state", consume_state)
    monkeypatch.setattr(httpx.AsyncClient, "post", provider_post)
    monkeypatch.setattr(auth_router, f"verify_{provider}_id_token", verify_token)
    monkeypatch.setattr(auth_router, "_issue_access_token", issue_access_token)
    monkeypatch.setattr(auth_router, "_save_callback_replay", save_replay)
    monkeypatch.setattr(auth_router, "_save_callback_token", save_callback_token)
    monkeypatch.setattr(auth_router.settings, "PUBLIC_SIGNUP_ENABLED", False)


async def _invite(
    db_session, tenant: Tenant, email: str = INVITEE_EMAIL
) -> tuple[User, str]:
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=email,
        full_name=None,
        role="user",
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    await set_tenant_context(db_session, str(tenant.id))
    token = await invitations.create_invitation(
        db_session, tenant_id=tenant.id, user_id=user.id, created_by_user_id=None
    )
    await db_session.commit()
    return user, token


async def _invitation(db_session, user_id) -> UserInvitation:
    return await db_session.scalar(
        select(UserInvitation).where(UserInvitation.user_id == user_id)
    )


def _google_claims(email: str, *, verified: bool = True, sub: str = "google-new"):
    return {"sub": sub, "email": email, "email_verified": verified, "name": "Invitee"}


def _microsoft_claims(
    email: str | None,
    *,
    preferred_username: str | None = None,
    tid: str = "11111111-1111-1111-1111-111111111111",
    oid: str = "22222222-2222-2222-2222-222222222222",
):
    return {
        "sub": "ms-pairwise-sub",
        "email": email,
        "preferred_username": preferred_username,
        "tid": tid,
        "oid": oid,
        "name": "Invitee",
    }


def _assert_login_redirect(response, code: str) -> None:
    assert response.status_code == 303, response.text
    assert response.headers["location"].endswith(f"/login?error={code}")


async def _callback(client, provider: str):
    return await client.get(
        f"/api/auth/{provider}/callback",
        params={"code": "provider-code", "state": "valid-state"},
    )


@pytest.mark.asyncio
async def test_google_invitation_links_verified_account_and_activates(
    client, db_session, test_tenant, monkeypatch
):
    user, token = await _invite(db_session, test_tenant)
    _mock_callback(
        monkeypatch, "google", _google_claims("Invitee@TestFirm.com"), invite=token
    )

    response = await _callback(client, "google")

    assert response.status_code == 307, response.text
    assert response.headers["location"].endswith(
        "/auth/callback?code=one-time-callback-code"
    )
    await db_session.refresh(user)
    assert user.is_active is True
    assert (user.oauth_provider, user.oauth_subject) == ("google", "google-new")
    assert user.full_name == "Invitee"
    invitation = await _invitation(db_session, user.id)
    assert invitation.accepted_method == "google"


@pytest.mark.asyncio
async def test_microsoft_invitation_links_entra_identity_from_upn(
    client, db_session, test_tenant, monkeypatch
):
    user, token = await _invite(db_session, test_tenant)
    claims = _microsoft_claims(None, preferred_username=INVITEE_EMAIL)
    _mock_callback(monkeypatch, "microsoft", claims, invite=token)

    response = await _callback(client, "microsoft")

    assert response.status_code == 307, response.text
    await db_session.refresh(user)
    assert user.is_active is True
    assert user.oauth_provider == "microsoft"
    assert user.entra_tenant_id == claims["tid"]
    assert user.entra_object_id == claims["oid"]
    assert (await _invitation(db_session, user.id)).accepted_method == "microsoft"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "microsoft"])
async def test_wrong_account_is_refused_and_invitation_stays_usable(
    client, db_session, test_tenant, monkeypatch, provider
):
    user, token = await _invite(db_session, test_tenant)
    claims = (
        _google_claims("someone.else@elsewhere.example")
        if provider == "google"
        else _microsoft_claims("someone.else@elsewhere.example")
    )
    _mock_callback(monkeypatch, provider, claims, invite=token)

    response = await _callback(client, provider)

    _assert_login_redirect(response, "invite_email_mismatch")
    await db_session.refresh(user)
    assert user.is_active is False
    assert user.oauth_subject is None
    invitation = await _invitation(db_session, user.id)
    assert invitation.accepted_at is None and invitation.revoked_at is None


@pytest.mark.asyncio
async def test_unverified_google_email_cannot_accept(
    client, db_session, test_tenant, monkeypatch
):
    user, token = await _invite(db_session, test_tenant)
    _mock_callback(
        monkeypatch,
        "google",
        _google_claims(INVITEE_EMAIL, verified=False),
        invite=token,
    )

    response = await _callback(client, "google")

    _assert_login_redirect(response, "google_email_unverified")
    await db_session.refresh(user)
    assert user.is_active is False
    assert (await _invitation(db_session, user.id)).accepted_at is None


@pytest.mark.asyncio
async def test_microsoft_identity_owned_by_another_user_fails_closed(
    client, db_session, test_tenant, monkeypatch
):
    claims = _microsoft_claims(INVITEE_EMAIL)
    other_tenant = Tenant(
        id=uuid.uuid4(),
        name="Other Firm",
        domain=f"other-{uuid.uuid4().hex[:8]}.example",
        billing_tier="payg",
        is_active=True,
    )
    owner = User(
        id=uuid.uuid4(),
        tenant_id=other_tenant.id,
        email="owner@other.example",
        role="admin",
        is_active=True,
        oauth_provider="microsoft",
        oauth_subject="established-sub",
        entra_tenant_id=claims["tid"],
        entra_object_id=claims["oid"],
    )
    db_session.add_all([other_tenant, owner])
    await db_session.commit()
    user, token = await _invite(db_session, test_tenant)
    _mock_callback(monkeypatch, "microsoft", claims, invite=token)

    response = await _callback(client, "microsoft")

    _assert_login_redirect(response, "identity_already_linked")
    await db_session.refresh(user)
    await db_session.refresh(owner)
    assert user.is_active is False
    assert user.entra_object_id is None
    assert owner.tenant_id == other_tenant.id
    assert owner.oauth_subject == "established-sub"
    assert (await _invitation(db_session, user.id)).accepted_at is None


@pytest.mark.asyncio
async def test_expired_invitation_is_refused_through_provider(
    client, db_session, test_tenant, monkeypatch
):
    user, token = await _invite(db_session, test_tenant)
    await db_session.execute(
        update(UserInvitation)
        .where(UserInvitation.user_id == user.id)
        .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    )
    await db_session.commit()
    _mock_callback(monkeypatch, "google", _google_claims(INVITEE_EMAIL), invite=token)

    response = await _callback(client, "google")

    _assert_login_redirect(response, "invite_expired")
    await db_session.refresh(user)
    assert user.is_active is False


@pytest.mark.asyncio
async def test_acceptance_never_touches_same_address_in_another_firm(
    client, db_session, test_tenant, monkeypatch
):
    other_tenant = Tenant(
        id=uuid.uuid4(),
        name="Other Firm",
        domain=f"other-{uuid.uuid4().hex[:8]}.example",
        billing_tier="payg",
        is_active=True,
    )
    namesake = User(
        id=uuid.uuid4(),
        tenant_id=other_tenant.id,
        email=INVITEE_EMAIL,
        role="user",
        is_active=True,
    )
    db_session.add_all([other_tenant, namesake])
    await db_session.commit()
    user, token = await _invite(db_session, test_tenant)
    _mock_callback(monkeypatch, "google", _google_claims(INVITEE_EMAIL), invite=token)

    response = await _callback(client, "google")

    assert response.status_code == 307, response.text
    await db_session.refresh(user)
    await db_session.refresh(namesake)
    assert user.is_active is True and user.oauth_subject == "google-new"
    assert namesake.oauth_subject is None
    assert namesake.tenant_id == other_tenant.id


@pytest.mark.asyncio
async def test_legacy_invite_placeholder_is_cleared_on_acceptance(
    client, db_session, test_tenant, monkeypatch
):
    raw_token = "legacy-token-from-before-migration-192"
    user = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email=INVITEE_EMAIL,
        role="user",
        is_active=False,
        password_hash=f"invite:{raw_token}",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserInvitation(
            tenant_id=test_tenant.id,
            user_id=user.id,
            token_hash=invitations.hash_invite_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    await db_session.commit()
    _mock_callback(
        monkeypatch, "google", _google_claims(INVITEE_EMAIL), invite=raw_token
    )

    response = await _callback(client, "google")

    assert response.status_code == 307, response.text
    await db_session.refresh(user)
    assert user.is_active is True
    assert user.password_hash is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "microsoft"])
async def test_login_route_refuses_bad_invitation_before_provider_redirect(
    client, monkeypatch, provider
):
    monkeypatch.setattr(auth_router, "_oauth_configured", lambda *_: True)

    response = await client.get(
        f"/api/auth/{provider}/login", params={"invite": "not-a-real-token"}
    )

    # Refused here, before the person is ever sent to the provider.
    _assert_login_redirect(response, "invite_invalid")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "microsoft"])
async def test_login_route_carries_invitation_and_never_signup(
    client, db_session, test_tenant, monkeypatch, provider
):
    _, token = await _invite(db_session, test_tenant)
    monkeypatch.setattr(auth_router, "_oauth_configured", lambda *_: True)
    saved: list[dict] = []

    async def save_state(_request, _state, data=None):
        saved.append(data)

    monkeypatch.setattr(auth_router, "_save_state", save_state)

    response = await client.get(
        f"/api/auth/{provider}/login",
        params={"invite": token, "signup": "true", "company_name": "Ignored"},
    )

    assert response.status_code == 307
    host = urlsplit(response.headers["location"]).netloc
    assert host in {"accounts.google.com", "login.microsoftonline.com"}
    assert "invite" not in parse_qs(urlsplit(response.headers["location"]).query)
    assert saved[0]["invite"] == token
    assert saved[0]["signup"] is None


@pytest.mark.asyncio
async def test_login_route_without_invitation_keeps_state_shape(client, monkeypatch):
    monkeypatch.setattr(auth_router, "_oauth_configured", lambda *_: True)
    saved: list[dict] = []

    async def save_state(_request, _state, data=None):
        saved.append(data)

    monkeypatch.setattr(auth_router, "_save_state", save_state)

    response = await client.get("/api/auth/google/login")

    assert response.status_code == 307
    assert set(saved[0]) == {"signup", "nonce", "pkce_verifier", "return_to"}
