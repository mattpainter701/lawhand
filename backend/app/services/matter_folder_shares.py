"""Take back the cloud folder shares LawHand gave a person when they leave a matter.

Assigning someone to a matter shares its OneDrive and Google Drive folders with
them (``cloud_init.share_matter_folders``). Every permission the provider
creates is recorded in ``matter_folder_share_grants`` with its id. When the
person is removed from the matter, or deactivated, the grant is marked
``revoke_pending`` in the same transaction and removed from the provider right
after the commit. The removal is best effort for the request: a provider
failure never blocks the unassign. It is recorded on the matter timeline, on
the admin integration health page and in the error log, and a durable job
retries it until it succeeds.

Only LawHand's own permission is removed. A share a person already held
before LawHand invited them is marked ``kept`` and left alone. A share made
before ids were recorded (``legacy``) is matched on the person's email plus
the exact role LawHand grants on that folder, and inherited permissions are
never touched.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.durable_job import DurableJob
from app.models.matter_assignment import MatterAssignment
from app.models.matter_folder_share_grant import MatterFolderShareGrant
from app.models.plugin import Matter, MatterEvent
from app.models.user import User
from app.services import cloud_init
from app.services.durable_jobs import enqueue_job
from app.services.integration_observability import (
    capture_integration_error,
    record_integration_sync_run,
)

logger = logging.getLogger(__name__)

UNSHARE_JOB_KIND = "matter_folder_unshare"
SYNC_JOB_TYPE = "matter_folder_unshare"
# The queue backs off to an hour between attempts, so this keeps retrying for
# most of a working day; the hourly sweep re-queues anything still pending.
UNSHARE_JOB_MAX_ATTEMPTS = 12
_AUTH_PROVIDER = {"onedrive": "microsoft", "google_drive": "google"}
_PROVIDER_LABEL = {"onedrive": "OneDrive", "google_drive": "Google Drive"}


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


async def record_folder_grants(
    db: AsyncSession,
    *,
    tenant_id,
    matter_id,
    provider: str,
    folder_id: str,
    role: str,
    granted: dict[str, str | None],
    existing: list[dict] | None,
    user_ids_by_email: dict[str, object],
) -> None:
    """Record the permissions one share call created, one row per person.

    ``existing`` is the folder's permission list read before the invite.
    Providers merge a repeat invite into a direct share the person already
    holds, so a returned id that was already there is only LawHand's when it
    carries LawHand's role (a legacy LawHand share) or LawHand recorded it.
    """
    tenant_uuid = uuid.UUID(str(tenant_id))
    matter_uuid = uuid.UUID(str(matter_id))
    user_ids = {normalize_email(key): value for key, value in user_ids_by_email.items()}
    prior_by_email: dict[str, list[dict]] = defaultdict(list)
    for permission in existing or []:
        if permission.get("direct"):
            for email in permission.get("emails") or ():
                prior_by_email[email].append(permission)

    now = datetime.now(timezone.utc)
    for raw_email, permission_id in granted.items():
        email = normalize_email(raw_email)
        if not email:
            continue
        row = await db.scalar(
            select(MatterFolderShareGrant).where(
                MatterFolderShareGrant.tenant_id == tenant_uuid,
                MatterFolderShareGrant.matter_id == matter_uuid,
                MatterFolderShareGrant.provider == provider,
                MatterFolderShareGrant.folder_id == folder_id,
                MatterFolderShareGrant.grantee_email == email,
            )
        )
        prior = prior_by_email.get(email, [])
        prior_ids = {permission["id"] for permission in prior}
        if (
            row is not None
            and permission_id
            and row.permission_id == permission_id
            and row.status in ("active", "revoke_pending", "kept")
        ):
            origin = row.origin
        elif existing is None or (permission_id and permission_id not in prior_ids):
            origin = "lawhand" if permission_id else "legacy"
        elif permission_id:
            merged = next(p for p in prior if p["id"] == permission_id)
            origin = "lawhand" if role in merged["roles"] else "preexisting"
        elif not prior or any(role in p["roles"] for p in prior):
            origin = "legacy"
        else:
            origin, permission_id = "preexisting", prior[0]["id"]

        user_id = user_ids.get(email)
        if row is None:
            row = MatterFolderShareGrant(
                tenant_id=tenant_uuid,
                matter_id=matter_uuid,
                grantee_email=email,
                provider=provider,
                folder_id=folder_id,
            )
            db.add(row)
        row.user_id = uuid.UUID(str(user_id)) if user_id else row.user_id
        row.role = role
        row.permission_id = permission_id
        row.origin = origin
        row.status = "active"
        row.granted_at = now
        row.revoke_attempts = 0
        row.last_error = None
        row.revoke_requested_at = None
        row.revoke_requested_by = None
        row.revoke_reason = None
        row.revoked_at = None
    await db.flush()


async def _enqueue_unshare_job(
    db: AsyncSession, tenant_id, *, key: str, payload: dict
) -> None:
    job = await enqueue_job(
        db,
        tenant_id=tenant_id,
        kind=UNSHARE_JOB_KIND,
        idempotency_key=key[:200],
        payload=payload,
        requeue_failed=True,
        requeue_completed=True,
    )
    if job is not None and job.status == "pending":
        job.max_attempts = UNSHARE_JOB_MAX_ATTEMPTS
        await db.flush()


async def request_share_revocation(
    db: AsyncSession,
    *,
    tenant_id,
    matter_id,
    cloud_folder: dict | None,
    user_id,
    email: str | None,
    actor_user_id,
    reason: str,
    enqueue: bool = True,
) -> int:
    """Mark a person's shares on one matter for removal; return how many.

    Runs inside the caller's transaction, so the revocation is durable exactly
    when the unassign is. Provider calls happen after the commit.
    """
    email = normalize_email(email)
    if not email:
        return 0
    tenant_uuid = uuid.UUID(str(tenant_id))
    matter_uuid = uuid.UUID(str(matter_id))
    rows = list(
        (
            await db.scalars(
                select(MatterFolderShareGrant).where(
                    MatterFolderShareGrant.tenant_id == tenant_uuid,
                    MatterFolderShareGrant.matter_id == matter_uuid,
                    MatterFolderShareGrant.grantee_email == email,
                )
            )
        ).all()
    )
    by_target = {(row.provider, row.folder_id): row for row in rows}
    # A folder with no record was shared before ids were stored, if at all.
    # Its removal matches the person's email and LawHand's role on that folder.
    for provider, folder_id, role in cloud_init.matter_folder_share_targets(
        cloud_folder
    ):
        if (provider, folder_id) in by_target:
            continue
        legacy = MatterFolderShareGrant(
            tenant_id=tenant_uuid,
            matter_id=matter_uuid,
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            grantee_email=email,
            provider=provider,
            folder_id=folder_id,
            role=role,
            permission_id=None,
            origin="legacy",
            status="active",
        )
        db.add(legacy)
        by_target[(provider, folder_id)] = legacy

    now = datetime.now(timezone.utc)
    pending = 0
    for row in by_target.values():
        if row.status != "active":
            continue
        row.revoke_requested_at = now
        row.revoke_requested_by = (
            uuid.UUID(str(actor_user_id)) if actor_user_id else None
        )
        row.revoke_reason = reason[:40]
        row.revoke_attempts = 0
        row.last_error = None
        if row.origin == "preexisting":
            # Someone gave this person the share directly; it is not LawHand's.
            row.status = "kept"
            row.revoked_at = now
        else:
            row.status = "revoke_pending"
            pending += 1
    await db.flush()
    if pending and enqueue:
        await _enqueue_unshare_job(
            db,
            tenant_uuid,
            key=f"matter:{matter_uuid}:{email}",
            payload={"matter_id": str(matter_uuid), "email": email},
        )
    return pending


async def request_user_share_revocations(
    db: AsyncSession,
    *,
    tenant_id,
    user_id,
    email: str | None,
    actor_user_id,
    reason: str,
) -> int:
    """Mark every matter share a person holds for removal (deactivation)."""
    email = normalize_email(email)
    if not email:
        return 0
    tenant_uuid = uuid.UUID(str(tenant_id))
    user_uuid = uuid.UUID(str(user_id))
    matter_ids = set(
        (
            await db.scalars(
                select(MatterAssignment.matter_id).where(
                    MatterAssignment.tenant_id == tenant_uuid,
                    MatterAssignment.user_id == user_uuid,
                )
            )
        ).all()
    )
    matter_ids.update(
        matter_id
        for matter_id in (
            await db.scalars(
                select(MatterFolderShareGrant.matter_id).where(
                    MatterFolderShareGrant.tenant_id == tenant_uuid,
                    MatterFolderShareGrant.grantee_email == email,
                    MatterFolderShareGrant.status == "active",
                )
            )
        ).all()
        if matter_id is not None
    )
    pending = 0
    for matter_id in sorted(matter_ids, key=str):
        cloud_folder = await db.scalar(
            select(Matter.cloud_folder).where(
                Matter.id == matter_id, Matter.tenant_id == tenant_uuid
            )
        )
        pending += await request_share_revocation(
            db,
            tenant_id=tenant_uuid,
            matter_id=matter_id,
            cloud_folder=cloud_folder,
            user_id=user_uuid,
            email=email,
            actor_user_id=actor_user_id,
            reason=reason,
            enqueue=False,
        )
    if pending:
        await _enqueue_unshare_job(
            db,
            tenant_uuid,
            key=f"user:{email}",
            payload={"matter_id": None, "email": email},
        )
    return pending


@dataclass(frozen=True)
class _PendingGrant:
    id: uuid.UUID
    matter_id: uuid.UUID | None
    user_id: uuid.UUID | None
    email: str
    provider: str
    folder_id: str
    role: str
    permission_id: str | None
    requested_by: uuid.UUID | None


async def _still_entitled(
    db: AsyncSession, tenant_id: uuid.UUID, grant: _PendingGrant
) -> bool:
    """True when the person is back on the matter and still owed this folder."""
    if grant.matter_id is None or grant.user_id is None:
        return False
    assigned = await db.scalar(
        select(MatterAssignment.id)
        .join(User, User.id == MatterAssignment.user_id)
        .where(
            MatterAssignment.tenant_id == tenant_id,
            MatterAssignment.matter_id == grant.matter_id,
            MatterAssignment.user_id == grant.user_id,
            User.is_active.is_(True),
        )
    )
    if assigned is None:
        return False
    cloud_folder = await db.scalar(
        select(Matter.cloud_folder).where(
            Matter.id == grant.matter_id, Matter.tenant_id == tenant_id
        )
    )
    return (grant.provider, grant.folder_id) in {
        (provider, folder_id)
        for provider, folder_id, _role in cloud_init.matter_folder_share_targets(
            cloud_folder
        )
    }


async def _shared_by_another_matter(
    db: AsyncSession, tenant_id: uuid.UUID, grant: _PendingGrant
) -> bool:
    """True when another matter still holds a share of the same folder for them."""
    other = await db.scalar(
        select(MatterFolderShareGrant.id).where(
            MatterFolderShareGrant.tenant_id == tenant_id,
            MatterFolderShareGrant.provider == grant.provider,
            MatterFolderShareGrant.folder_id == grant.folder_id,
            MatterFolderShareGrant.grantee_email == grant.email,
            MatterFolderShareGrant.status == "active",
            MatterFolderShareGrant.id != grant.id,
        )
    )
    return other is not None


async def _remove_from_provider(token, grant: _PendingGrant) -> int:
    """Remove LawHand's permission; return how many provider permissions went."""
    if grant.permission_id:
        await cloud_init.delete_folder_permission(
            token, grant.provider, grant.folder_id, grant.permission_id
        )
        return 1
    removed = 0
    for permission in await cloud_init.list_folder_permissions(
        token, grant.provider, grant.folder_id
    ):
        if (
            permission["direct"]
            and grant.email in permission["emails"]
            and grant.role in permission["roles"]
            and "owner" not in permission["roles"]
        ):
            await cloud_init.delete_folder_permission(
                token, grant.provider, grant.folder_id, permission["id"]
            )
            removed += 1
    return removed


async def process_pending_revocations(
    db: AsyncSession,
    tenant_id,
    *,
    matter_id=None,
    email: str | None = None,
    limit: int = 200,
) -> dict:
    """Remove pending shares from the provider and record every outcome."""
    tenant_uuid = uuid.UUID(str(tenant_id))
    stmt = select(MatterFolderShareGrant).where(
        MatterFolderShareGrant.tenant_id == tenant_uuid,
        MatterFolderShareGrant.status == "revoke_pending",
    )
    if matter_id is not None:
        stmt = stmt.where(MatterFolderShareGrant.matter_id == uuid.UUID(str(matter_id)))
    if email:
        stmt = stmt.where(
            MatterFolderShareGrant.grantee_email == normalize_email(email)
        )
    stmt = (
        stmt.order_by(MatterFolderShareGrant.revoke_requested_at)
        .limit(limit)
        .execution_options(populate_existing=True)
    )
    # Plain snapshots: token refreshes commit the session mid-run.
    grants = [
        _PendingGrant(
            id=row.id,
            matter_id=row.matter_id,
            user_id=row.user_id,
            email=row.grantee_email,
            provider=row.provider,
            folder_id=row.folder_id,
            role=row.role,
            permission_id=row.permission_id,
            requested_by=row.revoke_requested_by,
        )
        for row in (await db.scalars(stmt)).all()
    ]
    summary = {"revoked": 0, "failed": 0, "restored": 0, "released": 0}
    if not grants:
        return summary

    outcomes: dict[uuid.UUID, tuple[str, str | None]] = {}
    tokens: dict[str, object] = {}
    token_errors: dict[str, str] = {}
    for grant in grants:
        if await _still_entitled(db, tenant_uuid, grant):
            outcomes[grant.id] = ("restored", None)
            continue
        if await _shared_by_another_matter(db, tenant_uuid, grant):
            outcomes[grant.id] = ("released", None)
            continue
        if grant.provider not in tokens:
            try:
                tokens[grant.provider] = await cloud_init.provider_share_token(
                    db, str(tenant_uuid), grant.provider
                )
            except Exception as exc:
                tokens[grant.provider] = None
                token_errors[grant.provider] = str(exc)
        token = tokens[grant.provider]
        if not token:
            label = _PROVIDER_LABEL[grant.provider]
            outcomes[grant.id] = (
                "failed",
                token_errors.get(grant.provider)
                or f"{label} is not connected; reconnect it so LawHand can remove the share",
            )
            continue
        try:
            await _remove_from_provider(token, grant)
            outcomes[grant.id] = ("revoked", None)
        except Exception as exc:
            logger.warning(
                "Could not remove %s folder share %s: %s",
                _PROVIDER_LABEL[grant.provider],
                grant.id,
                exc,
            )
            outcomes[grant.id] = ("failed", str(exc)[:500] or type(exc).__name__)

    now = datetime.now(timezone.utc)
    first_failures: set[uuid.UUID] = set()
    rows = {
        row.id: row
        for row in (
            await db.scalars(
                select(MatterFolderShareGrant)
                .where(
                    MatterFolderShareGrant.tenant_id == tenant_uuid,
                    MatterFolderShareGrant.id.in_(list(outcomes)),
                )
                # Re-read: another session may have re-shared meanwhile.
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    for grant_id, (outcome, error) in outcomes.items():
        row = rows.get(grant_id)
        if row is None or row.status != "revoke_pending":
            # Re-shared while the provider call ran: the newer grant wins.
            continue
        summary[outcome] += 1
        if outcome == "restored":
            row.status = "active"
            row.revoke_requested_at = None
            row.revoke_reason = None
        elif outcome == "failed":
            row.revoke_attempts += 1
            row.last_error = error
            if row.revoke_attempts == 1:
                first_failures.add(grant_id)
        else:
            row.status = "revoked"
            row.revoked_at = now
            row.last_error = None

    await _record_outcomes(db, tenant_uuid, grants, outcomes, first_failures)
    await db.commit()
    return summary


async def _record_outcomes(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    grants: list[_PendingGrant],
    outcomes: dict[uuid.UUID, tuple[str, str | None]],
    first_failures: set[uuid.UUID],
) -> None:
    """Write the matter timeline, admin health row and error log for a run."""
    by_provider: dict[str, dict] = defaultdict(
        lambda: {"ok": 0, "failed": 0, "new_failures": 0, "errors": []}
    )
    by_person: dict[tuple, dict] = defaultdict(
        lambda: {"removed": set(), "failed": set(), "new_failure": False}
    )
    for grant in grants:
        outcome, error = outcomes.get(grant.id, ("", None))
        if outcome not in ("revoked", "failed"):
            continue
        provider_stats = by_provider[_AUTH_PROVIDER[grant.provider]]
        person = by_person[(grant.matter_id, grant.email, grant.requested_by)]
        label = _PROVIDER_LABEL[grant.provider]
        if outcome == "revoked":
            provider_stats["ok"] += 1
            person["removed"].add(label)
        else:
            provider_stats["failed"] += 1
            provider_stats["errors"].append(error or "unknown error")
            provider_stats["new_failures"] += grant.id in first_failures
            person["failed"].add(label)
            person["new_failure"] |= grant.id in first_failures

    for provider, stats in by_provider.items():
        summary = "; ".join(sorted(set(stats["errors"])))[:1000] or None
        await record_integration_sync_run(
            db,
            tenant_id=tenant_id,
            provider=provider,
            job_type=SYNC_JOB_TYPE,
            status="failed" if stats["failed"] else "success",
            items_ok=stats["ok"],
            items_failed=stats["failed"],
            error_summary=summary,
        )
        # One error-log entry per share that starts failing, not per retry:
        # the sync-run row above already shows the current state.
        if stats["new_failures"]:
            await capture_integration_error(
                db,
                tenant_id=tenant_id,
                provider=provider,
                job_type=SYNC_JOB_TYPE,
                message=(
                    f"{stats['failed']} matter folder share(s) could not be "
                    f"removed; retrying. {summary or ''}"
                ).strip(),
            )

    for (matter_id, email, actor_id), person in by_person.items():
        if matter_id is None or actor_id is None:
            continue
        if person["failed"]:
            if not person["new_failure"]:
                continue
            labels = " and ".join(sorted(person["failed"]))
            db.add(
                MatterEvent(
                    tenant_id=tenant_id,
                    matter_id=matter_id,
                    event_type="cloud_folder_unshare_failed",
                    title=f"{labels} access not yet removed for {email}",
                    content=(
                        f"LawHand could not remove the {labels} folder share it "
                        f"gave {email}. It keeps retrying automatically; an "
                        "administrator can see the failure on the integrations page."
                    ),
                    note_type="system",
                    metadata_json={
                        "grantee_email": email,
                        "providers": sorted(person["failed"]),
                    },
                    created_by=actor_id,
                )
            )
        else:
            labels = " and ".join(sorted(person["removed"]))
            db.add(
                MatterEvent(
                    tenant_id=tenant_id,
                    matter_id=matter_id,
                    event_type="cloud_folder_unshared",
                    title=f"{labels} access removed for {email}",
                    content=(
                        f"LawHand removed the {labels} folder share it gave "
                        f"{email} for this matter."
                    ),
                    note_type="system",
                    metadata_json={
                        "grantee_email": email,
                        "providers": sorted(person["removed"]),
                    },
                    created_by=actor_id,
                )
            )
    await db.flush()


async def revoke_pending_shares_now(
    db: AsyncSession, tenant_id, *, matter_id=None, email: str | None = None
) -> dict | None:
    """Try the provider removal straight after an unassign; never raise.

    The durable job queued with the revocation retries whatever this misses.
    """
    try:
        return await process_pending_revocations(
            db, tenant_id, matter_id=matter_id, email=email
        )
    except Exception:
        logger.warning(
            "Immediate cloud folder unshare failed for tenant %s; the retry job "
            "will pick it up",
            tenant_id,
            exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            logger.debug("Rollback after unshare failure also failed", exc_info=True)
        return None


async def run_unshare_job(db: AsyncSession, row: DurableJob) -> dict:
    """Durable-job handler: retry pending removals; fail so the queue backs off."""
    payload = row.payload or {}
    summary = await process_pending_revocations(
        db,
        row.tenant_id,
        matter_id=payload.get("matter_id"),
        email=payload.get("email"),
    )
    if summary["failed"]:
        raise RuntimeError(
            f"{summary['failed']} matter folder share(s) could not be removed yet"
        )
    return summary


async def enqueue_stale_unshare_jobs() -> int:
    """Hourly backstop: queue a sweep for every tenant with shares still pending."""
    from app.database import async_session_maker, set_tenant_context
    from app.models.tenant import Tenant

    async with async_session_maker() as root:
        tenant_ids = list(
            (await root.scalars(select(Tenant.id).order_by(Tenant.id))).all()
        )
    queued = 0
    for tenant_id in tenant_ids:
        async with async_session_maker() as db:
            await set_tenant_context(db, str(tenant_id))
            pending = await db.scalar(
                select(MatterFolderShareGrant.id)
                .where(
                    MatterFolderShareGrant.tenant_id == tenant_id,
                    MatterFolderShareGrant.status == "revoke_pending",
                )
                .limit(1)
            )
            if pending is None:
                continue
            await _enqueue_unshare_job(
                db,
                tenant_id,
                key="sweep",
                payload={"matter_id": None, "email": None},
            )
            await db.commit()
            queued += 1
    return queued


async def share_user_matter_folders(db: AsyncSession, tenant_id, user: User) -> None:
    """Share every assigned matter's folders with a person again (reactivation)."""
    tenant_uuid = uuid.UUID(str(tenant_id))
    email = user.email
    user_id = user.id
    rows = (
        await db.execute(
            select(Matter.id, Matter.cloud_folder)
            .join(MatterAssignment, MatterAssignment.matter_id == Matter.id)
            .where(
                MatterAssignment.tenant_id == tenant_uuid,
                MatterAssignment.user_id == user_id,
                Matter.tenant_id == tenant_uuid,
                Matter.cloud_folder.is_not(None),
            )
        )
    ).all()
    for matter_id, cloud_folder in rows:
        try:
            await cloud_init.share_matter_folders(
                db=db,
                tenant_id=str(tenant_uuid),
                cloud_folder=cloud_folder,
                user_emails=[email],
                matter_id=matter_id,
                user_ids_by_email={email: user_id},
            )
        except Exception:
            logger.warning(
                "Failed to share cloud folders for matter %s", matter_id, exc_info=True
            )
