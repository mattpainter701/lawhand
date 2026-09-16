"""Printed signature lines, across the layouts real agreements actually use.

Detection is what saves a flat PDF that carries no AcroForm widgets: it reads
the page text and ruled lines and decides where a signer signs. These tests
cover the layouts a firm's documents come in, and pin two properties that
matter more than any single layout -- a detected box never overlaps the field
beside it, and every detected box is one the placement validator will accept.
"""

from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.services.esign.placement import validate_placements
from app.services.esign.plan import SignerRef, build_plan, detect_signature_lines

CLIENT = SignerRef("s1", "Jane Client", "client", 0)
ATTORNEY = SignerRef("s2", "Ann Attorney", "attorney", 1)


def draw(*instructions, pagesize=letter, pages=1) -> bytes:
    """Build a PDF from ``(kind, *args)`` drawing instructions."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=pagesize)
    pdf.setFont("Helvetica", 11)
    for _ in range(pages):
        for kind, *args in instructions:
            if kind == "text":
                pdf.drawString(*args)
            elif kind == "line":
                pdf.line(*args)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def detect(source: bytes):
    return detect_signature_lines(PdfReader(BytesIO(source)))


INLINE_BLANKS = (
    ("text", 72, 600, "Client Signature: ______________________   Date: ____________"),
)
LABEL_ABOVE_RULE = (
    ("text", 72, 606, "Client Signature"),
    ("line", 72, 600, 300, 600),
    ("text", 340, 606, "Date"),
    ("line", 340, 600, 480, 600),
)
LABEL_BELOW_RULE = (
    ("line", 72, 600, 300, 600),
    ("text", 72, 586, "Client Signature"),
    ("line", 340, 600, 480, 600),
    ("text", 340, 586, "Date"),
)
EXECUTION_BLOCK = (
    ("text", 72, 640, "CLIENT:"),
    ("text", 72, 610, "By: ______________________________"),
    ("text", 72, 590, "Name: Jane Client"),
    ("text", 72, 570, "Date: ____________"),
)
BARE_RULE = (
    ("text", 72, 600, "______________________________"),
    ("text", 72, 586, "Client"),
)

LAYOUTS = {
    "inline underscore blanks": INLINE_BLANKS,
    "label above the ruled line": LABEL_ABOVE_RULE,
    "label below the ruled line": LABEL_BELOW_RULE,
    "By: execution block": EXECUTION_BLOCK,
    "bare rule with no label": BARE_RULE,
}


# ── Every layout a firm's paperwork arrives in ──────────────────────────────


@pytest.mark.parametrize("label", sorted(LAYOUTS))
def test_each_printed_layout_yields_a_signature_line(label):
    found = detect(draw(*LAYOUTS[label]))

    assert found, f"no signature line detected in the {label} layout"
    assert all(item.page == 1 for item in found)


@pytest.mark.parametrize("label", sorted(set(LAYOUTS) - {"bare rule with no label"}))
def test_a_date_printed_beside_the_line_is_paired_with_it(label):
    found = detect(draw(*LAYOUTS[label]))

    assert found[0].date_rect is not None


def test_an_unpaired_date_is_left_alone():
    """A filing date on a form is not the signer's date."""
    found = detect(draw(("text", 72, 700, "Date of incident: ____________")))

    assert found == []


@pytest.mark.parametrize(
    "line",
    [
        "Name: ______________________",
        "Referred by: ______________________",
        "Reviewed by: ______________________",
        "Case number: ______________________",
    ],
)
def test_a_blank_that_is_not_a_signature_line_is_not_offered_as_one(line):
    assert detect(draw(("text", 72, 600, line))) == []


def test_a_sentence_mentioning_signing_is_not_a_signature_line():
    found = detect(
        draw(("text", 72, 700, "This agreement is signed by the parties below."))
    )

    assert found == []


# ── The regression: two fields on one baseline ──────────────────────────────


def test_a_detected_signature_box_never_covers_the_date_beside_it():
    """The default 200pt box used to be laid straight over the date label."""
    found = detect(draw(*INLINE_BLANKS))

    signature = found[0]
    assert signature.date_rect is not None
    assert signature.rect[2] <= signature.date_rect[0], (
        "signature box overlaps the date field on the same baseline"
    )


def test_three_fields_on_one_baseline_stay_apart():
    found = detect(
        draw(
            (
                "text",
                40,
                600,
                "Signature: __________  Initials: ______  Date: __________",
            )
        )
    )

    assert found
    boxes = sorted(
        [item.rect for item in found]
        + [item.date_rect for item in found if item.date_rect]
    )
    for left, right in zip(boxes, boxes[1:]):
        assert left[2] <= right[0], f"{left} overlaps {right}"


def test_a_blank_with_nothing_after_it_still_gets_a_usable_box():
    """Clamping to the next field must not shrink a line that has no neighbour."""
    # Eight underscores is the shortest run the detector reads as a blank.
    found = detect(draw(("text", 72, 600, "Client Signature: ________")))

    assert found[0].rect[2] - found[0].rect[0] >= 180


def test_a_wide_printed_blank_is_not_narrowed_to_the_default_box():
    wide = detect(draw(("text", 72, 600, "Signature: " + "_" * 60)))[0]

    assert wide.rect[2] - wide.rect[0] > 200


# ── Detected geometry has to satisfy the validator that gates dispatch ──────


@pytest.mark.parametrize("label", sorted(LAYOUTS))
def test_every_detected_box_is_one_the_placement_validator_accepts(label):
    """Detection and validation disagreeing would block a signable document."""
    source = draw(*LAYOUTS[label])
    plan = build_plan(source, signers=[CLIENT])
    persisted = plan.positioned_fields()

    assert persisted
    validate_placements(
        persisted,
        source_sha256=plan.source_sha256,
        signer_roles={"client"},
        required_roles=["client"],
    )


@pytest.mark.parametrize("label", sorted(LAYOUTS))
def test_detected_boxes_stay_inside_the_page(label):
    for item in detect(draw(*LAYOUTS[label])):
        x0, y0, x1, y1 = item.rect
        assert 0 <= x0 < x1 <= 612 and 0 <= y0 < y1 <= 792


def test_a_line_drawn_hard_against_the_right_margin_is_clamped():
    found = detect(draw(("text", 560, 600, "Signature: ______________________")))

    assert all(item.rect[2] <= 612 for item in found)


# ── The plan always ends with somewhere to sign ─────────────────────────────


@pytest.mark.parametrize("label", sorted(LAYOUTS))
def test_every_signer_gets_a_signature_field_whatever_the_layout(label):
    plan = build_plan(draw(*LAYOUTS[label]), signers=[CLIENT, ATTORNEY])

    covered = {field.role for field in plan.fields if field.kind == "signature"}
    assert covered == {"client", "attorney"}


def test_a_document_with_nothing_printed_still_falls_back_to_a_block():
    plan = build_plan(draw(("text", 72, 700, "Nothing to sign here.")), signers=[CLIENT])

    signatures = [field for field in plan.fields if field.kind == "signature"]
    assert [field.source for field in signatures] == ["fallback"]
    assert signatures[0].role == "client"


def test_detection_runs_on_every_page():
    plan = build_plan(draw(*INLINE_BLANKS, pages=3), signers=[CLIENT])

    pages = {field.page for field in plan.fields if field.kind == "signature"}
    assert pages == {1, 2, 3}


def test_an_a4_agreement_is_detected_the_same_way():
    found = detect(draw(*INLINE_BLANKS, pagesize=(595, 842)))

    assert found and found[0].rect[2] <= 595
