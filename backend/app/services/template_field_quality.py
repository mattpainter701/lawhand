"""Whether a fillable template's fields will fill and read correctly.

The shared sample library shipped PDFs whose fields were named by whoever
built the PDF: "Text3", "undefined 2", "Check Box4", radio options called
"Choice 1", and generic names such as "Address", "Email" and "Full Name".
Smart Fill reads a generic name as the *client's* value (see
``template_fill_engine.NAME_SYNONYMS``), so an attorney signature block's
"Email" box filled with the client's email, and a landlord's "Address" with
the client's street. Nothing in the document said so.

Two kinds of finding come out of here:

* ``accidental_fills`` -- a field that would fill by guesswork from the
  client's record because of its generic name, with nothing declaring that is
  what the author meant. This puts the wrong person's details into a legal
  document, so publishing a PDF template is refused until the field is bound
  (to the client if that is right, or ``manual``). A field named after a
  platform variable (``client_email``, ``plaintiff_name``) is deliberate and is
  not reported.
* ``warnings`` -- labels a person cannot act on (tool-generated names, labels
  shared by several fields, labels too long to scan) and options that read as
  "Choice 1". These make a template hard to fill, not wrong, so they are shown
  to the author rather than enforced; ``template_labels`` keeps the narrow
  publish block for labels that name nothing at all.

The shared sample library holds itself to both lists in
``tests/test_sample_template_library.py`` and in its seeder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.template_fill_engine import NAME_SYNONYMS, normalize_variable_name

#: Labels an authoring tool generated rather than a person wrote: "Text3",
#: "Check Box4", "undefined 2", the discovery fallback "Source field 12 (page
#: 1)", bare numbers, and one- or two-letter fragments.
PLACEHOLDER_LABEL = re.compile(
    r"^(source field \d+.*|undefined[\s_]*\d*|text[\s_]*(field)?[\s_]*\d*"
    r"|check[\s_]*box[\s_]*\d*|field[\s_]*\d+|fill[\s_]*\d+|group[\s_]*\d+"
    r"|radio[\s_]*button[\s_]*\d*|toggle[\s_]*\d*|dropdown[\s_]*\d*"
    r"|button[\s_]*\d*|[\d\s_.,-]+|[a-z]{1,2}[\s_]*\d*)$",
    re.I,
)

#: Option labels that say nothing about the choice: "Choice 1", "0".
_PLACEHOLDER_OPTION = re.compile(r"^(choice[\s_]*\d+)$", re.I)

#: Longest label that still scans in a field list.
MAX_LABEL_LENGTH = 90

#: Short answers that are complete option labels under their question.
_ANSWER_WORDS = frozenset({"yes", "no"})


@dataclass(frozen=True)
class FieldFinding:
    name: str
    message: str


def _fields(variable_schema: dict | None) -> list[dict]:
    fields = (variable_schema or {}).get("fields")
    if not isinstance(fields, list):
        return []
    return [
        field
        for field in fields
        if isinstance(field, dict)
        and str(field.get("name") or "").strip()
        and field.get("included") is not False
    ]


def _is_signing(field: dict) -> bool:
    return str(field.get("field_type") or "").lower() == "signature" or bool(
        str(field.get("signer_role") or "").strip()
    )


def _shown_label(field: dict) -> str:
    """What every surface displays: the label, else the name made readable."""

    label = str(field.get("label") or "").strip()
    return label or re.sub(r"[_\-]+", " ", str(field.get("name"))).strip()


def accidental_fills(variable_schema: dict | None) -> list[FieldFinding]:
    """Fields that would fill with the client's details only because of their name."""

    findings: list[FieldFinding] = []
    for field in _fields(variable_schema):
        if _is_signing(field) or field.get("binding") or field.get("value_from"):
            continue
        synonym = NAME_SYNONYMS.get(normalize_variable_name(field["name"]))
        if not synonym:
            continue
        findings.append(
            FieldFinding(
                field["name"],
                f"{_shown_label(field)!r} would fill with the client's "
                f"{synonym.removeprefix('client_').replace('_', ' ')} because of "
                "its name. Bind it to the record it belongs to, or mark it "
                "entered by hand.",
            )
        )
    return findings


def warnings(variable_schema: dict | None) -> list[FieldFinding]:
    """Labels and options a person filling the template cannot act on."""

    findings: list[FieldFinding] = []
    seen: dict[str, tuple[str, list[str]]] = {}
    for field in _fields(variable_schema):
        name = field["name"]
        label = _shown_label(field)
        if PLACEHOLDER_LABEL.match(label):
            findings.append(
                FieldFinding(name, f"{label!r} does not say what goes in this field.")
            )
        elif len(label) > MAX_LABEL_LENGTH:
            findings.append(
                FieldFinding(
                    name,
                    f"{label[:40]!r}... is longer than {MAX_LABEL_LENGTH} characters; "
                    "shorten it so the field list scans.",
                )
            )
        seen.setdefault(label.casefold(), (label, []))[1].append(name)
        for option in field.get("options") or []:
            text = str(option.get("label") if isinstance(option, dict) else option)
            text = text.strip()
            if text.casefold() in _ANSWER_WORDS:
                continue
            if PLACEHOLDER_LABEL.match(text) or _PLACEHOLDER_OPTION.match(text):
                findings.append(
                    FieldFinding(
                        name,
                        f"Option {text!r} of {label!r} does not say what it chooses.",
                    )
                )
    for shown, names in seen.values():
        if len(names) > 1:
            findings.extend(
                FieldFinding(
                    name,
                    f"{len(names)} fields are labelled {shown!r}; give each its own label.",
                )
                for name in names
            )
    return findings


def summary(variable_schema: dict | None) -> dict:
    """Both lists, shaped for the template response."""

    return {
        "accidental_fills": [
            {"name": item.name, "message": item.message}
            for item in accidental_fills(variable_schema)
        ],
        "warnings": [
            {"name": item.name, "message": item.message}
            for item in warnings(variable_schema)
        ],
    }
