"""Tenant onboarding wizard — guided setup after first admin login.

Steps:
  0 = welcome
  1 = consent (connect MS/Google integrations)
  2 = storage (choose the provider and confirm the root folder)
  3 = syncing (directory users being pulled)
  4 = review (review imported users)
  5 = complete

Storage is an explicit step. ``initialize_cloud_root_folder`` used to run
silently inside ``/complete``, so a firm never chose a provider or saw where
its documents would live. ``/complete`` now refuses until a root exists.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, set_tenant_context
from app.middleware.tenant import get_current_user, require_admin
from app.models.tenant import Tenant, TenantSettings
from app.models.tenant_credential import TenantCredential
from app.models.user import User
from app.schemas.onboarding import (
    OnboardingStatusResponse,
    OnboardingCompleteResponse,
    OnboardingStorageRequest,
    OnboardingStorageResponse,
    IntegrationConnectionStatus,
)
from app.services.compliance import agreement_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/onboarding", tags=["onboarding"])

STEP_WELCOME = 0
STEP_CONNECT = 1
STEP_STORAGE = 2
STEP_SYNC = 3
STEP_REVIEW = 4
STEP_COMPLETE = 5

# Storage provider → the tenant credential that must be connected for it.
STORAGE_PROVIDER_CREDENTIAL = {
    "google_drive": "google",
    "onedrive": "microsoft",
    "sharepoint": "microsoft",
}
STORAGE_PROVIDER_LABELS = {
    "google_drive": "Google Drive",
    "onedrive": "Microsoft OneDrive",
    "sharepoint": "Microsoft SharePoint",
}


class OnboardingReentryRequest(BaseModel):
    target_provider: str | None = None


def _root_binding(cloud_root, provider: str) -> dict | None:
    """Return the saved root binding for ``provider`` when it is usable."""
    if not isinstance(cloud_root, dict):
        return None
    binding = cloud_root.get(provider)
    if isinstance(binding, dict) and str(binding.get("id") or "").strip():
        return binding
    return None


def _has_any_root(cloud_root) -> bool:
    return any(
        _root_binding(cloud_root, provider) for provider in STORAGE_PROVIDER_CREDENTIAL
    )


async def _get_integration_status(
    db: AsyncSession, tenant_id: str
) -> dict[str, IntegrationConnectionStatus]:
    """Query TenantCredential for MS and Google connection status."""
    result = await db.execute(
        select(TenantCredential).where(
            TenantCredential.tenant_id == tenant_id,
            TenantCredential.is_active.is_(True),
        )
    )
    creds = result.scalars().all()

    status = {}
    for provider in ("microsoft", "google"):
        match = next((c for c in creds if c.provider == provider), None)
        status[provider] = IntegrationConnectionStatus(
            connected=match is not None,
            scopes=match.scopes if match else None,
            service_account_email=match.service_account_email if match else None,
            granted_by_user_id=str(match.granted_by_user_id)
            if match and match.granted_by_user_id
            else None,
            account_type=match.account_type if match else None,
        )
    return status


async def _load_tenant(db: AsyncSession, tenant_id) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


async def _load_or_create_settings(db: AsyncSession, tenant_id) -> TenantSettings:
    result = await db.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        record = TenantSettings(tenant_id=tenant_id)
        db.add(record)
    return record


async def _load_primary_provider(db: AsyncSession, tenant_id) -> str | None:
    result = await db.execute(
        select(TenantSettings.primary_cloud_provider).where(
            TenantSettings.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get current onboarding state for the tenant."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))

    tenant = await _load_tenant(db, user.tenant_id)

    # Count synced users per provider
    ms_count = (
        await db.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == user.tenant_id,
                User.oauth_provider == "microsoft",
            )
        )
        or 0
    )
    google_count = (
        await db.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == user.tenant_id,
                User.oauth_provider == "google",
            )
        )
        or 0
    )

    total = (
        await db.scalar(
            select(func.count(User.id)).where(User.tenant_id == user.tenant_id)
        )
        or 0
    )

    integrations = await _get_integration_status(db, str(user.tenant_id))
    primary = await _load_primary_provider(db, user.tenant_id)
    settings_record = await _load_or_create_settings(db, user.tenant_id)
    cloud_root = (
        tenant.cloud_root_folder if isinstance(tenant.cloud_root_folder, dict) else None
    )
    agreements = await agreement_status(db, user.tenant_id)

    return OnboardingStatusResponse(
        onboarding_completed=tenant.onboarding_completed,
        onboarding_step=tenant.onboarding_step,
        integrations=integrations,
        synced_users={"microsoft": ms_count, "google": google_count},
        total_users=total,
        primary_cloud_provider=primary,
        cloud_root=cloud_root,
        storage_ready=_has_any_root(cloud_root),
        agreements_configured=agreements["configured"],
        agreements_blocking=agreements["blocking"],
        setup_deferred=bool((settings_record.custom_config or {}).get("onboarding_setup_deferred")),
    )


@router.post("/step/{step}")
async def update_onboarding_step(
    step: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Persist wizard progress."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))

    if step < STEP_WELCOME or step > STEP_COMPLETE:
        raise HTTPException(
            status_code=400, detail=f"Invalid step ({STEP_WELCOME}-{STEP_COMPLETE})"
        )

    tenant = await _load_tenant(db, user.tenant_id)
    tenant.onboarding_step = step
    await db.commit()
    return {"status": "ok", "step": step}


@router.post("/reenter")
async def reenter_onboarding(
    body: OnboardingReentryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reopen setup without discarding the completed tenant's cloud root."""
    admin = await require_admin(request, db)
    await set_tenant_context(db, str(admin.tenant_id))
    result = await db.execute(select(Tenant).where(Tenant.id == admin.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.cloud_root_folder:
        from app.models.storage_migration import OnboardingRootAudit

        db.add(
            OnboardingRootAudit(
                tenant_id=tenant.id,
                root=tenant.cloud_root_folder,
                action="onboarding_reentry",
                actor_id=admin.id,
            )
        )
    tenant.onboarding_step = STEP_CONNECT
    settings_record = await _load_or_create_settings(db, admin.tenant_id)
    config = dict(getattr(settings_record, "custom_config", None) or {})
    config.pop("onboarding_setup_deferred", None)
    settings_record.custom_config = config
    # Keep completed true so existing writes remain available during setup.
    if body.target_provider:
        from app.services.storage_migration import storage_migration

        try:
            migration = await storage_migration.start(
                db,
                str(admin.tenant_id),
                body.target_provider,
                str(admin.id),
                target_root=(tenant.cloud_root_folder or {}).get(body.target_provider),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await db.commit()
        return {
            "status": "ok",
            "onboarding_step": STEP_CONNECT,
            "migration_id": str(migration.id),
        }
    await db.commit()
    return {
        "status": "ok",
        "onboarding_step": STEP_CONNECT,
        "cloud_root": tenant.cloud_root_folder,
    }


@router.post("/storage", response_model=OnboardingStorageResponse)
async def confirm_onboarding_storage(
    body: OnboardingStorageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Choose the document storage provider and create its root folder.

    The chosen provider becomes ``primary_cloud_provider``. A root that already
    exists for it is kept and shown, never recreated or repointed: folder IDs
    are the authority for every matter binding underneath them.
    """
    admin = await require_admin(request, db)
    tenant_id = str(admin.tenant_id)
    await set_tenant_context(db, tenant_id)

    provider = (body.provider or "").strip()
    credential = STORAGE_PROVIDER_CREDENTIAL.get(provider)
    if not credential:
        raise HTTPException(
            status_code=400,
            detail="Choose Google Drive, Microsoft OneDrive or Microsoft SharePoint.",
        )
    integrations = await _get_integration_status(db, tenant_id)
    if not integrations[credential].connected:
        raise HTTPException(
            status_code=400,
            detail=f"Connect {'Google Workspace' if credential == 'google' else 'Microsoft 365'} "
            f"before choosing {STORAGE_PROVIDER_LABELS[provider]} for documents.",
        )

    tenant = await _load_tenant(db, admin.tenant_id)
    settings_record = await _load_or_create_settings(db, admin.tenant_id)
    if settings_record.primary_cloud_provider != provider:
        from app.services.storage_migration import assert_provider_change_allowed

        try:
            await assert_provider_change_allowed(db, tenant_id, provider)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        settings_record.primary_cloud_provider = provider

    from app.services.cloud_init import (
        cloud_root_binding_repair_needed,
        initialize_cloud_root_folder,
    )

    existing_root = (
        tenant.cloud_root_folder if isinstance(tenant.cloud_root_folder, dict) else {}
    )
    repair_needed = cloud_root_binding_repair_needed(tenant.cloud_root_folder)
    if repair_needed:
        # Never silently rebind a tenant whose saved root is malformed.
        await db.commit()
        return OnboardingStorageResponse(
            status="repair_needed",
            provider=provider,
            cloud_root=existing_root or None,
            root_repair_needed=repair_needed,
            error=(
                "A saved storage root needs administrator repair before setup can continue. "
                "Open Admin → Integrations → Advanced → Storage migration."
            ),
        )

    binding = _root_binding(existing_root, provider)
    created = False
    error = None
    if not binding:
        try:
            fresh = await initialize_cloud_root_folder(
                db, tenant_id, existing_root=existing_root
            )
        except Exception as exc:  # provider or token failure
            logger.warning(
                "Onboarding storage root init failed for tenant %s: %s", tenant_id, exc
            )
            fresh = {}
            error = str(exc)
        if fresh:
            existing_root = {**existing_root, **fresh}
            tenant.cloud_root_folder = existing_root
        binding = _root_binding(existing_root, provider)
        created = binding is not None

    if binding:
        tenant.onboarding_step = max(tenant.onboarding_step, STEP_SYNC)
        await db.commit()
        return OnboardingStorageResponse(
            status="ready",
            provider=provider,
            cloud_root=existing_root,
            root=binding,
            created=created,
        )

    await db.commit()
    if provider == "sharepoint":
        hint = (
            "Select a SharePoint site and library first (Admin → Integrations → Cloud → "
            "Document storage), or choose OneDrive for now."
        )
    else:
        hint = (
            f"LawHand could not create the root folder in {STORAGE_PROVIDER_LABELS[provider]}. "
            "Check the connected account has Drive access, then try again."
        )
    return OnboardingStorageResponse(
        status="failed",
        provider=provider,
        cloud_root=existing_root or None,
        error=f"{hint} {error}".strip() if error else hint,
    )


@router.post("/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark onboarding as complete once storage has been confirmed."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))

    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Verify at least one integration is connected
    agreement_gate = await agreement_status(db, user.tenant_id)
    if agreement_gate["blocking"]:
        raise HTTPException(
            status_code=428,
            detail={
                "message": "Current tenant agreements must be accepted before onboarding activation.",
                "agreements": agreement_gate["agreements"],
            },
        )
    integrations = await _get_integration_status(db, str(user.tenant_id))
    has_any = any(s.connected for s in integrations.values())

    if not has_any:
        raise HTTPException(
            status_code=400,
            detail="At least one integration (Microsoft or Google) must be connected to complete onboarding.",
        )

    # Storage is confirmed in its own step; completing without a root would
    # leave the firm with no place for matter documents.
    cloud_root = tenant.cloud_root_folder
    if not _has_any_root(cloud_root):
        raise HTTPException(
            status_code=400,
            detail="Confirm where matter documents will be stored before completing setup.",
        )

    # Re-entry is deliberately distinct from first-run setup: preserve the
    # existing root and record that it was observed.
    from app.models.storage_migration import OnboardingRootAudit

    db.add(
        OnboardingRootAudit(
            tenant_id=tenant.id,
            root=cloud_root,
            action="onboarding_rerun"
            if tenant.onboarding_completed
            else "onboarding_complete",
            actor_id=user.id,
        )
    )

    tenant.onboarding_completed = True
    tenant.onboarding_step = STEP_COMPLETE
    settings_record = await _load_or_create_settings(db, user.tenant_id)
    config = dict(getattr(settings_record, "custom_config", None) or {})
    config.pop("onboarding_setup_deferred", None)
    settings_record.custom_config = config
    await db.commit()

    return OnboardingCompleteResponse(status="ok", cloud_root=cloud_root)


@router.post("/skip")
async def skip_onboarding(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Defer integration setup without claiming that onboarding is complete."""
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))

    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Deferring setup is safe even while counsel-owned agreements are still
    # being prepared: no cloud connection or matter-document root is created.
    # Keep the tenant eligible for core workspace access and truthful re-entry.
    tenant.onboarding_completed = False
    tenant.onboarding_step = STEP_WELCOME
    settings_record = await _load_or_create_settings(db, user.tenant_id)
    config = dict(getattr(settings_record, "custom_config", None) or {})
    config["onboarding_setup_deferred"] = True
    settings_record.custom_config = config
    await db.commit()
    return {
        "status": "ok",
        "message": "Setup deferred — integrations can be set up later from Admin settings.",
    }
