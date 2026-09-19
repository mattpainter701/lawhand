"""Run one scenario against one document and record every field's fate.

The resolver is called exactly as the ``smart-fill-preview`` route calls it,
with the database loaders replaced by the scenario's in-memory records (the
pattern the existing smart-fill unit tests use).  The suggested values are then
pushed through the production PDF or DOCX writer and read back, so a value
that the resolver produced but the renderer dropped is reported as blank
rather than assumed to be on the page.
"""

from __future__ import annotations

import io
import logging
import uuid
from contextlib import ExitStack
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from app.routers import document_templates
from app.schemas.document_template import DocumentTemplateVariableSuggestion
from app.services import template_fill_coverage, template_fill_engine
from app.services.template_bindings import binding_label, custom_binding
from app.services.docx_templates import TemplateDocxError, fill_docx_template
from app.services.pdf_templates import (
    TemplatePdfError,
    fill_pdf_template,
    read_pdf_form_values,
)

from .scenarios import Scenario, current_user

# pypdf reports every missing font dictionary and every page without widgets;
# neither is a finding.
for _name in ("pypdf", "pypdf._writer", "pypdf._page"):
    logging.getLogger(_name).setLevel(logging.ERROR)

FILLED = "filled"
BLANK = "blank"
CHOICE_MISMATCH = "choice_mismatch"
SIGNATURE = "signature"
DROPPED = "dropped_by_renderer"


@dataclass
class FieldOutcome:
    name: str
    state: str
    source_type: str | None = None
    value: str | None = None
    provenance_status: str | None = None
    binding: str | None = None
    confidence: float | None = None
    review_required: bool | None = None
    coverage_state: str | None = None
    note: str | None = None


@dataclass
class CaseResult:
    scenario: str
    document: str
    outcomes: list[FieldOutcome] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rendered: bytes | None = None

    def by_name(self) -> dict[str, FieldOutcome]:
        return {outcome.name: outcome for outcome in self.outcomes}

    def state(self, name: str) -> str:
        return self.by_name()[name].state


def _loader_patches(scenario: Scenario, stack: ExitStack, writes: list) -> None:
    async def load_matter(**_):
        return scenario.matter

    async def load_parties(**_):
        return list(scenario.parties)

    async def load_estate(**_):
        return scenario.estate

    async def load_retainer(**_):
        return scenario.retainer

    stack.enter_context(
        patch.object(document_templates, "_load_matter_context", load_matter)
    )
    stack.enter_context(
        patch.object(document_templates, "_load_matter_parties", load_parties)
    )
    stack.enter_context(
        patch.object(document_templates, "_load_estate_for_matter", load_estate)
    )
    stack.enter_context(
        patch.object(document_templates, "_load_current_retainer", load_retainer)
    )
    original = template_fill_engine.add_candidate

    def recording_add(candidates, alias, value, **kwargs):
        text = template_fill_engine.stringify_suggestion(value)
        if text is not None:
            writes.append(
                {
                    "alias": template_fill_coverage.normalize_variable_name(alias),
                    "source_type": kwargs.get("source_type"),
                    "source_field": kwargs.get("source_field"),
                    "value": text,
                }
            )
        return original(candidates, alias, value, **kwargs)

    stack.enter_context(
        patch.object(template_fill_engine, "add_candidate", recording_add)
    )

    # The firm-profile and custom-field resolvers query the database. Stand in
    # for them with the scenario's values, mirroring their real provenance.
    firm_fields = {
        "firm.name": "firm_name",
        "firm.address": "firm_address",
        "firm.phone": "firm_phone",
        "firm.email": "firm_email",
        "firm.website": "firm_website",
    }

    async def firm_suggestions(db, tenant_id, bindings):
        resolved = {}
        for name, path in bindings.items():
            if path not in firm_fields:
                continue
            value = (scenario.firm.get(firm_fields[path]) or "").strip() or None
            resolved[name] = DocumentTemplateVariableSuggestion(
                variable=name,
                suggested_value=value,
                source_type="firm_profile",
                source_field=firm_fields[path],
                provenance={
                    "source_type": "firm_profile",
                    "record_id": str(tenant_id),
                    "binding": path,
                    "binding_label": binding_label(path),
                    "status": "configured" if value else "firm_profile_missing",
                },
                confidence=1.0 if value else 0.0,
                review_required=value is None,
            )
        return resolved

    async def custom_suggestions(db, tenant_id, matter, bindings):
        resolved = {}
        for name, path in bindings.items():
            if not custom_binding(path):
                continue
            value = scenario.custom_fields.get(path)
            resolved[name] = DocumentTemplateVariableSuggestion(
                variable=name,
                suggested_value=value,
                source_type="custom_field",
                source_field=path,
                provenance={
                    "source_type": "custom_field",
                    "binding": path,
                    "status": "from_custom_record" if value else "custom_field_missing",
                },
                confidence=1.0 if value else 0.0,
                review_required=True,
            )
        return resolved

    stack.enter_context(
        patch.object(
            template_fill_engine.template_firm_fields, "suggestions", firm_suggestions
        )
    )
    stack.enter_context(
        patch.object(
            template_fill_engine.template_custom_fields,
            "suggestions",
            custom_suggestions,
        )
    )


def collisions_from(writes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aliases written more than once. First writer wins; the rest vanish."""

    by_alias: dict[str, list[dict[str, Any]]] = {}
    for write in writes:
        by_alias.setdefault(write["alias"], []).append(write)
    output = []
    for alias, entries in by_alias.items():
        if len(entries) < 2:
            continue
        winner, losers = entries[0], entries[1:]
        # Two sources agreeing on the value is not a quirk worth a row.
        if all(loser["value"] == winner["value"] for loser in losers):
            continue
        output.append({"alias": alias, "winner": winner, "losers": losers})
    return output


async def resolve(
    scenario: Scenario,
    schema: dict[str, Any],
    *,
    body: str = "",
    requested: list[str] | None = None,
    user: SimpleNamespace | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Smart Fill ``schema`` against ``scenario``; return suggestions and collisions."""

    template = SimpleNamespace(id=uuid.uuid4(), body=body, variable_schema=schema)
    names = requested
    if names is None:
        names = [
            str(f.get("name") or "").strip()
            for f in schema.get("fields", [])
            if f.get("included", True) is not False and f.get("name")
        ]
    writes: list[dict[str, Any]] = []
    with ExitStack() as stack:
        _loader_patches(scenario, stack, writes)
        _, suggestions = await document_templates.build_variable_suggestions(
            template=template,
            requested_variables=names,
            matter_id=scenario.matter_id,
            tenant_id=uuid.uuid4(),
            current_user=user or current_user(),
            db=SimpleNamespace(),
        )
    return {item.variable: item for item in suggestions}, collisions_from(writes)


def _option_values(field: dict[str, Any]) -> list[str]:
    values = []
    for option in field.get("options") or []:
        if isinstance(option, dict):
            values.append(str(option.get("value") or ""))
        else:
            values.append(str(option))
    return values


def values_for_render(
    schema: dict[str, Any], suggestions: dict[str, Any]
) -> tuple[dict[str, str], list[FieldOutcome]]:
    """Turn suggestions into the renderer's value map, noting what cannot go in."""

    values: dict[str, str] = {}
    problems: list[FieldOutcome] = []
    for spec in schema.get("fields", []):
        name = str(spec.get("name") or "").strip()
        if not name or spec.get("included", True) is False:
            continue
        if template_fill_coverage.is_signing_field(spec):
            continue
        suggestion = suggestions.get(name)
        value = getattr(suggestion, "suggested_value", None)
        if value in (None, ""):
            continue
        field_type = str(spec.get("field_type") or spec.get("type") or "text")
        if field_type in ("choice", "radio"):
            options = _option_values(spec)
            if options and value not in options:
                problems.append(
                    FieldOutcome(
                        name=name,
                        state=CHOICE_MISMATCH,
                        source_type=suggestion.source_type,
                        value=value,
                        note=f"value not among export values {options}",
                    )
                )
                continue
        if field_type == "checkbox" and value.strip().lower() not in (
            "true",
            "false",
            "yes",
            "no",
            "1",
            "0",
            "x",
        ):
            problems.append(
                FieldOutcome(
                    name=name,
                    state=CHOICE_MISMATCH,
                    source_type=suggestion.source_type,
                    value=value,
                    note="checkbox needs true/false",
                )
            )
            continue
        values[name] = value
    return values, problems


def _readback_pdf(rendered: bytes, schema: dict[str, Any]) -> dict[str, str]:
    by_pdf_name = {
        str(spec.get("pdf_field_name")): str(spec.get("name"))
        for spec in schema.get("fields", [])
        if spec.get("pdf_field_name")
    }
    output: dict[str, str] = {}
    for entry in read_pdf_form_values(rendered):
        name = by_pdf_name.get(str(entry.get("pdf_field_name")), entry.get("name"))
        if name:
            output[str(name)] = str(entry.get("value") or "")
    return output


def _readback_docx(rendered: bytes, values: dict[str, str]) -> dict[str, str]:
    from docx import Document

    document = Document(io.BytesIO(rendered))
    text = "\n".join(p.text for p in document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                text += "\n" + cell.text
    return {name: value for name, value in values.items() if value and value in text}


async def run_case(
    scenario: Scenario,
    *,
    document: str,
    schema: dict[str, Any],
    source: bytes,
    fmt: str,
    body: str = "",
    vocabulary: frozenset[str] | None = None,
) -> CaseResult:
    """Resolve, render, read back, and classify every field of one document."""

    result = CaseResult(scenario=scenario.key, document=document)
    suggestions, result.collisions = await resolve(scenario, schema, body=body)
    values, problems = values_for_render(schema, suggestions)
    coverage = template_fill_coverage.coverage(
        schema,
        vocabulary=(
            vocabulary
            if vocabulary is not None
            else document_templates._smart_fill_alias_vocabulary()
        ),
    )

    readback: dict[str, str] = {}
    try:
        if fmt == "pdf":
            result.rendered = fill_pdf_template(
                source, variable_schema=schema, variables=values, flatten=False
            )
            readback = _readback_pdf(result.rendered, schema)
        else:
            result.rendered = fill_docx_template(
                source, variable_schema=schema, variables=values
            )
            readback = _readback_docx(result.rendered, values)
    except (TemplatePdfError, TemplateDocxError) as exc:
        result.errors.append(f"{type(exc).__name__}: {exc}")

    problem_by_name = {p.name: p for p in problems}
    for spec in schema.get("fields", []):
        name = str(spec.get("name") or "").strip()
        if not name or spec.get("included", True) is False:
            continue
        suggestion = suggestions.get(name)
        provenance = dict(getattr(suggestion, "provenance", None) or {})
        outcome = FieldOutcome(
            name=name,
            state=BLANK,
            source_type=getattr(suggestion, "source_type", None),
            value=getattr(suggestion, "suggested_value", None),
            provenance_status=provenance.get("status"),
            binding=provenance.get("binding") or spec.get("binding"),
            confidence=getattr(suggestion, "confidence", None),
            review_required=getattr(suggestion, "review_required", None),
            coverage_state=coverage.states.get(name),
            note=scenario.notes.get(name),
        )
        if template_fill_coverage.is_signing_field(spec):
            outcome.state = SIGNATURE
        elif name in problem_by_name:
            outcome = problem_by_name[name]
            outcome.coverage_state = coverage.states.get(name)
            outcome.note = outcome.note or scenario.notes.get(name)
        elif name in values:
            if result.errors:
                outcome.state = DROPPED
                outcome.note = outcome.note or "render failed; see errors"
            elif readback.get(name, "") == values[name]:
                outcome.state = FILLED
            else:
                outcome.state = DROPPED
                outcome.note = outcome.note or (
                    f"resolver produced {values[name]!r}; page holds {readback.get(name, '')!r}"
                )
        else:
            outcome.state = BLANK
            if outcome.coverage_state in ("bound", "name_matched") and not outcome.note:
                outcome.note = (
                    f"coverage reports {outcome.coverage_state} but the resolver "
                    f"returned {outcome.provenance_status or 'nothing'}"
                )
        result.outcomes.append(outcome)
    return result
