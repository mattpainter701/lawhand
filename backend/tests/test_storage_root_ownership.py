"""Ownership classification and Google service-account auth.

These cover the turnover guarantee: a root is only "durable" when it is
organisation-owned, and the Google Shared Drive path mints its own token
instead of borrowing a departing admin's.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import cloud_init, google_service_account, storage_root_ownership

# Patching ``<module>.httpx.AsyncClient`` mutates the shared httpx module, so
# capture the real class before the monkeypatch to avoid recursive calls.
RealAsyncClient = httpx.AsyncClient

_ORG_ROOT = {
    "google_drive": {
        "id": "root-1",
        "folder_name": "lawhand-records",
        "drive_id": "shared-1",
        "owner_type": "org_shared_drive",
    }
}


def _mock_client(handler):
    return lambda **kwargs: RealAsyncClient(
        transport=httpx.MockTransport(handler), **kwargs
    )


# ── classification ───────────────────────────────────────────────────────────


def test_legacy_onedrive_root_is_at_risk():
    result = storage_root_ownership.classify_cloud_root(
        {"onedrive": {"id": "od-root", "folder_name": "lawhand-records"}}
    )
    assert result["status"] == storage_root_ownership.AT_RISK
    assert result["org_owned"] is False
    assert result["providers"]["onedrive"]["owner_type"] == "user_personal_drive"
    assert result["providers"]["onedrive"]["label"] == "Microsoft OneDrive"


def test_sharepoint_site_library_is_org_owned_even_without_owner_type():
    result = storage_root_ownership.classify_cloud_root(
        {
            "sharepoint": {
                "id": "sp-root",
                "drive_id": "drive-1",
                "site_id": "site-1",
            }
        }
    )
    assert result["status"] == storage_root_ownership.DURABLE
    assert result["org_owned"] is True
    assert result["providers"]["sharepoint"]["owner_type"] == "org_site_library"


def test_google_shared_drive_binding_is_org_owned():
    result = storage_root_ownership.classify_cloud_root(
        {
            "google_drive": {
                "id": "gd-root",
                "drive_id": "shared-drive-1",
                "owner_type": "org_shared_drive",
            }
        }
    )
    assert result["status"] == storage_root_ownership.DURABLE
    assert result["org_owned"] is True


def test_google_my_drive_and_mixed_roots_report_at_risk():
    result = storage_root_ownership.classify_cloud_root(
        {
            "google_drive": {"id": "gd-root", "folder_name": "lawhand-records"},
            "sharepoint": {"id": "sp-root", "drive_id": "d", "site_id": "s"},
        }
    )
    assert result["status"] == storage_root_ownership.AT_RISK
    assert result["at_risk_providers"] == ["Google Drive"]


def test_empty_and_malformed_roots_are_unbound():
    assert (
        storage_root_ownership.classify_cloud_root(None)["status"]
        == storage_root_ownership.UNBOUND
    )
    result = storage_root_ownership.classify_cloud_root({"onedrive": "not-a-dict"})
    assert result["status"] == storage_root_ownership.UNBOUND
    assert result["providers"]["onedrive"]["status"] == storage_root_ownership.UNBOUND


# ── google service account ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_token_cache():
    google_service_account._clear_cache()
    google_service_account._clear_drive_access_cache()
    yield
    google_service_account._clear_cache()
    google_service_account._clear_drive_access_cache()


def _configure_service_account(monkeypatch):
    monkeypatch.setattr(
        google_service_account,
        "load_service_account",
        lambda: {"client_email": "svc@proj.iam", "private_key": "private"},
    )
    monkeypatch.setattr(
        google_service_account.jwt, "encode", lambda payload, key, algorithm=None: "jwt"
    )


@pytest.mark.asyncio
async def test_get_access_token_mints_and_caches(monkeypatch):
    _configure_service_account(monkeypatch)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, json={"access_token": "sa-token", "expires_in": 3600}
        )

    monkeypatch.setattr(
        google_service_account.httpx, "AsyncClient", _mock_client(handler)
    )

    first = await google_service_account.get_access_token(["scope-a"])
    second = await google_service_account.get_access_token(["scope-a"])

    assert first == second == "sa-token"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_get_access_token_includes_delegation_subject(monkeypatch):
    _configure_service_account(monkeypatch)
    payloads: list[dict] = []

    def fake_encode(payload, key, algorithm=None):
        payloads.append(payload)
        return "jwt"

    monkeypatch.setattr(google_service_account.jwt, "encode", fake_encode)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"access_token": "sa-token", "expires_in": 3600}
        )

    monkeypatch.setattr(
        google_service_account.httpx, "AsyncClient", _mock_client(handler)
    )

    await google_service_account.get_access_token(["scope-a"], subject="admin@firm.com")

    assert payloads[0]["sub"] == "admin@firm.com"
    assert payloads[0]["scope"] == "scope-a"


@pytest.mark.asyncio
async def test_get_access_token_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(google_service_account, "load_service_account", lambda: None)
    assert await google_service_account.get_access_token(["scope-a"]) is None


@pytest.mark.asyncio
async def test_get_access_token_returns_none_on_rejection(monkeypatch):
    _configure_service_account(monkeypatch)
    monkeypatch.setattr(
        google_service_account.httpx,
        "AsyncClient",
        _mock_client(
            lambda request: httpx.Response(400, json={"error": "invalid_grant"})
        ),
    )

    assert await google_service_account.get_access_token(["scope-a"]) is None


# ── cloud_init org-owned root ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_org_shared_drive_preferred_over_personal_my_drive(monkeypatch):
    async def fake_token(*_args, **_kwargs):
        return None

    monkeypatch.setattr(cloud_init, "get_fresh_token", fake_token)
    monkeypatch.setattr(
        cloud_init,
        "_google_org_shared_drive_id",
        AsyncMock(return_value="tenant-drive-9"),
    )
    org_root = AsyncMock(
        return_value={
            "id": "org-root",
            "folder_name": "lawhand-records",
            "url": "https://drive/org-root",
            "drive_id": "tenant-drive-9",
            "owner_type": "org_shared_drive",
        }
    )
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_org_root", org_root)
    personal = AsyncMock(return_value="personal-root")
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_folder", personal)

    root = await cloud_init.initialize_cloud_root_folder(None, "tenant-1")

    org_root.assert_awaited_once_with(
        "tenant-drive-9", cloud_init.ROOT_FOLDER_NAME, fallback_token=None
    )
    personal.assert_not_awaited()
    assert root["google_drive"]["owner_type"] == "org_shared_drive"


@pytest.mark.asyncio
async def test_workspace_connect_auto_provisions_a_per_tenant_shared_drive(monkeypatch):
    async def fake_token(*_args, **_kwargs):
        return "g-token"

    monkeypatch.setattr(cloud_init, "get_fresh_token", fake_token)
    monkeypatch.setattr(
        cloud_init, "_google_org_shared_drive_id", AsyncMock(return_value="")
    )
    monkeypatch.setattr(cloud_init.settings, "GOOGLE_AUTO_SHARED_DRIVE", True)
    monkeypatch.setattr(
        cloud_init, "_google_account_type", AsyncMock(return_value="workspace")
    )
    provision = AsyncMock(return_value="auto-drive-1")
    monkeypatch.setattr(cloud_init, "_provision_org_shared_drive", provision)
    org_root = AsyncMock(
        return_value={
            "id": "org-root",
            "folder_name": "lawhand-records",
            "url": "https://drive/org-root",
            "drive_id": "auto-drive-1",
            "owner_type": "org_shared_drive",
        }
    )
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_org_root", org_root)
    personal = AsyncMock(return_value="personal-root")
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_folder", personal)

    root = await cloud_init.initialize_cloud_root_folder(None, "tenant-1")

    provision.assert_awaited_once()
    org_root.assert_awaited_once_with(
        "auto-drive-1", cloud_init.ROOT_FOLDER_NAME, fallback_token="g-token"
    )
    personal.assert_not_awaited()
    assert root["google_drive"]["owner_type"] == "org_shared_drive"


@pytest.mark.asyncio
async def test_personal_google_never_auto_provisions_a_shared_drive(monkeypatch):
    async def fake_token(*_args, **_kwargs):
        return "g-token"

    monkeypatch.setattr(cloud_init, "get_fresh_token", fake_token)
    monkeypatch.setattr(
        cloud_init, "_google_org_shared_drive_id", AsyncMock(return_value="")
    )
    monkeypatch.setattr(cloud_init.settings, "GOOGLE_AUTO_SHARED_DRIVE", True)
    monkeypatch.setattr(
        cloud_init, "_google_account_type", AsyncMock(return_value="personal")
    )
    monkeypatch.setattr(
        cloud_init,
        "_get_gdrive_folder_metadata",
        AsyncMock(
            return_value={
                "id": "personal-root",
                "name": "lawhand-records",
                "webViewLink": "https://drive/personal-root",
                "mimeType": "application/vnd.google-apps.folder",
            }
        ),
    )
    provision = AsyncMock(return_value="auto-drive-1")
    monkeypatch.setattr(cloud_init, "_provision_org_shared_drive", provision)
    personal = AsyncMock(return_value="personal-root")
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_folder", personal)

    root = await cloud_init.initialize_cloud_root_folder(None, "tenant-1")

    provision.assert_not_awaited()
    personal.assert_awaited_once()
    assert root["google_drive"]["id"] == "personal-root"


@pytest.mark.asyncio
async def test_org_root_creation_uses_the_official_files_create_shape(monkeypatch):
    monkeypatch.setattr(
        google_service_account,
        "get_access_token",
        AsyncMock(return_value="sa-token"),
    )
    monkeypatch.setattr(
        cloud_init, "_list_shared_drive_child_folders", AsyncMock(return_value=[])
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "folder-1",
                "name": "lawhand-records",
                "driveId": "shared-drive-9",
                "webViewLink": "https://drive/folder-1",
            },
        )

    monkeypatch.setattr(cloud_init.httpx, "AsyncClient", _mock_client(handler))

    binding = await cloud_init._ensure_gdrive_org_root(
        "shared-drive-9", "lawhand-records"
    )

    assert binding["owner_type"] == "org_shared_drive"
    assert binding["drive_id"] == "shared-drive-9"
    assert binding["id"] == "folder-1"
    # files.create selects the Shared Drive through parents, not a driveId
    # query parameter, which Drive v3 rejects.
    assert "driveId=" not in str(requests[0].url)
    assert "supportsAllDrives=true" in str(requests[0].url)
    assert b'"parents":["shared-drive-9"]' in requests[0].content


@pytest.mark.asyncio
async def test_org_root_retries_with_delegated_token_when_service_account_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        google_service_account,
        "get_access_token",
        AsyncMock(return_value="sa-token"),
    )
    binding = {"id": "folder-1", "owner_type": "org_shared_drive"}
    attempts = AsyncMock(side_effect=[RuntimeError("403 access denied"), binding])
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_org_root_with_token", attempts)

    result = await cloud_init._ensure_gdrive_org_root(
        "shared-drive-9", "lawhand-records", fallback_token="delegated-token"
    )

    assert result == binding
    assert attempts.await_count == 2
    assert attempts.await_args_list[0].args == (
        "sa-token",
        "shared-drive-9",
        "lawhand-records",
    )
    assert attempts.await_args_list[1].args == (
        "delegated-token",
        "shared-drive-9",
        "lawhand-records",
    )


@pytest.mark.asyncio
async def test_org_root_requires_a_token(monkeypatch):
    monkeypatch.setattr(
        google_service_account, "get_access_token", AsyncMock(return_value=None)
    )

    with pytest.raises(RuntimeError, match="no service account or delegated token"):
        await cloud_init._ensure_gdrive_org_root("shared-drive-9", "lawhand-records")


@pytest.mark.asyncio
async def test_provision_org_shared_drive_registers_lawhand_service_account(
    monkeypatch,
):
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/drives"):
            return httpx.Response(200, json={"id": "drive-1"})
        return httpx.Response(200, json={"id": "perm-1"})

    monkeypatch.setattr(cloud_init.httpx, "AsyncClient", _mock_client(handler))
    monkeypatch.setattr(
        google_service_account, "service_account_email", lambda: "svc@lawhand.iam"
    )

    drive_id = await cloud_init._provision_org_shared_drive(None, "tenant-1", "g-token")

    assert drive_id == "drive-1"
    assert ("POST", "/drive/v3/drives") in calls
    # Shared Drive membership is created through the permissions resource with
    # the drive id as the file id.
    assert ("POST", "/drive/v3/files/drive-1/permissions") in calls
    assert not any("/drives/drive-1/permissions" in path for _, path in calls)


@pytest.mark.asyncio
async def test_provision_org_shared_drive_rolls_back_when_membership_fails(monkeypatch):
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path.endswith("/drives"):
            return httpx.Response(200, json={"id": "drive-1"})
        return httpx.Response(403, json={"error": "external sharing disabled"})

    monkeypatch.setattr(cloud_init.httpx, "AsyncClient", _mock_client(handler))
    monkeypatch.setattr(
        google_service_account, "service_account_email", lambda: "svc@lawhand.iam"
    )

    with pytest.raises(RuntimeError, match="Failed to add"):
        await cloud_init._provision_org_shared_drive(None, "tenant-1", "g-token")

    assert ("DELETE", "/drive/v3/drives/drive-1") in calls


@pytest.mark.asyncio
async def test_provision_org_shared_drive_requires_a_service_account(monkeypatch):
    monkeypatch.setattr(google_service_account, "service_account_email", lambda: None)

    def unexpected_client(**_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("no provider call without a service account")

    monkeypatch.setattr(cloud_init.httpx, "AsyncClient", unexpected_client)

    with pytest.raises(RuntimeError, match="service account"):
        await cloud_init._provision_org_shared_drive(None, "tenant-1", "g-token")


@pytest.mark.asyncio
async def test_create_shared_drive_raises_without_an_id(monkeypatch):
    monkeypatch.setattr(
        cloud_init.httpx,
        "AsyncClient",
        _mock_client(lambda request: httpx.Response(403, text="forbidden")),
    )

    with pytest.raises(RuntimeError, match="Failed to create Google Shared Drive"):
        await cloud_init._create_gdrive_shared_drive("g-token", "LawHand Firm Records")


@pytest.mark.asyncio
async def test_google_account_type_reads_the_active_credential(monkeypatch):
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: "workspace")
    assert (
        await cloud_init._google_account_type(
            db, "11111111-1111-1111-1111-111111111111"
        )
        == "workspace"
    )
    assert await cloud_init._google_account_type(None, "tenant-1") is None


@pytest.mark.asyncio
async def test_org_shared_drive_id_is_tenant_scoped(monkeypatch):
    tenant_id = "11111111-1111-1111-1111-111111111111"
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: SimpleNamespace(
            custom_config={"google_shared_drive_id": "tenant-drive"}
        )
    )
    assert await cloud_init._google_org_shared_drive_id(db, tenant_id) == "tenant-drive"

    empty = AsyncMock()
    empty.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: SimpleNamespace(custom_config={})
    )
    # No deployment-global default: absent config must not resolve to another
    # tenant's drive.
    assert await cloud_init._google_org_shared_drive_id(empty, tenant_id) == ""

    assert await cloud_init._google_org_shared_drive_id(None, tenant_id) == ""


# -- runtime access identity (staff-turnover guarantee) ----------------------


def test_sharepoint_org_root_reports_access_at_risk(monkeypatch):
    result = storage_root_ownership.classify_cloud_root(
        {"sharepoint": {"id": "sp", "drive_id": "d", "site_id": "s"}}
    )
    assert result["org_owned"] is True
    assert result["access_at_risk"] == ["Microsoft SharePoint"]


def test_google_org_root_access_is_durable_with_a_service_account(monkeypatch):
    monkeypatch.setattr(
        storage_root_ownership.google_service_account, "is_configured", lambda: True
    )
    result = storage_root_ownership.classify_cloud_root(
        {
            "google_drive": {
                "id": "gd",
                "drive_id": "shared-1",
                "owner_type": "org_shared_drive",
            }
        }
    )
    assert result["access_at_risk"] == []
    assert result["providers"]["google_drive"]["access_org_owned"] is True


@pytest.mark.asyncio
async def test_prefer_service_account_uses_the_service_account_for_an_org_drive(
    monkeypatch,
):
    monkeypatch.setattr(google_service_account, "is_configured", lambda: True)
    monkeypatch.setattr(
        google_service_account, "get_access_token", AsyncMock(return_value="sa-token")
    )
    monkeypatch.setattr(
        google_service_account,
        "_service_account_can_access_drive",
        AsyncMock(return_value=True),
    )

    assert (
        await google_service_account.prefer_service_account(
            object(), "tenant", "delegated", cloud_root=_ORG_ROOT
        )
        == "sa-token"
    )


@pytest.mark.asyncio
async def test_prefer_service_account_keeps_delegated_token_off_org(monkeypatch):
    monkeypatch.setattr(google_service_account, "is_configured", lambda: True)
    mint = AsyncMock(return_value="sa-token")
    monkeypatch.setattr(google_service_account, "get_access_token", mint)

    assert (
        await google_service_account.prefer_service_account(
            object(), "tenant", "delegated", cloud_root={}
        )
        == "delegated"
    )
    mint.assert_not_awaited()


@pytest.mark.asyncio
async def test_prefer_service_account_falls_back_when_minting_fails(monkeypatch):
    monkeypatch.setattr(google_service_account, "is_configured", lambda: True)
    monkeypatch.setattr(
        google_service_account, "get_access_token", AsyncMock(return_value=None)
    )

    assert (
        await google_service_account.prefer_service_account(
            object(), "tenant", "delegated", cloud_root=_ORG_ROOT
        )
        == "delegated"
    )


@pytest.mark.asyncio
async def test_prefer_service_account_falls_back_when_it_cannot_reach_the_drive(
    monkeypatch,
):
    """A minted service-account token that cannot access the drive must not be used."""
    monkeypatch.setattr(google_service_account, "is_configured", lambda: True)
    monkeypatch.setattr(
        google_service_account, "get_access_token", AsyncMock(return_value="sa-token")
    )
    monkeypatch.setattr(
        google_service_account,
        "_service_account_can_access_drive",
        AsyncMock(return_value=False),
    )

    assert (
        await google_service_account.prefer_service_account(
            object(), "tenant", "delegated", cloud_root=_ORG_ROOT
        )
        == "delegated"
    )


@pytest.mark.asyncio
async def test_matter_provisioning_uses_service_account_when_delegated_is_gone(
    monkeypatch,
):
    """Acceptance: folder provisioning survives the delegated credential being lost."""
    monkeypatch.setattr(cloud_init, "get_fresh_token", AsyncMock(return_value=None))
    monkeypatch.setattr(google_service_account, "is_configured", lambda: True)
    monkeypatch.setattr(
        google_service_account, "get_access_token", AsyncMock(return_value="sa-token")
    )
    monkeypatch.setattr(
        google_service_account,
        "_service_account_can_access_drive",
        AsyncMock(return_value=True),
    )

    tokens = await cloud_init.get_matter_provisioning_tokens(
        object(), "tenant-1", _ORG_ROOT
    )

    assert tokens["google"] == "sa-token"


@pytest.mark.asyncio
async def test_org_root_creation_failure_falls_back_to_my_drive(monkeypatch):
    """Acceptance: a failed Shared Drive root must not strand onboarding."""

    async def fake_token(*_args, **_kwargs):
        return "g-token"

    monkeypatch.setattr(cloud_init, "get_fresh_token", fake_token)
    monkeypatch.setattr(
        cloud_init, "_google_org_shared_drive_id", AsyncMock(return_value="drive-1")
    )
    monkeypatch.setattr(
        cloud_init,
        "_ensure_gdrive_org_root",
        AsyncMock(side_effect=RuntimeError("root create failed")),
    )
    ensure_personal = AsyncMock(return_value="my-drive-root")
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_folder", ensure_personal)
    monkeypatch.setattr(
        cloud_init,
        "_get_gdrive_folder_metadata",
        AsyncMock(
            return_value={
                "id": "my-drive-root",
                "name": "lawhand-records",
                "webViewLink": "https://drive/my-drive-root",
            }
        ),
    )

    root = await cloud_init.initialize_cloud_root_folder(None, "tenant-1")

    assert root["google_drive"]["id"] == "my-drive-root"
    ensure_personal.assert_awaited_once_with(
        "g-token", cloud_init.ROOT_FOLDER_NAME, "root"
    )


@pytest.mark.asyncio
async def test_storage_token_uses_service_account_for_google(monkeypatch):
    from app.services import matter_file_store

    monkeypatch.setattr(
        matter_file_store, "get_fresh_token", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        google_service_account,
        "prefer_service_account",
        AsyncMock(return_value="sa-token"),
    )

    assert (
        await matter_file_store._storage_token(object(), "tenant-1", "google")
        == "sa-token"
    )


@pytest.mark.asyncio
async def test_storage_token_leaves_microsoft_on_the_delegated_token(monkeypatch):
    from app.services import matter_file_store

    monkeypatch.setattr(
        matter_file_store, "get_fresh_token", AsyncMock(return_value="ms-token")
    )
    prefer = AsyncMock(return_value="should-not-be-used")
    monkeypatch.setattr(google_service_account, "prefer_service_account", prefer)

    assert (
        await matter_file_store._storage_token(object(), "tenant-1", "microsoft")
        == "ms-token"
    )
    prefer.assert_not_awaited()


@pytest.mark.asyncio
async def test_org_drive_provision_failure_falls_back_to_my_drive(monkeypatch):
    """Acceptance: a failed Shared Drive *creation* must not strand onboarding."""

    async def fake_token(*_args, **_kwargs):
        return "g-token"

    monkeypatch.setattr(cloud_init, "get_fresh_token", fake_token)
    monkeypatch.setattr(
        cloud_init, "_google_org_shared_drive_id", AsyncMock(return_value="")
    )
    monkeypatch.setattr(cloud_init.settings, "GOOGLE_AUTO_SHARED_DRIVE", True)
    monkeypatch.setattr(
        cloud_init, "_google_account_type", AsyncMock(return_value="workspace")
    )
    monkeypatch.setattr(
        cloud_init,
        "_provision_org_shared_drive",
        AsyncMock(side_effect=RuntimeError("drive create failed")),
    )
    ensure_personal = AsyncMock(return_value="my-drive-root")
    monkeypatch.setattr(cloud_init, "_ensure_gdrive_folder", ensure_personal)
    monkeypatch.setattr(
        cloud_init,
        "_get_gdrive_folder_metadata",
        AsyncMock(
            return_value={
                "id": "my-drive-root",
                "name": "lawhand-records",
                "webViewLink": "https://drive/my-drive-root",
            }
        ),
    )

    root = await cloud_init.initialize_cloud_root_folder(None, "tenant-1")

    assert root["google_drive"]["id"] == "my-drive-root"
    ensure_personal.assert_awaited_once_with(
        "g-token", cloud_init.ROOT_FOLDER_NAME, "root"
    )


@pytest.mark.asyncio
async def test_no_google_credential_leaves_no_root_without_raising(monkeypatch):
    """No delegated token and no service account: return cleanly, no root."""
    monkeypatch.setattr(cloud_init, "get_fresh_token", AsyncMock(return_value=None))
    monkeypatch.setattr(
        cloud_init, "_google_org_shared_drive_id", AsyncMock(return_value="")
    )
    monkeypatch.setattr(google_service_account, "is_configured", lambda: False)

    root = await cloud_init.initialize_cloud_root_folder(None, "tenant-1")

    assert "google_drive" not in root
