"""End-to-end contract of the admin and per-user cloud OAuth round trip.

Each test drives the real ``/connect`` endpoint, so the OAuth state lives in
Redis exactly as in production, then replays the provider's redirect against
``/callback`` with only the token endpoint (and Google's signature check)
faked. That pins what an administrator actually sees: where a failure lands,
which error it names, what is sent to Microsoft or Google, and that a failed
grant never leaves a credential behind.
"""

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, parse_qsl, urlsplit

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.tenant_credential import TenantCredential
from app.models.user import User
from app.models.user_oauth_token import UserOAuthToken
from app.routers import integrations
from app.services.teams import TEAMS_CONNECT_SCOPES

ENTRA_TID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
SIGN_IN_SCOPES = {"openid", "email", "profile"}
GRAPH_ADMIN_SCOPES = set(integrations.MICROSOFT_ADMIN_SCOPES.split())
TEAMS_SCOPES = set(TEAMS_CONNECT_SCOPES.split())

_FRONTEND = urlsplit(integrations.settings.FRONTEND_URL.rstrip("/"))
FRONTEND_ORIGIN = f"{_FRONTEND.scheme}://{_FRONTEND.netloc}"
FRONTEND_PATH = _FRONTEND.path


class _TokenEndpoint:
    """Stands in for the provider token endpoint and records every exchange."""

    def __init__(self, payload=None, status_code=200):
        self.payload = payload if payload is not None else {}
        self.status_code = status_code
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, data=None, **_kwargs):
        self.requests.append((url, dict(data or {})))
        return SimpleNamespace(status_code=self.status_code, json=lambda: self.payload)


class _HttpxWithTokenEndpoint:
    """The ``httpx`` module as the integrations router sees it, minus the network."""

    def __init__(self, endpoint):
        self._endpoint = endpoint

    def AsyncClient(self, **_kwargs):  # noqa: N802 - mirrors httpx.AsyncClient
        return self._endpoint

    def __getattr__(self, name):
        return getattr(httpx, name)


def _token_endpoint(monkeypatch, payload=None, status_code=200) -> _TokenEndpoint:
    endpoint = _TokenEndpoint(payload, status_code)
    monkeypatch.setattr(integrations, "httpx", _HttpxWithTokenEndpoint(endpoint))
    return endpoint


def _refuse_google_verification(monkeypatch) -> list:
    calls = []

    async def verify(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("the Google identity must not be verified here")

    monkeypatch.setattr(integrations, "verify_google_id_token", verify)
    return calls


def _id_token(claims) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


async def _connect(client, provider, **params):
    response = await client.get(
        f"/api/integrations/{provider}/connect", params=params, follow_redirects=False
    )
    assert response.status_code == 307, response.text
    authorize = urlsplit(response.headers["location"])
    return authorize, parse_qs(authorize.query)


async def _start(client, provider, **params) -> str:
    _authorize, query = await _connect(client, provider, **params)
    return query["state"][0]


async def _callback(client, provider, **params):
    return await client.get(
        f"/api/integrations/{provider}/callback",
        params=params,
        follow_redirects=False,
    )


async def _rewrite_state(redis, state, **changes) -> None:
    key = f"integration:statedata:{state}"
    meta = json.loads(await redis.get(key))
    meta.update(changes)
    await redis.set(key, json.dumps(meta), keepttl=True)


def _landing(response):
    """(origin, path, query) of a redirect, refusing duplicated query keys."""
    assert response.status_code == 302
    target = urlsplit(response.headers["location"])
    pairs = parse_qsl(target.query, keep_blank_values=True)
    query = dict(pairs)
    assert len(query) == len(pairs), f"duplicated query key in {target.query}"
    return f"{target.scheme}://{target.netloc}", target.path, query


def _failure_landing(destination: str, code: str, provider: str):
    if destination == "integrations":
        return (
            FRONTEND_ORIGIN,
            f"{FRONTEND_PATH}/admin",
            {
                "tab": "integrations",
                "integration": "cloud",
                "error": code,
                "provider": provider,
            },
        )
    return (
        FRONTEND_ORIGIN,
        f"{FRONTEND_PATH}/{destination}",
        {"error": code, "provider": provider},
    )


async def _stored_grants(db_session):
    credentials = (await db_session.execute(select(TenantCredential))).scalars().all()
    user_tokens = (await db_session.execute(select(UserOAuthToken))).scalars().all()
    return credentials, user_tokens


# Each case is the connect query the administrator started from and the
# destination a failure must return them to.
RETURN_DESTINATIONS = [
    pytest.param({"return_to": "integrations"}, "integrations", id="integrations"),
    pytest.param({"return_to": "onboarding"}, "onboarding", id="onboarding"),
    pytest.param({}, "onboarding", id="default"),
]


# ── Failures after the code exchange ──────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(("connect_params", "destination"), RETURN_DESTINATIONS)
async def test_microsoft_admin_grant_without_access_token_stores_nothing(
    client, db_session, monkeypatch, connect_params, destination
):
    state = await _start(client, "microsoft", intent="admin", **connect_params)
    endpoint = _token_endpoint(
        monkeypatch,
        {
            "refresh_token": "refresh",
            "scope": integrations.MICROSOFT_ADMIN_SCOPES,
            "id_token": _id_token(
                {"tid": ENTRA_TID, "preferred_username": "it@firm.example"}
            ),
        },
    )

    response = await _callback(client, "microsoft", state=state, code="auth-code")

    assert _landing(response) == _failure_landing(
        destination, "no_access_token", "microsoft"
    )
    assert len(endpoint.requests) == 1
    assert await _stored_grants(db_session) == ([], [])


@pytest.mark.asyncio
@pytest.mark.parametrize(("connect_params", "destination"), RETURN_DESTINATIONS)
async def test_google_admin_grant_without_access_token_stores_nothing(
    client, db_session, monkeypatch, connect_params, destination
):
    state = await _start(client, "google", intent="admin", **connect_params)
    endpoint = _token_endpoint(
        monkeypatch,
        {"id_token": "signed", "scope": integrations.GOOGLE_ADMIN_SCOPES},
    )
    verifications = _refuse_google_verification(monkeypatch)

    response = await _callback(client, "google", state=state, code="auth-code")

    assert _landing(response) == _failure_landing(
        destination, "no_access_token", "google"
    )
    assert len(endpoint.requests) == 1
    assert verifications == []
    assert await _stored_grants(db_session) == ([], [])


@pytest.mark.asyncio
@pytest.mark.parametrize(("connect_params", "destination"), RETURN_DESTINATIONS)
async def test_google_admin_grant_with_unverifiable_identity_stores_nothing(
    client, db_session, monkeypatch, connect_params, destination
):
    state = await _start(client, "google", intent="admin", **connect_params)
    _token_endpoint(
        monkeypatch,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "forged.id.token",
            "scope": integrations.GOOGLE_ADMIN_SCOPES,
        },
    )
    verifications = []

    async def reject(id_token, **kwargs):
        verifications.append((id_token, kwargs))
        raise HTTPException(status_code=401, detail="Invalid id_token signature")

    monkeypatch.setattr(integrations, "verify_google_id_token", reject)

    response = await _callback(client, "google", state=state, code="auth-code")

    assert _landing(response) == _failure_landing(
        destination, "identity_verification_failed", "google"
    )
    assert verifications == [
        (
            "forged.id.token",
            {
                "client_id": integrations.settings.GOOGLE_CLIENT_ID,
                "access_token": "access",
            },
        )
    ]
    assert await _stored_grants(db_session) == ([], [])


@pytest.mark.asyncio
@pytest.mark.parametrize(("connect_params", "destination"), RETURN_DESTINATIONS)
async def test_google_admin_state_with_unknown_account_mode_never_exchanges_code(
    client, db_session, test_redis, monkeypatch, connect_params, destination
):
    state = await _start(client, "google", intent="admin", **connect_params)
    # /connect only saves workspace or personal; anything else in the saved
    # state is a tampered or stale record and must not pick a scope bundle.
    await _rewrite_state(test_redis, state, account_mode="enterprise")
    endpoint = _token_endpoint(monkeypatch, {"access_token": "access"})

    response = await _callback(client, "google", state=state, code="auth-code")

    assert _landing(response) == _failure_landing(
        destination, "invalid_state", "google"
    )
    assert endpoint.requests == []
    assert await _stored_grants(db_session) == ([], [])


# ── return_to is an allow-list carried in server-side state ───────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
@pytest.mark.parametrize(
    "return_to",
    [
        "https://evil.example/phish",
        "//evil.example",
        "javascript:alert(1)",
        "/admin?tab=integrations",
        "calendar",
        "Integrations",
    ],
)
async def test_connect_refuses_a_return_to_outside_the_allow_list(
    client, test_redis, provider, return_to
):
    response = await client.get(
        f"/api/integrations/{provider}/connect",
        params={"intent": "admin", "return_to": return_to},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "location" not in response.headers
    assert [key async for key in test_redis.scan_iter("integration:state*")] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_return_to_stays_server_side_and_out_of_the_authorize_url(
    client, test_redis, provider
):
    authorize, query = await _connect(
        client, provider, intent="admin", return_to="integrations"
    )

    assert "return_to" not in query
    assert authorize.netloc in {"login.microsoftonline.com", "accounts.google.com"}
    assert "integrations" not in {
        value for values in query.values() for value in values
    }
    saved = json.loads(
        await test_redis.get(f"integration:statedata:{query['state'][0]}")
    )
    assert saved["return_to"] == "integrations"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
@pytest.mark.parametrize(
    ("connect_params", "callback_return_to", "destination"),
    [
        pytest.param({}, "integrations", "onboarding", id="query-cannot-upgrade"),
        pytest.param(
            {"return_to": "integrations"},
            "https://evil.example",
            "integrations",
            id="query-cannot-hijack",
        ),
    ],
)
async def test_callback_ignores_a_return_to_in_the_provider_redirect(
    client, db_session, provider, connect_params, callback_return_to, destination
):
    state = await _start(client, provider, intent="admin", **connect_params)

    response = await _callback(
        client,
        provider,
        state=state,
        error="access_denied",
        return_to=callback_return_to,
    )

    assert _landing(response) == _failure_landing(
        destination, "access_denied", provider
    )
    assert "evil.example" not in response.headers["location"]
    assert await _stored_grants(db_session) == ([], [])


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
@pytest.mark.parametrize(
    "saved_return_to",
    ["https://evil.example", "//evil.example", "admin", None, 7],
)
async def test_unexpected_saved_return_to_falls_back_to_onboarding(
    client, test_redis, provider, saved_return_to
):
    state = await _start(client, provider, intent="admin", return_to="integrations")
    await _rewrite_state(test_redis, state, return_to=saved_return_to)

    response = await _callback(client, provider, state=state, error="access_denied")

    assert _landing(response) == _failure_landing(
        "onboarding", "access_denied", provider
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_replayed_state_cannot_reuse_the_integrations_destination(
    client, provider
):
    state = await _start(client, provider, intent="admin", return_to="integrations")
    first = await _callback(client, provider, state=state, error="access_denied")
    assert _landing(first)[1] == f"{FRONTEND_PATH}/admin"

    replay = await _callback(client, provider, state=state, error="access_denied")

    assert _landing(replay) == _failure_landing("onboarding", "invalid_state", provider)


# ── Per-user connections always return to Calendar ────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
@pytest.mark.parametrize(
    ("callback_params", "token_payload", "code"),
    [
        pytest.param({"error": "access_denied"}, None, "access_denied", id="cancel"),
        pytest.param(
            {"code": "auth-code"},
            {"refresh_token": "refresh"},
            "no_access_token",
            id="no-access-token",
        ),
    ],
)
async def test_per_user_failure_returns_to_calendar_even_from_integrations(
    client,
    db_session,
    monkeypatch,
    provider,
    callback_params,
    token_payload,
    code,
):
    state = await _start(client, provider, intent="user", return_to="integrations")
    endpoint = _token_endpoint(monkeypatch, token_payload)

    response = await _callback(client, provider, state=state, **callback_params)

    assert _landing(response) == _failure_landing("calendar", code, provider)
    assert len(endpoint.requests) == (1 if token_payload is not None else 0)
    assert await _stored_grants(db_session) == ([], [])


# ── Microsoft admin consent: sign-in scopes requested, Graph scopes audited ─


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("teams", "graph_scopes"),
    [
        pytest.param(0, GRAPH_ADMIN_SCOPES, id="cloud"),
        pytest.param(1, GRAPH_ADMIN_SCOPES | TEAMS_SCOPES, id="teams"),
    ],
)
async def test_microsoft_admin_authorize_url_asks_for_sign_in_and_graph_scopes(
    client, teams, graph_scopes
):
    authorize, query = await _connect(client, "microsoft", intent="admin", teams=teams)

    assert authorize.netloc == "login.microsoftonline.com"
    assert set(query["scope"][0].split()) == graph_scopes | SIGN_IN_SCOPES


@pytest.mark.asyncio
async def test_microsoft_per_user_authorize_url_keeps_its_scope_set(client):
    _authorize, query = await _connect(client, "microsoft", intent="user")

    assert query["scope"][0].split() == integrations.MICROSOFT_USER_SCOPES.split()
    assert not SIGN_IN_SCOPES & set(query["scope"][0].split())


def _wire_post_connect(monkeypatch) -> list:
    scheduled = []

    async def no_cloud_root(*_args):
        return None

    monkeypatch.setattr(integrations, "_ensure_cloud_root", no_cloud_root)
    monkeypatch.setattr(
        integrations,
        "_schedule_user_sync_post_connect",
        lambda tenant_id, provider: scheduled.append((tenant_id, provider)),
    )
    return scheduled


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("teams", "granted", "missing"),
    [
        pytest.param(
            0,
            GRAPH_ADMIN_SCOPES - {"Sites.Read.All"},
            ["Sites.Read.All"],
            id="cloud-missing-graph-scope",
        ),
        pytest.param(
            1,
            GRAPH_ADMIN_SCOPES,
            sorted(TEAMS_SCOPES),
            id="teams-missing-teams-scopes",
        ),
    ],
)
async def test_microsoft_admin_exchange_requests_sign_in_scopes_but_audits_graph_only(
    client,
    db_session,
    test_tenant,
    test_user,
    monkeypatch,
    teams,
    granted,
    missing,
):
    scheduled = _wire_post_connect(monkeypatch)
    state = await _start(client, "microsoft", intent="admin", teams=teams)
    # Entra did not echo openid/email/profile back: that must not read as a
    # missing permission, while a genuinely missing Graph scope still does.
    endpoint = _token_endpoint(
        monkeypatch,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "scope": " ".join(sorted(granted)),
            "id_token": _id_token(
                {"tid": ENTRA_TID, "preferred_username": "partner@firm.example"}
            ),
        },
    )

    response = await _callback(client, "microsoft", state=state, code="auth-code")

    assert response.status_code == 302
    [(url, sent)] = endpoint.requests
    assert urlsplit(url).netloc == "login.microsoftonline.com"
    expected_graph = GRAPH_ADMIN_SCOPES | (TEAMS_SCOPES if teams else set())
    assert set(sent["scope"].split()) == expected_graph | SIGN_IN_SCOPES
    assert sent["code"] == "auth-code"
    assert sent["grant_type"] == "authorization_code"
    assert sent["code_verifier"]
    assert sent["redirect_uri"].endswith("/api/integrations/microsoft/callback")

    [credential], user_tokens = await _stored_grants(db_session)
    assert user_tokens == []
    assert credential.tenant_id == test_tenant.id
    assert credential.granted_by_user_id == test_user.id
    assert credential.missing_scopes == " ".join(missing)
    assert not SIGN_IN_SCOPES & set(credential.missing_scopes.split())
    assert credential.health == "missing_scopes"
    assert credential.account_type == "azure_ad"
    assert credential.account_domain == "firm.example"
    assert credential.account_detected_at is not None
    assert credential.service_account_email == "partner@firm.example"
    assert scheduled == [(str(test_tenant.id), "microsoft")]


async def _existing_microsoft_credential(db_session, tenant_id, **fields):
    credential = TenantCredential(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider="microsoft",
        encrypted_access_token="old",
        scopes=integrations.MICROSOFT_ADMIN_SCOPES,
        is_active=True,
        **fields,
    )
    db_session.add(credential)
    await db_session.commit()
    return credential.id


@pytest.mark.asyncio
async def test_microsoft_reauthorization_without_id_token_keeps_a_detected_tier(
    client, db_session, test_tenant, monkeypatch
):
    detected_at = datetime(2026, 1, 5, tzinfo=timezone.utc)
    credential_id = await _existing_microsoft_credential(
        db_session,
        test_tenant.id,
        account_type="azure_ad",
        account_domain="firm.example",
        account_detected_at=detected_at,
        service_account_email="partner@firm.example",
    )
    _wire_post_connect(monkeypatch)
    state = await _start(client, "microsoft", intent="admin")
    _token_endpoint(
        monkeypatch,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "scope": integrations.MICROSOFT_ADMIN_SCOPES,
        },
    )

    response = await _callback(client, "microsoft", state=state, code="auth-code")

    assert response.status_code == 302
    [credential], _ = await _stored_grants(db_session)
    assert credential.id == credential_id
    assert credential.account_type == "azure_ad"
    assert credential.account_domain == "firm.example"
    assert credential.account_detected_at == detected_at
    assert credential.service_account_email == "partner@firm.example"
    assert credential.health == "healthy"


@pytest.mark.asyncio
@pytest.mark.parametrize("id_token", ["not-a-jwt", "header.%%%.signature"])
async def test_microsoft_reauthorization_with_unreadable_id_token_leaves_tier_unset(
    client, db_session, test_tenant, monkeypatch, id_token
):
    await _existing_microsoft_credential(db_session, test_tenant.id)
    _wire_post_connect(monkeypatch)
    state = await _start(client, "microsoft", intent="admin")
    _token_endpoint(
        monkeypatch,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "scope": integrations.MICROSOFT_ADMIN_SCOPES,
            "id_token": id_token,
        },
    )

    response = await _callback(client, "microsoft", state=state, code="auth-code")

    assert response.status_code == 302
    [credential], _ = await _stored_grants(db_session)
    # Left for backfill_unknown_credentials, which skips stamped rows.
    assert credential.account_type is None
    assert credential.account_domain is None
    assert credential.account_detected_at is None
    assert credential.health == "healthy"


# ── /auth/calendar-providers: missing_features ────────────────────────────

FEATURES = ["mail_read", "mail_send", "calendar", "files"]
PERSONAL_SCOPES = {
    "microsoft": {
        "mail_read": "Mail.Read",
        "mail_send": "Mail.Send",
        "calendar": "Calendars.ReadWrite",
        "files": "Files.ReadWrite.All",
    },
    "google": {
        "mail_read": "https://www.googleapis.com/auth/gmail.readonly",
        "mail_send": "https://www.googleapis.com/auth/gmail.send",
        "calendar": "https://www.googleapis.com/auth/calendar",
        "files": "https://www.googleapis.com/auth/drive",
    },
}


def _personal_token(tenant_id, user_id, provider, features, extra=()):
    scopes = [PERSONAL_SCOPES[provider][feature] for feature in features]
    return UserOAuthToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        provider=provider,
        encrypted_access_token="placeholder",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=" ".join([*extra, *scopes]),
    )


@pytest.fixture
def fresh_personal_token(monkeypatch):
    async def fresh_token(*_args):
        return "valid-token"

    monkeypatch.setattr("app.services.token_vault.get_fresh_user_token", fresh_token)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
@pytest.mark.parametrize(
    ("granted", "connected", "missing_features"),
    [
        pytest.param(FEATURES, True, [], id="full"),
        pytest.param(
            ["mail_read", "files"], False, ["mail_send", "calendar"], id="no-calendar"
        ),
        pytest.param([], False, FEATURES, id="nothing"),
    ],
)
async def test_calendar_providers_reports_missing_personal_features(
    client,
    db_session,
    test_tenant,
    test_user,
    fresh_personal_token,
    provider,
    granted,
    connected,
    missing_features,
):
    db_session.add(
        _personal_token(
            test_tenant.id, test_user.id, provider, granted, extra=("offline_access",)
        )
    )
    await db_session.commit()

    response = await client.get("/api/auth/calendar-providers")

    assert response.status_code == 200
    status = response.json()["provider_status"][provider]
    assert status["missing_features"] == missing_features
    assert status["connected"] is connected
    assert status["reason"] == (None if connected else "missing_scopes")
    other = "google" if provider == "microsoft" else "microsoft"
    assert response.json()["provider_status"][other]["missing_features"] == []


@pytest.mark.asyncio
async def test_calendar_providers_reports_no_missing_features_before_connecting(
    client,
):
    response = await client.get("/api/auth/calendar-providers")

    assert response.status_code == 200
    for provider in ("microsoft", "google"):
        status = response.json()["provider_status"][provider]
        assert status["reason"] == "not_connected"
        assert status["missing_features"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_calendar_providers_reads_only_the_callers_own_grant(
    client, db_session, test_tenant, test_user, fresh_personal_token, provider
):
    colleague = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="colleague@testfirm.com",
        full_name="Colleague",
        role="user",
        is_active=True,
    )
    db_session.add(colleague)
    await db_session.commit()
    db_session.add_all(
        [
            _personal_token(test_tenant.id, colleague.id, provider, FEATURES),
            _personal_token(test_tenant.id, test_user.id, provider, ["calendar"]),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/auth/calendar-providers")

    status = response.json()["provider_status"][provider]
    assert status["missing_features"] == ["mail_read", "mail_send", "files"]
