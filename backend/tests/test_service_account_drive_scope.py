"""The shared platform service account must never cross tenant boundaries.

One Google service account is a member of every tenant's org Shared Drive.
Cloud search and the tenant-wide Drive sync fall back to it when a user has
no personal grant, so a ``corpora=allDrives`` / ``includeItemsFromAllDrives``
request made with its token returned other firms' files. Every such request
is now pinned to the requesting tenant's own drive, which the token carries
from the moment :func:`prefer_service_account` chooses it.
"""

import types

import pytest

from app.services import cloud_search as cloud_search_module
from app.services import cloud_sync as cloud_sync_module
from app.services import google_service_account as sa
from app.services.cloud_search import CloudHit, CloudSearchService

SA_TOKEN = "service-account-token"
TENANT_ROOT = {
    "google_drive": {"owner_type": "org_shared_drive", "drive_id": "drive-A"}
}
TENANT_DB = object()


@pytest.fixture(autouse=True)
def _clean_caches():
    sa._clear_cache()
    sa._clear_drive_access_cache()
    yield
    sa._clear_cache()
    sa._clear_drive_access_cache()


@pytest.fixture
def tenant_roots(monkeypatch):
    roots = {"tenant-a": TENANT_ROOT, "tenant-no-drive": {}}

    async def root(db, tenant_id):
        # Like the real loader: no session, no root.
        if db is None:
            return None
        return roots.get(str(tenant_id))

    async def reachable(_token, _drive_id):
        return True

    monkeypatch.setattr(sa, "_load_tenant_cloud_root", root)
    monkeypatch.setattr(sa, "_service_account_can_access_drive", reachable)


@pytest.fixture
def service_account(monkeypatch, tenant_roots):
    async def token(*_args, **_kwargs):
        return SA_TOKEN

    monkeypatch.setattr(sa, "is_configured", lambda: True)
    monkeypatch.setattr(sa, "get_access_token", token)


@pytest.fixture
def minting(monkeypatch, tenant_roots):
    """Drive the real ``get_access_token`` with a controllable clock and issuer."""
    clock = {"now": 1000.0}
    issued = []

    class _TokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return issued.pop(0)

    monkeypatch.setattr(
        sa,
        "load_service_account",
        lambda: {"client_email": "sa@example.test", "private_key": "unused"},
    )
    monkeypatch.setattr(sa, "_build_assertion", lambda *_args: "assertion")
    monkeypatch.setattr(sa.httpx, "AsyncClient", lambda **_kwargs: _TokenClient())
    monkeypatch.setattr(sa, "time", types.SimpleNamespace(time=lambda: clock["now"]))
    return clock, issued


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


class _Client:
    def __init__(self, calls, responses=None, files=None):
        self.calls = calls
        self.responses = responses or {}
        self.files = files or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, *, headers=None, params=None, **_kwargs):
        self.calls.append((url, dict(params or {})))
        for suffix, response in self.responses.items():
            if url.endswith(suffix) and (params or {}).get("fields") == "driveId":
                return response
        if url.endswith("/files"):
            return _Response({"files": self.files})
        return _Response({})


async def _sa_token_for(tenant_id="tenant-a"):
    return await sa.prefer_service_account(TENANT_DB, tenant_id, "delegated")


def test_scope_is_none_for_a_delegated_token():
    assert sa.service_account_drive_scope("delegated") is None
    assert sa.service_account_drive_scope(None) is None


@pytest.mark.asyncio
async def test_prefer_service_account_returns_a_token_bound_to_the_tenant_drive(
    service_account,
):
    token = await _sa_token_for()

    assert token == SA_TOKEN
    assert f"Bearer {token}" == f"Bearer {SA_TOKEN}"
    assert sa.service_account_drive_scope(token) == "drive-A"


def test_scope_of_a_service_account_token_without_a_drive_is_empty():
    token = sa.ServiceAccountDriveToken(SA_TOKEN, "")
    assert sa.service_account_drive_scope(token) == sa.NO_TENANT_DRIVE


@pytest.mark.asyncio
async def test_scope_survives_token_rotation_and_failed_refresh(minting):
    clock, issued = minting
    # Token A is still valid, but inside the 60s refresh skew 1.5s later.
    issued.append(_Response({"access_token": "token-A", "expires_in": 61}))
    token_a = await _sa_token_for()
    assert token_a == "token-A"

    # The cache then refreshes to token B...
    clock["now"] = 1001.5
    issued[:] = [_Response({"access_token": "token-B", "expires_in": 3600})]
    assert await sa.get_access_token(sa.DRIVE_SCOPES) == "token-B"
    assert sa.service_account_drive_scope(token_a) == "drive-A"

    # ...or the refresh fails outright.
    sa._token_cache.clear()
    issued[:] = [_Response({}, status_code=503)]
    assert await sa.get_access_token(sa.DRIVE_SCOPES) is None
    assert sa.service_account_drive_scope(token_a) == "drive-A"


@pytest.mark.asyncio
async def test_a_bare_service_account_token_fails_closed_after_rotation(minting):
    clock, issued = minting
    issued.append(_Response({"access_token": "token-A", "expires_in": 61}))
    assert await sa.get_access_token(sa.DRIVE_SCOPES) == "token-A"

    clock["now"] = 1001.5
    issued.append(_Response({"access_token": "token-B", "expires_in": 3600}))
    assert await sa.get_access_token(sa.DRIVE_SCOPES) == "token-B"

    # Without the drive it was chosen for, neither token may list anything.
    assert sa.service_account_drive_scope("token-A") == sa.NO_TENANT_DRIVE
    assert sa.service_account_drive_scope("token-B") == sa.NO_TENANT_DRIVE


@pytest.mark.asyncio
async def test_rotated_token_still_pins_search_and_rejects_foreign_files(
    monkeypatch, minting
):
    clock, issued = minting
    issued.append(_Response({"access_token": "token-A", "expires_in": 61}))
    token_a = await _sa_token_for()
    clock["now"] = 1001.5
    issued.append(_Response({"access_token": "token-B", "expires_in": 3600}))
    await sa.get_access_token(sa.DRIVE_SCOPES)

    service = CloudSearchService()
    calls = []

    async def token(*_args, **_kwargs):
        return token_a

    monkeypatch.setattr(service, "_get_google_token", token)
    monkeypatch.setattr(
        cloud_search_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(
            calls, {"/files/foreign-file": _Response({"driveId": "drive-B"})}
        ),
    )

    await service._search_google_drive(
        db=None,
        keywords=["matter"],
        date_after="",
        max_hits=10,
        tenant_id="tenant-a",
        user_id=None,
        token=token_a,
    )
    assert calls[0][1]["corpora"] == "drive"
    assert calls[0][1]["driveId"] == "drive-A"

    calls.clear()
    hit = CloudHit(
        provider="google",
        source="drive",
        object_id="foreign-file",
        title="Other firm's memo",
        snippet="other firm snippet",
        url="",
        modified_time="",
        mime_type="application/pdf",
    )
    assert (
        await service._fetch_google_drive_content(None, hit, "tenant-a", 2000, None)
        is None
    )
    assert [params.get("fields") for _url, params in calls] == ["driveId"]


@pytest.mark.asyncio
async def test_public_search_pins_a_prefetched_service_account_token(
    monkeypatch, service_account
):
    """The provider fan-out runs without a session; the drive must travel along."""
    service = CloudSearchService()
    calls = []

    async def delegated(*_args, **_kwargs):
        return "delegated"

    async def no_user_token(*_args, **_kwargs):
        return None

    async def no_index(*_args, **_kwargs):
        return []

    monkeypatch.setattr(cloud_search_module, "get_fresh_token", delegated)
    monkeypatch.setattr(cloud_search_module, "get_fresh_user_token", no_user_token)
    monkeypatch.setattr(service, "search_index", no_index)
    monkeypatch.setattr(
        cloud_search_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(
            calls,
            files=[
                {
                    "id": "file-1",
                    "name": "Engagement letter.pdf",
                    "mimeType": "application/pdf",
                    "webViewLink": "https://drive.test/file-1",
                    "modifiedTime": "2026-09-01T00:00:00Z",
                    "owners": [],
                }
            ],
        ),
    )

    hits = await service.search(
        TENANT_DB,
        {"keywords": ["engagement"], "sources": ["drive"]},
        "tenant-a",
    )

    listing = [params for url, params in calls if url.endswith("/files")]
    assert listing, "the Drive search request never ran"
    assert listing[0]["corpora"] == "drive"
    assert listing[0]["driveId"] == "drive-A"
    assert [hit.object_id for hit in hits] == ["file-1"]


@pytest.mark.asyncio
async def test_drive_search_refuses_a_bare_service_account_token(
    monkeypatch, service_account
):
    service = CloudSearchService()
    calls = []
    sa._ISSUED_SERVICE_TOKENS[SA_TOKEN] = float("inf")
    monkeypatch.setattr(
        cloud_search_module.httpx, "AsyncClient", lambda **_kwargs: _Client(calls)
    )

    hits = await service._search_google_drive(
        db=None,
        keywords=["matter"],
        date_after="",
        max_hits=10,
        tenant_id="tenant-a",
        user_id=None,
        token=SA_TOKEN,
    )

    assert hits == []
    assert calls == []


@pytest.mark.asyncio
async def test_drive_search_with_delegated_token_is_unchanged(monkeypatch):
    service = CloudSearchService()
    calls = []
    monkeypatch.setattr(
        cloud_search_module.httpx, "AsyncClient", lambda **_kwargs: _Client(calls)
    )

    await service._search_google_drive(
        db=None,
        keywords=["matter"],
        date_after="",
        max_hits=10,
        tenant_id="tenant-a",
        user_id=None,
        token="delegated",
    )

    assert calls[0][1]["corpora"] == "allDrives"
    assert "driveId" not in calls[0][1]


@pytest.mark.asyncio
async def test_tenant_drive_sync_with_service_account_is_limited_to_tenant_drive(
    monkeypatch, service_account
):
    service = cloud_sync_module.CloudSyncService()
    calls = []
    sa_token = await _sa_token_for()

    async def token(*_args, **_kwargs):
        return sa_token

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


@pytest.mark.asyncio
async def test_tenant_drive_sync_refuses_a_bare_service_account_token(
    monkeypatch, service_account
):
    service = cloud_sync_module.CloudSyncService()
    calls = []
    sa._ISSUED_SERVICE_TOKENS[SA_TOKEN] = float("inf")

    async def token(*_args, **_kwargs):
        return SA_TOKEN

    monkeypatch.setattr(service, "_get_token", token)
    monkeypatch.setattr(
        cloud_sync_module.httpx, "AsyncClient", lambda **_kwargs: _Client(calls)
    )

    assert await service.sync_google_drive(object(), "tenant-a") == 0
    assert calls == []


def test_a_bound_token_keeps_its_drive_when_copied():
    import copy
    import pickle

    token = sa.ServiceAccountDriveToken(SA_TOKEN, "drive-A")

    for clone in (
        copy.copy(token),
        copy.deepcopy(token),
        pickle.loads(pickle.dumps(token)),
    ):
        assert clone == SA_TOKEN
        assert sa.service_account_drive_scope(clone) == "drive-A"


@pytest.mark.asyncio
async def test_expired_service_account_tokens_are_forgotten(minting):
    clock, issued = minting
    issued.append(_Response({"access_token": "token-A", "expires_in": 100}))
    await sa.get_access_token(sa.DRIVE_SCOPES)

    clock["now"] = 2000.0
    issued.append(_Response({"access_token": "token-B", "expires_in": 3600}))
    await sa.get_access_token(sa.DRIVE_SCOPES)

    assert "token-A" not in sa._ISSUED_SERVICE_TOKENS
    assert sa.service_account_drive_scope("token-B") == sa.NO_TENANT_DRIVE
