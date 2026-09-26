"""Microsoft sign-in asks only for what verifying the person needs (D28).

Sign-in keeps the verified id_token and discards the access token after a
presence check; no refresh token is ever read. So the sign-in consent must not
ask for ``offline_access`` ("maintain access to data you have given it access
to"). Mail, files and calendar come from the separate integration consent.
"""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import HTTPException

from app.routers import auth as auth_router

SIGN_IN_SCOPES = {"openid", "email", "profile", "User.Read"}


def test_sign_in_scope_constant_is_identity_only():
    assert set(auth_router.MICROSOFT_SIGN_IN_SCOPE.split()) == SIGN_IN_SCOPES


@pytest.mark.asyncio
async def test_microsoft_login_authorize_url_does_not_request_offline_access(
    client, monkeypatch
):
    monkeypatch.setattr(auth_router, "_oauth_configured", lambda *_: True)

    response = await client.get("/api/auth/microsoft/login", follow_redirects=False)

    assert response.status_code in (302, 307), response.text
    authorize = urlsplit(response.headers["location"])
    assert authorize.netloc == "login.microsoftonline.com"
    [scope] = parse_qs(authorize.query)["scope"]
    assert set(scope.split()) == SIGN_IN_SCOPES
    assert "offline_access" not in scope


@pytest.mark.asyncio
async def test_microsoft_callback_token_exchange_does_not_request_offline_access(
    client, monkeypatch
):
    sent: list[dict] = []

    async def consume_state(_request, _state):
        return True, {"signup": None, "nonce": "nonce", "pkce_verifier": "verifier"}

    class _TokenResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"access_token": "access", "id_token": "header.body.signature"}

    async def provider_post(_self, _url, **kwargs):
        sent.append(dict(kwargs.get("data") or {}))
        return _TokenResponse()

    async def verify_token(_raw_token, **_kwargs):
        # Stop after the exchange; the scope sent is what is under test.
        raise HTTPException(status_code=400, detail="stop here")

    monkeypatch.setattr(auth_router, "_consume_state", consume_state)
    monkeypatch.setattr(httpx.AsyncClient, "post", provider_post)
    monkeypatch.setattr(auth_router, "verify_microsoft_id_token", verify_token)

    await client.get(
        "/api/auth/microsoft/callback",
        params={"code": "provider-code", "state": "valid-state"},
        follow_redirects=False,
    )

    [exchange] = sent
    assert exchange["grant_type"] == "authorization_code"
    assert set(exchange["scope"].split()) == SIGN_IN_SCOPES
