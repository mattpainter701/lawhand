from types import SimpleNamespace

import pytest

from app.routers import integrations

USER_ID = "12345678-1234-1234-1234-123456789abc"
TENANT_ID = "12345678-1234-1234-1234-123456789abd"


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class _Client:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return _Response(self.payload, self.status_code)


def _callback(provider):
    return getattr(integrations, f"{provider}_callback")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_invalid_or_mismatched_state_never_uses_claimed_user_intent(
    monkeypatch, provider
):
    async def consume(*_args):
        return False, {"intent": "user", "provider": provider}

    monkeypatch.setattr(integrations, "_consume_state", consume)
    response = await _callback(provider)(
        "state", code=None, request=None, db=None, error="access_denied"
    )
    assert "/onboarding?error=invalid_state" in response.headers["location"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_provider_mismatch_state_falls_back_to_invalid_state(monkeypatch, provider):
    async def consume(*_args):
        return True, {"intent": "user", "provider": "other"}

    monkeypatch.setattr(integrations, "_consume_state", consume)
    response = await _callback(provider)(
        "state", code=None, request=None, db=None, error="access_denied"
    )
    assert "/onboarding?error=invalid_state" in response.headers["location"]


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", [None, "unexpected"])
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_missing_or_unknown_intent_is_invalid_state(monkeypatch, provider, intent):
    async def consume(*_args):
        metadata = {"provider": provider}
        if intent is not None:
            metadata["intent"] = intent
        return True, metadata

    monkeypatch.setattr(integrations, "_consume_state", consume)
    response = await _callback(provider)(
        "state", code="code", request=None, db=None
    )
    assert "/onboarding?error=invalid_state" in response.headers["location"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_valid_user_errors_are_safe_and_return_to_calendar(monkeypatch, provider):
    async def consume(*_args):
        return True, {"intent": "user", "provider": provider}

    monkeypatch.setattr(integrations, "_consume_state", consume)
    response = await _callback(provider)(
        "state", code=None, request=None, db=None, error="attacker_redirect"
    )
    assert response.headers["location"].endswith(
        f"/calendar?error=oauth_failed&provider={provider}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_valid_user_missing_code_returns_friendly_calendar_error(
    monkeypatch, provider
):
    async def consume(*_args):
        return True, {"intent": "user", "provider": provider}

    monkeypatch.setattr(integrations, "_consume_state", consume)
    response = await _callback(provider)("state", code=None, request=None, db=None)
    assert response.headers["location"].endswith(
        f"/calendar?error=oauth_failed&provider={provider}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_user_token_exchange_failure_returns_to_calendar(monkeypatch, provider):
    async def consume(*_args):
        return True, {"intent": "user", "provider": provider}

    monkeypatch.setattr(integrations, "_consume_state", consume)
    monkeypatch.setattr(
        integrations.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client({"error": "invalid_grant"}, status_code=400),
    )
    response = await _callback(provider)(
        "state", code="code", request=None, db=None
    )
    assert response.headers["location"].endswith(
        f"/calendar?error=token_exchange_failed&provider={provider}"
    )


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

    redirect_calls = []

    async def redirect(*args, **_kwargs):
        redirect_calls.append((args, _kwargs))
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

    response = await integrations.google_callback("state", None, Db(), code="code")
    assert response.headers["location"] == "/ok"
    assert redirect_calls[-1][1]["intent"] == "user"


@pytest.mark.asyncio
async def test_per_user_google_cancellation_returns_to_calendar(monkeypatch):
    async def consume(*_args):
        return True, {"intent": "user", "provider": "google"}

    monkeypatch.setattr(integrations, "_consume_state", consume)
    response = await integrations.google_callback(
        "state", code=None, request=None, db=None, error="access_denied"
    )
    assert response.headers["location"].endswith(
        "/calendar?error=access_denied&provider=google"
    )


@pytest.mark.asyncio
async def test_per_user_microsoft_cancellation_returns_to_calendar(monkeypatch):
    async def consume(*_args):
        return True, {"intent": "user", "provider": "microsoft"}

    monkeypatch.setattr(integrations, "_consume_state", consume)
    response = await integrations.microsoft_callback(
        "state", code=None, request=None, db=None, error="access_denied"
    )
    assert response.headers["location"].endswith(
        "/calendar?error=access_denied&provider=microsoft"
    )


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
    response = await integrations.google_callback("state", None, db, code="code")
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
    response = await integrations.google_callback("state", None, db, code="code")
    assert "account_mode_mismatch" in response.headers["location"]
    assert db.executed is False
