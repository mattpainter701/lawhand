"""Helpers for integration health, scope audit, and sync-run reporting."""

import uuid
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import set_tenant_context
from app.models.integration_sync_run import IntegrationSyncRun
from app.services.error_tracker import capture_error


def normalize_scope_list(scopes: str | Iterable[str] | None) -> list[str]:
    if scopes is None:
        return []
    if isinstance(scopes, str):
        return [s.strip() for s in scopes.split() if s.strip()]
    return [str(s).strip() for s in scopes if str(s).strip()]


def missing_scopes(
    provider: str,
    granted: str | Iterable[str] | None,
    required: str | Iterable[str] | None,
    scope_matcher,
) -> list[str]:
    granted_set = set(normalize_scope_list(granted))
    return sorted(
        scope
        for scope in normalize_scope_list(required)
        if not scope_matcher(scope, granted_set, provider)
    )


def health_from_missing(missing: list[str], active: bool = True) -> str:
    if not active:
        return "revoked"
    return "healthy" if not missing else "missing_scopes"


def apply_scope_audit(row, provider: str, required: str, scope_matcher) -> list[str]:
    """Record the scope gap and derive health from it.

    A ``revoked`` health is deliberately never lifted here. On a refresh cycle
    the stored scope string still looks complete after the provider has
    revoked the grant, so scopes alone must not paper over a dead credential.
    Fresh consent is the one event that supersedes a revocation; the callback
    paths call :func:`clear_refresh_failure` before auditing scopes.
    """
    missing = missing_scopes(provider, row.scopes, required, scope_matcher)
    row.missing_scopes = " ".join(missing) if missing else None
    if getattr(row, "health", None) != "revoked":
        row.health = health_from_missing(missing, getattr(row, "is_active", True))
    return missing


def clear_refresh_failure(row) -> None:
    """Reset stale failure state after a fresh authorization-code grant.

    Every credential upsert path used to set ``is_active`` and stop, leaving
    ``health``, ``last_refresh_error`` and ``last_refresh_at`` from the last
    failed refresh in place. Combined with the ``revoked`` guard in
    :func:`apply_scope_audit`, a successful re-authorization kept rendering as
    "Reconnect Required" beside a weeks-old ``invalid_grant`` until some later
    refresh happened to clear it — which drove administrators to re-authorize
    in a loop. A fresh grant is a new refresh token, so the failure it replaces
    is cleared here and the consent exchange is recorded as the last successful
    token issuance.
    """
    if hasattr(row, "health"):
        row.health = "healthy"
    if hasattr(row, "last_refresh_error"):
        row.last_refresh_error = None
    if hasattr(row, "last_refresh_at"):
        row.last_refresh_at = datetime.now(timezone.utc)
    if hasattr(row, "is_active"):
        row.is_active = True


USER_TOKEN_REAUTH_HEALTH = frozenset({"revoked", "refresh_failed", "missing_scopes"})


def summarize_user_tokens(rows: Iterable, provider: str) -> dict:
    """Summarize per-user OAuth tokens for one provider.

    Per-user tokens refresh through a different code path than the tenant-wide
    credential and fail independently of it: the tenant grant can be revoked
    for weeks while user-level sync keeps running clean, or the reverse. One
    status line cannot be true for both, so the card renders them separately.
    """
    total = 0
    healthy = 0
    needs_reauth = 0
    for row in rows:
        if getattr(row, "provider", None) != provider:
            continue
        total += 1
        health = getattr(row, "health", None) or "healthy"
        if health in USER_TOKEN_REAUTH_HEALTH:
            needs_reauth += 1
        else:
            healthy += 1
    return {"total": total, "healthy": healthy, "needs_reauth": needs_reauth}


async def record_integration_sync_run(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID | str,
    provider: str,
    job_type: str,
    status: str,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    items_ok: int = 0,
    items_failed: int = 0,
    error_summary: str | None = None,
) -> IntegrationSyncRun:
    tenant_uuid = uuid.UUID(str(tenant_id))
    await set_tenant_context(db, str(tenant_uuid))
    run = IntegrationSyncRun(
        tenant_id=tenant_uuid,
        provider=provider,
        job_type=job_type,
        started_at=started_at or datetime.now(timezone.utc),
        finished_at=finished_at or datetime.now(timezone.utc),
        status=status,
        items_ok=items_ok,
        items_failed=items_failed,
        error_summary=error_summary[:4000] if error_summary else None,
    )
    db.add(run)
    await db.flush()
    return run


async def capture_integration_error(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID | str,
    provider: str,
    job_type: str,
    message: str,
    severity: str = "error",
) -> None:
    await capture_error(
        db=db,
        tenant_id=uuid.UUID(str(tenant_id)),
        error_type="integration_sync_error",
        severity=severity,
        message=f"{provider} {job_type}: {message}",
    )
