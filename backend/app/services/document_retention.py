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
from app.services.fill_sessions import SESSION_DAYS

logger = logging.getLogger(__name__)

#: Physical retention. A fill session is unusable after SESSION_DAYS; the cache
#: is derived. Both are kept this many days before they are deleted, comfortably
#: past the documented window.
DOCUMENT_RETENTION_DAYS = 30
#: How long past its own expiry a session is kept before deletion.
SESSION_PURGE_GRACE_DAYS = DOCUMENT_RETENTION_DAYS - SESSION_DAYS


async def purge_expired_document_data() -> int:
    """Delete fill sessions and cached text older than the retention window."""

    now = datetime.now(timezone.utc)
    # A session is deleted a grace period past its own expiry, not from
    # ``created_at``: resuming one extends ``expires_at``, and a session still
    # in use must not be removed because it was opened a while ago. The text
    # cache has no expiry, so it ages from creation.
    session_cutoff = now - timedelta(days=SESSION_PURGE_GRACE_DAYS)
    cache_cutoff = now - timedelta(days=DOCUMENT_RETENTION_DAYS)
    plans = (
        (DocumentFillSession, DocumentFillSession.expires_at, session_cutoff),
        (DocumentTextExtraction, DocumentTextExtraction.created_at, cache_cutoff),
    )

    removed = 0
    async with async_session_maker() as db:
        tenant_ids = list(
            (await db.scalars(select(Tenant.id).order_by(Tenant.id))).all()
        )
        for tenant_id in tenant_ids:
            try:
                await set_tenant_context(db, str(tenant_id))
                for model, column, cutoff in plans:
                    result = await db.execute(
                        delete(model)
                        .where(
                            model.tenant_id == tenant_id,
                            column < cutoff,
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
