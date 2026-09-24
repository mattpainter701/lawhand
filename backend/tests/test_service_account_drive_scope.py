"""The shared platform service account must never cross tenant boundaries.

One Google service account is a member of every tenant's org Shared Drive.
Cloud search and the tenant-wide Drive sync fall back to it when a user has
no personal grant, so a ``corpora=allDrives`` / ``includeItemsFromAllDrives``
request made with its token returned other firms' files. Every such request
is now pinned to the requesting tenant's own drive, which the token carries
from the moment :func:`prefer_service_account` chooses it.
"""

import types

import httpx
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
DRIVE = cloud_search_module.GOOGLE_DRIVE_BASE


@pytest.fixture(autouse=True)
def _clean_caches():
    sa._clear_cache()
    sa._clear_drive_access_cache()
    yield
    sa._clear_cache()
    sa._clear_drive_access_cache()


@pytest.fixture
def tenant_roots(monkeypatch):
    roots = {
        "tenant-a": TENANT_ROOT,
        "tenant-b": {
            "google_drive": {"owner_type": "org_shared_drive", "drive_id": "drive-B"}
        },
        "tenant-no-drive": {},
        "tenant-my-drive": {
            "google_drive": {"owner_type": "user_my_drive", "folder_id": "root-folder"}
        },
        "tenant-blank-drive": {
            "google_drive": {"owner_type": "org_shared_drive", "drive_id": "  "}
        },
    }

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


class _Download:
    status_code = 200

    def __init__(self, content):
        self.content = content
        self.headers = {"content-length": str(len(content))}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def aiter_bytes(self):
        yield self.content


class _Client:
    def __init__(self, calls, responses=None, files=None, pages=None, body=b""):
        self.calls = calls
        self.responses = responses or {}
        self.files = files or []
        self.pages = list(pages or [])
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, *, headers=None, params=None, **_kwargs):
        self.calls.append((url, dict(params or {})))
        for suffix, response in self.responses.items():
            if url.endswith(suffix) and (params or {}).get("fields") == "driveId":
                if isinstance(response, Exception):
                    raise response
                return response
        if url.endswith("/files"):
            if self.pages:
                return _Response(self.pages.pop(0))
            return _Response({"files": self.files})
        return _Response({})

    def stream(self, _method, url, *, headers=None, params=None, **_kwargs):
        self.calls.append((url, dict(params or {})))
        return _Download(self.body)


class _Db:
    async def commit(self):
        pass

    async def rollback(self):
        pass


async def _sa_token_for(tenant_id="tenant-a"):
    return await sa.prefer_service_account(TENANT_DB, tenant_id, "delegated")


def _drive_hit(object_id="own-file", mime_type="text/plain", snippet="cached snippet"):
    return CloudHit(
        provider="google",
        source="drive",
        object_id=object_id,
        title="Engagement letter",
        snippet=snippet,
        url="",
        modified_time="",
        mime_type=mime_type,
    )


def _probe(file_id):
    return (
        f"{DRIVE}/files/{file_id}",
        {"fields": "driveId", "supportsAllDrives": True},
    )


async def _fetch_content(monkeypatch, token, hit, calls, **client_kwargs):
    service = CloudSearchService()

    async def google_token(*_args, **_kwargs):
        return token

    monkeypatch.setattr(service, "_get_google_token", google_token)
    monkeypatch.setattr(
        cloud_search_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(calls, **client_kwargs),
    )
    return await service._fetch_google_drive_content(None, hit, "tenant-a", 2000, None)


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "probe",
    [
        pytest.param(httpx.ConnectError("drive unreachable"), id="request-error"),
        pytest.param(
            _Response({"driveId": "drive-A"}, status_code=404), id="not-found"
        ),
        pytest.param(
            _Response({"driveId": "drive-A"}, status_code=403), id="forbidden"
        ),
        pytest.param(_Response({}), id="drive-id-missing"),
        pytest.param(_Response({"driveId": None}), id="drive-id-null"),
        pytest.param(_Response({"driveId": "drive-B"}), id="other-tenant-drive"),
    ],
)
async def test_content_is_refused_unless_drive_confirms_the_tenant_drive(
    monkeypatch, probe
):
    calls = []

    content = await _fetch_content(
        monkeypatch,
        sa.ServiceAccountDriveToken(SA_TOKEN, "drive-A"),
        _drive_hit(),
        calls,
        responses={"/files/own-file": probe},
        body=b"another firm's privileged memo",
    )

    assert content is None
    # Only the membership check ran; the file body was never requested.
    assert calls == [_probe("own-file")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        pytest.param(sa.ServiceAccountDriveToken(SA_TOKEN, ""), id="bound-no-drive"),
        pytest.param(SA_TOKEN, id="bare"),
    ],
)
async def test_content_fetch_with_an_unscoped_service_account_token_reads_nothing(
    monkeypatch, token
):
    sa._ISSUED_SERVICE_TOKENS[SA_TOKEN] = float("inf")
    calls = []

    content = await _fetch_content(
        monkeypatch,
        token,
        _drive_hit(),
        calls,
        responses={"/files/own-file": _Response({"driveId": "drive-A"})},
        body=b"file body",
    )

    assert content == "cached snippet"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime_type", "download"),
    [
        pytest.param(
            "application/vnd.google-apps.document",
            (f"{DRIVE}/files/own-file/export", {"mimeType": "text/plain"}),
            id="google-native-export",
        ),
        pytest.param(
            "text/plain",
            (f"{DRIVE}/files/own-file", {"alt": "media", "supportsAllDrives": True}),
            id="binary-alt-media",
        ),
    ],
)
async def test_own_drive_file_is_downloaded_after_the_drive_check(
    monkeypatch, mime_type, download
):
    calls = []

    content = await _fetch_content(
        monkeypatch,
        sa.ServiceAccountDriveToken(SA_TOKEN, "drive-A"),
        _drive_hit(mime_type=mime_type),
        calls,
        responses={"/files/own-file": _Response({"driveId": "drive-A"})},
        body=b"Tenant A engagement terms",
    )

    assert content == "Tenant A engagement terms"
    assert calls == [_probe("own-file"), download]


@pytest.mark.asyncio
async def test_delegated_content_fetch_skips_the_drive_check(monkeypatch):
    """A user's own grant already limits what it can open; no pin applies."""
    calls = []

    content = await _fetch_content(
        monkeypatch,
        "delegated",
        _drive_hit(object_id="shared-with-me"),
        calls,
        responses={"/files/shared-with-me": _Response({"driveId": "drive-B"})},
        body=b"Shared with the user",
    )

    assert content == "Shared with the user"
    assert calls == [
        (f"{DRIVE}/files/shared-with-me", {"alt": "media", "supportsAllDrives": True})
    ]


@pytest.mark.asyncio
async def test_folder_scoped_search_with_a_bound_token_stays_in_the_tenant_drive(
    monkeypatch,
):
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
        folder_id="matter-folder",
        token=sa.ServiceAccountDriveToken(SA_TOKEN, "drive-A"),
    )

    assert [url for url, _params in calls] == [f"{DRIVE}/files"]
    params = calls[0][1]
    assert "'matter-folder' in parents" in params["q"]
    assert params["corpora"] == "drive"
    assert params["driveId"] == "drive-A"
    assert params["includeItemsFromAllDrives"] is True
    assert params["supportsAllDrives"] is True


def _synced_file(file_id):
    return {"id": file_id, "name": f"{file_id}.pdf", "mimeType": "application/pdf"}


@pytest.mark.asyncio
async def test_tenant_drive_sync_keeps_the_drive_pin_on_every_page(monkeypatch):
    service = cloud_sync_module.CloudSyncService()
    calls = []
    upserted = []

    async def token(*_args, **_kwargs):
        return sa.ServiceAccountDriveToken(SA_TOKEN, "drive-A")

    async def upsert(_db, tenant_id, **data):
        upserted.append((tenant_id, data["object_id"]))

    monkeypatch.setattr(service, "_get_token", token)
    monkeypatch.setattr(service, "_upsert", upsert)
    monkeypatch.setattr(
        cloud_sync_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(
            calls,
            pages=[
                {"files": [_synced_file("file-1")], "nextPageToken": "page-2"},
                {"files": [_synced_file("file-2")]},
            ],
        ),
    )

    assert await service.sync_google_drive(_Db(), "tenant-a") == 2

    assert [url for url, _params in calls] == [f"{DRIVE}/files", f"{DRIVE}/files"]
    for _url, params in calls:
        assert params["corpora"] == "drive"
        assert params["driveId"] == "drive-A"
    assert "pageToken" not in calls[0][1]
    assert calls[1][1]["pageToken"] == "page-2"
    assert upserted == [("tenant-a", "file-1"), ("tenant-a", "file-2")]


@pytest.mark.asyncio
async def test_tenant_drive_sync_with_a_delegated_token_lists_the_users_corpus(
    monkeypatch,
):
    service = cloud_sync_module.CloudSyncService()
    calls = []

    async def token(*_args, **_kwargs):
        return "delegated"

    monkeypatch.setattr(service, "_get_token", token)
    monkeypatch.setattr(
        cloud_sync_module.httpx, "AsyncClient", lambda **_kwargs: _Client(calls)
    )

    assert await service.sync_google_drive(_Db(), "tenant-a") == 0

    params = calls[0][1]
    assert params["corpora"] == "user"
    assert "driveId" not in params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tenant_id", ["tenant-my-drive", "tenant-no-drive", "tenant-blank-drive"]
)
async def test_prefer_service_account_keeps_the_delegated_token_without_an_org_drive(
    monkeypatch, tenant_roots, tenant_id
):
    minted = []

    async def token(*args, **kwargs):
        minted.append((args, kwargs))
        return SA_TOKEN

    monkeypatch.setattr(sa, "get_access_token", token)

    result = await _sa_token_for(tenant_id)

    assert result == "delegated"
    assert type(result) is str
    assert sa.service_account_drive_scope(result) is None
    assert minted == []


@pytest.mark.asyncio
async def test_prefer_service_account_keeps_the_delegated_token_when_minting_fails(
    monkeypatch, tenant_roots
):
    probes = []

    async def no_token(*_args, **_kwargs):
        return None

    async def reachable(_token, drive_id):
        probes.append(drive_id)
        return True

    monkeypatch.setattr(sa, "get_access_token", no_token)
    monkeypatch.setattr(sa, "_service_account_can_access_drive", reachable)

    result = await _sa_token_for()

    assert result == "delegated"
    assert type(result) is str
    assert probes == []


@pytest.mark.asyncio
async def test_prefer_service_account_keeps_the_delegated_token_when_drive_unreachable(
    monkeypatch, service_account
):
    probes = []

    async def unreachable(token, drive_id):
        probes.append((token, drive_id))
        return False

    monkeypatch.setattr(sa, "_service_account_can_access_drive", unreachable)

    first = await _sa_token_for()
    second = await _sa_token_for()

    for result in (first, second):
        assert result == "delegated"
        assert type(result) is str
        assert sa.service_account_drive_scope(result) is None
    # A failed probe is never remembered as access.
    assert probes == [(SA_TOKEN, "drive-A"), (SA_TOKEN, "drive-A")]


@pytest.mark.asyncio
async def test_a_confirmed_drive_probe_is_reused_only_for_its_own_tenant(
    monkeypatch, service_account
):
    probes = []

    async def reachable(_token, drive_id):
        probes.append(drive_id)
        return drive_id == "drive-A"

    monkeypatch.setattr(sa, "_service_account_can_access_drive", reachable)

    first = await _sa_token_for("tenant-a")
    second = await _sa_token_for("tenant-a")
    other = await _sa_token_for("tenant-b")

    assert probes == ["drive-A", "drive-B"]
    for token in (first, second):
        assert isinstance(token, sa.ServiceAccountDriveToken)
        assert sa.service_account_drive_scope(token) == "drive-A"
    assert other == "delegated"
    assert type(other) is str


@pytest.mark.asyncio
async def test_a_user_impersonation_token_is_not_the_platform_identity(minting):
    _clock, issued = minting
    issued.append(_Response({"access_token": "platform-token", "expires_in": 3600}))
    issued.append(_Response({"access_token": "impersonated-token", "expires_in": 3600}))

    assert await sa.get_access_token(sa.DRIVE_SCOPES) == "platform-token"
    assert (
        await sa.get_access_token(sa.DRIVE_SCOPES, subject="partner@firm.test")
        == "impersonated-token"
    )

    assert "impersonated-token" not in sa._ISSUED_SERVICE_TOKENS
    assert sa.service_account_drive_scope("impersonated-token") is None
    assert sa.service_account_drive_scope("platform-token") == sa.NO_TENANT_DRIVE
