"""The two gates that keep an unsignable document from reaching a client.

The publish gate refuses a template whose signing fields could never bind to a
generated document. The dispatch gate refuses to send a document that carries
no placements -- and, since this change, says which field is wrong and whether
placing fields by hand can still clear it.

Between them they close the path that stalled a matter: a template that looked
published and fine, generating a document that was silently unsendable.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.document_templates import _ensure_signing_fields_placeable
from app.routers.esignature import _is_pdf_document
from app.services.esign.placement import (
    MISSING_PDF_PLACEMENT,
    MISSING_SIGNER_ROLE,
    NO_PDF_OUTPUT,
    REMEDIES,
    placement_block_detail,
)


def template(fmt="pdf"):
    return SimpleNamespace(id=uuid.uuid4(), format=fmt, title="Fee agreement")


def schema(*fields):
    return {"fields": list(fields)}


OVERLAY = {"page": 1, "rect": [72, 100, 272, 136]}


# ── Publish gate ────────────────────────────────────────────────────────────


def test_a_pdf_template_with_bound_signing_fields_publishes():
    _ensure_signing_fields_placeable(
        template(),
        schema(
            {
                "name": "client_sig",
                "field_type": "signature",
                "signer_role": "client",
                "pdf_overlays": [OVERLAY],
            }
        ),
    )


def test_a_template_with_no_signing_fields_publishes():
    _ensure_signing_fields_placeable(
        template(), schema({"name": "client_name", "field_type": "text"})
    )


@pytest.mark.parametrize("variable_schema", [None, {}, {"fields": []}])
def test_an_empty_schema_publishes(variable_schema):
    _ensure_signing_fields_placeable(template(), variable_schema)


def test_a_signature_field_with_no_signer_role_is_refused():
    """Template Studio leaves the role optional; this is where that is caught."""
    with pytest.raises(HTTPException) as caught:
        _ensure_signing_fields_placeable(
            template(),
            schema(
                {
                    "name": "client_sig",
                    "field_type": "signature",
                    "pdf_overlays": [OVERLAY],
                }
            ),
        )

    assert caught.value.status_code == 422
    assert "client_sig" in caught.value.detail
    assert "signer role" in caught.value.detail


def test_a_pdf_signing_field_nobody_positioned_is_refused():
    with pytest.raises(HTTPException) as caught:
        _ensure_signing_fields_placeable(
            template(),
            schema(
                {
                    "name": "witness_sig",
                    "field_type": "signature",
                    "signer_role": "witness",
                }
            ),
        )

    assert "witness_sig" in caught.value.detail
    assert "position" in caught.value.detail.lower()


def test_a_word_template_needs_a_role_but_not_pdf_geometry():
    """Word carries no overlays; its positions are placed on the output PDF."""
    _ensure_signing_fields_placeable(
        template("docx"),
        schema(
            {"name": "client_sig", "field_type": "signature", "signer_role": "client"}
        ),
    )

    with pytest.raises(HTTPException):
        _ensure_signing_fields_placeable(
            template("docx"),
            schema({"name": "client_sig", "field_type": "signature"}),
        )


def test_a_word_field_with_an_anchor_that_is_present_but_empty_is_refused():
    """The anchor is derived when absent; one that is there and blank binds to nothing."""
    with pytest.raises(HTTPException) as caught:
        _ensure_signing_fields_placeable(
            template("docx"),
            schema(
                {
                    "name": "client_sig",
                    "field_type": "signature",
                    "signer_role": "client",
                    "pdf_anchor": {"text": "   ", "placement": "after"},
                }
            ),
        )

    assert "client_sig" in caught.value.detail
    assert "anchor text" in caught.value.detail


def test_a_word_field_with_a_named_anchor_publishes():
    _ensure_signing_fields_placeable(
        template("docx"),
        schema(
            {
                "name": "client_sig",
                "field_type": "signature",
                "signer_role": "client",
                "pdf_anchor": {"text": "Client Signature:", "placement": "after"},
            }
        ),
    )


def test_every_offending_field_is_named_so_it_is_one_pass_through_the_editor():
    with pytest.raises(HTTPException) as caught:
        _ensure_signing_fields_placeable(
            template(),
            schema(
                {"name": "client_sig", "field_type": "signature"},
                {"name": "witness_sig", "field_type": "signature"},
                {
                    "name": "notary_sig",
                    "field_type": "signature",
                    "signer_role": "notary",
                    "pdf_overlays": [OVERLAY],
                },
            ),
        )

    detail = caught.value.detail
    assert "client_sig" in detail and "witness_sig" in detail
    assert "notary_sig" not in detail


def test_an_excluded_signing_field_does_not_block_publishing():
    _ensure_signing_fields_placeable(
        template(),
        schema(
            {"name": "old_sig", "field_type": "signature", "included": False},
            {
                "name": "client_sig",
                "field_type": "signature",
                "signer_role": "client",
                "pdf_overlays": [OVERLAY],
            },
        ),
    )


def test_a_signing_date_is_held_to_the_same_bar():
    with pytest.raises(HTTPException):
        _ensure_signing_fields_placeable(
            template(),
            schema(
                {"name": "signed_on", "field_type": "date", "signer_role": "client"}
            ),
        )


def test_an_ordinary_date_is_not_a_signing_field():
    _ensure_signing_fields_placeable(
        template(), schema({"name": "filed_on", "field_type": "date"})
    )


def test_a_legacy_single_overlay_field_still_counts_as_positioned():
    _ensure_signing_fields_placeable(
        template(),
        schema(
            {
                "name": "client_sig",
                "field_type": "signature",
                "signer_role": "client",
                "pdf_overlay": OVERLAY,
            }
        ),
    )


# ── Dispatch gate ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "content_type,filename,expected",
    [
        ("application/pdf", "Agreement.pdf", True),
        ("application/pdf", "Agreement", True),
        (None, "Agreement.PDF", True),
        (None, "Agreement.pdf", True),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "Agreement.docx",
            False,
        ),
        ("text/markdown", "Agreement.md", False),
        (None, None, False),
    ],
)
def test_only_a_pdf_offers_a_placement_review(content_type, filename, expected):
    """The review renders with pdf.js: anything else has no recovery path."""
    document = SimpleNamespace(content_type=content_type, filename=filename)

    assert _is_pdf_document(document) is expected


def test_the_pdf_block_tells_staff_they_can_place_the_fields_themselves():
    detail = placement_block_detail(
        [
            {
                "code": MISSING_SIGNER_ROLE,
                "detail": "Signing field 'client_sig' requires a signer role",
                "field": "client_sig",
                "role": "",
                "remedy": "Open the template, select this field, and set its signer role.",
            }
        ],
        filename="Fee agreement.pdf",
        output_is_pdf=True,
    )

    assert "client_sig" in detail
    assert "Place the fields on the generated PDF" in detail


def test_the_word_block_does_not_ask_for_a_review_that_cannot_happen():
    detail = placement_block_detail(
        [
            {
                "code": NO_PDF_OUTPUT,
                "detail": "This document was generated as DOCX, which has no PDF page",
                "field": "",
                "role": "",
                "remedy": "Regenerate this document with Word-to-PDF conversion enabled.",
            }
        ],
        filename="Engagement.docx",
        output_is_pdf=False,
    )

    assert "Engagement.docx" in detail
    assert "Word-to-PDF conversion" in detail
    assert "Place the fields" not in detail


def test_several_unbound_fields_are_all_listed():
    detail = placement_block_detail(
        [
            {
                "code": MISSING_SIGNER_ROLE,
                "detail": "Signing field 'a' requires a signer role",
                "field": "a",
                "role": "",
            },
            {
                "code": MISSING_PDF_PLACEMENT,
                "detail": "Signing field 'b' has no reviewed PDF placement",
                "field": "b",
                "role": "client",
            },
        ],
        filename="Both.pdf",
    )

    assert "'a'" in detail and "'b'" in detail
    assert REMEDIES[MISSING_SIGNER_ROLE] in detail
    assert REMEDIES[MISSING_PDF_PLACEMENT] in detail


def test_the_remedy_is_read_from_the_current_table_not_the_stored_row():
    """Improving the advice must reach documents blocked before the change."""
    detail = placement_block_detail(
        [
            {
                "code": MISSING_SIGNER_ROLE,
                "detail": "Signing field 'a' requires a signer role",
                "field": "a",
                "remedy": "advice written months ago",
            }
        ],
        filename="Old.pdf",
    )

    assert REMEDIES[MISSING_SIGNER_ROLE] in detail
    assert "advice written months ago" not in detail
