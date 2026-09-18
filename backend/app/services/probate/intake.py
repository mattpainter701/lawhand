"""Turn probate questionnaire answers into :class:`ProbateFacts`.

The same question keys arrive three ways — the portal questionnaire (typed
answers), a returned fillable "ND Probate Intake Questionnaire" PDF (whatever
the person typed or ticked), and staff keying in a mailed paper copy — and
all three land here. Nothing in this module writes to an estate: ``harvest``
reads, and the Probate tab's "pull from intake" action decides what to keep.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.practice_resolution import PROBATE_QUESTIONS
from app.services.probate.determination import determine
from app.services.probate.facts import ProbateFacts, from_json, is_blank, to_json

#: Question key -> facts field, where the names differ.
_KEY_TO_FIELD = {
    "will_date": "will_execution_date",
    "heirs_list": "heirs",
    "priority_persons": "persons_with_prior_or_equal_priority",
}

_QUESTION_KEYS = tuple(q.key for q in PROBATE_QUESTIONS)
_YES_NO_KEYS = tuple(q.key for q in PROBATE_QUESTIONS if q.kind == "yes_no")


def has_probate_answers(values: Mapping[str, Any] | None) -> bool:
    """True when any probate question was answered (not merely present)."""

    if not values:
        return False
    for key in _QUESTION_KEYS:
        if str(values.get(key) or "").strip():
            return True
        if (
            str(values.get(f"{key}_yes") or "").strip()
            or str(values.get(f"{key}_no") or "").strip()
        ):
            return True
    return False


def _yes_no(values: Mapping[str, Any], key: str) -> Any:
    """Read a yes/no answer from a radio value or a pair of checkboxes."""

    direct = values.get(key)
    if direct is not None and str(direct).strip():
        return direct
    yes = str(values.get(f"{key}_yes") or "").strip().lower()
    no = str(values.get(f"{key}_no") or "").strip().lower()
    if yes in {"true", "yes", "on", "1", "x"} and no not in {
        "true",
        "yes",
        "on",
        "1",
        "x",
    }:
        return "yes"
    if no in {"true", "yes", "on", "1", "x"} and yes not in {
        "true",
        "yes",
        "on",
        "1",
        "x",
    }:
        return "no"
    return None


def facts_from_values(values: Mapping[str, Any] | None) -> ProbateFacts:
    """Map answers keyed by question key onto the facts dataclass."""

    if not values:
        return ProbateFacts()
    payload: dict[str, Any] = {}
    for key in _QUESTION_KEYS:
        raw = _yes_no(values, key) if key in _YES_NO_KEYS else values.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        payload[_KEY_TO_FIELD.get(key, key)] = raw
    return from_json(payload)


def preview(values: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Facts plus determination for a submitted questionnaire, or ``None``."""

    if not has_probate_answers(values):
        return None
    facts = facts_from_values(values)
    if is_blank(facts):
        return None
    determination = determine(facts)
    return {
        "facts": to_json(facts),
        "track": determination.track,
        "label": determination.label,
        "missing_facts": list(determination.missing_facts),
        "warnings": list(determination.warnings),
    }


def values_from_pdf_fields(form_values: list[dict[str, Any]]) -> dict[str, str]:
    """``read_pdf_form_values`` output keyed by field name, for the authored PDF."""

    return {
        str(entry.get("pdf_field_name") or ""): str(entry.get("value") or "")
        for entry in form_values
        if entry.get("pdf_field_name")
    }


async def harvest(db, user, estate) -> tuple[ProbateFacts, list[dict[str, Any]]]:
    """Collect every probate answer the estate's matter has received.

    Returns the merged facts (portal answers first, then each returned PDF
    questionnaire filling gaps) and a source list for the workbench so staff
    can see where a value came from. A matter with no packet yields blank
    facts and no sources; it is not an error.
    """

    from sqlalchemy import select

    from app.models.matter_document import MatterDocument
    from app.models.matter_intake import MatterIntake
    from app.services import matter_fact_extraction
    from app.services.pdf_templates import TemplatePdfError, read_pdf_form_values
    from app.services.probate.facts import merge

    facts = ProbateFacts()
    sources: list[dict[str, Any]] = []
    if not getattr(estate, "matter_id", None):
        return facts, sources
    packet = await db.scalar(
        select(MatterIntake).where(
            MatterIntake.tenant_id == estate.tenant_id,
            MatterIntake.matter_id == estate.matter_id,
        )
    )
    if packet is None:
        return facts, sources
    if has_probate_answers(packet.answers):
        facts = merge(facts, facts_from_values(packet.answers))
        sources.append(
            {
                "kind": "portal_questionnaire",
                "packet_id": str(packet.id),
                "completed_at": packet.completed_at.isoformat()
                if packet.completed_at
                else None,
            }
        )
    for key, requirement in (packet.requirements or {}).items():
        document_id = requirement.get("submitted_document_id")
        if not document_id:
            continue
        document = await db.scalar(
            select(MatterDocument).where(
                MatterDocument.tenant_id == estate.tenant_id,
                MatterDocument.matter_id == estate.matter_id,
                MatterDocument.id == document_id,
            )
        )
        if document is None or not document.filename.lower().endswith(".pdf"):
            continue
        try:
            _, _, content = await matter_fact_extraction._load_source(
                db, user, estate.matter_id, document.id
            )
            values = values_from_pdf_fields(read_pdf_form_values(content))
        except (TemplatePdfError, Exception):  # noqa: BLE001 - a bad scan is not fatal
            continue
        if not has_probate_answers(values):
            continue
        facts = merge(facts, facts_from_values(values))
        sources.append(
            {
                "kind": "returned_pdf",
                "requirement": key,
                "document_id": str(document.id),
                "filename": document.filename,
            }
        )
    return facts, sources
