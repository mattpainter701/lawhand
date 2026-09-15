"""Browser OAuth refusals land on the login page instead of a raw JSON body.

Google/Microsoft sign-in is a full-page navigation, so whatever the backend
returns is what the person sees. Expected refusals redirect to
``/login?error=<code>`` with an allowlisted code; server errors are left alone
so they still reach error logging; JSON endpoints keep their JSON.
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.tenant import Tenant
from app.models.user import User
from app.routers import auth as auth_router


class _ProviderTokenResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"access_token": "provider-access-token", "id_token": "provider-id"}


def _mock_google_callback(monkeypatch, claims: dict) -> None:
    async def consume_state(_request, _state):
        return True, {"signup": None, "nonce": "nonce", "pkce_verifier": "verifier"}

    async def provider_post(_self, _url, **_kwargs):
        return _ProviderTokenResponse()

    async def verify_token(_raw_token, **_kwargs):
        return claims

    monkeypatch.setattr(auth_router, "_consume_state", consume_state)
    monkeypatch.setattr(httpx.AsyncClient, "post", provider_post)
    monkeypatch.setattr(auth_router, "verify_google_id_token", verify_token)
    monkeypatch.setattr(auth_router.settings, "PUBLIC_SIGNUP_ENABLED", False)


def _google_claims(email: str, sub: str = "google-subject") -> dict:
    return {"sub": sub, "email": email, "email_verified": True, "name": "Person"}


async def _google_callback(client):
    return await client.get(
        "/api/auth/google/callback",
        params={"code": "provider-code", "state": "valid-state"},
    )


def _assert_login_redirect(response, code: str) -> None:
    assert response.status_code == 303, response.text
    assert response.headers["location"] == f"http://localhost:3000/login?error={code}"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_uninvited_address_at_existing_firm_redirects_not_invited(
    client, db_session, test_tenant, monkeypatch, caplog
):
    monkeypatch.setattr(auth_router.settings, "FRONTEND_URL", "http://localhost:3000")
    _mock_google_callback(monkeypatch, _google_claims("stranger@testfirm.com"))
    users_before = await db_session.scalar(select(func.count()).select_from(User))
    # The route shares this session in tests; end the read transaction the
    # count opened so the callback can begin its own.
    await db_session.commit()

    response = await _google_callback(client)

    _assert_login_redirect(response, "not_invited")
    assert await db_session.scalar(select(func.count()).select_from(User)) == (
        users_before
    )
    assert "stranger@testfirm.com" not in caplog.text


@pytest.mark.asyncio
async def test_inactive_user_redirects_account_inactive(
    client, db_session, test_tenant, monkeypatch
):
    monkeypatch.setattr(auth_router.settings, "FRONTEND_URL", "http://localhost:3000")
    user = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="former@testfirm.com",
        role="user",
        is_active=False,
        oauth_provider="google",
        oauth_subject="former-subject",
    )
    db_session.add(user)
    await db_session.commit()
    _mock_google_callback(
        monkeypatch, _google_claims("former@testfirm.com", sub="former-subject")
    )

    response = await _google_callback(client)

    _assert_login_redirect(response, "account_inactive")


@pytest.mark.asyncio
async def test_expired_firm_redirects_tenant_inactive(client, db_session, monkeypatch):
    monkeypatch.setattr(auth_router.settings, "FRONTEND_URL", "http://localhost:3000")
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Lapsed Firm",
        domain=f"lapsed-{uuid.uuid4().hex[:8]}.example",
        billing_tier="payg",
        is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="owner@lapsed.example",
        role="admin",
        is_active=True,
        oauth_provider="google",
        oauth_subject="lapsed-subject",
    )
    db_session.add_all([tenant, user])
    await db_session.commit()
    _mock_google_callback(
        monkeypatch, _google_claims("owner@lapsed.example", sub="lapsed-subject")
    )

    response = await _google_callback(client)

    _assert_login_redirect(response, "tenant_inactive")


@pytest.mark.asyncio
async def test_expired_oauth_state_redirects_state_expired(client, monkeypatch):
    monkeypatch.setattr(auth_router.settings, "FRONTEND_URL", "http://localhost:3000")

    async def no_replay(_request, _state, _code):
        return None

    monkeypatch.setattr(auth_router, "_wait_for_replayed_frontend_callback", no_replay)

    response = await client.get(
        "/api/auth/microsoft/callback",
        params={"code": "provider-code", "state": "never-issued"},
    )

    _assert_login_redirect(response, "oauth_state_expired")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "microsoft"])
async def test_unconfigured_provider_redirects_provider_unavailable(
    client, monkeypatch, provider
):
    monkeypatch.setattr(auth_router.settings, "FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setattr(auth_router, "_oauth_configured", lambda *_: False)

    response = await client.get(f"/api/auth/{provider}/login")

    _assert_login_redirect(response, "provider_unavailable")


@pytest.mark.asyncio
async def test_unexpected_client_error_redirects_generic_code(client, monkeypatch):
    monkeypatch.setattr(auth_router.settings, "FRONTEND_URL", "http://localhost:3000")

    async def consume_state(_request, _state):
        return True, {"signup": None, "nonce": "nonce", "pkce_verifier": "verifier"}

    class _Rejected(_ProviderTokenResponse):
        status_code = 400

    async def provider_post(_self, _url, **_kwargs):
        return _Rejected()

    monkeypatch.setattr(auth_router, "_consume_state", consume_state)
    monkeypatch.setattr(httpx.AsyncClient, "post", provider_post)

    response = await _google_callback(client)

    _assert_login_redirect(response, "oauth_failed")


@pytest.mark.asyncio
async def test_server_errors_are_not_turned_into_redirects(
    client, db_session, monkeypatch
):
    _mock_google_callback(monkeypatch, _google_claims("person@testfirm.com"))

    async def broken(*_args, **_kwargs):
        raise HTTPException(status_code=503, detail="Directory unavailable")

    monkeypatch.setattr(auth_router, "_resolve_oauth_tenant_and_user", broken)
    # Fixture setup left a read transaction open on the shared test session.
    await db_session.commit()

    response = await _google_callback(client)

    assert response.status_code == 503
    assert "location" not in response.headers


def test_redirect_never_carries_an_unknown_code(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "FRONTEND_URL", "http://localhost:3000")

    response = auth_router._login_error_redirect("<script>alert(1)</script>")

    assert response.headers["location"] == (
        "http://localhost:3000/login?error=oauth_failed"
    )


@pytest.mark.asyncio
async def test_json_signup_endpoint_keeps_json_refusal(client, monkeypatch):
    monkeypatch.setattr(auth_router.settings, "PUBLIC_SIGNUP_ENABLED", False)

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "someone@new-firm.example",
            "password": "correct-horse-battery-staple-42",
        },
    )

    assert response.status_code == 403
    assert "location" not in response.headers
    assert "public signup is not enabled" in response.json()["detail"].lower()
