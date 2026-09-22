from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import integrations


class _Result:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


def _request(tenant_id="tenant-id"):
    return SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))


def _credential(provider, scopes, *, health="healthy", active=True, **extra):
    return SimpleNamespace(
        provider=provider,
        scopes=scopes,
        health=health,
        is_active=active,
        **extra,
    )


async def _call(monkeypatch, settings, credentials, *, role="user"):
    user = SimpleNamespace(tenant_id="tenant-id", role=role)
    db = AsyncMock()
    db.execute.side_effect = [
        _Result(scalar=settings),
        _Result(rows=credentials),
    ]
    monkeypatch.setattr(integrations, "get_current_user", AsyncMock(return_value=user))
    monkeypatch.setattr(integrations, "set_tenant_context", AsyncMock())
    return await integrations.storage_readiness(_request(), db)


@pytest.mark.asyncio
async def test_explicit_onedrive_reports_reconnect_for_revoked_credential(monkeypatch):
    result = await _call(
        monkeypatch,
        SimpleNamespace(primary_cloud_provider="onedrive"),
        [_credential("microsoft", "Files.ReadWrite.All", health="revoked", active=False)],
    )

    assert result["provider"] == "onedrive"
    assert result["status"] == "needs_reconnect"
    assert result["ready"] is False


@pytest.mark.asyncio
async def test_auto_mode_follows_active_microsoft_before_google(monkeypatch):
    result = await _call(
        monkeypatch,
        SimpleNamespace(primary_cloud_provider=None),
        [
            _credential("microsoft", "Files.ReadWrite.All", health="refresh_failed"),
            _credential("google", "https://www.googleapis.com/auth/drive"),
        ],
    )

    assert result["provider"] == "onedrive"
    assert result["status"] == "needs_reconnect"


@pytest.mark.asyncio
async def test_missing_mail_scope_does_not_block_google_document_storage(monkeypatch):
    result = await _call(
        monkeypatch,
        SimpleNamespace(primary_cloud_provider="google_drive"),
        [
            _credential(
                "google",
                "https://www.googleapis.com/auth/drive",
                health="missing_scopes",
            )
        ],
    )

    assert result["status"] == "ready"
    assert result["ready"] is True


@pytest.mark.asyncio
async def test_google_shared_drive_service_account_credential_is_ready(monkeypatch):
    result = await _call(
        monkeypatch,
        SimpleNamespace(primary_cloud_provider="google_drive"),
        [
            _credential(
                "google",
                "https://www.googleapis.com/auth/drive",
                service_account_email="storage@firm.iam.gserviceaccount.com",
            )
        ],
    )

    assert result["status"] == "ready"
    assert result["ready"] is True


@pytest.mark.asyncio
async def test_authenticated_non_admin_can_read_storage_preflight(monkeypatch):
    result = await _call(
        monkeypatch,
        SimpleNamespace(primary_cloud_provider=None),
        [],
        role="staff",
    )

    assert result["status"] == "not_connected"
    assert result["ready"] is False
