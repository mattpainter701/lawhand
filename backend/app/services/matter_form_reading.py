"""Read a matter's scanned, hand-filled form against the template that printed it.

The matter side of ``template_form_reading``: find which templates this matter
has generated documents from (the ``document_generated`` events name them),
load the scan and the template version, read each field window, and return
the readings in the same shape ``matter_fact_extraction.propose`` returns, so
a matched field is accepted through the existing accept path and nothing new
writes to a record.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.models.document_template import DocumentTemplate
from app.models.plugin import MatterEvent
from app.services import matter_fact_extraction as facts
from app.services import template_form_reading as reading
from app.services.document_template_versions import get_version, published_template_view
from app.services.template_cards import canonical_path
from app.services.template_ocr import TemplateOcrError

MAX_SOURCES = 25
#: A crop read below this OCR confidence is offered to the vision model.
VISION_FLOOR = 0.35
VISION_CONFIDENCE = 0.6
#: Wall-clock ceiling for the whole vision pass in one request. The clips are
#: read sequentially and each is a metered provider call, so without a budget a
#: slow provider could hold the request for many minutes. Fields left unread
#: past the budget stay blank for a manual read.
VISION_TIME_BUDGET_SECONDS = 90


async def _read_unreadable_clips(
    db, user, readings, *, document_sha256: str
) -> list[str]:
    """Send the clips OCR could not read to the vision model, if allowed."""

    from app.database import set_tenant_context
    from app.models.tenant import TenantSettings
    from app.services import intake_extraction_ai

    clips = [item for item in readings if item.clip_png]
    if not clips:
        return []
    settings_row = await db.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == user.tenant_id)
    )
    allowed = facts.ai_extraction_enabled(settings_row)
    read = 0
    skipped = 0
    failure: str | None = None
    deadline = time.monotonic() + VISION_TIME_BUDGET_SECONDS
    for item in clips:
        if failure is None and time.monotonic() < deadline:
            try:
                value = await intake_extraction_ai.read_field_clip(
                    db=db,
                    user=user,
                    png_bytes=item.clip_png,
                    label=item.label,
                    document_sha256=document_sha256,
                    tenant_ai_enabled=allowed,
                )
            except intake_extraction_ai.IntakeExtractionUnavailable as exc:
                failure = str(exc)
                value = None
            if value:
                item.text = value
                item.confidence = VISION_CONFIDENCE
                item.read_by = "vision"
                read += 1
        elif failure is None:
            skipped += 1
        item.clip_png = None
    # The vision read commits its usage rows, which drops the transaction's
    # tenant context; restore it before the target lookups that follow.
    await set_tenant_context(db, str(user.tenant_id))
    if failure:
        return [failure]
    notes = []
    if read:
        notes.append(
            f"AI read {read} field(s) OCR could not. Check each against its clip before accepting."
        )
    else:
        notes.append("AI could not read the remaining fields either.")
    if skipped:
        notes.append(
            f"{skipped} field(s) were left blank because the AI read reached its "
            "time budget; read them by hand."
        )
    return notes


async def form_sources(db, *, tenant_id, matter_id) -> list[dict[str, Any]]:
    """The templates this matter has generated documents from, newest first."""

    rows = await db.execute(
        select(MatterEvent.metadata_json, MatterEvent.created_at)
        .where(
            MatterEvent.tenant_id == uuid.UUID(str(tenant_id)),
            MatterEvent.matter_id == uuid.UUID(str(matter_id)),
            MatterEvent.event_type == "document_generated",
        )
        .order_by(MatterEvent.created_at.desc())
        .limit(200)
    )
    seen: set[tuple[str, int | None]] = set()
    sources: list[dict[str, Any]] = []
    for metadata, created_at in rows.all():
        metadata = metadata or {}
        template_id = str(metadata.get("template_id") or "")
        if not template_id or str(metadata.get("output_format") or "pdf") != "pdf":
            continue
        try:
            version_no = int(metadata.get("template_version_no"))
        except (TypeError, ValueError):
            version_no = None
        key = (template_id, version_no)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "template_id": template_id,
                "template_title": str(metadata.get("template_title") or ""),
                "version_no": version_no,
                "output_filename": str(metadata.get("output_filename") or ""),
                "generated_at": created_at.isoformat() if created_at else None,
            }
        )
        if len(sources) >= MAX_SOURCES:
            break
    return sources


def _target_for(window: reading.FieldWindow, targets) -> facts.FactTarget | None:
    if window.binding:
        try:
            path = canonical_path(window.binding)
        except Exception:
            path = window.binding
        for target in targets:
            if target.binding in {path, window.binding}:
                return target
    keys = {facts.normalize_text(window.name), facts.normalize_text(window.label)}
    keys.discard("")
    for target in targets:
        if keys & set(target.match_keys):
            return target
    return None


async def read_against_form(
    db,
    user,
    matter_id,
    document_id,
    *,
    template_id,
    version_no=None,
    use_ai: bool = False,
) -> dict[str, Any]:
    """Propose values for a scan by reading each field window of its template.

    ``use_ai`` sends the clips OCR could not read to the vision model, one
    metered call per clip, when the platform has one and the firm allowed the
    model to read its documents. It only ever adds candidates for the same
    human review.
    """

    from app.routers.document_templates import _verified_template_source

    tenant_id = uuid.UUID(str(user.tenant_id))
    matter, document, content = await facts._load_source(
        db, user, matter_id, document_id
    )
    template = await db.scalar(
        select(DocumentTemplate).where(
            DocumentTemplate.tenant_id == tenant_id,
            DocumentTemplate.id == uuid.UUID(str(template_id)),
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if version_no is not None:
        version = await get_version(
            db, tenant_id=tenant_id, template_id=template.id, version_no=int(version_no)
        )
        if version is None:
            raise HTTPException(status_code=404, detail="Template version not found")
        if version.source_sha256 != template.source_sha256:
            raise HTTPException(
                status_code=409,
                detail="That version's form differs from the current template source; read against the current published version instead.",
            )
        schema = version.variable_schema or {}
        used_version = int(version.version_no)
    else:
        try:
            view = await published_template_view(db, template)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        schema = view.variable_schema or {}
        used_version = int(view.current_version_no)
    if str(template.format or "").lower() not in {"pdf", "image"}:
        raise HTTPException(
            status_code=422,
            detail="Only a PDF form can be read field by field; this template is not one.",
        )
    windows = reading.field_windows(schema)
    if not windows:
        raise HTTPException(
            status_code=422,
            detail="This template records no field positions to read from.",
        )
    source = await _verified_template_source(template)
    try:
        scan = await asyncio.to_thread(
            reading.normalize_scan, content, document.filename
        )
        sizes = await asyncio.to_thread(reading.page_sizes, source)
        readings = await asyncio.to_thread(
            reading.read_scan,
            scan,
            windows,
            template_page_sizes=sizes,
            keep_clips_below=VISION_FLOOR if use_ai else None,
            max_clips=int(get_settings().INTAKE_EXTRACTION_VISION_MAX_FIELDS),
        )
    except TemplateOcrError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    vision_notes: list[str] = []
    if use_ai:
        vision_notes = await _read_unreadable_clips(
            db, user, readings, document_sha256=document.document_sha256 or ""
        )

    targets = await facts.build_targets(db, tenant_id)
    candidates: dict[str, list[facts.Candidate]] = {}
    matched: dict[str, str] = {}
    for item in readings:
        target = _target_for(item, targets)
        if target is None or not item.text:
            continue
        value = target.normalize(item.text)
        if value is None:
            continue
        matched[item.name] = target.key
        candidates.setdefault(target.key, []).append(
            facts.Candidate(
                str(value),
                "ocr_field_vision" if item.read_by == "vision" else "ocr_field",
                f"field:{item.name}",
                item.confidence,
            )
        )

    proposals = []
    for target in targets:
        found = candidates.get(target.key)
        if not found:
            continue
        distinct = facts._distinct(found)
        current = (
            await facts._custom_value_row(db, tenant_id, matter, target)
            if target.kind.startswith("custom_")
            else facts._standard_current(matter, target)
        )
        best = max(distinct, key=lambda candidate: candidate.confidence)
        proposals.append(
            {
                "target_key": target.key,
                "label": target.label,
                "kind": target.kind,
                "binding": target.binding,
                "entity": target.entity,
                "field": target.field,
                "field_type": target.field_type,
                "binding_label": target.label,
                "value": best.value,
                "current_value": facts._custom_display(current)
                if target.kind.startswith("custom_")
                else current,
                "status": "conflicting_sources" if len(distinct) > 1 else "suggested",
                "confidence": best.confidence,
                "source_kind": best.source_kind,
                "source_locator": best.source_locator,
                "values": [
                    {
                        "value": candidate.value,
                        "source_kind": candidate.source_kind,
                        "source_locator": candidate.source_locator,
                        "confidence": candidate.confidence,
                    }
                    for candidate in distinct
                ],
                "review_required": True,
            }
        )
    thumbnails = {
        item.name: item.thumbnail_png_b64 for item in readings if item.thumbnail_png_b64
    }
    for proposal in proposals:
        field_name = proposal["source_locator"].split(":", 1)[1]
        proposal["thumbnail_png_b64"] = thumbnails.get(field_name)
    warnings = [
        "Values were read from a scan, field by field, against the form it was printed from. Each carries the confidence it was read at; check the thumbnail before accepting."
    ]
    unread = [item.name for item in readings if not item.text]
    if unread:
        warnings.append(f"{len(unread)} field(s) could not be read from the scan.")
    warnings.extend(vision_notes)
    return {
        "source_document_id": str(document.id),
        "source_filename": document.filename,
        "template_id": str(template.id),
        "template_title": template.title,
        "template_version_no": used_version,
        "alignment": reading.ALIGNMENT,
        "candidates": proposals,
        "readings": [
            {**item.as_dict(), "target_key": matched.get(item.name)}
            for item in readings
        ],
        "warnings": warnings,
        "review_required": True,
    }
