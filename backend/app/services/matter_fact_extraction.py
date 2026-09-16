"""Deterministic matter facts from an intake document, proposed for review.

A signed fee agreement, a completed intake form, or a client questionnaire that
a person has already filled in is a *data source*: the answers it carries belong
on the matter and client records so every later template fills itself. This
module reads that source and proposes field values; it never writes one. A staff
member reviews each proposal and accepts it, and acceptance re-reads and
re-extracts the source so the value a reviewer confirms must still be the value
the document yields.

Sources are read in descending order of trust:

* AcroForm widget values a client typed into a digital form (exact);
* exact ``Label: value`` lines, the same conservative rule as
  ``template_fact_review`` (exact, case-insensitive label);
* a narrow set of format-validated patterns (email, phone, ZIP) that only ever
  propose a value for the client contact, and only when the text yields exactly
  one candidate.

Nothing here guesses. An ambiguous target is reported as ``conflicting_sources``
rather than averaged or chosen, and a target the source does not mention yields
no proposal at all. Value patterns are matched against bounded extracted text;
no model runs, so a scan with no text layer proposes nothing until OCR text is
supplied.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.database import set_tenant_context
from app.models.configurable_workflow import (
    ContactCustomFieldValue,
    CustomFieldDefinition,
    MatterCustomFieldValue,
)
from app.models.matter_document import MatterDocument
from app.models.plugin import Matter, MatterEvent
from app.models.task import Task
from app.models.tenant import TenantSettings
from app.schemas.configurable_workflow import normalized_field_value
from app.services import intake_writeback, template_custom_fields
from app.services.configurable_workflows import value_hmac
from app.services.docx_templates import validate_docx_package
from app.services.matter_file_store import MatterFileReadError, MatterFileStore
from app.services.pdf_templates import TemplatePdfError, read_pdf_form_values
from app.services.template_bindings import binding_label
from app.utils.text_processing import extract_text

#: A source document larger than this is not scanned for facts. Intake forms
#: are small; a bound large enough to hold one keeps a hostile upload from
#: turning every review into a full-text scan.
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_TEXT = 200_000


class FactReviewUnavailable(RuntimeError):
    """The source cannot be read well enough to propose facts from it."""


class FactDecision(BaseModel):
    """One reviewed value to write to a record."""

    target_key: str = Field(max_length=120)
    value: str | bool = Field(union_mode="left_to_right")
    replace_existing: bool = False


@dataclass(frozen=True)
class FactTarget:
    """One record field an intake document may supply a value for."""

    key: str
    label: str
    binding: str
    kind: str
    entity: str
    field: str
    field_type: str
    options: tuple
    max_length: int | None
    match_keys: frozenset

    def normalize(self, raw):
        """Return the canonical stored value, or ``None`` when unsupported."""

        if self.kind == "standard":
            text = " ".join(str(raw).split())
            if not text or (
                self.max_length is not None and len(text) > self.max_length
            ):
                return None
            return text
        if self.field_type == "boolean" and isinstance(raw, str):
            folded = raw.strip().lower()
            if folded in {"yes", "true"}:
                raw = True
            elif folded in {"no", "false"}:
                raw = False
        try:
            return normalized_field_value(self.field_type, list(self.options), raw)
        except ValueError:
            return None


def normalize_text(value) -> str:
    """Fold a label for exact comparison; never for fuzzy matching."""

    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


#: Accepted labels for each standard binding, beyond the label the catalogue
#: already gives it. Intake forms are written by people, so "Case No." and
#: "Docket Number" both mean one thing; a synonym is listed only when it is
#: unambiguous, and no entry is a verb or a stray word.
_STANDARD_LABELS = {
    "client.name": ("client name", "client", "name", "full name", "applicant"),
    "client.email": ("email", "e mail", "email address", "client email"),
    "client.phone": (
        "phone",
        "phone number",
        "telephone",
        "cell",
        "cell phone",
        "mobile",
    ),
    "client.address.street": (
        "address",
        "street",
        "street address",
        "address line 1",
        "mailing address",
    ),
    "client.address.city": ("city", "town"),
    "client.address.state": ("state", "province"),
    "client.address.zip": ("zip", "zip code", "postal code", "postcode"),
    "matter.name": ("matter name", "case name", "case title"),
    "matter.type": ("matter type", "case type", "type of matter", "practice area"),
    "matter.description": ("description", "matter description", "nature of matter"),
    "matter.role": ("represented side", "matter role", "client role"),
    "matter.counterparty": (
        "counterparty",
        "opposing party",
        "adverse party",
        "other parties",
    ),
    "matter.court": ("court", "court name", "forum"),
    "matter.case_number": (
        "case number",
        "case no",
        "docket number",
        "docket no",
        "cause number",
    ),
    "matter.judge": ("judge", "judge name"),
    "matter.jurisdiction": ("jurisdiction", "county", "venue"),
}

_STANDARD_PATTERNS = {
    "client.email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "client.phone": re.compile(
        r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"
    ),
    "client.address.zip": re.compile(r"\b\d{5}(?:-\d{4})?\b"),
}


def _standard_match_keys(binding: str) -> frozenset:
    keys = {normalize_text(binding_label(binding) or binding)}
    keys.update(normalize_text(token) for token in binding.split("."))
    for label in _STANDARD_LABELS.get(binding, ()):
        keys.add(normalize_text(label))
    keys.discard("")
    return frozenset(keys)


async def build_targets(db, tenant_id) -> list[FactTarget]:
    """Every tenant field an intake document may propose a value for."""

    targets: list[FactTarget] = []
    for binding, spec in intake_writeback.FIELD_TARGETS.items():
        targets.append(
            FactTarget(
                key=binding,
                label=binding_label(binding) or spec["field"],
                binding=binding,
                kind="standard",
                entity=spec["entity"],
                field=spec["field"],
                field_type="text",
                options=(),
                max_length=spec.get("max"),
                match_keys=_standard_match_keys(binding),
            )
        )
    for definition in await template_custom_fields.definitions(db, tenant_id):
        binding = f"custom.{definition.entity_type}.{definition.id}"
        targets.append(
            FactTarget(
                key=binding,
                label=definition.label or definition.field_key,
                binding=binding,
                kind=f"custom_{definition.entity_type}",
                entity=definition.entity_type,
                field=str(definition.id),
                field_type=definition.field_type,
                options=tuple(definition.options_json or ()),
                max_length=None,
                match_keys=frozenset(
                    {
                        normalize_text(definition.label),
                        normalize_text(definition.field_key),
                    }
                    - {""}
                ),
            )
        )
    return targets


@dataclass(frozen=True)
class Candidate:
    value: str
    source_kind: str
    source_locator: str
    confidence: float


def _form_candidates(form_values, targets):
    found: dict[str, list[Candidate]] = {}
    for entry in form_values:
        keys = {
            normalize_text(entry.get("label")),
            normalize_text(entry.get("pdf_field_name")),
        }
        keys.discard("")
        raw = str(entry.get("value", "")).strip()
        if not raw:
            continue
        locator = f"field:{entry.get('pdf_field_name')}"
        for target in targets:
            if not keys.intersection(target.match_keys):
                continue
            value = target.normalize(raw)
            if value is None:
                continue
            found.setdefault(target.key, []).append(
                Candidate(str(value), "acroform", locator, 1.0)
            )
    return found


def _label_line_candidates(text, targets):
    """Exact ``Label: value`` lines, matched against a target's own labels.

    Only an exact, case-insensitive label prefix counts, and only a single
    colon split; a line with no colon, or a longer sentence that merely starts
    with the label, is not an answer.
    """

    found: dict[str, list[Candidate]] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        prefix, separator, raw = line.partition(":")
        if not separator:
            continue
        label = normalize_text(prefix)
        if not label or len(label) > 80:
            continue
        raw = raw.strip()
        if not raw:
            continue
        for target in targets:
            if label not in target.match_keys:
                continue
            value = target.normalize(raw)
            if value is None:
                continue
            found.setdefault(target.key, []).append(
                Candidate(str(value), "label_value", f"line:{line_number}", 1.0)
            )
    return found


def _pattern_candidates(text, targets):
    """Format-validated client values, only when the text is unambiguous."""

    found: dict[str, list[Candidate]] = {}
    for target in targets:
        pattern = _STANDARD_PATTERNS.get(target.key)
        if pattern is None:
            continue
        matches = {match.group(0).strip() for match in pattern.finditer(text)}
        matches.discard("")
        if len(matches) != 1:
            continue
        value = target.normalize(next(iter(matches)))
        if value is None:
            continue
        found.setdefault(target.key, []).append(
            Candidate(str(value), "regex", "text", 0.6)
        )
    return found


def _merge(*sources):
    merged: dict[str, list[Candidate]] = {}
    for source in sources:
        for key, candidates in source.items():
            merged.setdefault(key, []).extend(candidates)
    return merged


def extract_candidates(*, text, form_values, targets):
    """Return the distinct values each target's source text supports.

    Pure and free of any record access: the caller decides what is already on
    the record and what a reviewer should see.
    """

    return _merge(
        _form_candidates(form_values, targets),
        _label_line_candidates(text, targets),
        _pattern_candidates(text, targets),
    )


def _distinct(candidates):
    by_value: dict[str, Candidate] = {}
    for candidate in candidates:
        folded = candidate.value.casefold()
        existing = by_value.get(folded)
        if existing is None or candidate.confidence > existing.confidence:
            by_value[folded] = candidate
    return list(by_value.values())


async def _load_source(db, user, matter_id, document_id):
    """Read the exact source bytes, restoring tenant context the provider may clear."""

    tenant_id = uuid.UUID(str(user.tenant_id))
    matter = await db.scalar(
        select(Matter)
        .options(selectinload(Matter.client))
        .where(Matter.tenant_id == tenant_id, Matter.id == matter_id)
    )
    document = await db.scalar(
        select(MatterDocument).where(
            MatterDocument.tenant_id == tenant_id,
            MatterDocument.matter_id == matter_id,
            MatterDocument.id == document_id,
        )
    )
    if matter is None or document is None:
        raise HTTPException(status_code=404, detail="Matter or source not found")
    if document.storage_state in {"conflict", "deleted", "pending"}:
        raise HTTPException(
            status_code=409,
            detail="Reconcile the source document before reading its details.",
        )
    if not document.filename.lower().endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(
            status_code=422, detail="Choose a PDF, Word, or plain-text source"
        )
    stable_user = SimpleNamespace(id=user.id, tenant_id=tenant_id)
    try:
        content = await MatterFileStore().read_matter_file_bytes(
            db=db,
            tenant_id=str(tenant_id),
            document=document,
            expected_sha256=document.document_sha256
            if document.storage_state == "verified"
            else None,
            max_bytes=MAX_SOURCE_BYTES,
        )
    except MatterFileReadError as exc:
        raise HTTPException(
            status_code=409,
            detail="The exact source could not be verified; reopen or reconcile it",
        ) from exc
    await set_tenant_context(db, str(stable_user.tenant_id))
    return matter, document, content


def _extract_text(document, content) -> str:
    try:
        if document.filename.lower().endswith(".docx"):
            validate_docx_package(content)
        text = extract_text(
            content,
            document.content_type or "",
            document.filename,
            max_pdf_pages=100,
            max_pdf_chars=MAX_SOURCE_TEXT,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Source text could not be read. Review the original and enter the value manually.",
        ) from exc
    return text[:MAX_SOURCE_TEXT]


def _form_values(document, content):
    if not document.filename.lower().endswith(".pdf"):
        return []
    try:
        return read_pdf_form_values(content)
    except TemplatePdfError:
        # A filled, scanned, or unusual PDF can still carry label:value text;
        # failing to read widgets is not failing to read the document.
        return []


def _standard_current(matter, target):
    contact = matter.client
    if target.entity == "contact":
        if contact is None:
            return None
        return intake_writeback._current_value(contact, "contact", target.field)
    return intake_writeback._current_value(matter, "matter", target.field)


async def _custom_value_row(db, tenant_id, matter, target):
    definition_id = uuid.UUID(target.field)
    if target.kind == "custom_matter":
        return await db.scalar(
            select(MatterCustomFieldValue).where(
                MatterCustomFieldValue.tenant_id == tenant_id,
                MatterCustomFieldValue.matter_id == matter.id,
                MatterCustomFieldValue.field_definition_id == definition_id,
            )
        )
    contact_id = getattr(matter, "client_contact_id", None)
    if contact_id is None:
        return None
    return await db.scalar(
        select(ContactCustomFieldValue).where(
            ContactCustomFieldValue.tenant_id == tenant_id,
            ContactCustomFieldValue.contact_id == contact_id,
            ContactCustomFieldValue.field_definition_id == definition_id,
        )
    )


async def propose(db, user, matter_id, document_id):  # noqa: C901 - one review pass
    """Build every reviewed proposal the source supports for this matter."""

    tenant_id = uuid.UUID(str(user.tenant_id))
    matter, document, content = await _load_source(db, user, matter_id, document_id)
    targets = await build_targets(db, tenant_id)
    text = _extract_text(document, content)
    candidates = extract_candidates(
        text=text, form_values=_form_values(document, content), targets=targets
    )

    warnings: list[str] = []
    if not text.strip() and not candidates:
        warnings.append(
            "No text layer or form values were found. A scan needs OCR before its answers can be proposed."
        )

    proposals = []
    for target in targets:
        candidates_for_target = candidates.get(target.key)
        if not candidates_for_target:
            continue
        distinct = _distinct(candidates_for_target)
        current = (
            await _custom_value_row(db, tenant_id, matter, target)
            if target.kind.startswith("custom_")
            else _standard_current(matter, target)
        )
        # Only a custom-field row needs unwrapping; a standard target already
        # resolves to the display string the reviewer compares against.
        if target.kind.startswith("custom_"):
            current_display = _custom_display(current)
        else:
            current_display = current
        if len(distinct) > 1:
            status = "conflicting_sources"
        else:
            status = "suggested"
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
                "current_value": current_display,
                "status": status,
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

    return {
        "source_document_id": str(document.id),
        "source_filename": document.filename,
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "candidates": proposals,
        "warnings": warnings,
        "review_required": True,
    }


def _custom_display(row):
    if row is None:
        return None
    value = row.value_json
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _find_proposal(proposal, target_key):
    for entry in proposal["candidates"]:
        if entry["target_key"] == target_key:
            return entry
    return None


async def accept(db, user, matter_id, document_id, payload: FactDecision):
    """Apply one reviewed value after re-proving it against the live source.

    The source is re-read and re-extracted, so a value that the document no
    longer yields is refused rather than written. A differing value already on
    the record is refused until the reviewer explicitly asks to replace it.
    """

    tenant_id = uuid.UUID(str(user.tenant_id))
    matter, document, content = await _load_source(db, user, matter_id, document_id)
    targets = await build_targets(db, tenant_id)
    target = next((entry for entry in targets if entry.key == payload.target_key), None)
    if target is None:
        raise HTTPException(
            status_code=404, detail="That matter detail is no longer available."
        )

    text = _extract_text(document, content)
    candidates = extract_candidates(
        text=text, form_values=_form_values(document, content), targets=targets
    ).get(target.key, [])
    live = target.normalize(payload.value)
    if live is None:
        raise HTTPException(status_code=422, detail="That value is not supported.")
    supported = {candidate.value.casefold() for candidate in candidates}
    if str(live).casefold() not in supported:
        raise HTTPException(
            status_code=409,
            detail="The source no longer contains that value. Read the document again before accepting.",
        )

    if target.kind.startswith("custom_"):
        return await _accept_custom(db, user, matter, target, live, payload)
    return await _accept_standard(db, user, matter, target, live, payload)


async def _accept_standard(db, user, matter, target, live, payload):
    contact = matter.client
    if target.entity == "contact" and contact is None:
        raise HTTPException(
            status_code=409,
            detail="This matter has no client contact to write that detail to.",
        )
    record = contact if target.entity == "contact" else matter
    previous = intake_writeback._current_value(record, target.entity, target.field)
    if (
        previous is not None
        and intake_writeback._normalized(previous) != intake_writeback._normalized(live)
        and not payload.replace_existing
    ):
        raise HTTPException(
            status_code=409,
            detail="An existing value differs. Confirm replacement after reviewing the conflict.",
        )
    intake_writeback._apply_value(
        contact,
        matter,
        {"entity": target.entity, "field": target.field, "proposed": live},
    )
    _record_event(db, user, matter, target, live, previous, method="standard_record")
    await db.commit()
    return {
        "status": "accepted",
        "target_key": target.key,
        "value": live,
        "replaced": previous is not None
        and intake_writeback._normalized(previous)
        != intake_writeback._normalized(live),
    }


async def _accept_custom(db, user, matter, target, live, payload):
    definition_id = uuid.UUID(target.field)
    definition = await db.scalar(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.tenant_id == user.tenant_id,
            CustomFieldDefinition.id == definition_id,
            CustomFieldDefinition.active.is_(True),
            CustomFieldDefinition.sensitive.is_(False),
        )
    )
    if definition is None:
        raise HTTPException(
            status_code=404, detail="That matter detail is unavailable."
        )
    model = (
        MatterCustomFieldValue
        if target.kind == "custom_matter"
        else ContactCustomFieldValue
    )
    owner_column = (
        model.matter_id if target.kind == "custom_matter" else model.contact_id
    )
    owner_id = matter.id if target.kind == "custom_matter" else matter.client_contact_id
    if owner_id is None:
        raise HTTPException(
            status_code=409,
            detail="This matter has no client contact to write that detail to.",
        )
    previous_row = await db.scalar(
        select(model).where(
            model.tenant_id == user.tenant_id,
            owner_column == owner_id,
            model.field_definition_id == definition_id,
        )
    )
    previous = previous_row.value_json if previous_row else None
    if previous != live and previous is not None and not payload.replace_existing:
        raise HTTPException(
            status_code=409,
            detail="An existing value differs. Confirm replacement after reviewing the conflict.",
        )
    stamp = datetime.now(timezone.utc)
    values = {
        "tenant_id": user.tenant_id,
        str(owner_column.name): owner_id,
        "field_definition_id": definition_id,
        "entity_type": target.entity,
        "value_json": live,
        "value_hmac": value_hmac(live),
        "updated_by_user_id": user.id,
        "updated_at": stamp,
    }
    constraint = (
        "uq_matter_custom_field_values_field"
        if target.kind == "custom_matter"
        else "uq_contact_custom_field_values_field"
    )
    await db.execute(
        insert(model)
        .values(**values)
        .on_conflict_do_update(
            constraint=constraint,
            set_={
                key: values[key]
                for key in (
                    "value_json",
                    "value_hmac",
                    "updated_by_user_id",
                    "updated_at",
                )
            },
        )
    )
    _record_event(db, user, matter, target, live, previous, method="custom_record")
    await db.commit()
    return {
        "status": "accepted",
        "target_key": target.key,
        "value": live,
        "replaced": previous is not None and previous != live,
    }


def _record_event(db, user, matter, target, value, previous, *, method):
    """Audit the reviewed write without copying the value into the event.

    ``template_fact_review`` deliberately stores HMACs, not raw values, so a
    matter event is not a second copy of a client's SSN-adjacent answer. The
    same rule holds here: the event names the field and binds the accepted
    value by HMAC.
    """

    db.add(
        MatterEvent(
            tenant_id=user.tenant_id,
            matter_id=matter.id,
            event_type="matter_fact_extracted",
            title=f"Intake detail accepted: {target.label}"[:200],
            content=(
                "A staff member reviewed an intake document and accepted a "
                "matter detail."
            ),
            created_by=user.id,
            metadata_json={
                "target_key": target.key,
                "method": method,
                "accepted_value_hmac": value_hmac(value),
                "previous_present": previous is not None,
            },
        )
    )


#: Per-tenant switch. Off unless the firm turns it on, so every existing tenant
#: is unchanged on deploy and a firm opts in after seeing what it proposes.
FLAG_SECTION = "intake_fact_extraction"


def extraction_enabled(settings_row) -> bool:
    """Whether a tenant has turned on automatic intake-document extraction."""

    if settings_row is None:
        return False
    config = settings_row.custom_config or {}
    section = config.get(FLAG_SECTION) or {}
    return bool(section.get("enabled"))


async def tenant_enabled(db, tenant_id) -> bool:
    row = await db.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    return extraction_enabled(row)


TASK_KIND = "matter_fact_extraction"


async def extract_and_queue(
    *, db, tenant_id, matter_id, document_id, actor_id=None
) -> dict:
    """Run one extraction pass and raise a review task when it found anything.

    Called from the durable-job worker, so a "skip" — an unreadable source, a
    source the firm already reconciled, or simply no supported answers — is a
    normal outcome, not an error to retry. The task is the review queue: a
    person opens the document and accepts or rejects each proposed value.
    """

    user = SimpleNamespace(id=actor_id, tenant_id=tenant_id)
    try:
        proposal = await propose(db, user, matter_id, document_id)
    except HTTPException as exc:
        return {"status": "skipped", "reason": exc.detail}
    if not proposal["candidates"]:
        return {"status": "no_candidates", "document_id": str(document_id)}

    document = await db.scalar(
        select(MatterDocument).where(
            MatterDocument.tenant_id == tenant_id,
            MatterDocument.id == document_id,
        )
    )
    matter = await db.scalar(
        select(Matter).where(Matter.tenant_id == tenant_id, Matter.id == matter_id)
    )
    if document is None or matter is None:
        return {"status": "skipped", "reason": "Matter or source not found"}
    created_by = (
        actor_id
        or getattr(document, "uploaded_by_user_id", None)
        or getattr(matter, "user_id", None)
    )
    task_id = uuid.uuid5(document_id, TASK_KIND)
    existing = await db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.tenant_id == tenant_id)
        .with_for_update()
    )
    if existing is None:
        db.add(
            Task(
                id=task_id,
                tenant_id=tenant_id,
                matter_id=matter_id,
                contact_id=getattr(matter, "client_contact_id", None),
                title=f"Review intake details: {document.filename}"[:500],
                description=(
                    "A filled intake document carries answers this matter does "
                    "not yet hold. Open the document and accept or reject each "
                    "proposed detail; nothing is written until you accept it."
                ),
                task_type="review",
                status="pending",
                priority="medium",
                assigned_to_user_id=getattr(document, "uploaded_by_user_id", None),
                created_by_user_id=created_by,
                source="intake",
                external_ref=f"document_facts:{document_id}",
                pending_action={
                    "type": TASK_KIND,
                    "matter_id": str(matter_id),
                    "document_id": str(document_id),
                },
            )
        )
        await db.commit()
    return {
        "status": "queued",
        "document_id": str(document_id),
        "candidate_count": len(proposal["candidates"]),
        "task_id": str(task_id),
    }
