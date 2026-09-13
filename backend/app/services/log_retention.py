"""Age-based pruning for the two operator diagnostic log tables.

``api_access_logs`` gains one row per tenant API request and ``error_logs`` one
per 4xx/5xx response. Neither had a retention policy, so both grew for the life
of the deployment — eventually becoming the largest tables in the database and
slowing the very operator console used to triage incidents.

Both tables have ``FORCE ROW LEVEL SECURITY`` (migration 057) and production
connects as the ``NOBYPASSRLS`` ``clarity_app`` role, so this sweep cannot issue
one cross-tenant ``DELETE``. It enumerates the tenant registry and deletes
inside one ordinary tenant context at a time — the same discipline the platform
read routes use — plus a final pass for the tenantless ``error_logs`` rows that
migration 079 admits under any context.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_maker, clear_tenant_context, set_tenant_context
from app.models.api_access_log import ApiAccessLog
from app.models.error_log import ErrorLog
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    """What one sweep removed, and whether it ran out of budget before finishing."""

    error_logs_deleted: int = 0
    access_logs_deleted: int = 0
    incomplete: bool = False

    @property
    def total_deleted(self) -> int:
        return self.error_logs_deleted + self.access_logs_deleted


async def _delete_one_batch(
    db: AsyncSession,
    model,
    *,
    tenant_filter,
    cutoff: datetime,
    batch_size: int,
) -> int:
    """Delete at most ``batch_size`` expired rows visible in the current scope.

    Deleting a whole tenant's backlog in one statement would hold row locks on
    a table every request writes to. Bounding each statement keeps the sweep
    invisible to live traffic at the cost of more round trips.
    """

    doomed = (
        select(model.id)
        .where(tenant_filter, model.created_at < cutoff)
        .order_by(model.created_at)
        .limit(batch_size)
    )
    result = await db.execute(
        delete(model)
        .where(model.id.in_(doomed))
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


async def _purge_scope(
    db: AsyncSession,
    model,
    *,
    tenant_id: uuid.UUID | None,
    cutoff: datetime,
    batch_size: int,
    max_batches: int,
) -> tuple[int, bool]:
    """Drain one RLS scope in batches. Returns (deleted, hit_batch_cap)."""

    deleted = 0
    for _ in range(max_batches):
        # The tenant GUCs are transaction-local, so the commit at the end of
        # each batch discards them. Re-entering the scope every iteration is
        # what keeps the next DELETE from silently matching nothing.
        if tenant_id is None:
            await clear_tenant_context(db)
        else:
            await set_tenant_context(db, str(tenant_id))

        removed = await _delete_one_batch(
            db,
            model,
            tenant_filter=(
                model.tenant_id.is_(None)
                if tenant_id is None
                else model.tenant_id == tenant_id
            ),
            cutoff=cutoff,
            batch_size=batch_size,
        )
        await db.commit()
        deleted += removed

        # A short batch means the scope is drained; anything else risks looping
        # on a table that live traffic keeps refilling.
        if removed < batch_size:
            return deleted, False

    return deleted, True


async def purge_expired_logs() -> RetentionResult:
    """Delete diagnostic log rows older than their configured retention window.

    Safe to run repeatedly: each pass removes whatever has since aged out. A
    retention window of zero (or less) disables pruning for that table, which
    is the escape hatch for a deployment under a litigation hold.
    """

    settings = get_settings()
    result = RetentionResult()

    if not settings.LOG_RETENTION_ENABLED:
        logger.info("[log-retention] disabled by configuration")
        return result

    now = datetime.now(timezone.utc)
    batch_size = max(1, settings.LOG_RETENTION_BATCH_SIZE)
    max_batches = max(1, settings.LOG_RETENTION_MAX_BATCHES_PER_SCOPE)

    plans = [
        (ErrorLog, settings.ERROR_LOG_RETENTION_DAYS, True),
        (ApiAccessLog, settings.API_ACCESS_LOG_RETENTION_DAYS, False),
    ]

    async with async_session_maker() as db:
        # The registry is deliberately not tenant-RLS data; reading it is how
        # every scoped pass below learns which contexts to enter.
        tenant_ids = list(
            (await db.scalars(select(Tenant.id).order_by(Tenant.id))).all()
        )

        for model, retention_days, include_system_rows in plans:
            if retention_days <= 0:
                continue

            cutoff = now - timedelta(days=retention_days)
            deleted = 0

            scopes: list[uuid.UUID | None] = list(tenant_ids)
            if include_system_rows:
                scopes.append(None)

            for scope in scopes:
                try:
                    removed, capped = await _purge_scope(
                        db,
                        model,
                        tenant_id=scope,
                        cutoff=cutoff,
                        batch_size=batch_size,
                        max_batches=max_batches,
                    )
                except Exception:
                    # One unhealthy tenant must not strand every later scope's
                    # backlog; the next run retries it from scratch.
                    await db.rollback()
                    logger.exception(
                        "[log-retention] %s purge failed for scope %s",
                        model.__tablename__,
                        scope or "system",
                    )
                    result.incomplete = True
                    continue

                deleted += removed
                if capped:
                    result.incomplete = True

            if model is ErrorLog:
                result.error_logs_deleted = deleted
            else:
                result.access_logs_deleted = deleted

    logger.info(
        "[log-retention] removed %d error_logs (>%dd) and %d api_access_logs (>%dd)%s",
        result.error_logs_deleted,
        settings.ERROR_LOG_RETENTION_DAYS,
        result.access_logs_deleted,
        settings.API_ACCESS_LOG_RETENTION_DAYS,
        " — batch cap reached, more remains for the next run"
        if result.incomplete
        else "",
    )
    return result
