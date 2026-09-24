"""Database-free coverage for the wizard's step plumbing and loaders.

The storage-step tests monkeypatch the router's loaders so they can drive the
endpoint logic; these exercise the loaders themselves, the step-number guard,
and the two places outside the router that move a tenant between steps. They
use a sequenced fake session rather than a database so they stay in the
no-database CI job.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import integrations, onboarding, user_sync
from app.schemas.onboarding import IntegrationConnectionStatus

TENANT_ID = "12345678-1234-1234-1234-123456789abc"


def _result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


class _SeqDb:
    """Fake session returning queued execute()/scalar() results in order."""

    def __init__(self, results=(), scalars=()):
        self._results = list(results)
        self._scalars = list(scalars)
        self.added = []
        self.commits = 0

    async def execute(self, _statement):
        return self._results.pop(0)

    async def scalar(self, _statement):
        return self._scalars.pop(0)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


def _tenant(**overrides):
    base = dict(
        id=TENANT_ID,
        onboarding_completed=False,
        onboarding_step=onboarding.STEP_CONNECT,
        cloud_root_folder=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ── Loaders ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_tenant_returns_the_row():
    tenant = _tenant()

    assert await onboarding._load_tenant(_SeqDb([_result(tenant)]), TENANT_ID) is tenant


@pytest.mark.asyncio
async def test_load_tenant_raises_404_when_missing():
    with pytest.raises(HTTPException) as exc:
        await onboarding._load_tenant(_SeqDb([_result(None)]), TENANT_ID)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_load_or_create_settings_reuses_an_existing_row():
    existing = SimpleNamespace(primary_cloud_provider="onedrive")
    db = _SeqDb([_result(existing)])

    assert await onboarding._load_or_create_settings(db, TENANT_ID) is existing
    assert db.added == []


@pytest.mark.asyncio
async def test_load_or_create_settings_creates_one_when_absent():
    db = _SeqDb([_result(None)])

    record = await onboarding._load_or_create_settings(db, TENANT_ID)

    assert db.added == [record]
    assert record.primary_cloud_provider is None


@pytest.mark.asyncio
async def test_load_primary_provider_returns_the_saved_choice():
    db = _SeqDb([_result("google_drive")])

    assert await onboarding._load_primary_provider(db, TENANT_ID) == "google_drive"


# ── Step guard ───────────────────────────────────────────────────────────


def _wire_auth(monkeypatch, tenant=None):
    admin = SimpleNamespace(tenant_id=TENANT_ID, id="admin-1")

    async def current_user(_request, _db):
        return admin

    async def no_context(*_args):
        return None

    monkeypatch.setattr(onboarding, "get_current_user", current_user)
    monkeypatch.setattr(onboarding, "set_tenant_context", no_context)
    if tenant is not None:

        async def load_tenant(_db, _tenant_id):
            return tenant

        monkeypatch.setattr(onboarding, "_load_tenant", load_tenant)
    return admin


@pytest.mark.parametrize("step", [-1, onboarding.STEP_COMPLETE + 1])
@pytest.mark.asyncio
async def test_update_step_rejects_a_step_outside_the_wizard(monkeypatch, step):
    _wire_auth(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await onboarding.update_onboarding_step(step, None, _SeqDb())

    assert exc.value.status_code == 400
    assert "0-5" in exc.value.detail


@pytest.mark.asyncio
async def test_update_step_persists_the_new_storage_step(monkeypatch):
    tenant = _tenant()
    _wire_auth(monkeypatch, tenant)
    db = _SeqDb()

    response = await onboarding.update_onboarding_step(
        onboarding.STEP_STORAGE, None, db
    )

    assert response == {"status": "ok", "step": onboarding.STEP_STORAGE}
    assert tenant.onboarding_step == onboarding.STEP_STORAGE
    assert db.commits == 1


# ── Status ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_reports_the_provider_and_root_the_storage_step_saved(monkeypatch):
    root = {"google_drive": {"id": "root-1", "folder_name": "claritylegal-records"}}
    tenant = _tenant(onboarding_step=onboarding.STEP_SYNC, cloud_root_folder=root)
    _wire_auth(monkeypatch)

    async def load_tenant(_db, _tenant_id):
        return tenant

    async def integration_status(*_args):
        return {
            "microsoft": IntegrationConnectionStatus(connected=False),
            "google": IntegrationConnectionStatus(connected=True),
        }

    monkeypatch.setattr(onboarding, "_load_tenant", load_tenant)
    monkeypatch.setattr(onboarding, "_get_integration_status", integration_status)

    async def agreements(*_args):
        return {"configured": True, "blocking": False}
    monkeypatch.setattr(onboarding, "agreement_status", agreements)
    db = _SeqDb(results=[_result("google_drive"), _result(SimpleNamespace(custom_config={}))], scalars=[0, 3, 4])
    response = await onboarding.get_onboarding_status(None, db)

    assert response.primary_cloud_provider == "google_drive"
    assert response.cloud_root == root
    assert response.storage_ready is True
    assert response.synced_users == {"microsoft": 0, "google": 3}
    assert response.total_users == 4


@pytest.mark.asyncio
async def test_status_reports_storage_not_ready_for_a_malformed_root(monkeypatch):
    tenant = _tenant(cloud_root_folder={"google_drive": {"folder_name": "no id"}})
    _wire_auth(monkeypatch)

    async def load_tenant(_db, _tenant_id):
        return tenant

    async def integration_status(*_args):
        return {
            "microsoft": IntegrationConnectionStatus(connected=False),
            "google": IntegrationConnectionStatus(connected=True),
        }

    monkeypatch.setattr(onboarding, "_load_tenant", load_tenant)
    monkeypatch.setattr(onboarding, "_get_integration_status", integration_status)

    async def agreements(*_args):
        return {"configured": True, "blocking": False}
    monkeypatch.setattr(onboarding, "agreement_status", agreements)
    db = _SeqDb(results=[_result(None), _result(SimpleNamespace(custom_config={}))], scalars=[0, 0, 1])
    response = await onboarding.get_onboarding_status(None, db)

    assert response.storage_ready is False
    assert response.primary_cloud_provider is None


@pytest.mark.asyncio
async def test_status_reports_agreement_configuration(monkeypatch):
    tenant = _tenant()
    _wire_auth(monkeypatch, tenant)

    async def load_tenant(_db, _tenant_id): return tenant
    async def integration_status(*_args):
        return {
            "microsoft": IntegrationConnectionStatus(connected=False),
            "google": IntegrationConnectionStatus(connected=False),
        }
    async def agreements(*_args):
        return {"configured": False, "blocking": False}

    monkeypatch.setattr(onboarding, "_load_tenant", load_tenant)
    monkeypatch.setattr(onboarding, "_get_integration_status", integration_status)
    monkeypatch.setattr(onboarding, "agreement_status", agreements)
    db = _SeqDb(results=[_result(None), _result(SimpleNamespace(custom_config={}))], scalars=[0, 0, 0])

    response = await onboarding.get_onboarding_status(None, db)

    assert response.agreements_configured is False
    assert response.agreements_blocking is False


@pytest.mark.asyncio
async def test_unconfigured_agreements_block_new_tenant_cloud_connection(monkeypatch):
    tenant = _tenant(onboarding_completed=False)

    async def agreements(*_args):
        return {"configured": False, "complete": False, "enforced": False, "blocking": False}

    class Db(_SeqDb):
        def __init__(self):
            super().__init__()
            self.values = [tenant, None]
        async def scalar(self, _statement): return self.values.pop(0)

    monkeypatch.setattr(onboarding, "agreement_status", agreements)
    # The helper lives in compliance; patch its imported dependency to keep
    # this lifecycle invariant database-free.
    from app.services import compliance
    monkeypatch.setattr(compliance, "agreement_status", agreements)

    assert not await compliance.onboarding_cloud_connection_blocked(Db(), TENANT_ID)

    async def enforced(*_args):
        return {"configured": False, "complete": False, "enforced": True, "blocking": True}

    monkeypatch.setattr(compliance, "agreement_status", enforced)
    assert await compliance.onboarding_cloud_connection_blocked(Db(), TENANT_ID)


@pytest.mark.asyncio
async def test_configured_existing_tenant_is_not_blocked_by_rollout_flag(monkeypatch):
    tenant = _tenant(onboarding_completed=True)

    async def agreements(*_args):
        return {"configured": False, "complete": False, "enforced": False, "blocking": False}

    class Db(_SeqDb):
        def __init__(self):
            super().__init__()
            self.values = [tenant, "credential-id"]
        async def scalar(self, _statement): return self.values.pop(0)

    from app.services import compliance
    monkeypatch.setattr(compliance, "agreement_status", agreements)

    assert not await compliance.onboarding_cloud_connection_blocked(Db(), TENANT_ID)


# ── Directory sync must not skip the storage step ────────────────────────


@pytest.mark.asyncio
async def test_user_sync_advances_syncing_to_review_only():
    tenant = _tenant(onboarding_step=onboarding.STEP_SYNC)
    db = _SeqDb([_result(tenant)])

    await user_sync._advance_onboarding_step(db, TENANT_ID)

    assert tenant.onboarding_step == onboarding.STEP_REVIEW
    assert db.commits == 1


@pytest.mark.asyncio
async def test_user_sync_never_jumps_a_tenant_past_the_storage_step():
    tenant = _tenant(onboarding_step=onboarding.STEP_STORAGE)
    db = _SeqDb([_result(tenant)])

    await user_sync._advance_onboarding_step(db, TENANT_ID)

    assert tenant.onboarding_step == onboarding.STEP_STORAGE
    assert db.commits == 0


@pytest.mark.asyncio
async def test_user_sync_step_advance_swallows_database_errors():
    class _Boom:
        async def execute(self, _statement):
            raise RuntimeError("connection reset")

    # Best-effort: a sync must not fail because the step could not be moved.
    await user_sync._advance_onboarding_step(_Boom(), TENANT_ID)


@pytest.mark.asyncio
async def test_post_connect_sync_advances_syncing_to_review_only(monkeypatch):
    tenant = _tenant(onboarding_step=onboarding.STEP_SYNC)
    calls = []

    class _Sync:
        async def sync_google_users(self, _db, tenant_id):
            calls.append(tenant_id)

    monkeypatch.setattr("app.services.user_sync.UserSyncService", lambda: _Sync())
    db = _SeqDb([_result(tenant)])

    await integrations._sync_users_post_connect_with_session(db, TENANT_ID, "google")

    assert calls == [TENANT_ID]
    assert tenant.onboarding_step == integrations.ONBOARDING_STEP_REVIEW
    assert db.commits == 1


@pytest.mark.asyncio
async def test_post_connect_sync_leaves_a_tenant_on_the_storage_step(monkeypatch):
    tenant = _tenant(onboarding_step=integrations.ONBOARDING_STEP_STORAGE)

    class _Sync:
        async def sync_google_users(self, _db, _tenant_id):
            return None

    monkeypatch.setattr("app.services.user_sync.UserSyncService", lambda: _Sync())
    db = _SeqDb([_result(tenant)])

    await integrations._sync_users_post_connect_with_session(db, TENANT_ID, "google")

    assert tenant.onboarding_step == integrations.ONBOARDING_STEP_STORAGE
    assert db.commits == 0


# ── Post-connect redirect ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reauthorization_returns_to_the_cloud_card_not_cloud_search():
    """The refreshed health is shown on the card they re-authorized from."""
    db = _SeqDb([_result(_tenant(onboarding_completed=True))])

    response = await integrations._post_connect_redirect(db, TENANT_ID, "google")

    assert "tab=integrations&integration=cloud" in response.headers["location"]
    assert "connected=google" in response.headers["location"]


@pytest.mark.asyncio
async def test_zoom_reauthorization_returns_to_the_zoom_card():
    db = _SeqDb([_result(_tenant(onboarding_completed=True))])

    response = await integrations._post_connect_redirect(db, TENANT_ID, "zoom")

    assert "integration=zoom" in response.headers["location"]


@pytest.mark.asyncio
async def test_first_connect_returns_to_the_wizard():
    db = _SeqDb([_result(_tenant(onboarding_completed=False))])

    response = await integrations._post_connect_redirect(db, TENANT_ID, "google")

    assert "/onboarding?connected=google" in response.headers["location"]


@pytest.mark.asyncio
async def test_per_user_reauthorization_returns_to_calendar_for_each_provider():
    for provider in ("microsoft", "google"):
        response = await integrations._post_connect_redirect(
            _SeqDb([]), TENANT_ID, provider, intent="user"
        )
        assert response.headers["location"].endswith(f"/calendar?connected={provider}")


def test_per_user_oauth_errors_return_to_calendar():
    for provider in ("microsoft", "google"):
        response = integrations._error_redirect(
            provider, "token_exchange_failed", intent="user"
        )
        assert response.headers["location"].endswith(f"/calendar?error=token_exchange_failed&provider={provider}")


def test_oauth_redirect_defaults_remain_admin_or_onboarding():
    response = integrations._error_redirect("microsoft", "token_exchange_failed")
    assert "/onboarding?error=token_exchange_failed&provider=microsoft" in response.headers["location"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_admin_oauth_failure_returns_to_integration_card(monkeypatch, provider):
    async def consume_state(_request, _state):
        return True, {
            "provider": provider,
            "intent": "admin",
            "return_to": "integrations",
        }

    monkeypatch.setattr(integrations, "_consume_state", consume_state)
    callback = getattr(integrations, f"{provider}_callback")

    response = await callback(
        state="valid-state",
        request=SimpleNamespace(),
        db=_SeqDb(),
        error="access_denied",
    )

    assert response.headers["location"].endswith(
        "/admin?tab=integrations&integration=cloud"
        f"&error=access_denied&provider={provider}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["microsoft", "google"])
async def test_admin_connect_saves_integration_return_destination(monkeypatch, provider):
    saved = []

    async def current_user(_request, _db):
        return SimpleNamespace(id=TENANT_ID, tenant_id=TENANT_ID, role="admin")

    async def no_op(*_args):
        return None

    async def not_blocked(*_args):
        return False

    async def save_state(_request, _state, meta):
        saved.append(meta)

    monkeypatch.setattr(integrations, "get_current_user", current_user)
    monkeypatch.setattr(integrations, "set_tenant_context", no_op)
    monkeypatch.setattr(integrations, "onboarding_cloud_connection_blocked", not_blocked)
    monkeypatch.setattr(integrations, "_save_state", save_state)
    monkeypatch.setattr(integrations, "is_oauth_client_configured", lambda *_args: True)

    connect = getattr(integrations, f"{provider}_connect")
    kwargs = {"teams": 1} if provider == "microsoft" else {"account_mode": "workspace"}
    await connect(
        request=SimpleNamespace(),
        intent="admin",
        return_to="integrations",
        db=_SeqDb(),
        **kwargs,
    )

    assert saved[0]["return_to"] == "integrations"
