"""Age-based pruning for the customer-content stores the Smart Fill programme added.

``document_fill_sessions`` keeps the answers a preparer typed (encrypted) and
``document_text_extractions`` keeps a document's text (its text layer or OCR).
Both are customer content. A fill session is inaccessible after its 14-day
window and the text cache is derived data, but neither was physically removed,
so both grew for the life of the deployment. Expiry hides the session; this
sweep removes it, and the cached text, once the documented window has long
passed. Both tables have ``FORCE ROW LEVEL SECURITY`` and production connects as
a ``NOBYPASSRLS`` role, so it enumerates the tenant registry and deletes inside
one ordinary tenant context at a time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.database import async_session_maker, set_tenant_context
from app.models.document_fill_session import DocumentFillSession
from app.models.document_text_extraction import DocumentTextExtraction
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

#: Physical retention, measured from ``created_at``. A fill session is unusable
#: after its own 14-day window; the cache is derived. Both are kept this many
#: days before they are deleted, comfortably past the documented window.
DOCUMENT_RETENTION_DAYS = 30

_MODELS = (DocumentFillSession, DocumentTextExtraction)


async def purge_expired_document_data() -> int:
    """Delete fill sessions and cached text older than the retention window."""

    cutoff = datetime.now(timezone.utc) - timedelta(days=DOCUMENT_RETENTION_DAYS)
    removed = 0
    async with async_session_maker() as db:
        tenant_ids = list(
            (await db.scalars(select(Tenant.id).order_by(Tenant.id))).all()
        )
        for tenant_id in tenant_ids:
            try:
                await set_tenant_context(db, str(tenant_id))
                for model in _MODELS:
                    result = await db.execute(
                        delete(model)
                        .where(
                            model.tenant_id == tenant_id,
                            model.created_at < cutoff,
                        )
                        .execution_options(synchronize_session=False)
                    )
                    removed += int(result.rowcount or 0)
                await db.commit()
            except Exception:
                # One unhealthy tenant must not strand every later tenant; the
                # next run retries it from scratch.
                await db.rollback()
                logger.exception(
                    "[document-retention] purge failed for tenant %s", tenant_id
                )
    logger.info(
        "[document-retention] removed %d rows older than %dd",
        removed,
        DOCUMENT_RETENTION_DAYS,
    )
    return removed
