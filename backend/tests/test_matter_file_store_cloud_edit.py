"""Provider contracts behind "Open in Word / Google Docs" and "Upload revised version".

The store must hand back fresh, host-checked open links (including the WebDAV
address Word desktop needs), and must overwrite a document *in place* so the
copy someone has open in Word stays the one LawHand points to — never
silently over a newer Word edit.
"""

import json
from types import SimpleNamespace

import httpx
import pytest

import app.services.matter_file_store as store_module
from app.services.matter_file_store import (
    MatterFileAccessError,
    MatterFileIntegrityError,
    MatterFileMetadataError,
    MatterFileNotFound,
    MatterFileStore,
)
from app.services.provider_http import ProviderAuthError, ProviderError

TENANT = "tenant-a"


def _mock_http_client(monkeypatch, handler):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(store_module.httpx, "AsyncClient", client)


def _token(monkeypatch, value="token-1"):
    async def token(db, tenant_id, provider):
        return value

    monkeypatch.setattr(store_module, "_storage_token", token)


def _doc(backend, **extra):
    base = dict(
        tenant_id=TENANT,
        _storage_backend=backend,
        storage_backend=backend,
        storage_provider="google" if backend == "google_drive" else "microsoft",
        storage_path="https://attacker.invalid/display-only",
        provider_object_id="item-1",
        provider_drive_id="drive-1" if backend != "google_drive" else None,
        provider_parent_id="parent-1",
        file_size=10,
    )
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_sharepoint_metadata_returns_web_and_desktop_links_and_markers(monkeypatch):
    _token(monkeypatch)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "item-1",
                "webUrl": "https://firm.sharepoint.com/:w:/r/sites/m/Doc.aspx?sourcedoc=x",
                "webDavUrl": "https://firm.sharepoint.com/sites/m/Shared%20Documents/a.docx",
                "eTag": '"{E},3"',
                "cTag": '"c:{E},3"',
                "lastModifiedDateTime": "2026-09-25T10:00:00Z",
                "file": {"hashes": {"quickXorHash": "qx"}},
            },
        )

    _mock_http_client(monkeypatch, handler)
    meta = await MatterFileStore().get_matter_file_metadata(
        db=object(), tenant_id=TENANT, document=_doc("sharepoint")
    )
    assert meta.web_url.startswith("https://firm.sharepoint.com/")
    assert meta.desktop_url == "https://firm.sharepoint.com/sites/m/Shared%20Documents/a.docx"
    assert meta.etag == '"{E},3"'
    assert meta.version_id == '"c:{E},3"'
    assert meta.checksum == "qx"
    assert "/drives/drive-1/items/item-1" in str(seen[0].url)
    assert "webDavUrl" in str(seen[0].url)
    assert seen[0].headers["Authorization"] == "Bearer token-1"


@pytest.mark.asyncio
async def test_metadata_drops_an_off_domain_webdav_address(monkeypatch):
    _token(monkeypatch)
    _mock_http_client(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "webUrl": "https://onedrive.live.com/edit?id=1",
                "webDavUrl": "https://d.docs.live.net/abc/a.docx",
            },
        ),
    )
    meta = await MatterFileStore().get_matter_file_metadata(
        db=object(), tenant_id=TENANT, document=_doc("onedrive", provider_drive_id=None)
    )
    assert meta.web_url == "https://onedrive.live.com/edit?id=1"
    assert meta.desktop_url is None


@pytest.mark.asyncio
async def test_google_metadata_uses_web_view_link_and_version(monkeypatch):
    _token(monkeypatch)
    _mock_http_client(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "webViewLink": "https://docs.google.com/document/d/item-1/edit",
                "version": "42",
                "sha256Checksum": "abc",
                "modifiedTime": "2026-09-25T10:00:00Z",
            },
        ),
    )
    meta = await MatterFileStore().get_matter_file_metadata(
        db=object(), tenant_id=TENANT, document=_doc("google_drive")
    )
    assert meta.web_url == "https://docs.google.com/document/d/item-1/edit"
    assert meta.desktop_url is None
    assert meta.version_id == "42"
    assert meta.checksum == "abc"


@pytest.mark.asyncio
async def test_metadata_reports_a_trashed_file_as_missing(monkeypatch):
    _token(monkeypatch)
    _mock_http_client(
        monkeypatch, lambda request: httpx.Response(200, json={"trashed": True})
    )
    with pytest.raises(MatterFileNotFound):
        await MatterFileStore().get_matter_file_metadata(
            db=object(), tenant_id=TENANT, document=_doc("google_drive")
        )


@pytest.mark.asyncio
async def test_metadata_refuses_foreign_tenant_local_and_unbound_documents(monkeypatch):
    store = MatterFileStore()
    with pytest.raises(MatterFileAccessError):
        await store.get_matter_file_metadata(
            db=object(), tenant_id="other", document=_doc("onedrive")
        )
    with pytest.raises(MatterFileMetadataError):
        await store.get_matter_file_metadata(
            db=object(), tenant_id=TENANT, document=_doc("local", storage_provider="local")
        )
    with pytest.raises(MatterFileMetadataError):
        await store.get_matter_file_metadata(
            db=object(), tenant_id=TENANT, document=_doc("onedrive", provider_object_id="")
        )
    with pytest.raises(MatterFileMetadataError):
        await store.get_matter_file_metadata(
            db=object(), tenant_id=TENANT, document=_doc("sharepoint", provider_drive_id=None)
        )


@pytest.mark.asyncio
async def test_metadata_requires_credentials(monkeypatch):
    _token(monkeypatch, value=None)
    with pytest.raises(ProviderAuthError):
        await MatterFileStore().get_matter_file_metadata(
            db=object(), tenant_id=TENANT, document=_doc("onedrive")
        )


@pytest.mark.asyncio
async def test_graph_replace_keeps_the_item_and_sends_if_match(monkeypatch):
    _token(monkeypatch)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "item-1",
                "webUrl": "https://firm.sharepoint.com/a.docx",
                "eTag": '"{E},4"',
                "cTag": '"c:{E},4"',
                "file": {"hashes": {"sha256Hash": "ABC"}},
            },
        )

    _mock_http_client(monkeypatch, handler)
    result = await MatterFileStore().replace_matter_file_content(
        db=object(),
        tenant_id=TENANT,
        document=_doc("sharepoint"),
        content=b"new-bytes",
        content_type="application/octet-stream",
        if_match='"{E},3"',
    )
    request = seen[0]
    assert request.method == "PUT"
    assert str(request.url).endswith("/drives/drive-1/items/item-1/content")
    assert request.headers["If-Match"] == '"{E},3"'
    assert request.content == b"new-bytes"
    assert result.provider_item_id == "item-1"
    assert result.provider_etag == '"{E},4"'
    assert result.drive_id == "drive-1"
    assert result.parent_id == "parent-1"


@pytest.mark.asyncio
async def test_graph_replace_raises_integrity_error_when_word_changed_it(monkeypatch):
    _token(monkeypatch)
    _mock_http_client(monkeypatch, lambda request: httpx.Response(412))
    with pytest.raises(MatterFileIntegrityError):
        await MatterFileStore().replace_matter_file_content(
            db=object(),
            tenant_id=TENANT,
            document=_doc("onedrive"),
            content=b"x",
            content_type="application/octet-stream",
            if_match='"old"',
        )


@pytest.mark.asyncio
async def test_graph_replace_of_a_large_file_uses_320k_multiple_chunks(monkeypatch):
    _token(monkeypatch)
    store = MatterFileStore()
    monkeypatch.setattr(store, "_CHUNK_THRESHOLD_ONEDRIVE", 10)
    monkeypatch.setattr(store, "_REPLACE_CHUNK_SIZE", 327680)
    content = b"a" * (327680 + 5)
    ranges = []

    def handler(request):
        if request.url.path.endswith("/createUploadSession"):
            assert json.loads(request.content)["item"]["@microsoft.graph.conflictBehavior"] == "replace"
            assert request.headers["If-Match"] == '"e"'
            return httpx.Response(200, json={"uploadUrl": "https://upload.example/session"})
        ranges.append(request.headers["Content-Range"])
        if len(ranges) == 1:
            return httpx.Response(202, json={})
        return httpx.Response(200, json={"id": "item-1", "webUrl": "https://firm.sharepoint.com/a"})

    _mock_http_client(monkeypatch, handler)
    result = await store.replace_matter_file_content(
        db=object(),
        tenant_id=TENANT,
        document=_doc("onedrive", provider_drive_id=None),
        content=content,
        content_type="application/octet-stream",
        if_match='"e"',
    )
    assert ranges == [f"bytes 0-327679/{len(content)}", f"bytes 327680-{len(content) - 1}/{len(content)}"]
    assert result.provider_item_id == "item-1"


@pytest.mark.asyncio
async def test_graph_replace_maps_missing_auth_and_failed_uploads(monkeypatch):
    _token(monkeypatch)
    store = MatterFileStore()
    current = {"status": 404}
    _mock_http_client(monkeypatch, lambda request: httpx.Response(current["status"]))
    for status, error in ((404, MatterFileNotFound), (401, ProviderAuthError), (500, ProviderError)):
        current["status"] = status
        with pytest.raises(error):
            await store.replace_matter_file_content(
                db=object(),
                tenant_id=TENANT,
                document=_doc("onedrive"),
                content=b"x",
                content_type="application/octet-stream",
            )


@pytest.mark.asyncio
async def test_google_replace_uses_a_resumable_update_of_the_same_file(monkeypatch):
    _token(monkeypatch)
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "PATCH":
            assert "/upload/drive/v3/files/item-1" in str(request.url)
            assert "uploadType=resumable" in str(request.url)
            assert request.headers["X-Upload-Content-Length"] == "9"
            return httpx.Response(200, headers={"Location": "https://upload.example/g"})
        assert request.method == "PUT"
        assert request.content == b"new-bytes"
        return httpx.Response(
            200,
            json={
                "id": "item-1",
                "webViewLink": "https://docs.google.com/document/d/item-1/edit",
                "version": "43",
                "sha256Checksum": "def",
            },
        )

    _mock_http_client(monkeypatch, handler)
    result = await MatterFileStore().replace_matter_file_content(
        db=object(),
        tenant_id=TENANT,
        document=_doc("google_drive"),
        content=b"new-bytes",
        content_type="application/octet-stream",
    )
    assert [r.method for r in seen] == ["PATCH", "PUT"]
    assert result.provider_item_id == "item-1"
    assert result.provider_version_id == "43"
    assert result.backend == "google_drive"


@pytest.mark.asyncio
async def test_google_replace_needs_a_session_location(monkeypatch):
    _token(monkeypatch)
    _mock_http_client(monkeypatch, lambda request: httpx.Response(200))
    with pytest.raises(ProviderError):
        await MatterFileStore().replace_matter_file_content(
            db=object(),
            tenant_id=TENANT,
            document=_doc("google_drive"),
            content=b"x",
            content_type="application/octet-stream",
        )


@pytest.mark.asyncio
async def test_local_replace_is_atomic_and_tenant_scoped(tmp_path, monkeypatch):
    tenant_root = tmp_path / TENANT
    tenant_root.mkdir()
    path = tenant_root / "a.docx"
    path.write_bytes(b"old")
    monkeypatch.setattr(store_module.settings, "UPLOAD_DIR", str(tmp_path))
    document = _doc("local", storage_provider="local", storage_path=str(path))
    result = await MatterFileStore().replace_matter_file_content(
        db=object(),
        tenant_id=TENANT,
        document=document,
        content=b"new",
        content_type="application/octet-stream",
    )
    assert path.read_bytes() == b"new"
    assert result.backend == "local"
    assert list(tenant_root.iterdir()) == [path]

    outside = tmp_path / "elsewhere.docx"
    outside.write_bytes(b"x")
    with pytest.raises(MatterFileAccessError):
        await MatterFileStore().replace_matter_file_content(
            db=object(),
            tenant_id=TENANT,
            document=_doc("local", storage_provider="local", storage_path=str(outside)),
            content=b"new",
            content_type="application/octet-stream",
        )


@pytest.mark.asyncio
async def test_replace_refuses_another_tenants_document():
    with pytest.raises(MatterFileAccessError):
        await MatterFileStore().replace_matter_file_content(
            db=object(),
            tenant_id="other",
            document=_doc("onedrive"),
            content=b"x",
            content_type="application/octet-stream",
        )


def test_template_saves_keep_the_provider_change_markers():
    from datetime import datetime, timezone

    from app.routers import document_templates
    from app.services.matter_file_store import StorageResult

    fields = document_templates._storage_document_fields(
        StorageResult(
            provider="microsoft",
            backend="sharepoint",
            provider_item_id="item-1",
            provider_etag='"{E},1"',
            provider_version_id='"c:{E},1"',
            provider_checksum="qx",
            provider_modified_at="2026-09-25T10:00:00Z",
        )
    )
    assert fields["provider_etag"] == '"{E},1"'
    assert fields["provider_version_id"] == '"c:{E},1"'
    assert fields["provider_checksum"] == "qx"
    assert fields["provider_modified_at"] == datetime(2026, 9, 25, 10, tzinfo=timezone.utc)

    moment = datetime(2026, 9, 25, tzinfo=timezone.utc)
    assert document_templates._provider_time(moment) is moment
    assert document_templates._provider_time("not a time") is None
    assert document_templates._provider_time(None) is None
