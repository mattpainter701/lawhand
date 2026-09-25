import hashlib
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest

import app.services.matter_file_store as store_module
from app.services.matter_file_store import (
    MatterFileAccessError,
    MatterFileCleanupError,
    MatterFileIntegrityError,
    MatterFileMetadataError,
    MatterFileStoragePolicyError,
    MatterFileStore,
    MatterFileTooLarge,
    StorageResult,
)


def _mock_http_client(monkeypatch, handler):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(store_module.httpx, "AsyncClient", client)


def _document(
    tenant_id: str,
    *,
    backend: str,
    storage_path: str = "https://attacker.invalid/not-a-download-source",
    provider: str | None = None,
    item_id: str | None = None,
    drive_id: str | None = None,
    file_size: int | None = None,
):
    return SimpleNamespace(
        tenant_id=tenant_id,
        _storage_backend=backend,
        storage_backend=backend,
        storage_provider=provider,
        storage_path=storage_path,
        provider_object_id=item_id,
        provider_drive_id=drive_id,
        file_size=file_size,
    )


@pytest.mark.asyncio
async def test_local_read_is_tenant_scoped_size_bounded_and_hash_checked(
    tmp_path, monkeypatch
):
    tenant_id = "tenant-a"
    tenant_root = tmp_path / tenant_id
    tenant_root.mkdir()
    path = tenant_root / "agreement.pdf"
    content = b"%PDF-1.7\nsource bytes"
    path.write_bytes(content)
    monkeypatch.setattr(store_module.settings, "UPLOAD_DIR", str(tmp_path))

    document = _document(
        tenant_id,
        backend="local",
        storage_path=str(path),
        provider="local",
        file_size=len(content),
    )
    expected_hash = hashlib.sha256(content).hexdigest()
    store = MatterFileStore()

    assert (
        await store.read_matter_file_bytes(
            db=object(),
            tenant_id=tenant_id,
            document=document,
            expected_sha256=expected_hash,
        )
        == content
    )

    with pytest.raises(MatterFileIntegrityError):
        await store.read_matter_file_bytes(
            db=object(),
            tenant_id=tenant_id,
            document=document,
            expected_sha256="0" * 64,
        )

    with pytest.raises(MatterFileTooLarge):
        await store.read_matter_file_bytes(
            db=object(),
            tenant_id=tenant_id,
            document=document,
            max_bytes=len(content) - 1,
        )


@pytest.mark.asyncio
async def test_local_read_rejects_cross_tenant_and_traversal_paths(
    tmp_path, monkeypatch
):
    tenant_id = "tenant-a"
    (tmp_path / tenant_id).mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside")
    monkeypatch.setattr(store_module.settings, "UPLOAD_DIR", str(tmp_path))
    store = MatterFileStore()

    with pytest.raises(MatterFileAccessError):
        await store.read_matter_file_bytes(
            db=object(),
            tenant_id=tenant_id,
            document=_document(
                tenant_id,
                backend="local",
                provider="local",
                storage_path=str(outside),
                file_size=len(b"outside"),
            ),
        )

    with pytest.raises(MatterFileAccessError):
        await store._store_local(
            tenant_id,
            "matter",
            "documents",
            "../../../../outside.pdf",
            b"blocked",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend", "provider", "item_id", "drive_id", "token_provider", "path"),
    [
        (
            "google_drive",
            "google",
            "google-item",
            None,
            "google",
            "/drive/v3/files/google-item",
        ),
        (
            "onedrive",
            "microsoft",
            "onedrive-item",
            None,
            "microsoft",
            "/v1.0/me/drive/items/onedrive-item/content",
        ),
        (
            "sharepoint",
            "microsoft",
            "sharepoint-item",
            "sharepoint-drive",
            "microsoft",
            "/v1.0/drives/sharepoint-drive/items/sharepoint-item/content",
        ),
    ],
)
async def test_cloud_read_uses_fresh_tenant_token_and_only_durable_provider_ids(
    monkeypatch,
    backend,
    provider,
    item_id,
    drive_id,
    token_provider,
    path,
):
    tenant_id = "tenant-a"
    content = b"provider document bytes"
    token_calls = []
    requested_urls = []

    async def fake_get_fresh_token(db, resolved_tenant_id, resolved_provider):
        token_calls.append((db, resolved_tenant_id, resolved_provider))
        return "fresh-token"

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        assert request.headers["Authorization"] == "Bearer fresh-token"
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Length": str(len(content))},
        )

    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(store_module, "get_fresh_token", fake_get_fresh_token)
    monkeypatch.setattr(store_module.httpx, "AsyncClient", mock_client)

    db = object()
    document = _document(
        tenant_id,
        backend=backend,
        provider=provider,
        item_id=item_id,
        drive_id=drive_id,
        file_size=len(content),
    )
    result = await MatterFileStore().read_matter_file_bytes(
        db=db,
        tenant_id=tenant_id,
        document=document,
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )

    assert result == content
    assert token_calls == [(db, tenant_id, token_provider)]
    assert len(requested_urls) == 1
    assert path in requested_urls[0]
    assert "attacker.invalid" not in requested_urls[0]


@pytest.mark.asyncio
async def test_cloud_read_requires_durable_item_id_before_any_token_or_http_call(
    monkeypatch,
):
    async def unexpected_token(*_args, **_kwargs):
        raise AssertionError("token lookup must not occur without a provider item ID")

    monkeypatch.setattr(store_module, "get_fresh_token", unexpected_token)
    document = _document(
        "tenant-a",
        backend="google_drive",
        provider="google",
        item_id=None,
        file_size=1,
    )

    with pytest.raises(MatterFileMetadataError):
        await MatterFileStore().read_matter_file_bytes(
            db=object(),
            tenant_id="tenant-a",
            document=document,
        )


@pytest.mark.asyncio
async def test_explicit_primary_cloud_fails_closed_without_local_or_cross_cloud_spill(
    tmp_path,
    monkeypatch,
):
    tenant_id = "tenant-a"
    monkeypatch.setattr(store_module.settings, "UPLOAD_DIR", str(tmp_path))
    store = MatterFileStore()
    calls = []

    async def failed_google(*_args, **_kwargs):
        calls.append("google_drive")
        return StorageResult(
            provider="google",
            backend="google_drive",
            error="provider failure that must not be exposed verbatim",
        )

    async def unexpected_onedrive(*_args, **_kwargs):
        raise AssertionError("explicit Google preference must not spill to OneDrive")

    async def unexpected_sharepoint(*_args, **_kwargs):
        raise AssertionError("explicit Google preference must not spill to SharePoint")

    monkeypatch.setattr(store, "_try_store_google_drive", failed_google)
    monkeypatch.setattr(store, "_try_store_onedrive", unexpected_onedrive)
    monkeypatch.setattr(store, "_try_store_sharepoint", unexpected_sharepoint)

    content = b"durably retained bytes"
    with pytest.raises(MatterFileStoragePolicyError) as exc_info:
        await store.store_matter_file_result(
            db=object(),
            tenant_id=tenant_id,
            matter_slug="matter-1",
            category="documents",
            filename="agreement.pdf",
            content=content,
            content_type="application/pdf",
            preferred_provider="google_drive",
        )

    assert calls == ["google_drive"]
    message = str(exc_info.value)
    assert "No durable local copy was created" in message
    assert "Reconnect Google Drive" in message
    assert "provider failure that must not be exposed verbatim" not in message
    assert not (
        tmp_path / tenant_id / "matters" / "matter-1" / "documents" / "agreement.pdf"
    ).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 503])
async def test_google_lookup_failure_does_not_start_upload(monkeypatch, status_code):
    requests = []

    async def token(*_args):
        return "google-token"

    async def no_lock(*_args, **_kwargs):
        return None

    def handler(request):
        requests.append(request.method)
        return httpx.Response(status_code, text="provider failure")

    monkeypatch.setattr(store_module, "_storage_token", token)
    monkeypatch.setattr(MatterFileStore, "_lock_write_binding", no_lock)
    _mock_http_client(monkeypatch, handler)

    result = await MatterFileStore()._try_store_google_drive(
        db=object(),
        tenant_id="tenant-a",
        matter_slug="matter-1",
        category="documents",
        filename="agreement.pdf",
        content=b"content",
        content_type="application/pdf",
        folder_id="parent-1",
    )

    assert result is not None
    assert result.error
    assert requests == ["GET"]


@pytest.mark.asyncio
async def test_google_lookup_transport_failure_does_not_start_upload(monkeypatch):
    requests = []

    async def token(*_args):
        return "google-token"

    async def no_lock(*_args, **_kwargs):
        return None

    def handler(request):
        requests.append(request.method)
        raise httpx.ConnectError("temporary lookup failure", request=request)

    monkeypatch.setattr(store_module, "_storage_token", token)
    monkeypatch.setattr(MatterFileStore, "_lock_write_binding", no_lock)
    _mock_http_client(monkeypatch, handler)

    result = await MatterFileStore()._try_store_google_drive(
        db=object(),
        tenant_id="tenant-a",
        matter_slug="matter-1",
        category="documents",
        filename="agreement.pdf",
        content=b"content",
        content_type="application/pdf",
        folder_id="parent-1",
    )

    assert result is not None
    assert result.error == "Google Drive file lookup did not complete"
    assert requests == ["GET"]


@pytest.mark.asyncio
async def test_google_empty_lookup_proceeds_to_upload(monkeypatch):
    requests = []

    async def token(*_args):
        return "google-token"

    async def no_lock(*_args, **_kwargs):
        return None

    def handler(request):
        requests.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"files": []})
        return httpx.Response(200, json={"id": "item-1", "parents": ["parent-1"]})

    monkeypatch.setattr(store_module, "_storage_token", token)
    monkeypatch.setattr(MatterFileStore, "_lock_write_binding", no_lock)
    _mock_http_client(monkeypatch, handler)

    result = await MatterFileStore()._try_store_google_drive(
        db=object(),
        tenant_id="tenant-a",
        matter_slug="matter-1",
        category="documents",
        filename="agreement.pdf",
        content=b"content",
        content_type="application/pdf",
        folder_id="parent-1",
    )

    assert result is not None
    assert result.provider_item_id == "item-1"
    assert requests == ["GET", "POST"]


@pytest.mark.asyncio
async def test_auto_mode_binds_an_active_microsoft_tenant_to_onedrive(monkeypatch):
    class _Result:
        def __init__(self, *, scalar=None, values=None):
            self.scalar = scalar
            self.values = values or []

        def scalar_one_or_none(self):
            return self.scalar

        def scalars(self):
            return self

        def all(self):
            return self.values

    class _Db:
        def __init__(self):
            self.results = [
                _Result(scalar=None),  # no saved matter folder
                _Result(scalar=None),
                _Result(values=["google", "microsoft"]),
            ]

        async def execute(self, _query):
            return self.results.pop(0)

    store = MatterFileStore()
    calls = []

    async def successful_onedrive(*_args, **_kwargs):
        calls.append("onedrive")
        return StorageResult(
            provider="microsoft",
            backend="onedrive",
            storage_path="https://contoso.sharepoint.com/document.pdf",
            provider_item_id="item-1",
        )

    async def unexpected_provider(*_args, **_kwargs):
        raise AssertionError("Microsoft Auto binding must be exclusive")

    monkeypatch.setattr(store, "_try_store_onedrive", successful_onedrive)
    monkeypatch.setattr(store, "_try_store_sharepoint", unexpected_provider)
    monkeypatch.setattr(store, "_try_store_google_drive", unexpected_provider)

    result = await store.store_matter_file_result(
        db=_Db(),
        tenant_id=str(uuid.uuid4()),
        matter_slug="matter-1",
        category="client_uploads",
        filename="statement.pdf",
        content=b"content",
        content_type="application/pdf",
    )

    assert calls == ["onedrive"]
    assert result.backend == "onedrive"


@pytest.mark.asyncio
async def test_auto_mode_keeps_first_available_cross_cloud_cascade(monkeypatch):
    store = MatterFileStore()
    calls = []

    async def failed_onedrive(*_args, **_kwargs):
        calls.append("onedrive")
        return StorageResult(
            provider="microsoft",
            backend="onedrive",
            error="not connected",
        )

    async def successful_sharepoint(*_args, **_kwargs):
        calls.append("sharepoint")
        return StorageResult(
            provider="microsoft",
            backend="sharepoint",
            storage_path="https://contoso.sharepoint.com/document.pdf",
            provider_item_id="item-1",
            drive_id="drive-1",
        )

    async def unexpected_google(*_args, **_kwargs):
        raise AssertionError("auto mode should stop at the first successful provider")

    monkeypatch.setattr(store, "_try_store_onedrive", failed_onedrive)
    monkeypatch.setattr(store, "_try_store_sharepoint", successful_sharepoint)
    monkeypatch.setattr(store, "_try_store_google_drive", unexpected_google)

    result = await store.store_matter_file_result(
        db=object(),
        tenant_id="tenant-a",
        matter_slug="matter-1",
        category="documents",
        filename="agreement.pdf",
        content=b"content",
        content_type="application/pdf",
        preferred_provider=None,
    )

    assert calls == ["onedrive", "sharepoint"]
    assert result.backend == "sharepoint"
    assert result.error is None


@pytest.mark.asyncio
async def test_cleanup_deletes_only_exact_local_file_beneath_tenant_root(
    tmp_path, monkeypatch
):
    tenant_id = "tenant-a"
    tenant_root = tmp_path / tenant_id
    tenant_root.mkdir()
    staged = tenant_root / "matters" / "matter-1" / "generated" / "form.pdf"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"staged")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside")
    monkeypatch.setattr(store_module.settings, "UPLOAD_DIR", str(tmp_path))
    store = MatterFileStore()

    await store.delete_stored_result(
        db=object(),
        tenant_id=tenant_id,
        result=StorageResult(
            provider="local",
            backend="local",
            storage_path=str(staged),
        ),
    )
    assert not staged.exists()

    with pytest.raises(MatterFileAccessError):
        await store.delete_stored_result(
            db=object(),
            tenant_id=tenant_id,
            result=StorageResult(
                provider="local",
                backend="local",
                storage_path=str(outside),
            ),
        )
    assert outside.read_bytes() == b"outside"


@pytest.mark.asyncio
async def test_cleanup_rejects_local_symlink_even_when_target_is_in_tenant_root(
    tmp_path, monkeypatch
):
    tenant_id = "tenant-a"
    tenant_root = tmp_path / tenant_id
    tenant_root.mkdir()
    target = tenant_root / "real-staged.pdf"
    target.write_bytes(b"inside target")
    link = tenant_root / "linked.pdf"
    try:
        link.symlink_to(target)
    except OSError:
        # Windows may disallow symlink creation without Developer Mode. Still
        # exercise the fail-closed branch; Linux CI uses the real symlink above.
        link.write_bytes(b"simulated symlink entry")
        original_is_symlink = type(link).is_symlink
        monkeypatch.setattr(
            type(link),
            "is_symlink",
            lambda path: path == link or original_is_symlink(path),
        )
    monkeypatch.setattr(store_module.settings, "UPLOAD_DIR", str(tmp_path))

    with pytest.raises(MatterFileAccessError):
        await MatterFileStore().delete_stored_result(
            db=object(),
            tenant_id=tenant_id,
            result=StorageResult(
                provider="local",
                backend="local",
                storage_path=str(link),
            ),
        )
    assert target.read_bytes() == b"inside target"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend", "provider", "item_id", "drive_id", "token_provider", "expected_url"),
    [
        (
            "google_drive",
            "google",
            "google item",
            None,
            "google",
            "https://www.googleapis.com/drive/v3/files/google%20item?supportsAllDrives=true",
        ),
        (
            "onedrive",
            "microsoft",
            "one item",
            None,
            "microsoft",
            "https://graph.microsoft.com/v1.0/me/drive/items/one%20item",
        ),
        (
            "sharepoint",
            "microsoft",
            "share item",
            "drive id",
            "microsoft",
            "https://graph.microsoft.com/v1.0/drives/drive%20id/items/share%20item",
        ),
    ],
)
async def test_cloud_cleanup_uses_fixed_host_and_durable_provider_ids(
    monkeypatch,
    backend,
    provider,
    item_id,
    drive_id,
    token_provider,
    expected_url,
):
    tenant_id = "tenant-a"
    token_calls = []
    requested = []

    async def token(db, resolved_tenant, resolved_provider):
        token_calls.append((db, resolved_tenant, resolved_provider))
        return "fresh-token"

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert request.method == "DELETE"
        assert request.headers["Authorization"] == "Bearer fresh-token"
        return httpx.Response(204)

    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(store_module, "get_fresh_token", token)
    monkeypatch.setattr(store_module.httpx, "AsyncClient", mock_client)
    db = object()
    await MatterFileStore().delete_stored_result(
        db=db,
        tenant_id=tenant_id,
        result=StorageResult(
            provider=provider,
            backend=backend,
            storage_path="https://attacker.invalid/display-only",
            provider_item_id=item_id,
            drive_id=drive_id,
        ),
    )

    assert token_calls == [(db, tenant_id, token_provider)]
    assert requested == [expected_url]
    assert "attacker.invalid" not in requested[0]


@pytest.mark.asyncio
async def test_cloud_cleanup_treats_provider_404_as_idempotent_success(monkeypatch):
    async def token(*_args):
        return "fresh-token"

    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _request: httpx.Response(404))

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(store_module, "get_fresh_token", token)
    monkeypatch.setattr(store_module.httpx, "AsyncClient", mock_client)

    await MatterFileStore().delete_stored_result(
        db=object(),
        tenant_id="tenant-a",
        result=StorageResult(
            provider="google",
            backend="google_drive",
            provider_item_id="already-gone",
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        StorageResult(provider="google", backend="google_drive"),
        StorageResult(
            provider="microsoft",
            backend="sharepoint",
            provider_item_id="item-without-drive",
        ),
        StorageResult(
            provider="unknown",
            backend="unsupported",
            provider_item_id="item",
        ),
    ],
)
async def test_cloud_cleanup_missing_metadata_and_unknown_backends_fail_closed(
    monkeypatch, result
):
    async def unexpected_token(*_args):
        raise AssertionError("metadata must be validated before token lookup")

    monkeypatch.setattr(store_module, "get_fresh_token", unexpected_token)
    with pytest.raises(MatterFileCleanupError):
        await MatterFileStore().delete_stored_result(
            db=object(), tenant_id="tenant-a", result=result
        )


@pytest.mark.asyncio
async def test_cloud_cleanup_missing_tenant_token_fails_closed(monkeypatch):
    async def missing_token(*_args):
        return None

    monkeypatch.setattr(store_module, "get_fresh_token", missing_token)
    with pytest.raises(MatterFileCleanupError, match="credentials are unavailable"):
        await MatterFileStore().delete_stored_result(
            db=object(),
            tenant_id="tenant-a",
            result=StorageResult(
                provider="google",
                backend="google_drive",
                provider_item_id="item",
            ),
        )


GRAPH_FRAGMENT_UNIT = 320 * 1024
GOOGLE_CHUNK_UNIT = 256 * 1024
LARGE_UPLOAD_SIZE = 10 * 1024 * 1024 + 123


def _content_range_spans(ranges, total):
    spans = []
    expected_start = 0
    for value in ranges:
        unit, _, rest = value.partition(" ")
        assert unit == "bytes"
        span, _, size = rest.partition("/")
        start, _, end = span.partition("-")
        assert int(size) == total
        assert int(start) == expected_start
        spans.append(int(end) - int(start) + 1)
        expected_start = int(end) + 1
    assert expected_start == total
    return spans


def test_upload_chunk_sizes_match_each_provider_unit():
    assert MatterFileStore._GRAPH_CHUNK_SIZE % GRAPH_FRAGMENT_UNIT == 0
    assert MatterFileStore._GOOGLE_CHUNK_SIZE % GOOGLE_CHUNK_UNIT == 0
    # Graph caps a single fragment below 60 MiB.
    assert MatterFileStore._GRAPH_CHUNK_SIZE < 60 * 1024 * 1024


@pytest.mark.asyncio
async def test_large_onedrive_upload_sends_320k_multiple_fragments(monkeypatch):
    store = MatterFileStore()
    content = b"x" * LARGE_UPLOAD_SIZE
    assert len(content) > store._CHUNK_THRESHOLD_ONEDRIVE
    ranges = []

    def handler(request):
        if request.url.path.endswith(":/createUploadSession"):
            assert request.headers["Authorization"] == "Bearer token-1"
            return httpx.Response(
                200, json={"uploadUrl": "https://upload.example/session"}
            )
        assert request.url.host == "upload.example"
        assert "Authorization" not in request.headers
        assert int(request.headers["Content-Length"]) == len(request.content)
        ranges.append(request.headers["Content-Range"])
        end = int(ranges[-1].split("-")[1].split("/")[0])
        if end + 1 < len(content):
            return httpx.Response(202, json={"nextExpectedRanges": [f"{end + 1}-"]})
        return httpx.Response(
            201,
            json={
                "id": "item-large",
                "webUrl": "https://contoso.sharepoint.com/large.pdf",
            },
        )

    _mock_http_client(monkeypatch, handler)
    result = await store._upload_large_onedrive(
        "token-1", "parent-1", "large.pdf", content, "application/pdf"
    )

    assert result.error is None
    assert result.provider_item_id == "item-large"
    spans = _content_range_spans(ranges, len(content))
    assert len(spans) > 1
    assert all(span % GRAPH_FRAGMENT_UNIT == 0 for span in spans[:-1])
    assert spans[-1] <= store._GRAPH_CHUNK_SIZE


@pytest.mark.asyncio
async def test_large_google_drive_upload_sends_256k_multiple_chunks(monkeypatch):
    store = MatterFileStore()
    content = b"y" * LARGE_UPLOAD_SIZE
    assert len(content) > store._CHUNK_THRESHOLD_GOOGLE
    ranges = []

    def handler(request):
        if request.method == "POST":
            assert request.url.params["uploadType"] == "resumable"
            assert request.headers["X-Upload-Content-Length"] == str(len(content))
            return httpx.Response(
                200, headers={"Location": "https://upload.example/resumable"}
            )
        assert request.url.host == "upload.example"
        assert int(request.headers["Content-Length"]) == len(request.content)
        ranges.append(request.headers["Content-Range"])
        end = int(ranges[-1].split("-")[1].split("/")[0])
        if end + 1 < len(content):
            return httpx.Response(308, headers={"Range": f"bytes=0-{end}"})
        return httpx.Response(
            200,
            json={
                "id": "drive-large",
                "webViewLink": "https://drive.google.com/file/d/drive-large/view",
            },
        )

    _mock_http_client(monkeypatch, handler)
    result = await store._upload_large_google_drive(
        "token-1", "parent-1", "large.pdf", content, "application/pdf"
    )

    assert result.error is None
    assert result.provider_item_id == "drive-large"
    spans = _content_range_spans(ranges, len(content))
    assert len(spans) > 1
    assert all(span % GOOGLE_CHUNK_UNIT == 0 for span in spans[:-1])
    assert spans[-1] <= store._GOOGLE_CHUNK_SIZE


# D37: Graph addresses a new child by name inside the URL path
# (``items/{parent}:/{name}:/content``). A raw "#" starts a fragment, "?" starts
# a query and "%" is read as an escape, so every name must be sent as one
# percent-encoded path segment while the stored name keeps its characters.
GRAPH_PATH_NAMES = [
    pytest.param("Exhibit #3.pdf", "Exhibit%20%233.pdf", id="hash"),
    pytest.param("50% off.pdf", "50%25%20off.pdf", id="percent"),
    pytest.param("a?b.pdf", "a%3Fb.pdf", id="question-mark"),
    pytest.param("Invoice %20A.pdf", "Invoice%20%2520A.pdf", id="literal-escape"),
    pytest.param("Board minutes.pdf", "Board%20minutes.pdf", id="spaces"),
    pytest.param(
        "Résumé 日本.docx",
        "R%C3%A9sum%C3%A9%20%E6%97%A5%E6%9C%AC.docx",
        id="non-ascii",
    ),
]


def _assert_graph_name_path(request, prefix, encoded, suffix, name):
    raw_path, _, raw_query = request.url.raw_path.decode("ascii").partition("?")
    assert raw_path == f"{prefix}{encoded}{suffix}"
    assert request.url.fragment == ""
    # What Graph decodes back is the original name, character for character.
    assert request.url.path == f"{prefix}{name}{suffix}"
    return raw_query


async def _fresh_token(_db, _tenant_id, provider):
    assert provider == "microsoft"
    return "token-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "encoded"), GRAPH_PATH_NAMES)
async def test_onedrive_simple_upload_encodes_name_path_segment(
    monkeypatch, name, encoded
):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(
            201,
            json={"id": "item-1", "name": name, "webUrl": "https://1drv.ms/x"},
        )

    monkeypatch.setattr(store_module, "get_fresh_token", _fresh_token)
    _mock_http_client(monkeypatch, handler)
    result = await MatterFileStore()._try_store_onedrive(
        db=None,
        tenant_id=str(uuid.uuid4()),
        matter_slug="matter-a",
        category="documents",
        filename=name,
        content=b"pdf",
        content_type="application/pdf",
        folder_id="parent-1",
    )

    assert result.error is None
    assert result.provider_item_id == "item-1"
    assert len(sent) == 1
    assert sent[0].method == "PUT"
    query = _assert_graph_name_path(
        sent[0], "/v1.0/me/drive/items/parent-1:/", encoded, ":/content", name
    )
    assert query == "@microsoft.graph.conflictBehavior=rename"
    assert sent[0].url.params["@microsoft.graph.conflictBehavior"] == "rename"


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "encoded"), GRAPH_PATH_NAMES)
async def test_onedrive_upload_session_encodes_name_and_keeps_raw_body_name(
    monkeypatch, name, encoded
):
    sent = []

    def handler(request):
        sent.append(request)
        if request.url.host == "graph.microsoft.com":
            return httpx.Response(
                200, json={"uploadUrl": "https://upload.example/session"}
            )
        return httpx.Response(201, json={"id": "item-large", "name": name})

    _mock_http_client(monkeypatch, handler)
    result = await MatterFileStore()._upload_large_onedrive(
        "token-1", "parent-1", name, b"x" * 1024, "application/pdf"
    )

    assert result.error is None
    assert result.provider_item_id == "item-large"
    session = sent[0]
    assert session.method == "POST"
    query = _assert_graph_name_path(
        session,
        "/v1.0/me/drive/items/parent-1:/",
        encoded,
        ":/createUploadSession",
        name,
    )
    assert query == ""
    # The JSON body is not a URL: it carries the raw name and the conflict rule.
    assert json.loads(session.content) == {
        "item": {"@microsoft.graph.conflictBehavior": "rename", "name": name}
    }
    assert [request.url.host for request in sent[1:]] == ["upload.example"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "encoded"), GRAPH_PATH_NAMES)
async def test_sharepoint_upload_encodes_name_path_segment(monkeypatch, name, encoded):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "id": "sp-item-1",
                "name": name,
                "webUrl": "https://contoso.sharepoint.com/sites/s/doc",
            },
        )

    monkeypatch.setattr(store_module, "get_fresh_token", _fresh_token)
    _mock_http_client(monkeypatch, handler)
    result = await MatterFileStore()._try_store_sharepoint(
        db=None,
        tenant_id=str(uuid.uuid4()),
        filename=name,
        content=b"pdf",
        content_type="application/pdf",
        folder_id="folder-1",
        drive_id="drive-1",
    )

    assert result.error is None
    assert result.provider_item_id == "sp-item-1"
    assert len(sent) == 1
    assert sent[0].method == "PUT"
    query = _assert_graph_name_path(
        sent[0], "/v1.0/drives/drive-1/items/folder-1:/", encoded, ":/content", name
    )
    assert query == "@microsoft.graph.conflictBehavior=rename"
