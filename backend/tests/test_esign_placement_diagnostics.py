"""Why a signing placement failed must survive to the person who can fix it.

A template's signing fields are bound to the freshly generated document at
generation time. When that binding failed, the reason used to be discarded and
the document saved anyway with ``signing_placement_required`` set -- so the
first anyone heard of it was a dispatch block that named no field, on a matter
with a client already waiting. These tests pin the properties that make that
impossible: a block always carries its reasons, a reason always carries a
remedy, one bad field never takes a good one with it, and the message never
asks for a review the saved artifact cannot support.
"""

import hashlib
import logging
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import FloatObject, NameObject, RectangleObject

from app.services.esign.placement import (
    ANCHOR_AMBIGUOUS,
    ANCHOR_NOT_FOUND,
    INVALID_GEOMETRY,
    MISSING_PDF_PLACEMENT,
    MISSING_SIGNER_ROLE,
    NO_PDF_OUTPUT,
    PAGE_OUT_OF_RANGE,
    REMEDIES,
    UNREADABLE_PDF,
    UNSUPPORTED_PDF_PAGE,
    WORD_SOURCE_NOT_POSITIONABLE,
    PlacementError,
    PlacementProblem,
    generated_signing_metadata,
    placement_block_detail,
    log_placement_report,
    signing_field_roles,
    template_placement_report,
    template_positioned_fields,
)


def pdf(width=612, height=792, pages=1, rotation=0, crop=None, unit=None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=width, height=height)
        if rotation:
            page.rotate(rotation)
        if crop:
            page.cropbox = RectangleObject(crop)
        if unit:
            page[NameObject("/UserUnit")] = FloatObject(unit)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


OVERLAY = {"page": 1, "rect": [72, 100, 272, 136]}


def sig(name="client_sig", role="client", overlays=(OVERLAY,), **extra):
    field = {"name": name, "field_type": "signature", **extra}
    if role is not None:
        field["signer_role"] = role
    if overlays is not None:
        field["pdf_overlays"] = list(overlays)
    return field


def report(*fields, source=None, template_format="pdf", output_format=None):
    return template_placement_report(
        {"fields": list(fields)},
        source=pdf() if source is None else source,
        template_format=template_format,
        output_format=output_format,
    )


def codes(result):
    return [problem.code for problem in result.problems]


# ── The master invariant ────────────────────────────────────────────────────


BLOCKING_SCHEMAS = {
    "no signer role": (sig(role=None),),
    "no overlay at all": (sig(overlays=None),),
    "overlay without a rect": (sig(overlays=[{"page": 1}]),),
    "overlay that is not an object": (sig(overlays=["nonsense"]),),
    "page the document does not have": (sig(overlays=[{"page": 9, "rect": [1, 1, 99, 99]}]),),
    "page zero": (sig(overlays=[{"page": 0, "rect": [1, 1, 99, 99]}]),),
    "page as a bool": (sig(overlays=[{"page": True, "rect": [1, 1, 99, 99]}]),),
    "rect off the right edge": (sig(overlays=[{"page": 1, "rect": [600, 10, 900, 60]}]),),
    "rect off the bottom": (sig(overlays=[{"page": 1, "rect": [10, -40, 210, 20]}]),),
    "rect with no area": (sig(overlays=[{"page": 1, "rect": [10, 10, 10.2, 10.2]}]),),
    "rect that is not numeric": (sig(overlays=[{"page": 1, "rect": ["a", 1, 2, 3]}]),),
    "two fields, both unroled": (sig(name="a", role=None), sig(name="b", role=None)),
}


@pytest.mark.parametrize("label", sorted(BLOCKING_SCHEMAS))
def test_a_blocked_document_always_says_why(label):
    """The defect in one sentence: blocked with nothing to act on."""
    result = report(*BLOCKING_SCHEMAS[label])

    assert result.blocked is True
    assert result.problems, f"{label} blocked dispatch while explaining nothing"
    assert all(problem.detail.strip() for problem in result.problems)
    assert all(problem.remedy.strip() for problem in result.problems)


@pytest.mark.parametrize("label", sorted(BLOCKING_SCHEMAS))
def test_the_block_message_names_the_remedy(label):
    result = report(*BLOCKING_SCHEMAS[label])
    detail = placement_block_detail(
        result.as_dicts(), filename="Fee agreement.pdf", output_is_pdf=result.recoverable
    )

    assert "Fee agreement.pdf" in detail
    assert any(problem.remedy in detail for problem in result.problems)
    # The old message. It named nothing and is what sent staff in circles.
    assert detail != "Review signing field positions on the final generated PDF before sending."


def test_every_reason_code_carries_a_remedy():
    """A code with no remedy is a dead end wearing a diagnosis."""
    assert set(REMEDIES) == {
        MISSING_SIGNER_ROLE,
        MISSING_PDF_PLACEMENT,
        UNREADABLE_PDF,
        UNSUPPORTED_PDF_PAGE,
        PAGE_OUT_OF_RANGE,
        INVALID_GEOMETRY,
        NO_PDF_OUTPUT,
        WORD_SOURCE_NOT_POSITIONABLE,
        ANCHOR_NOT_FOUND,
        ANCHOR_AMBIGUOUS,
    }
    assert all(text.strip() for text in REMEDIES.values())


# ── One bad field must not take the good ones with it ───────────────────────


def test_a_misconfigured_field_no_longer_discards_its_working_neighbour():
    result = report(sig(name="client_sig"), sig(name="witness_sig", role=None))

    assert [item["role"] for item in result.placements] == ["client"]
    assert codes(result) == [MISSING_SIGNER_ROLE]
    # One template defect used to strand a document that was otherwise ready.
    assert result.blocked is False


def test_several_good_fields_survive_several_bad_ones():
    result = report(
        sig(name="a", role="client"),
        sig(name="b", role=None),
        sig(name="c", role="attorney"),
        sig(name="d", role="witness", overlays=None),
        sig(name="e", role="notary"),
    )

    assert sorted(item["role"] for item in result.placements) == [
        "attorney",
        "client",
        "notary",
    ]
    assert sorted(codes(result)) == [MISSING_PDF_PLACEMENT, MISSING_SIGNER_ROLE]
    assert {problem.field for problem in result.problems} == {"b", "d"}


def test_a_field_with_two_placements_keeps_the_good_one():
    result = report(
        sig(overlays=[OVERLAY, {"page": 1, "rect": [900, 900, 1000, 1000]}])
    )

    assert [item["field_id"] for item in result.placements] == ["field-0-0"]
    assert codes(result) == [INVALID_GEOMETRY]


def test_a_fully_bound_template_reports_no_problems():
    result = report(sig(name="a"), sig(name="b", role="attorney"))

    assert len(result.placements) == 2
    assert result.problems == []
    assert result.blocked is False and result.recoverable is True


# ── Each reason is reported as itself ───────────────────────────────────────


@pytest.mark.parametrize(
    "fields,expected",
    [
        ((sig(role=None),), MISSING_SIGNER_ROLE),
        ((sig(overlays=None),), MISSING_PDF_PLACEMENT),
        ((sig(overlays=[{"page": 1}]),), MISSING_PDF_PLACEMENT),
        ((sig(overlays=[{"page": 4, "rect": [1, 1, 99, 99]}]),), PAGE_OUT_OF_RANGE),
        ((sig(overlays=[{"page": 1, "rect": [600, 10, 900, 60]}]),), INVALID_GEOMETRY),
    ],
)
def test_each_failure_reports_its_own_reason(fields, expected):
    assert codes(report(*fields)) == [expected]


def test_the_failing_field_is_named_so_it_can_be_found_in_the_editor():
    problem = report(sig(name="landlord_signature", role=None)).problems[0]

    assert problem.field == "landlord_signature"
    assert "landlord_signature" in problem.detail


def test_a_field_with_no_name_still_identifies_itself():
    problem = report(sig(name=None, role=None, label="Tenant sign here")).problems[0]

    assert problem.field == "Tenant sign here"


def test_an_unreadable_document_is_reported_not_swallowed():
    result = report(sig(), source=b"not a pdf at all")

    assert codes(result) == [UNREADABLE_PDF]
    assert result.blocked is True


@pytest.mark.parametrize(
    "options",
    [
        {"rotation": 90},
        {"rotation": 180},
        {"crop": [10, 10, 612, 792]},
        {"crop": [0, 0, 600, 790]},
        {"unit": 2},
    ],
)
def test_a_page_that_cannot_hold_a_placement_says_so_per_page(options):
    result = report(sig(), source=pdf(**options))

    assert codes(result) == [UNSUPPORTED_PDF_PAGE]
    assert result.placements == []


def test_a_page_level_defect_is_stated_once_not_once_per_field():
    result = report(
        sig(name="a"), sig(name="b", role="attorney"), source=pdf(rotation=90)
    )
    detail = placement_block_detail(result.as_dicts(), filename="Deed.pdf")

    assert len(result.problems) == 2
    assert detail.count("Rotated or scaled PDF pages") == 1


# ── Format: what can bind, and what can be rescued by hand ──────────────────


def test_a_word_document_cannot_be_signed_and_says_to_regenerate_as_pdf():
    """The hard dead end: no screen in the product can place a field on DOCX."""
    result = report(sig(overlays=None), source=b"PK\x03\x04", template_format="docx")

    assert codes(result) == [NO_PDF_OUTPUT]
    assert result.blocked is True
    assert result.recoverable is False
    detail = placement_block_detail(
        result.as_dicts(), filename="Engagement.docx", output_is_pdf=False
    )
    assert "Word-to-PDF conversion" in detail
    # Telling staff to place fields on a .docx is the instruction that stalled
    # a matter: the placement review renders with pdf.js and cannot open it.
    assert "Place the fields on the generated PDF" not in detail


def test_a_markdown_document_is_refused_the_same_way():
    result = report(
        sig(overlays=None), source=b"# Agreement", template_format="markdown"
    )

    assert codes(result) == [NO_PDF_OUTPUT]
    assert result.recoverable is False


def test_a_word_template_converted_to_pdf_is_unbound_but_rescuable_by_hand():
    result = report(
        sig(overlays=None), template_format="docx", output_format="pdf"
    )

    assert codes(result) == [WORD_SOURCE_NOT_POSITIONABLE]
    assert result.blocked is True
    # It is a real PDF, so the placement review can still open it.
    assert result.recoverable is True
    detail = placement_block_detail(result.as_dicts(), output_is_pdf=True)
    assert "placement review" in detail


def test_a_pdf_template_saved_as_pdf_binds_its_overlays():
    result = report(sig(), template_format="pdf", output_format="pdf")

    assert len(result.placements) == 1 and result.problems == []


def test_a_document_with_no_signing_fields_is_never_blocked():
    result = report(
        {"name": "client_name", "field_type": "text"},
        {"name": "filed_on", "field_type": "date"},
    )

    assert result.signing_required is False
    assert result.blocked is False and result.problems == []


def test_an_excluded_signature_field_does_not_require_signing():
    result = report(sig(included=False))

    assert result.signing_required is False and result.problems == []


# ── The manifest itself ─────────────────────────────────────────────────────


def test_bound_placements_are_pinned_to_the_exact_generated_bytes():
    source = pdf()
    result = template_placement_report(
        {"fields": [sig()]}, source=source, template_format="pdf"
    )

    digest = hashlib.sha256(source).hexdigest()
    assert all(item["source_sha256"] == digest for item in result.placements)
    assert all(item["page_width"] == 612.0 for item in result.placements)


def test_the_signing_type_decides_signature_versus_initials():
    result = report(sig(signing_type="initials"))

    assert result.placements[0]["field_type"] == "initials"


def test_a_signing_date_binds_but_an_ordinary_date_does_not():
    result = report(
        {
            "name": "signed_on",
            "field_type": "date",
            "signer_role": "client",
            "pdf_overlays": [OVERLAY],
        },
        {"name": "filed_on", "field_type": "date", "pdf_overlays": [OVERLAY]},
    )

    assert [item["field_type"] for item in result.placements] == ["date"]


def test_roles_are_reported_even_when_nothing_binds():
    """Dispatch needs the roles to know which signers the document expects."""
    result = report(sig(role="landlord", overlays=None))

    assert result.roles == ["landlord"]
    assert result.placements == []


def test_signing_field_roles_deduplicates_and_sorts():
    schema = {
        "fields": [
            sig(name="a", role="tenant"),
            sig(name="b", role="landlord"),
            sig(name="c", role="tenant"),
            sig(name="d", role=None),
        ]
    }

    assert signing_field_roles(schema) == ["landlord", "tenant"]


# ── Round-tripping through the database column ──────────────────────────────


def test_problems_survive_the_json_column_they_are_stored_in():
    result = report(sig(role=None))
    stored = result.as_dicts()

    assert stored == [
        {
            "code": MISSING_SIGNER_ROLE,
            "detail": result.problems[0].detail,
            "field": "client_sig",
            "role": "",
            "remedy": REMEDIES[MISSING_SIGNER_ROLE],
        }
    ]
    assert PlacementProblem.from_dict(stored[0]) == result.problems[0]


@pytest.mark.parametrize("junk", [None, "string", 42, [], {}, {"field": "x"}])
def test_unreadable_stored_problems_are_ignored_rather_than_crashing_dispatch(junk):
    assert PlacementProblem.from_dict(junk) is None


def test_a_document_stored_before_this_change_still_gets_an_actionable_block():
    """Rows written by the old code carry no reasons at all."""
    detail = placement_block_detail([], filename="Old.pdf")

    assert "Old.pdf" in detail and "placement review" in detail


def test_the_message_reads_the_same_from_stored_dicts_as_from_the_report():
    result = report(sig(role=None))

    assert placement_block_detail(result.problems) == placement_block_detail(
        result.as_dicts()
    )


# ── Compatibility with the callers that only want the manifest ──────────────


def test_generated_signing_metadata_still_answers_the_old_three_tuple():
    placements, roles, required = generated_signing_metadata(
        {"fields": [sig()]}, source=pdf(), template_format="pdf"
    )

    assert len(placements) == 1 and roles == ["client"] and required is True


def test_generated_signing_metadata_still_saves_an_unsigned_document():
    """Generation must never fail because a signing field is misconfigured."""
    placements, roles, required = generated_signing_metadata(
        {"fields": [sig(role=None)]}, source=pdf(), template_format="pdf"
    )

    assert placements == [] and roles == [] and required is True


def test_template_positioned_fields_still_fails_closed_for_strict_callers():
    with pytest.raises(PlacementError, match="requires a signer role"):
        template_positioned_fields({"fields": [sig(role=None)]}, source=pdf())


# ── Operability ─────────────────────────────────────────────────────────────


def test_an_unbound_field_is_logged_so_an_incident_can_be_diagnosed(caplog):
    result = report(sig(role=None))
    with caplog.at_level(logging.WARNING):
        log_placement_report(result, template_id="t-1", matter_id="m-1")

    record = caplog.records[-1]
    assert MISSING_SIGNER_ROLE in record.getMessage()
    assert record.signing_placement_blocked is True
    assert record.signing_placement_problems == result.as_dicts()
    assert record.template_id == "t-1"


def test_a_clean_binding_stays_quiet(caplog):
    with caplog.at_level(logging.WARNING):
        log_placement_report(report(sig()))

    assert caplog.records == []
