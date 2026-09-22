"""Prepare a matter's documents the moment it has data.

Smart Fill used to run only when a person opened a template and chose a
matter. This module runs it unattended: when a matter is created, converted
from a lead, receives a questionnaire, or has intake answers accepted, a
``document_prefill`` durable job fills every published template the firm
could generate for that matter and records, per template, how much of it a
matter supplies. The record is a ``document_prefill_ready`` matter event whose
metadata carries counts and field *names* only -- never a value, never a
rendered page. Generating a document stays a human act behind the existing
preview-evidence gate; this job only tells the matter page what is ready.

Idempotency is keyed on the facts that feed a fill: a job runs once per
distinct fact digest per matter, so a second identical trigger is a no-op and
a change in the record queues a fresh run.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configurable_workflow import (
    ContactCustomFieldValue,
    MatterCustomFieldValue,
)
from app.models.document_template import DocumentTemplate
from app.models.plugin import Matter, MatterEvent
from app.models.user import User
from app.services import template_custom_fields, template_firm_fields
from app.services import template_fill_engine as engine
from app.services.configurable_workflows import digest_payload
from app.services.durable_jobs import enqueue_job
from app.services.matter_workspace_capabilities import (
    template_automation_ready,
    template_rank,
)
from app.services.template_fill_loaders import (
    load_document_evidence,
    memoized,
    MatterLookupError,
    load_current_retainer,
    load_estate_for_matter,
    load_matter_context,
    load_matter_parties,
)

logger = logging.getLogger(__name__)

JOB_KIND = "document_prefill"
EVENT_TYPE = "document_prefill_ready"
#: The bounded set of templates one run prepares, highest-ranked first.
MAX_TEMPLATES = 20
#: Field names reported per template; the count is always complete.
MAX_NAMED_FIELDS = 12

TRIGGER_EVENTS = (
    "matter_created",
    "intake_submitted",
    "intake_writeback_accepted",
    # A document was read (a scan through OCR included) and yielded values.
    "document_extracted",
)


async def _custom_field_evidence(
    db: AsyncSession, matter: Matter
) -> list[tuple[str, str]]:
    """The matter's and its client's custom-field values, for the digest.

    ``custom.*`` bindings are fill sources too, and the template is not known
    when the digest is computed, so every set value is included rather than
    only the fields some template happens to bind. Over-including can only
    schedule an advisory run; under-including would leave a changed value
    reporting as fresh.
    """

    evidence: list[tuple[str, str]] = []
    matter_rows = await db.scalars(
        select(MatterCustomFieldValue).where(
            MatterCustomFieldValue.tenant_id == matter.tenant_id,
            MatterCustomFieldValue.matter_id == matter.id,
        )
    )
    for row in matter_rows:
        evidence.append((f"matter:{row.field_definition_id}", str(row.value_json)))
    client_id = getattr(matter, "client_contact_id", None)
    if client_id:
        contact_rows = await db.scalars(
            select(ContactCustomFieldValue).where(
                ContactCustomFieldValue.tenant_id == matter.tenant_id,
                ContactCustomFieldValue.contact_id == client_id,
            )
        )
        for row in contact_rows:
            evidence.append((f"contact:{row.field_definition_id}", str(row.value_json)))
    return sorted(evidence)


async def _firm_profile_evidence(db: AsyncSession, tenant_id) -> list[tuple[str, str]]:
    """The firm profile values a ``firm.*`` binding can fill, for the digest."""

    from app.models.tenant import Tenant
    from app.routers.firm import get_firm_branding

    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        return []
    branding = await get_firm_branding(db, tenant) or {}
    return sorted((str(key), str(value)) for key, value in branding.items() if value)


async def matter_facts_digest(db: AsyncSession, matter: Matter) -> str:
    """A digest of every value Smart Fill could draw from this matter.

    Computed from the engine's own candidate index, so it changes exactly
    when a fill would: a renamed client, a new party row, an opened retainer.
    Custom-field values and the firm profile are fill sources the index does
    not carry, so they are hashed beside it. Field names and values feed the
    hash; nothing is stored.
    """

    tenant_id = matter.tenant_id
    parties = await load_matter_parties(db=db, tenant_id=tenant_id, matter=matter)
    retainer = await load_current_retainer(db=db, tenant_id=tenant_id, matter=matter)
    estate = await load_estate_for_matter(db=db, tenant_id=tenant_id, matter=matter)
    evidence = await load_document_evidence(db=db, tenant_id=tenant_id, matter=matter)
    index = engine.collect(
        engine.FillRecords(
            matter=matter,
            parties=parties,
            current_user=None,
            retainer=retainer,
            estate=estate,
            document_evidence=evidence,
        )
    )
    return digest_payload(
        [
            sorted((alias, item.suggested_value) for alias, item in index.items()),
            await _custom_field_evidence(db, matter),
            await _firm_profile_evidence(db, tenant_id),
        ]
    )


async def enqueue_document_prefill(
    db: AsyncSession,
    *,
    tenant_id,
    matter_id,
    trigger_event: str,
    actor_user_id,
):
    """Queue one prefill run for the matter's current facts, in the caller's transaction.

    Prefill is advisory, so a failure here must never lose the save that
    triggered it: the work runs inside a savepoint and a failure is logged
    and released. Returns the job row, or ``None`` when nothing was queued.
    """

    if trigger_event not in TRIGGER_EVENTS:
        raise ValueError("Unsupported document prefill trigger")
    tenant_uuid = uuid.UUID(str(tenant_id))
    try:
        async with db.begin_nested():
            matter = await load_matter_context(
                db=db, tenant_id=tenant_uuid, matter_id=str(matter_id)
            )
            facts_sha256 = await matter_facts_digest(db, matter)
            return await enqueue_job(
                db,
                tenant_id=tenant_uuid,
                kind=JOB_KIND,
                idempotency_key=f"{matter.id}:{facts_sha256}",
                requeue_failed=True,
                payload={
                    "matter_id": str(matter.id),
                    "actor_user_id": str(actor_user_id) if actor_user_id else None,
                    "trigger_event": trigger_event,
                    "facts_sha256": facts_sha256,
                    "as_of": datetime.now(timezone.utc).isoformat(),
                },
            )
    except Exception:
        logger.warning(
            "Document prefill could not be queued for matter %s (%s)",
            matter_id,
            trigger_event,
            exc_info=True,
        )
        return None


async def _candidate_templates(
    db: AsyncSession, matter: Matter
) -> list[tuple[DocumentTemplate, list[str]]]:
    rows = (
        (
            await db.execute(
                select(DocumentTemplate)
                .where(
                    DocumentTemplate.tenant_id == matter.tenant_id,
                    DocumentTemplate.is_active.is_(True),
                    DocumentTemplate.published_version_no.isnot(None),
                )
                .order_by(DocumentTemplate.id.asc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    ranked: list[tuple[int, DocumentTemplate, list[str]]] = []
    for template in rows:
        if not template_automation_ready(template):
            continue
        score, reasons = template_rank(template, matter)
        ranked.append((score, template, reasons))
    ranked.sort(key=lambda item: (-item[0], str(item[1].title), str(item[1].id)))
    return [(template, reasons) for _, template, reasons in ranked[:MAX_TEMPLATES]]


def _prepared_counts(prepared) -> tuple[int, int]:
    """``(fields, filled)`` over the fields the coverage read-out enumerates.

    ``PreparedFill.values`` also carries body-only placeholders and copied
    (``value_from``) fields that the coverage split deliberately leaves out of
    its total, so ``len(values)`` can exceed ``coverage.total`` and report more
    than 100% filled. Count the numerator over the same field set the
    denominator describes.
    """

    fields = prepared.coverage.total
    filled = sum(
        1
        for name in prepared.coverage.states
        if (item := prepared.by_variable.get(name))
        and item.suggested_value not in (None, "")
    )
    return fields, filled


async def prepare_matter_documents(
    db: AsyncSession, *, matter: Matter, actor: User | None
) -> list[dict[str, Any]]:
    """Fill every candidate template for ``matter`` and describe the result.

    Each entry carries counts and field names, never values. A template that
    cannot be filled (an unpublishable version, a renderer contract error) is
    reported with its reason rather than dropped, so a reader sees why a
    document they expected is missing.
    """

    from app.services.document_template_versions import published_template_view

    from app.services.fill_sessions import verified_counts

    summaries: list[dict[str, Any]] = []
    # One read of each record family for the whole run, however many
    # templates the matter has.
    loaders = memoized()
    verified = await verified_counts(
        db, tenant_id=matter.tenant_id, matter_id=matter.id
    )
    # The custom-field definitions, their values, and the firm branding do not
    # depend on the template, so read them once for the whole run and hand the
    # snapshot to each fill.
    custom_sources = await template_custom_fields.load(db, matter.tenant_id, matter)
    firm_profile = await template_firm_fields.load(db, matter.tenant_id)
    for template, reasons in await _candidate_templates(db, matter):
        entry: dict[str, Any] = {
            "template_id": str(template.id),
            "title": template.title,
            "format": template.format or "markdown",
            "category": template.category,
            "rank_reasons": reasons,
        }
        try:
            view = await published_template_view(db, template)
            prepared = await engine.prepare_fill(
                db,
                template=view,
                tenant_id=matter.tenant_id,
                matter=matter,
                actor=actor,
                loaders=loaders,
                custom_sources=custom_sources,
                firm_profile=firm_profile,
            )
        except (ValueError, MatterLookupError) as exc:
            entry["status"] = "unavailable"
            entry["reason"] = str(exc)[:200]
            summaries.append(entry)
            continue
        coverage = prepared.coverage
        fields, filled = _prepared_counts(prepared)
        review = sorted(
            item.variable
            for item in prepared.suggestions
            if item.suggested_value not in (None, "") and item.review_required
        )
        entry.update(
            {
                "status": "ready" if filled else "empty",
                "fields": fields,
                "filled": filled,
                "percent": round(100 * filled / fields) if fields else 100,
                "missing_required": len(prepared.missing_required),
                "missing_required_names": prepared.missing_required[:MAX_NAMED_FIELDS],
                "review": len(review),
                "review_names": review[:MAX_NAMED_FIELDS],
                "verified": int(verified.get(str(template.id), 0)),
                "coverage": dict(coverage.counts),
                "sources_loaded": list(prepared.sources_loaded),
                "collisions": [c.alias for c in prepared.collisions][:MAX_NAMED_FIELDS],
            }
        )
        summaries.append(entry)
    return summaries


def _summary_text(summaries: list[dict[str, Any]]) -> str:
    ready = [s for s in summaries if s.get("status") == "ready"]
    if not ready:
        return "No published template fills from this matter yet."
    parts = [
        f"{s['title']} ({s['filled']} of {s['fields']} fields, {s['percent']}%)"
        for s in ready[:5]
    ]
    more = len(ready) - len(parts)
    text = "; ".join(parts)
    if more > 0:
        text += f"; and {more} more"
    return text + "."


async def run_prefill_job(db: AsyncSession, job) -> dict[str, Any]:
    """The ``document_prefill`` handler: fill, then record what is ready."""

    payload = job.payload or {}
    tenant_id = job.tenant_id
    try:
        matter = await load_matter_context(
            db=db, tenant_id=tenant_id, matter_id=str(payload.get("matter_id") or "")
        )
    except MatterLookupError:
        matter = None
    if matter is None:
        return {"outcome": "blocked", "failure_code": "source_unavailable"}

    actor = None
    actor_id = payload.get("actor_user_id")
    if actor_id:
        try:
            actor_uuid = uuid.UUID(str(actor_id))
        except (ValueError, TypeError, AttributeError):
            actor_uuid = None
        if actor_uuid is not None:
            actor = await db.scalar(
                select(User).where(
                    User.id == actor_uuid,
                    User.tenant_id == tenant_id,
                    User.is_active.is_(True),
                )
            )
    created_by = actor.id if actor is not None else matter.user_id

    # Record the digest of the facts this run actually read, not the digest
    # captured when the job was enqueued: facts can move between the two, and
    # the readiness record must describe the run, not the request that queued it.
    facts_sha256 = await matter_facts_digest(db, matter)
    summaries = await prepare_matter_documents(db, matter=matter, actor=actor)
    ready = [s for s in summaries if s.get("status") == "ready"]
    prepared_at = datetime.now(timezone.utc)
    metadata = {
        "job_id": str(job.id),
        "trigger_event": payload.get("trigger_event"),
        "facts_sha256": facts_sha256,
        "prepared_at": prepared_at.isoformat(),
        "ready": len(ready),
        "templates": summaries,
    }
    db.add(
        MatterEvent(
            tenant_id=tenant_id,
            matter_id=matter.id,
            event_type=EVENT_TYPE,
            title=(
                f"{len(ready)} document{'s' if len(ready) != 1 else ''} ready to review"
                if ready
                else "No documents ready to review yet"
            ),
            content=_summary_text(summaries),
            note_type="system",
            created_by=created_by,
            metadata_json=metadata,
        )
    )
    await db.flush()
    return {"outcome": "prepared", "ready": len(ready), "templates": len(summaries)}


async def latest_readiness(
    db: AsyncSession, *, matter: Matter
) -> dict[str, Any] | None:
    """The newest readiness record for ``matter`` plus whether it is stale."""

    event = await db.scalar(
        select(MatterEvent)
        .where(
            MatterEvent.tenant_id == matter.tenant_id,
            MatterEvent.matter_id == matter.id,
            MatterEvent.event_type == EVENT_TYPE,
        )
        .order_by(MatterEvent.created_at.desc(), MatterEvent.id.desc())
        .limit(1)
    )
    if event is None:
        return None
    metadata = dict(event.metadata_json or {})
    # Reload through the engine's loader so the relationships the digest reads
    # are eagerly present whatever query the caller fetched the matter with.
    loaded = await load_matter_context(
        db=db, tenant_id=matter.tenant_id, matter_id=str(matter.id)
    )
    current = await matter_facts_digest(db, loaded)
    return {
        "event_id": str(event.id),
        "prepared_at": metadata.get("prepared_at") or event.created_at.isoformat(),
        "trigger_event": metadata.get("trigger_event"),
        "stale": metadata.get("facts_sha256") != current,
        "ready": int(metadata.get("ready") or 0),
        "templates": list(metadata.get("templates") or []),
    }
