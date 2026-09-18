"""Move an existing Google root from a user's My Drive into an org Shared Drive.

Google preserves file and folder IDs across a cross-drive *move* — only the
parent changes — so every persisted matter folder and subfolder binding stays
valid. The migration therefore updates only the tenant root's ownership
metadata; it never rewrites matter rows and never copies or deletes content.

The operation is idempotent, dry-runnable, and fails closed: the binding is
updated only after the move is verified on the provider.
"""

from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import set_tenant_context
from app.models.storage_migration import OnboardingRootAudit
from app.models.tenant import Tenant
from app.services import cloud_init, google_service_account
from app.services.token_vault import get_fresh_token

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_API = "https://www.googleapis.com/drive/v3"


async def _file_metadata(token: str, file_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{GOOGLE_DRIVE_API}/files/{file_id}",
            params={
                "fields": "id,parents,driveId,webViewLink",
                "supportsAllDrives": "true",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Google file lookup failed: {resp.status_code} {resp.text[:200]}"
        )
    return resp.json()


async def _move_into_shared_drive(
    token: str, file_id: str, drive_id: str, old_parents: list[str]
) -> dict:
    params = {
        "addParents": drive_id,
        "supportsAllDrives": "true",
        "fields": "id,parents,driveId,webViewLink",
    }
    if old_parents:
        params["removeParents"] = ",".join(old_parents)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.patch(
            f"{GOOGLE_DRIVE_API}/files/{file_id}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Google Shared Drive move failed: {resp.status_code} {resp.text[:200]}"
        )
    return resp.json()


def _audit_actor(actor_id: object | None) -> uuid.UUID | None:
    if not actor_id:
        return None
    try:
        return uuid.UUID(str(actor_id))
    except (ValueError, TypeError):
        return None


async def migrate_google_root_to_shared_drive(
    db: AsyncSession,
    tenant_id: object,
    *,
    actor_id: object | None = None,
    dry_run: bool = False,
) -> dict:
    """Move the tenant's Google root into an org Shared Drive.

    Returns a report with ``status`` one of ``noop``, ``refused``, ``dry_run``,
    ``migrated`` or ``not_found``. Raises only on a provider failure after the
    decision to move, so the caller can surface it; the binding is never
    changed on failure.
    """
    tenant_uuid = uuid.UUID(str(tenant_id))
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_uuid))
    if tenant is None:
        return {"status": "not_found", "tenant_id": str(tenant_uuid)}

    roots = (
        tenant.cloud_root_folder if isinstance(tenant.cloud_root_folder, dict) else {}
    )
    binding = roots.get("google_drive")
    if not isinstance(binding, dict) or not str(binding.get("id") or "").strip():
        return {
            "status": "noop",
            "tenant_id": str(tenant_uuid),
            "reason": "no Google root is bound",
        }
    if (binding.get("owner_type") or "").strip() == "org_shared_drive":
        return {
            "status": "noop",
            "tenant_id": str(tenant_uuid),
            "reason": "root is already organisation-owned",
        }

    account_type = await cloud_init._google_account_type(db, str(tenant_uuid))
    if account_type != "workspace":
        return {
            "status": "refused",
            "tenant_id": str(tenant_uuid),
            "account_type": account_type,
            "reason": "Shared Drive migration requires a Google Workspace organisation",
        }
    if not google_service_account.is_configured():
        return {
            "status": "refused",
            "tenant_id": str(tenant_uuid),
            "reason": "no LawHand service account is configured",
        }
    delegated = await get_fresh_token(db, str(tenant_uuid), "google")
    if not delegated:
        return {
            "status": "refused",
            "tenant_id": str(tenant_uuid),
            "reason": "Google credential is unavailable",
        }

    root_id = str(binding["id"])
    pinned_drive = await cloud_init._google_org_shared_drive_id(db, str(tenant_uuid))
    if dry_run:
        return {
            "status": "dry_run",
            "tenant_id": str(tenant_uuid),
            "root_id": root_id,
            "drive_id": pinned_drive or None,
            "would_create_drive": not pinned_drive,
        }

    drive_id = pinned_drive or await cloud_init._provision_org_shared_drive(
        db, str(tenant_uuid), delegated
    )

    meta = await _file_metadata(delegated, root_id)
    if (meta.get("driveId") or "") == drive_id:
        moved = meta
    else:
        old_parents = [p for p in (meta.get("parents") or []) if p]
        moved = await _move_into_shared_drive(delegated, root_id, drive_id, old_parents)
        verified = await _file_metadata(delegated, root_id)
        if (verified.get("driveId") or "") != drive_id:
            raise RuntimeError(
                "Google Shared Drive move could not be verified; the tenant root "
                "was left unchanged"
            )

    previous = dict(binding)
    new_binding = {**binding, "owner_type": "org_shared_drive", "drive_id": drive_id}
    if moved.get("webViewLink"):
        new_binding["url"] = moved["webViewLink"]

    await set_tenant_context(db, str(tenant_uuid))
    tenant.cloud_root_folder = {**roots, "google_drive": new_binding}
    db.add(
        OnboardingRootAudit(
            tenant_id=tenant_uuid,
            root=previous,
            action="google_shared_drive_cutover",
            actor_id=_audit_actor(actor_id),
        )
    )
    await db.commit()
    logger.info(
        "Migrated Google root for tenant %s into Shared Drive %s",
        tenant_uuid,
        drive_id,
    )
    return {
        "status": "migrated",
        "tenant_id": str(tenant_uuid),
        "root_id": root_id,
        "drive_id": drive_id,
        "url": new_binding.get("url"),
    }
