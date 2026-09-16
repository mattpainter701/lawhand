from types import SimpleNamespace

import pytest

from app.routers import integrations

USER_ID = "12345678-1234-1234-1234-123456789abc"
TENANT_ID = "12345678-1234-1234-1234-123456789abd"


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class _Client:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return _Response(self.payload)


@pytest.mark.asyncio
async def test_per_user_google_callback_does_not_require_id_token(monkeypatch):
    monkeypatch.setattr(
        integrations.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(
            {"access_token": "access", "scope": integrations.GOOGLE_USER_SCOPES}
        ),
    )

    async def consume(*_args):
        return True, {
            "intent": "user",
            "provider": "google",
            "user_id": USER_ID,
            "tenant_id": TENANT_ID,
        }

    monkeypatch.setattr(integrations, "_consume_state", consume)

    async def redirect(*_args):
        return SimpleNamespace(headers={"location": "/ok"})

    monkeypatch.setattr(integrations, "_post_connect_redirect", redirect)
    monkeypatch.setattr(integrations, "encrypt_token", lambda value: f"enc:{value}")

    class Db:
        async def execute(self, _statement, *_args):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        def add(self, _value):
            pass

        async def commit(self):
            pass

    response = await integrations.google_callback("code", "state", None, Db())
    assert response.headers["location"] == "/ok"


@pytest.mark.asyncio
async def test_admin_google_callback_without_signed_identity_redirects_and_saves_nothing(
    monkeypatch,
):
    monkeypatch.setattr(
        integrations.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(
            {"access_token": "access", "scope": integrations.GOOGLE_SOLO_SCOPES}
        ),
    )

    async def consume(*_args):
        return True, {
            "intent": "admin",
            "provider": "google",
            "account_mode": "personal",
            "user_id": USER_ID,
            "tenant_id": TENANT_ID,
        }

    monkeypatch.setattr(integrations, "_consume_state", consume)

    class Db:
        def __init__(self):
            self.executed = False

        async def execute(self, _statement):
            self.executed = True
            raise AssertionError("credential lookup must not run")

    db = Db()
    response = await integrations.google_callback("code", "state", None, db)
    assert "identity_verification_failed" in response.headers["location"]
    assert db.executed is False


@pytest.mark.asyncio
async def test_admin_google_mode_mismatch_redirects_before_credential_lookup(
    monkeypatch,
):
    monkeypatch.setattr(
        integrations.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(
            {
                "access_token": "access",
                "id_token": "signed",
                "scope": integrations.GOOGLE_ADMIN_SCOPES,
            }
        ),
    )

    async def consume(*_args):
        return True, {
            "intent": "admin",
            "provider": "google",
            "account_mode": "workspace",
            "user_id": USER_ID,
            "tenant_id": TENANT_ID,
        }

    monkeypatch.setattr(integrations, "_consume_state", consume)

    async def verified(*_args, **_kwargs):
        return {"email": "person@gmail.com", "email_verified": True}

    monkeypatch.setattr(integrations, "verify_google_id_token", verified)

    class Db:
        def __init__(self):
            self.executed = False

        async def execute(self, _statement):
            self.executed = True
            raise AssertionError("credential lookup must not run")

    db = Db()
    response = await integrations.google_callback("code", "state", None, db)
    assert "account_mode_mismatch" in response.headers["location"]
    assert db.executed is False
