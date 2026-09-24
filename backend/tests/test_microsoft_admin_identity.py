"""The admin Microsoft 365 connect must record who granted it and the tier.

Before the connect requested ``openid``, Entra returned no id_token, the tier
was stamped ``unknown`` together with ``account_detected_at`` and the backfill
then skipped the credential forever: directory sync stayed blocked, Teams read
as unavailable and "Granted by" never rendered, and re-authorizing could not
fix it.
"""

import base64
import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.tenant_credential import TenantCredential
from app.routers import integrations

USER_ID = "12345678-1234-1234-1234-123456789abc"
TENANT_ID = "12345678-1234-1234-1234-123456789abd"
ENTRA_TID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def _id_token(claims: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


class _Client:
    def __init__(self, payload, sent):
        self.payload = payload
        self.sent = sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, _url, data=None, **_kwargs):
        self.sent.append(data)
        return SimpleNamespace(status_code=200, json=lambda: self.payload)


class _Db:
    def __init__(self):
        self.added = []

    async def execute(self, _statement, *_args):
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        pass


def _patch_callback(monkeypatch, token_payload, sent):
    async def consume(*_args):
        return True, {
            "intent": "admin",
            "provider": "microsoft",
            "user_id": USER_ID,
            "tenant_id": TENANT_ID,
            "role": "admin",
            "teams": False,
            "pkce_verifier": "verifier",
        }

    async def noop(*_args, **_kwargs):
        return None

    async def redirect(*_args, **_kwargs):
        return SimpleNamespace(headers={"location": "/admin?tab=integrations"})

    monkeypatch.setattr(integrations, "_consume_state", consume)
    monkeypatch.setattr(
        integrations.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(token_payload, sent),
    )
    monkeypatch.setattr(integrations, "set_tenant_context", noop)
    monkeypatch.setattr(integrations, "_onboarding_post_connect", noop)
    monkeypatch.setattr(integrations, "_ensure_cloud_root", noop)
    monkeypatch.setattr(
        integrations, "_schedule_user_sync_post_connect", lambda *_a: None
    )
    monkeypatch.setattr(integrations, "_post_connect_redirect", redirect)
    monkeypatch.setattr(integrations, "encrypt_token", lambda value: f"enc:{value}")


def test_admin_connect_requests_sign_in_scopes_but_audits_graph_permissions():
    requested = integrations._admin_request_scopes(False).split()
    for scope in ("openid", "email", "profile"):
        assert scope in requested
        # Sign-in scopes are never counted as a missing Graph permission.
        assert scope not in integrations.MICROSOFT_ADMIN_SCOPES.split()
    assert set(integrations.MICROSOFT_ADMIN_SCOPES.split()) <= set(requested)
    teams = integrations._admin_request_scopes(True).split()
    assert "openid" in teams and "ChannelMessage.Send" in teams


@pytest.mark.asyncio
async def test_admin_callback_records_tier_and_granting_account_from_id_token(
    monkeypatch,
):
    sent = []
    _patch_callback(
        monkeypatch,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            # Entra may or may not echo the sign-in scopes; health must not care.
            "scope": integrations.MICROSOFT_ADMIN_SCOPES,
            "id_token": _id_token(
                {"tid": ENTRA_TID, "preferred_username": "partner@firm.example"}
            ),
        },
        sent,
    )
    db = _Db()

    response = await integrations.microsoft_callback("state", None, db, code="code")

    assert response.headers["location"] == "/admin?tab=integrations"
    assert "openid" in sent[0]["scope"].split()
    [credential] = [row for row in db.added if isinstance(row, TenantCredential)]
    assert credential.account_type == "azure_ad"
    assert credential.account_domain == "firm.example"
    assert credential.account_detected_at is not None
    assert credential.service_account_email == "partner@firm.example"
    assert credential.health == "healthy"
    assert credential.granted_by_user_id == uuid.UUID(USER_ID)


@pytest.mark.asyncio
async def test_admin_callback_without_id_token_leaves_tier_to_the_backfill(monkeypatch):
    sent = []
    _patch_callback(
        monkeypatch,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "scope": integrations.MICROSOFT_ADMIN_SCOPES,
        },
        sent,
    )
    db = _Db()

    await integrations.microsoft_callback("state", None, db, code="code")

    [credential] = [row for row in db.added if isinstance(row, TenantCredential)]
    # Not stamped: backfill_unknown_credentials skips any row that has an
    # account_detected_at, so stamping "unknown" here would be permanent.
    assert credential.account_detected_at is None
    assert credential.account_type is None
