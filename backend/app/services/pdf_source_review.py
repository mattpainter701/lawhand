"""Human review of the fields a PDF scan found, enforced at publish.

A PDF or image upload is scanned, and the scan reports what it is unsure of: a
field read by OCR, a field it scored low, a field it explicitly flagged. Those
are the fields a person has to compare against the original document before the
template is used to produce anything, because a misread box silently fills the
wrong value into every document generated from it.

The product asked for that attestation, but only in the browser: the wizard's
"I compared every highlighted field with the original" checkbox disabled the
save button and was never sent anywhere, so it bound nobody and nothing
re-checked it afterwards. Word templates already had the real version of this
(``docx_source_review``), recomputed from the live source at publish. This is
the same property for the other half of the product.

Two rules follow from "recomputed", and they are the whole reason this is a
digest rather than a boolean:

* Confirming covers the field set that was on screen when it was confirmed.
  Add a field, move one, or let a rescan change what the fields are, and the
  attestation no longer describes what is there — so it re-arms.
* A template with nothing uncertain in it needs no attestation at all. The gate
  is for fields the scan is unsure of, not a ceremony on every template.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: Below this, the scan is not confident enough to publish unreviewed. Same
#: threshold the editors colour a field "needs review" at; they must agree,
#: or a firm sees a green page and is refused at publish.
CONFIDENCE_FLOOR = 0.75

#: A scan that had to read the page as an image rather than read its form
#: fields. Every field it produced is a guess about pixels.
OCR_SOURCE_KIND = "ocr"


def _overlays(field: dict[str, Any]) -> list[dict[str, Any]]:
    overlays = field.get("pdf_overlays")
    if isinstance(overlays, list) and overlays:
        return [entry for entry in overlays if isinstance(entry, dict)]
    overlay = field.get("pdf_overlay")
    return [overlay] if isinstance(overlay, dict) else []


def field_needs_review(field: dict[str, Any]) -> bool:
    """Whether a person has to check this field against the original.

    Mirrors the rule both editors colour by, field for field.
    """

    if field.get("review_required") is True:
        return True
    confidence = field.get("confidence")
    if confidence is not None:
        try:
            if float(confidence) < CONFIDENCE_FLOOR:
                return True
        except (TypeError, ValueError):
            # An unreadable confidence is not a confident one.
            return True
    return any(
        overlay.get("source_kind") == OCR_SOURCE_KIND for overlay in _overlays(field)
    )


def _reviewable_fields(variable_schema: dict | None) -> list[dict[str, Any]]:
    fields = (
        variable_schema.get("fields") if isinstance(variable_schema, dict) else None
    )
    if not isinstance(fields, list):
        return []
    return [
        field
        for field in fields
        if isinstance(field, dict) and field.get("included", True) is not False
    ]


def requires_review(variable_schema: dict | None) -> bool:
    """Whether this template has anything for a person to confirm.

    A scan whose detection method was OCR is uncertain as a whole, not only
    where it happened to score a field low.
    """

    if not isinstance(variable_schema, dict):
        return False
    detection = variable_schema.get("detection")
    method = (detection or {}).get("method") if isinstance(detection, dict) else None
    if OCR_SOURCE_KIND in str(method or "").lower():
        return True
    return any(
        field_needs_review(field) for field in _reviewable_fields(variable_schema)
    )


def review_digest(variable_schema: dict | None) -> str:
    """Identify the field set an attestation was made against.

    Covers what a person would have been looking at: which fields there are,
    where each sits, and how sure the scan was. A label or a binding changing
    does not re-arm review — neither moves a box on the page — but a field
    appearing, moving, or being rescanned does.
    """

    material = [
        [
            str(field.get("name") or ""),
            str(field.get("pdf_field_name") or ""),
            str(field.get("pdf_source_key") or ""),
            [
                [
                    overlay.get("page"),
                    overlay.get("rect"),
                    overlay.get("source_kind"),
                ]
                for overlay in _overlays(field)
            ],
            field.get("page"),
            field.get("confidence"),
            bool(field.get("review_required")),
        ]
        for field in _reviewable_fields(variable_schema)
    ]
    material.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
    encoded = json.dumps(material, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def confirmed_review(variable_schema: dict | None) -> dict[str, Any]:
    """The attestation recorded on this schema, if any."""

    if not isinstance(variable_schema, dict):
        return {}
    recorded = variable_schema.get("pdf_source_review")
    return recorded if isinstance(recorded, dict) else {}


def review_is_current(variable_schema: dict | None) -> bool:
    """Whether the recorded attestation still describes the fields on the page."""

    recorded = confirmed_review(variable_schema)
    digest = recorded.get("confirmed_digest")
    return isinstance(digest, str) and digest == review_digest(variable_schema)


def unresolved_reason(variable_schema: dict | None) -> str | None:
    """Why this template cannot be published yet, or ``None`` if it can.

    Returns the sentence a person reads, because the only useful version of
    this answer says which of the two states they are in: never confirmed, or
    confirmed against a field set that has since changed.
    """

    if not requires_review(variable_schema):
        return None
    if review_is_current(variable_schema):
        return None
    if confirmed_review(variable_schema):
        return (
            "The fields changed after this template's source review. Compare the "
            "highlighted fields with the original document again and confirm the "
            "review before publishing."
        )
    return (
        "This template has fields the scan is not sure of. Compare the highlighted "
        "fields with the original document and confirm the review before publishing."
    )
