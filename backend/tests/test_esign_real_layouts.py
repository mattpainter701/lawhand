"""Signature detection against the paperwork a firm actually receives.

Detection was tuned on the starter forms the firm generates, which caption
every line "Client signature". Four documents from outside the firm -- a
referral fee agreement, a shared parenting plan, a divorce stipulation and a
cover sheet -- went through the real pipeline and none came out right: the
client was placed on the firm's "By:" line, a parent was offered thirteen
child-support blanks to sign, a stipulation's execution blocks were invisible.
The fixtures in ``esign_real_layouts`` reproduce those documents' geometry;
these tests pin what the plan now does with them, and the principle behind
it: a signer is never placed on a line printed for somebody else.
"""

import os
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.services.esign.placement import validate_placements
from app.services.esign.plan import (
    PlanField,
    SignerRef,
    _content_x,
    _deal_detected_lines,
    _party_tag,
    _role_tokens,
    _text_lines,
    _text_runs,
    build_plan,
    detect_signature_lines,
)
from tests.esign_real_layouts import (
    cover_sheet_pdf,
    parenting_plan_pdf,
    referral_fee_agreement_pdf,
    stipulation_pdf,
)

CLIENT = SignerRef("s-client", "Cal Example", "client", 0)
ATTORNEY = SignerRef("s-attorney", "Ann Example", "attorney", 1)
MOTHER = SignerRef("s-mother", "Mo Example", "mother", 0)
FATHER = SignerRef("s-father", "Fa Example", "father", 1)
PLAINTIFF = SignerRef("s-plaintiff", "Pa Example", "plaintiff", 0)
DEFENDANT = SignerRef("s-defendant", "De Example", "defendant", 1)
NOTARY = SignerRef("s-notary", "No Example", "notary", 2)


def detected(source: bytes):
    return detect_signature_lines(PdfReader(BytesIO(source)))


def signatures(plan):
    return [f for f in plan.fields if f.kind == "signature"]


def dates(plan):
    return [f for f in plan.fields if f.kind == "date"]


def draw(*rows, font_size=11) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", font_size)
    for x, y, text in rows:
        pdf.drawString(x, y, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ── The referral fee agreement ──────────────────────────────────────────────


def test_the_clients_line_is_found_though_it_never_says_signature():
    found = detected(referral_fee_agreement_pdf())

    assert [(item.page, item.label) for item in found] == [(2, "Client"), (3, "By")]


def test_a_client_sent_alone_signs_on_the_clients_line_not_the_firms():
    """The incident: the only line detected was the firm's, and the client got it."""
    plan = build_plan(referral_fee_agreement_pdf(), signers=[CLIENT])

    placed = signatures(plan)
    assert [(f.role, f.page, f.label, f.source) for f in placed] == [
        ("client", 2, "Client", "detected")
    ]
    assert not any(f.page == 3 for f in plan.fields)


def test_dated_above_and_to_the_left_pairs_with_the_clients_line():
    plan = build_plan(referral_fee_agreement_pdf(), signers=[CLIENT])

    [date] = dates(plan)
    [signature] = signatures(plan)
    assert date.role == "client" and date.page == 2
    # Left of the signature and on the line above: neither "beside" nor "below".
    assert date.rect[2] < signature.rect[0]
    assert date.rect[1] > signature.rect[1]


def test_the_firm_takes_its_by_line_when_the_attorney_also_signs():
    plan = build_plan(referral_fee_agreement_pdf(), signers=[CLIENT, ATTORNEY])

    placed = {f.role: (f.page, f.label) for f in signatures(plan)}
    assert placed == {"client": (2, "Client"), "attorney": (3, "By")}
    assert plan.placement_source == "detected"


def test_a_dated_line_split_from_its_by_line_by_the_page_break_stays_unpaired():
    """Known limit, pinned so a change to it is deliberate: dates pair on a page."""
    plan = build_plan(referral_fee_agreement_pdf(), signers=[CLIENT, ATTORNEY])

    assert [f.role for f in dates(plan)] == ["client"]


# ── The shared parenting plan ───────────────────────────────────────────────


def test_fill_in_blanks_are_not_offered_as_places_to_sign():
    """Thirteen child-support and custody blanks used to be signature lines."""
    found = detected(parenting_plan_pdf())

    assert sorted((item.page, item.label) for item in found) == [
        (4, "MOTHER"),
        (4, "Notary Public"),
        (5, "FATHER"),
        (5, "Notary Public"),
    ]
    assert not any(item.page in (1, 2, 3) for item in found)


def test_each_parent_signs_once_on_their_own_line_and_dates_it():
    plan = build_plan(parenting_plan_pdf(), signers=[MOTHER, FATHER])

    assert [(f.role, f.page, f.label) for f in signatures(plan)] == [
        ("mother", 4, "MOTHER"),
        ("father", 5, "FATHER"),
    ]
    assert [(f.role, f.page) for f in dates(plan)] == [("mother", 4), ("father", 5)]
    assert plan.placement_source == "detected"


def test_the_name_line_under_the_signature_is_not_a_second_place_to_sign():
    """"______________, MOTHER" captions the rule above it; it is not signed."""
    plan = build_plan(parenting_plan_pdf(), signers=[MOTHER])

    assert len(signatures(plan)) == 1


def test_the_date_printed_left_of_the_signature_pairs_with_it():
    plan = build_plan(parenting_plan_pdf(), signers=[MOTHER])

    [date] = dates(plan)
    [signature] = signatures(plan)
    assert date.rect[2] < signature.rect[0]
    assert abs(date.rect[1] - signature.rect[1]) < 1


def test_the_notary_acknowledgement_is_left_for_the_notary():
    plan = build_plan(parenting_plan_pdf(), signers=[MOTHER, FATHER])
    assert not any(f.role == "notary" for f in plan.fields)
    assert not any("Notary" in f.label for f in plan.fields)

    with_notary = build_plan(parenting_plan_pdf(), signers=[MOTHER, FATHER, NOTARY])
    notary_lines = [f for f in signatures(with_notary) if f.role == "notary"]
    assert notary_lines and all(f.label == "Notary Public" for f in notary_lines)


def test_the_answer_blank_after_as_follows_is_not_a_signature():
    assert not any(item.page == 3 for item in detected(parenting_plan_pdf()))


def test_a_client_role_is_never_placed_on_a_parents_line():
    plan = build_plan(parenting_plan_pdf(), signers=[CLIENT])

    assert [f.source for f in signatures(plan)] == ["fallback"]
    assert plan.placement_source == "fallback"


# ── The divorce stipulation ─────────────────────────────────────────────────


@pytest.mark.parametrize("wrapped", [True, False], ids=["wrapped caption", "one-line caption"])
def test_each_party_signs_its_own_execution_block(wrapped):
    plan = build_plan(
        stipulation_pdf(wrapped_caption=wrapped), signers=[PLAINTIFF, DEFENDANT]
    )

    assert [(f.role, f.page, f.label) for f in signatures(plan)] == [
        ("plaintiff", 2, "Plaintiff"),
        ("defendant", 3, "Defendant"),
    ]
    assert plan.placement_source == "detected"


def test_a_margin_line_number_ahead_of_the_rule_is_not_its_label():
    """"[96] ________" used to be skipped as a blank labelled "[96]"."""
    found = detected(stipulation_pdf())

    assert sorted((item.page, item.label) for item in found) == [
        (2, "Notary Public"),
        (2, "Plaintiff"),
        (3, "Defendant"),
        (3, "Notary Public"),
    ]


def test_the_notary_blocks_are_captioned_past_the_margin_number():
    plan = build_plan(stipulation_pdf(), signers=[PLAINTIFF, DEFENDANT, NOTARY])

    assert [f.page for f in signatures(plan) if f.role == "notary"] == [2, 3]


def test_a_client_role_falls_back_rather_than_signing_as_a_party():
    plan = build_plan(stipulation_pdf(), signers=[CLIENT])

    assert plan.placement_source == "fallback"
    assert not any(f.source == "detected" for f in plan.fields)


# ── The cover sheet ─────────────────────────────────────────────────────────


def test_a_document_with_nothing_to_sign_falls_back_cleanly():
    assert detected(cover_sheet_pdf()) == []
    plan = build_plan(cover_sheet_pdf(), signers=[CLIENT])
    assert [(f.kind, f.source) for f in plan.fields] == [
        ("signature", "fallback"),
        ("date", "fallback"),
    ]


# ── Across all of them ──────────────────────────────────────────────────────


CORPUS = {
    "referral fee agreement": (referral_fee_agreement_pdf, [CLIENT, ATTORNEY]),
    "parenting plan": (parenting_plan_pdf, [MOTHER, FATHER]),
    "stipulation": (stipulation_pdf, [PLAINTIFF, DEFENDANT]),
    "cover sheet": (cover_sheet_pdf, [CLIENT]),
}


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_every_signer_gets_exactly_one_signature_line(name):
    build, signers = CORPUS[name]
    plan = build_plan(build(), signers=signers)

    roles = [f.role for f in signatures(plan)]
    assert sorted(roles) == sorted(s.role for s in signers)


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_no_signer_is_placed_on_a_line_captioned_for_somebody_else(name):
    """The principle every fix above serves."""
    build, signers = CORPUS[name]
    tokens = {s.role: _role_tokens(s) for s in signers}
    plan = build_plan(build(), signers=signers)

    for field in signatures(plan):
        caption = _party_tag(field.label)
        if caption is None:
            continue
        words = set(caption.lower().replace(",", " ").split())
        assert words & tokens[field.role], (
            f"{field.role} was placed on a line captioned {field.label!r}"
        )


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_every_planned_box_passes_the_dispatch_validator(name):
    build, signers = CORPUS[name]
    plan = build_plan(build(), signers=signers)
    roles = {s.role for s in signers}

    validate_placements(
        plan.positioned_fields(),
        source_sha256=plan.source_sha256,
        signer_roles=roles,
        required_roles=sorted(roles),
    )


# ── The rules, one at a time ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("MOTHER", "MOTHER"),
        ("Notary Public", "Notary Public"),
        ("[PLAINTIFF'S FULL NAME], Plaintiff", "Plaintiff"),
        ("NAME] , Plaintiff", "Plaintiff"),
        ("______________, MOTHER", "MOTHER"),
        ("Client", "Client"),
        ("Attorney for Plaintiff", "Attorney for Plaintiff"),
        (" shall be designated the residential parent", None),
        ("Mother shall pay to Father the amount of", None),
        ("o. Clothing and Miscellaneous Child Expenses", None),
        ("Print name", None),
        ("Address", None),
        ("", None),
        ("___", None),
    ],
)
def test_party_tag_reads_captions_and_rejects_prose(text, expected):
    assert _party_tag(text) == expected


def test_dated_is_a_date_word():
    found = detected(draw((72, 600, "Client Signature: ______________   Dated: ____________")))

    assert len(found) == 1 and found[0].date_rect is not None


@pytest.mark.parametrize(
    "above",
    ["Print name:", "Address:", "exemption for the minor child as follows:"],
)
def test_a_rule_under_a_colon_line_is_that_lines_answer_blank(above):
    assert detected(draw((72, 620, above), (72, 600, "______________________"))) == []


@pytest.mark.parametrize("above", ["Signature:", "Client:", "Witness:"])
def test_a_rule_under_a_signature_or_party_caption_is_still_a_signature(above):
    assert detected(draw((72, 620, above), (72, 600, "______________________")))


def test_a_blank_opening_a_wrapped_line_of_prose_is_a_fill_in():
    assert detected(draw((72, 600, "________ shall pay to the other parent the amount of $____"))) == []


def test_a_blank_with_a_party_caption_after_it_is_a_signature():
    [found] = detected(draw((284, 600, "______________, FATHER")))

    assert found.label == "FATHER"


def test_a_party_captioned_blank_needs_a_date_nearby_to_be_a_signature():
    """"Client: ______" on an intake form is a name box."""
    assert detected(draw((72, 600, "Client: ______________________"))) == []
    assert detected(
        draw((90, 611, "Dated: ____________"), (306, 587, "Client: ______________"))
    )


def test_content_x_skips_a_margin_number_that_is_its_own_run():
    source = draw((342, 600, "[106]"), (396, 600, "Notary Public"))
    [line] = [
        line for line in _text_lines(_text_runs(PdfReader(BytesIO(source)).pages[0]))
    ]

    assert _content_x(line) == pytest.approx(396.0)


def _field(label, role=None):
    return PlanField(
        field_id=f"auto:sig:{label}",
        kind="signature",
        page=1,
        rect=(0.0, 0.0, 10.0, 10.0),
        label=label,
        required=True,
        role=role,
        source="detected",
    )


def test_captioned_lines_go_to_their_party_and_nobody_else():
    fields = [_field("Client"), _field("By"), _field("Attorney")]
    _deal_detected_lines(fields, [CLIENT])

    assert [f.role for f in fields] == ["client", None, None]


def test_uncaptioned_lines_go_only_to_signers_still_without_one():
    fields = [_field("Client"), _field("By")]
    _deal_detected_lines(fields, [CLIENT, ATTORNEY])

    assert [f.role for f in fields] == ["client", "attorney"]


def test_uncaptioned_lines_are_dealt_in_order_when_nobody_is_captioned():
    fields = [_field("Signature"), _field("Signature"), _field("Signature")]
    _deal_detected_lines(fields, [CLIENT, ATTORNEY])

    assert [f.role for f in fields] == ["client", "attorney", "client"]


def test_a_line_for_a_party_not_in_the_request_is_left_alone():
    fields = [_field("Plaintiff"), _field("Defendant")]
    _deal_detected_lines(fields, [CLIENT])

    assert [f.role for f in fields] == [None, None]


def test_a_signer_named_on_the_line_takes_it():
    fields = [_field("Example, Plaintiff")]
    _deal_detected_lines(fields, [PLAINTIFF, DEFENDANT])

    assert fields[0].role == "plaintiff"


# ── Whatever real paperwork is to hand ──────────────────────────────────────

LOCAL_CORPUS = os.environ.get("LAWHAND_SIGNING_CORPUS")
LOCAL_PDFS = sorted(Path(LOCAL_CORPUS).glob("*.pdf")) if LOCAL_CORPUS else []


@pytest.mark.skipif(
    not LOCAL_PDFS,
    reason="set LAWHAND_SIGNING_CORPUS to a directory of PDFs to run against them",
)
@pytest.mark.parametrize("path", LOCAL_PDFS, ids=[p.name for p in LOCAL_PDFS])
def test_every_pdf_in_the_local_corpus_plans_cleanly_for_one_client(path):
    """Opt-in: drop real (never committed) documents in a folder and run this.

    A document should never offer one signer more than a few places to sign;
    thirteen was the parenting plan before the fill-in rule, and this is the
    bound that would have caught it on any similar form.
    """
    plan = build_plan(path.read_bytes(), signers=[CLIENT])

    assert plan.fill_supported, plan.error
    validate_placements(
        plan.positioned_fields(),
        source_sha256=plan.source_sha256,
        signer_roles={"client"},
        required_roles=["client"],
    )
    offered = [f for f in signatures(plan) if f.source == "detected"]
    assert len(offered) <= 3, [(f.page, f.label) for f in offered]
