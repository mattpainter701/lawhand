"""The onboarding wizard sets document storage up visibly, in its own step.

``initialize_cloud_root_folder`` used to run silently inside ``/complete``;
a firm never chose a provider or saw where its documents would live. These
tests pin the new ``/storage`` step and the ``/complete`` guard behind it,
without a database: the router's loaders are monkeypatched with fakes.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import onboarding

TENANT_ID = "12345678-1234-1234-1234-123456789abc"
GOOGLE_ROOT = {"id": "root-google", "folder_name": "claritylegal-records", "url": "https://drive"}


class _Db:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


def _tenant(**overrides):
    base = dict(
        id=TENANT_ID,
        onboarding_completed=False,
        onboarding_step=onboarding.STEP_STORAGE,
        cloud_root_folder=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _wire(monkeypatch, tenant, *, settings=None, connected=("google",)):
    admin = SimpleNamespace(tenant_id=TENANT_ID, id="admin-1")
    settings_record = settings or SimpleNamespace(primary_cloud_provider=None)
    calls = {"init": [], "guard": []}

    async def require_admin(_request, _db):
        return admin

    async def current_user(_request, _db):
        return admin

    async def no_context(*_args):
        return None

    async def integrations(*_args):
        return {
            provider: SimpleNamespace(connected=provider in connected)
            for provider in ("microsoft", "google")
        }

    async def load_tenant(_db, _tenant_id):
        return tenant

    async def load_settings(_db, _tenant_id):
        return settings_record

    async def agreements(*_args):
        return {"blocking": False}

    async def guard(_db, _tenant_id, provider):
        calls["guard"].append(provider)

    async def init_root(_db, _tenant_id, *, existing_root=None):
        calls["init"].append(dict(existing_root or {}))
        return {"google_drive": GOOGLE_ROOT}

    monkeypatch.setattr(onboarding, "require_admin", require_admin)
    monkeypatch.setattr(onboarding, "get_current_user", current_user)
    monkeypatch.setattr(onboarding, "set_tenant_context", no_context)
    monkeypatch.setattr(onboarding, "_get_integration_status", integrations)
    monkeypatch.setattr(onboarding, "_load_tenant", load_tenant)
    monkeypatch.setattr(onboarding, "_load_or_create_settings", load_settings)
    monkeypatch.setattr(onboarding, "agreement_status", agreements)
    monkeypatch.setattr(
        "app.services.storage_migration.assert_provider_change_allowed", guard
    )
    monkeypatch.setattr(
        "app.services.cloud_init.initialize_cloud_root_folder", init_root
    )
    return settings_record, calls


def _request(provider):
    return onboarding.OnboardingStorageRequest(provider=provider)


@pytest.mark.asyncio
async def test_storage_step_rejects_unknown_provider(monkeypatch):
    _wire(monkeypatch, _tenant())

    with pytest.raises(HTTPException) as exc:
        await onboarding.confirm_onboarding_storage(_request("dropbox"), None, _Db())

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_storage_step_requires_the_matching_credential(monkeypatch):
    _wire(monkeypatch, _tenant(), connected=("google",))

    with pytest.raises(HTTPException) as exc:
        await onboarding.confirm_onboarding_storage(_request("onedrive"), None, _Db())

    assert exc.value.status_code == 400
    assert "Microsoft 365" in exc.value.detail


@pytest.mark.asyncio
async def test_storage_step_creates_root_and_records_the_choice(monkeypatch):
    tenant = _tenant()
    settings_record, calls = _wire(monkeypatch, tenant)
    db = _Db()

    response = await onboarding.confirm_onboarding_storage(
        _request("google_drive"), None, db
    )

    assert response.status == "ready"
    assert response.created is True
    assert response.root == GOOGLE_ROOT
    assert tenant.cloud_root_folder == {"google_drive": GOOGLE_ROOT}
    assert settings_record.primary_cloud_provider == "google_drive"
    assert calls["guard"] == ["google_drive"]
    assert calls["init"] == [{}]
    assert tenant.onboarding_step == onboarding.STEP_SYNC
    assert db.commits == 1


@pytest.mark.asyncio
async def test_storage_step_keeps_an_existing_root_instead_of_recreating(monkeypatch):
    existing = {"google_drive": {"id": "keep-me", "folder_name": "records"}}
    tenant = _tenant(cloud_root_folder=dict(existing), onboarding_step=onboarding.STEP_REVIEW)
    settings_record = SimpleNamespace(primary_cloud_provider="google_drive")
    _, calls = _wire(monkeypatch, tenant, settings=settings_record)

    response = await onboarding.confirm_onboarding_storage(
        _request("google_drive"), None, _Db()
    )

    assert response.status == "ready"
    assert response.created is False
    assert response.root == existing["google_drive"]
    assert tenant.cloud_root_folder == existing
    assert calls["init"] == []
    assert calls["guard"] == []  # provider unchanged: no guard, no repoint
    assert tenant.onboarding_step == onboarding.STEP_REVIEW  # never moves backwards


@pytest.mark.asyncio
async def test_storage_step_reports_failure_without_marking_ready(monkeypatch):
    tenant = _tenant()
    _wire(monkeypatch, tenant)

    async def init_nothing(_db, _tenant_id, *, existing_root=None):
        return {}

    monkeypatch.setattr(
        "app.services.cloud_init.initialize_cloud_root_folder", init_nothing
    )

    response = await onboarding.confirm_onboarding_storage(
        _request("google_drive"), None, _Db()
    )

    assert response.status == "failed"
    assert response.root is None
    assert "Google Drive" in response.error
    assert tenant.cloud_root_folder is None
    assert tenant.onboarding_step == onboarding.STEP_STORAGE


@pytest.mark.asyncio
async def test_storage_step_refuses_to_rebind_a_malformed_root(monkeypatch):
    tenant = _tenant(cloud_root_folder={"google_drive": {"folder_name": "no id"}})
    _, calls = _wire(monkeypatch, tenant)

    response = await onboarding.confirm_onboarding_storage(
        _request("google_drive"), None, _Db()
    )

    assert response.status == "repair_needed"
    assert response.root_repair_needed == ["google_drive"]
    assert calls["init"] == []


@pytest.mark.asyncio
async def test_storage_step_surfaces_a_blocked_provider_change(monkeypatch):
    tenant = _tenant()
    settings_record = SimpleNamespace(primary_cloud_provider="onedrive")
    _wire(monkeypatch, tenant, settings=settings_record)

    async def blocked(_db, _tenant_id, _provider):
        raise ValueError("Complete or abandon the active storage migration first")

    monkeypatch.setattr(
        "app.services.storage_migration.assert_provider_change_allowed", blocked
    )

    with pytest.raises(HTTPException) as exc:
        await onboarding.confirm_onboarding_storage(_request("google_drive"), None, _Db())

    assert exc.value.status_code == 409
    assert settings_record.primary_cloud_provider == "onedrive"


@pytest.mark.asyncio
async def test_complete_requires_a_confirmed_storage_root(monkeypatch):
    tenant = _tenant(onboarding_step=onboarding.STEP_REVIEW)
    _wire(monkeypatch, tenant)

    class _TenantDb(_Db):
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: tenant)

    with pytest.raises(HTTPException) as exc:
        await onboarding.complete_onboarding(None, _TenantDb())

    assert exc.value.status_code == 400
    assert "stored" in exc.value.detail
    assert tenant.onboarding_completed is False


@pytest.mark.asyncio
async def test_complete_records_first_run_and_finishes(monkeypatch):
    tenant = _tenant(
        onboarding_step=onboarding.STEP_REVIEW,
        cloud_root_folder={"google_drive": GOOGLE_ROOT},
    )
    _wire(monkeypatch, tenant)

    class _TenantDb(_Db):
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: tenant)

    db = _TenantDb()
    response = await onboarding.complete_onboarding(None, db)

    assert response.status == "ok"
    assert response.cloud_root == {"google_drive": GOOGLE_ROOT}
    assert tenant.onboarding_completed is True
    assert tenant.onboarding_step == onboarding.STEP_COMPLETE
    assert [item.action for item in db.added] == ["onboarding_complete"]


def test_status_helpers_read_only_usable_bindings():
    assert onboarding._has_any_root(None) is False
    assert onboarding._has_any_root({"google_drive": {"folder_name": "x"}}) is False
    assert onboarding._has_any_root({"onedrive": {"id": " "}}) is False
    assert onboarding._has_any_root({"onedrive": {"id": "abc"}}) is True
    assert onboarding._root_binding({"sharepoint": {"id": "s1"}}, "sharepoint") == {"id": "s1"}
