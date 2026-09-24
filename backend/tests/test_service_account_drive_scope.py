"""The shared platform service account must never cross tenant boundaries.

One Google service account is a member of every tenant's org Shared Drive.
Cloud search and the tenant-wide Drive sync fall back to it when a user has
no personal grant, so a ``corpora=allDrives`` / ``includeItemsFromAllDrives``
request made with its token returned other firms' files. Every such request
is now pinned to the requesting tenant's own drive.
"""

import pytest

from app.services import cloud_search as cloud_search_module
from app.services import cloud_sync as cloud_sync_module
from app.services import google_service_account as sa
from app.services.cloud_search import CloudHit, CloudSearchService

SA_TOKEN = "service-account-token"
TENANT_ROOT = {"google_drive": {"owner_type": "org_shared_drive", "drive_id": "drive-A"}}


@pytest.fixture
def service_account(monkeypatch):
    async def token(*_args, **_kwargs):
        return SA_TOKEN

    monkeypatch.setattr(sa, "is_configured", lambda: True)
    monkeypatch.setattr(sa, "get_access_token", token)
    roots = {"tenant-a": TENANT_ROOT, "tenant-no-drive": {}}

    async def root(_db, tenant_id):
        return roots.get(str(tenant_id))

    monkeypatch.setattr(sa, "_load_tenant_cloud_root", root)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


class _Client:
    def __init__(self, calls, responses=None):
        self.calls = calls
        self.responses = responses or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, *, headers=None, params=None, **_kwargs):
        self.calls.append((url, dict(params or {})))
        for suffix, response in self.responses.items():
            if url.endswith(suffix) and (params or {}).get("fields") == "driveId":
                return response
        return _Response({"files": []})


@pytest.mark.asyncio
async def test_scope_is_none_for_a_delegated_token(service_account):
    assert await sa.service_account_drive_scope(None, "tenant-a", "delegated") is None


@pytest.mark.asyncio
async def test_scope_pins_the_service_account_to_the_tenant_drive(service_account):
    assert await sa.service_account_drive_scope(None, "tenant-a", SA_TOKEN) == "drive-A"
    assert (
        await sa.service_account_drive_scope(None, "tenant-no-drive", SA_TOKEN)
        == sa.NO_TENANT_DRIVE
    )


@pytest.mark.asyncio
async def test_drive_search_with_service_account_is_limited_to_tenant_drive(
    monkeypatch, service_account
):
    service = CloudSearchService()
    calls = []

    async def token(*_args, **_kwargs):
        return SA_TOKEN

    monkeypatch.setattr(service, "_get_google_token", token)
    monkeypatch.setattr(
        cloud_search_module.httpx, "AsyncClient", lambda **_kwargs: _Client(calls)
    )

    await service._search_google_drive(
        db=None, keywords=["matter"], date_after="", max_hits=10,
        tenant_id="tenant-a", user_id=None,
    )

    params = calls[0][1]
    assert params["corpora"] == "drive"
    assert params["driveId"] == "drive-A"


@pytest.mark.asyncio
async def test_drive_search_refuses_service_account_without_tenant_drive(
    monkeypatch, service_account
):
    service = CloudSearchService()
    calls = []

    async def token(*_args, **_kwargs):
        return SA_TOKEN

    monkeypatch.setattr(service, "_get_google_token", token)
    monkeypatch.setattr(
        cloud_search_module.httpx, "AsyncClient", lambda **_kwargs: _Client(calls)
    )

    hits = await service._search_google_drive(
        db=None, keywords=["matter"], date_after="", max_hits=10,
        tenant_id="tenant-no-drive", user_id=None,
    )

    assert hits == []
    assert calls == []


@pytest.mark.asyncio
async def test_content_fetch_refuses_a_file_from_another_tenants_drive(
    monkeypatch, service_account
):
    service = CloudSearchService()
    calls = []

    async def token(*_args, **_kwargs):
        return SA_TOKEN

    monkeypatch.setattr(service, "_get_google_token", token)
    monkeypatch.setattr(
        cloud_search_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(
            calls, {"/files/foreign-file": _Response({"driveId": "drive-B"})}
        ),
    )
    hit = CloudHit(
        provider="google", source="drive", object_id="foreign-file",
        title="Other firm's memo", snippet="other firm snippet", url="",
        modified_time="", mime_type="application/pdf",
    )

    content = await service._fetch_google_drive_content(None, hit, "tenant-a", 2000, None)

    assert content is None
    # Only the drive-membership probe ran; the file body was never requested.
    assert [params.get("fields") for _url, params in calls] == ["driveId"]


@pytest.mark.asyncio
async def test_tenant_drive_sync_with_service_account_is_limited_to_tenant_drive(
    monkeypatch, service_account
):
    service = cloud_sync_module.CloudSyncService()
    calls = []

    async def token(*_args, **_kwargs):
        return SA_TOKEN

    monkeypatch.setattr(service, "_get_token", token)
    monkeypatch.setattr(
        cloud_sync_module.httpx, "AsyncClient", lambda **_kwargs: _Client(calls)
    )

    class _Db:
        async def commit(self):
            pass

        async def rollback(self):
            pass

    await service.sync_google_drive(_Db(), "tenant-a")

    params = calls[0][1]
    assert params["corpora"] == "drive"
    assert params["driveId"] == "drive-A"
