"""Google My Drive -> organisation Shared Drive migration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import cloud_init, google_root_migration, google_service_account

RealAsyncClient = httpx.AsyncClient
TENANT_ID = "11111111-1111-1111-1111-111111111111"


class _FakeDb:
    def __init__(self, tenant):
        self.tenant = tenant
        self.added: list = []
        self.commits = 0

    async def scalar(self, _statement):
        return self.tenant

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


def _tenant(root: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=TENANT_ID,
        cloud_root_folder={"google_drive": root, "path": "lawhand-records"},
    )


def _mock_client(handler):
    return lambda **kwargs: RealAsyncClient(
        transport=httpx.MockTransport(handler), **kwargs
    )


def _no_provider_calls(monkeypatch):
    def boom(**_kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("no provider call expected")

    monkeypatch.setattr(google_root_migration.httpx, "AsyncClient", boom)


def _ready(
    monkeypatch,
    *,
    drive_id: str = "drive-1",
    account_type: str = "workspace",
    sa_configured: bool = True,
):
    monkeypatch.setattr(google_root_migration, "set_tenant_context", AsyncMock())
    monkeypatch.setattr(
        cloud_init, "_google_account_type", AsyncMock(return_value=account_type)
    )
    monkeypatch.setattr(google_service_account, "is_configured", lambda: sa_configured)
    monkeypatch.setattr(
        google_root_migration, "get_fresh_token", AsyncMock(return_value="delegated")
    )
    monkeypatch.setattr(
        cloud_init, "_google_org_shared_drive_id", AsyncMock(return_value=drive_id)
    )


@pytest.mark.asyncio
async def test_migrates_root_into_a_shared_drive_and_preserves_ids(monkeypatch):
    tenant = _tenant(
        {"id": "root-1", "folder_name": "lawhand-records", "url": "https://old"}
    )
    db = _FakeDb(tenant)
    _ready(monkeypatch)
    gets = {"n": 0}
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            gets["n"] += 1
            drive = "mydrive" if gets["n"] == 1 else "drive-1"
            return httpx.Response(
                200,
                json={
                    "id": "root-1",
                    "parents": ["mydrive-parent"],
                    "driveId": drive,
                    "webViewLink": "https://drive/root-1",
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "root-1",
                "driveId": "drive-1",
                "webViewLink": "https://drive/root-1",
            },
        )

    monkeypatch.setattr(
        google_root_migration.httpx, "AsyncClient", _mock_client(handler)
    )

    result = await google_root_migration.migrate_google_root_to_shared_drive(
        db, TENANT_ID
    )

    assert result["status"] == "migrated"
    binding = tenant.cloud_root_folder["google_drive"]
    assert binding["id"] == "root-1"
    assert binding["owner_type"] == "org_shared_drive"
    assert binding["drive_id"] == "drive-1"
    assert binding["url"] == "https://drive/root-1"

    patch = next(r for r in calls if r.method == "PATCH")
    assert "addParents=drive-1" in str(patch.url)
    assert "removeParents=mydrive-parent" in str(patch.url)
    assert "supportsAllDrives=true" in str(patch.url)
    assert db.commits == 1
    assert db.added[0].action == "google_shared_drive_cutover"


@pytest.mark.asyncio
async def test_move_failure_leaves_the_binding_unchanged(monkeypatch):
    original = {"id": "root-1", "folder_name": "lawhand-records", "url": "https://old"}
    tenant = _tenant(dict(original))
    db = _FakeDb(tenant)
    _ready(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "root-1",
                    "parents": ["mydrive-parent"],
                    "driveId": "mydrive",
                },
            )
        return httpx.Response(403, text="denied")

    monkeypatch.setattr(
        google_root_migration.httpx, "AsyncClient", _mock_client(handler)
    )

    with pytest.raises(RuntimeError, match="move failed"):
        await google_root_migration.migrate_google_root_to_shared_drive(db, TENANT_ID)

    assert tenant.cloud_root_folder["google_drive"] == original
    assert db.commits == 0
    assert db.added == []


@pytest.mark.asyncio
async def test_already_org_owned_is_a_noop(monkeypatch):
    tenant = _tenant(
        {"id": "root-1", "owner_type": "org_shared_drive", "drive_id": "drive-1"}
    )
    db = _FakeDb(tenant)
    _no_provider_calls(monkeypatch)

    result = await google_root_migration.migrate_google_root_to_shared_drive(
        db, TENANT_ID
    )

    assert result["status"] == "noop"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_personal_account_is_refused(monkeypatch):
    tenant = _tenant({"id": "root-1"})
    db = _FakeDb(tenant)
    _ready(monkeypatch, account_type="personal")
    _no_provider_calls(monkeypatch)

    result = await google_root_migration.migrate_google_root_to_shared_drive(
        db, TENANT_ID
    )

    assert result["status"] == "refused"
    assert "Workspace" in result["reason"]


@pytest.mark.asyncio
async def test_missing_service_account_is_refused(monkeypatch):
    tenant = _tenant({"id": "root-1"})
    db = _FakeDb(tenant)
    _ready(monkeypatch, sa_configured=False)
    _no_provider_calls(monkeypatch)

    result = await google_root_migration.migrate_google_root_to_shared_drive(
        db, TENANT_ID
    )

    assert result["status"] == "refused"
    assert "service account" in result["reason"]


@pytest.mark.asyncio
async def test_dry_run_makes_no_changes(monkeypatch):
    tenant = _tenant({"id": "root-1"})
    db = _FakeDb(tenant)
    _ready(monkeypatch, drive_id="pinned-drive")
    _no_provider_calls(monkeypatch)

    result = await google_root_migration.migrate_google_root_to_shared_drive(
        db, TENANT_ID, dry_run=True
    )

    assert result["status"] == "dry_run"
    assert result["drive_id"] == "pinned-drive"
    assert db.commits == 0
    assert tenant.cloud_root_folder["google_drive"] == {"id": "root-1"}


@pytest.mark.asyncio
async def test_unbound_root_is_a_noop(monkeypatch):
    tenant = SimpleNamespace(id=TENANT_ID, cloud_root_folder={})
    db = _FakeDb(tenant)
    _no_provider_calls(monkeypatch)

    result = await google_root_migration.migrate_google_root_to_shared_drive(
        db, TENANT_ID
    )

    assert result["status"] == "noop"
    assert db.commits == 0
