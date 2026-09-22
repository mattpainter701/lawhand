#!/usr/bin/env python3
"""Author the firm-paperwork samples in the global library as AcroForm PDFs.

The curated library in ``backend/seed/sample_templates`` is otherwise built
from scraped public forms (``scripts/build_sample_template_library.py``). The
three forms a firm opens every matter with — the fee agreement, the
prospective-client intake form, and the client questionnaire — have no public
source worth scraping: their value is that every field is named after the
variable the platform already fills from, so an answer a client gives once is
reused rather than retyped.

So they are authored here. This module is the source; the committed PDF is the
artifact. Each field declares the binding its value comes from (a path from the
server-owned catalogue in ``app.services.template_bindings``), and those
declarations ride into the seeded ``variable_schema`` through the manifest, so
Smart Fill resolves them without a firm re-declaring anything.

Entries are written with ``"origin": "authored"``, which the scraped-library
builder preserves.

Attorney review still applies. Fee, trust-account, and contingency terms are
regulated per jurisdiction: the agreement states the structure and leaves the
regulated wording to the firm rather than guessing at a rule.

Run:  python backend/scripts/build_library_intake_forms.py
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = BACKEND_ROOT / "seed" / "sample_templates"

sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db"
)
os.environ.setdefault(
    "SECRET_KEY", "build-script-only-0000000000000000000000000000000000000000"
)
os.environ.setdefault(
    "TOKEN_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)

from app.services.pdf_templates import discover_pdf_fields  # noqa: E402
from app.services.template_bindings import is_valid_binding  # noqa: E402

PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 54.0
BODY = ("Helvetica", 9.0)
BODY_BOLD = ("Helvetica-Bold", 9.0)


def _plain_tooltip(text: str) -> str:
    """Remove authoring-only emphasis markers from PDF accessibility labels."""

    return text.replace("**", "")


LEADING = 12.0
LABEL_SIZE = 6.8
BOX_HEIGHT = 13.0
BOX_LINE = 11.5
CHECK_SIZE = 9.0
FIELD_BORDER = Color(0.45, 0.50, 0.58)
FIELD_FILL = Color(0.95, 0.96, 0.98)
LABEL_INK = Color(0.36, 0.40, 0.46)
RULE = Color(0.78, 0.80, 0.84)
#: Long enough for a narrative answer, short enough that a paste cannot be used
#: to smuggle a document into a form field.
MAXLEN = 2000

#: reportlab defaults ``checkbox`` to ``fieldFlags='required'`` and ``radio`` to
#: ``'noToggleToOff required radio'``. A required checkbox that is false blocks
#: generation outright (``fill_pdf_template`` raises "Required PDF field(s) are
#: empty or unchecked"), and for a yes/no group the requirement is not even
#: satisfiable, so both are declared optional here. ``radio`` is kept because it
#: is what makes a group mutually exclusive; ``noToggleToOff`` is dropped so a
#: mis-click can be cleared.
CHECKBOX_FLAGS = ""
RADIO_FLAGS = "radio"


@dataclass(frozen=True)
class Field:
    """One AcroForm field and the platform variable it carries.

    ``binding`` is a path from the server-owned catalogue, and empty for a fact
    only the person filling the form knows — a witness's phone number has no
    record behind it. An empty binding is left undeclared rather than recorded
    as ``manual``: name matching still has a chance at it, and declaring
    ``manual`` would switch that off.
    """

    name: str
    label: str
    binding: str = ""
    weight: float = 1.0
    lines: int = 0
    default: str = ""


@dataclass(frozen=True)
class Choice:
    """One option inside a radio group.

    ``value`` becomes the widget's on-state, which is what
    ``discover_pdf_fields`` reports in ``options`` and what a generated
    document must supply.
    """

    value: str
    label: str


def H1(text: str) -> tuple:
    return ("h1", text)


def H2(text: str) -> tuple:
    return ("h2", text)


def H3(text: str) -> tuple:
    return ("h3", text)


def P(text: str) -> tuple:
    return ("p", text)


def NOTE(text: str) -> tuple:
    return ("note", text)


def RULE_() -> tuple:
    return ("rule",)


def ROW(*fields: Field) -> tuple:
    return ("row", fields)


def BLOCK(field: Field) -> tuple:
    return ("block", field)


def CHECKS(prompt: str, options: tuple[Field, ...], columns: int = 3) -> tuple:
    return ("checks", prompt, options, columns)


def RADIO(
    prompt: str,
    name: str,
    choices: tuple[Choice, ...],
    binding: str = "",
    label: str = "",
) -> tuple:
    """One mutually exclusive question.

    ``CHECKS`` models a yes/no question as two independent boxes, which a
    client can tick both of. A radio group is the AcroForm shape that says one
    answer: the reader enforces the exclusivity and the engine reports a single
    field carrying ``options``.
    """

    return ("radio", prompt, name, choices, binding, label or prompt)


def SIGN(label: str) -> tuple:
    return ("sign", label)


def KEEP(height: float) -> tuple:
    """Start a new page unless ``height`` points remain, so a closing section
    and the signature under it stay together."""

    return ("keep", height)


@dataclass(frozen=True)
class LibraryForm:
    """One authored sample: its catalog metadata and its printed blocks."""

    slug: str
    title: str
    category: str
    description: str
    blocks: tuple
    jurisdictions: tuple[str, ...] = ()

    @property
    def filename(self) -> str:
        return f"{self.category}/{self.slug}.pdf"

    def fields(self) -> list[Field]:
        found: list[Field] = []
        for block in self.blocks:
            if block[0] == "row":
                found.extend(block[1])
            elif block[0] == "block":
                found.append(block[1])
            elif block[0] == "checks":
                found.extend(block[2])
        return found

    def bindings(self) -> dict[str, str]:
        declared = {
            entry.name: entry.binding for entry in self.fields() if entry.binding
        }
        for block in self.blocks:
            if block[0] == "radio" and block[4]:
                declared[block[2]] = block[4]
        return declared

    def radio_names(self) -> list[str]:
        """Field names contributed by radio groups rather than ``Field`` rows."""

        return [block[2] for block in self.blocks if block[0] == "radio"]


class Sheet:
    """A paginated canvas that places prose and form fields as it goes."""

    def __init__(self, title: str):
        self.buffer = io.BytesIO()
        self.canvas = canvas.Canvas(self.buffer, pagesize=letter)
        self.canvas.setTitle(title)
        self.title = title
        self.y = PAGE_HEIGHT - MARGIN
        self.page = 1
        self.placed: list[str] = []
        self._footer()

    @property
    def width(self) -> float:
        return PAGE_WIDTH - 2 * MARGIN

    def _footer(self) -> None:
        self.canvas.setFont("Helvetica", 7.0)
        self.canvas.setFillColor(LABEL_INK)
        self.canvas.drawString(MARGIN, MARGIN - 24, self.title)
        self.canvas.drawRightString(
            PAGE_WIDTH - MARGIN, MARGIN - 24, f"Page {self.page}"
        )
        self.canvas.setFillColor(black)

    def space(self, needed: float) -> None:
        if self.y - needed < MARGIN + 6:
            self.canvas.showPage()
            self.page += 1
            self.y = PAGE_HEIGHT - MARGIN
            self._footer()

    def rule(self, gap: float = 9.0) -> None:
        self.space(gap + 6)
        self.y -= gap
        self.canvas.setStrokeColor(RULE)
        self.canvas.setLineWidth(0.6)
        self.canvas.line(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y)
        self.y -= gap

    def title_block(self, text: str) -> None:
        self.space(30)
        self.y -= 18
        self.canvas.setFont("Helvetica-Bold", 14.5)
        self.canvas.drawCentredString(PAGE_WIDTH / 2, self.y, text.upper())
        self.y -= 8

    def heading(self, text: str, level: int = 2) -> None:
        size = 10.0 if level == 2 else 9.0
        self.space(size + 24)
        self.y -= size + 9
        self.canvas.setFont("Helvetica-Bold", size)
        self.canvas.drawString(MARGIN, self.y, text)
        self.y -= 5

    def paragraph(
        self, text: str, *, indent: float = 0.0, small: bool = False, gap: float = 4.0
    ) -> None:
        """Wrap one paragraph, honouring ``**bold**`` runs."""

        font = ("Helvetica", 7.6) if small else BODY
        bold_font = ("Helvetica-Bold", 7.6) if small else BODY_BOLD
        leading = 10.0 if small else LEADING
        left = MARGIN + indent
        limit = PAGE_WIDTH - MARGIN
        self.space(leading * 2)
        self.y -= leading
        x = left
        bold = False
        if small:
            self.canvas.setFillColor(LABEL_INK)
        for chunk in text.split("**"):
            for word in chunk.split():
                active = bold_font if bold else font
                advance = self.canvas.stringWidth(word + " ", *active)
                if x + advance > limit and x > left:
                    self.y -= leading
                    self.space(leading)
                    x = left
                self.canvas.setFont(*active)
                self.canvas.drawString(x, self.y, word + " ")
                x += advance
            bold = not bold
        self.canvas.setFillColor(black)
        self.y -= gap

    def _textfield(
        self,
        entry: Field,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        multiline: bool = False,
    ) -> None:
        self.placed.append(entry.name)
        self.canvas.acroForm.textfield(
            name=entry.name,
            value=entry.default,
            tooltip=_plain_tooltip(entry.label),
            x=x,
            y=y,
            width=width,
            height=height,
            fontSize=8.5,
            maxlen=MAXLEN,
            borderWidth=0.6,
            borderColor=FIELD_BORDER,
            fillColor=FIELD_FILL,
            textColor=black,
            fieldFlags="multiline" if multiline else "",
        )

    def _caption(self, text: str, x: float, y: float) -> None:
        self.canvas.setFont("Helvetica", LABEL_SIZE)
        self.canvas.setFillColor(LABEL_INK)
        self.canvas.drawString(x, y, text)
        self.canvas.setFillColor(black)

    def row(self, fields: tuple[Field, ...]) -> None:
        """One row of captioned boxes, sized by each field's weight."""

        total = sum(entry.weight for entry in fields)
        gutter = 8.0
        available = self.width - gutter * (len(fields) - 1)
        self.space(BOX_HEIGHT + 20)
        self.y -= BOX_HEIGHT + 12
        x = MARGIN
        for entry in fields:
            width = available * (entry.weight / total)
            self._caption(entry.label, x, self.y + BOX_HEIGHT + 3)
            self._textfield(entry, x, self.y, width, BOX_HEIGHT)
            x += width + gutter
        self.y -= 4

    def block(self, entry: Field) -> None:
        """A paragraph-sized answer box under its own caption."""

        height = max(2, entry.lines or 3) * BOX_LINE + 4
        self.space(height + 22)
        self.y -= height + 12
        self._caption(entry.label, MARGIN, self.y + height + 3)
        self._textfield(entry, MARGIN, self.y, self.width, height, multiline=True)
        self.y -= 4

    def checks(self, prompt: str, options: tuple[Field, ...], columns: int) -> None:
        """A prompt and its checkboxes, laid out in columns."""

        column_width = self.width / columns
        rows = (len(options) + columns - 1) // columns
        needed = rows * (CHECK_SIZE + 6.5) + 8
        if prompt:
            # A prompt stranded at the foot of a page with its options overleaf
            # reads as an unanswered question, so the group moves as one.
            self.space(needed + 2 * LEADING)
            self.paragraph(prompt, gap=1.0)
        self.space(needed)
        for index, entry in enumerate(options):
            column = index % columns
            if column == 0:
                self.y -= CHECK_SIZE + 6.5
                self.space(CHECK_SIZE + 6.5)
            x = MARGIN + column * column_width
            self.placed.append(entry.name)
            self.canvas.acroForm.checkbox(
                name=entry.name,
                tooltip=_plain_tooltip(entry.label),
                x=x,
                y=self.y,
                size=CHECK_SIZE,
                buttonStyle="check",
                borderWidth=0.6,
                borderColor=FIELD_BORDER,
                fillColor=FIELD_FILL,
                textColor=black,
                fieldFlags=CHECKBOX_FLAGS,
            )
            self.canvas.setFont("Helvetica", 8.4)
            self.canvas.drawString(x + CHECK_SIZE + 5, self.y + 1.5, entry.label)
        self.y -= 6

    def radio_group(
        self, prompt: str, name: str, choices: tuple[Choice, ...], label: str
    ) -> None:
        """A prompt and its mutually exclusive options, on one line if they fit."""

        option_width = 14.0 + CHECK_SIZE
        options_width = sum(
            option_width + self.canvas.stringWidth(choice.label, "Helvetica", 8.4)
            for choice in choices
        )
        prompt_width = self.canvas.stringWidth(prompt, *BODY)
        one_line = prompt_width + 12 + options_width <= self.width

        self.space(CHECK_SIZE + 24 if one_line else CHECK_SIZE + 24 + LEADING)
        if one_line:
            self.y -= CHECK_SIZE + 8
            self.canvas.setFont(*BODY)
            self.canvas.drawString(MARGIN, self.y + 1.5, prompt)
            x = MARGIN + prompt_width + 12
        else:
            self.paragraph(prompt, gap=1.0)
            self.y -= CHECK_SIZE + 5
            x = MARGIN

        self.placed.append(name)
        for choice in choices:
            self.canvas.acroForm.radio(
                name=name,
                value=choice.value,
                tooltip=_plain_tooltip(label),
                selected=False,
                x=x,
                y=self.y,
                size=CHECK_SIZE,
                buttonStyle="circle",
                shape="circle",
                borderWidth=0.6,
                borderColor=FIELD_BORDER,
                fillColor=FIELD_FILL,
                textColor=black,
                fieldFlags=RADIO_FLAGS,
            )
            self.canvas.setFont("Helvetica", 8.4)
            self.canvas.drawString(x + CHECK_SIZE + 4, self.y + 1.5, choice.label)
            x += option_width + self.canvas.stringWidth(choice.label, "Helvetica", 8.4)
        self.y -= 6

    def signature(self, label: str) -> None:
        """A ruled line to sign on.

        Printed as a rule with a "Signature"/"Date" caption rather than a
        signature widget: that is the shape the portal's signature-line
        detection looks for, so an electronically signed copy lands on the same
        line a hand-signed copy does.
        """

        # A signature line is always followed by the printed-name row in these
        # forms; reserving its height too keeps the block off two pages.
        self.space(58 + BOX_HEIGHT + 24)
        self.y -= 26
        self.canvas.setStrokeColor(black)
        self.canvas.setLineWidth(0.8)
        self.canvas.line(MARGIN, self.y, MARGIN + 250, self.y)
        self.canvas.line(MARGIN + 280, self.y, MARGIN + 410, self.y)
        self.canvas.setFont("Helvetica", 7.5)
        self.canvas.drawString(MARGIN, self.y - 9, label)
        self.canvas.drawString(MARGIN + 280, self.y - 9, "Date")
        self.y -= 16

    def save(self) -> bytes:
        # Values printed as defaults have no appearance stream of their own;
        # without this a reader that does not regenerate appearances shows the
        # box empty even though the value is in the file.
        self.canvas.acroForm.extras["NeedAppearances"] = b"true"
        self.canvas.showPage()
        self.canvas.save()
        return self.buffer.getvalue()


def render(form: LibraryForm) -> bytes:
    sheet = Sheet(form.title)
    for block in form.blocks:
        kind = block[0]
        if kind == "h1":
            sheet.title_block(block[1])
        elif kind == "h2":
            sheet.heading(block[1], 2)
        elif kind == "h3":
            sheet.heading(block[1], 3)
        elif kind == "p":
            sheet.paragraph(block[1])
        elif kind == "note":
            sheet.paragraph(block[1], small=True)
        elif kind == "rule":
            sheet.rule()
        elif kind == "row":
            sheet.row(block[1])
        elif kind == "block":
            sheet.block(block[1])
        elif kind == "checks":
            sheet.checks(block[1], block[2], block[3])
        elif kind == "radio":
            sheet.radio_group(block[1], block[2], block[3], block[5])
        elif kind == "sign":
            sheet.signature(block[1])
        elif kind == "keep":
            sheet.space(block[1])
        else:  # pragma: no cover - a typo in a form definition
            raise ValueError(f"Unknown block: {kind}")
    return _strip_metadata(sheet.save())


def _strip_metadata(content: bytes) -> bytes:
    """Remove the producer/creator identity reportlab writes into the file.

    The catalog ships no authoring metadata — ``test_sample_template_library``
    asserts it — so the document information dictionary is dropped before the
    PDF is committed.
    """

    reader = PdfReader(io.BytesIO(content), strict=False)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer._info = None
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


REVIEW_NOTE = (
    "Attorney review required. This is a starting form, not legal advice. Fee, "
    "trust-account, contingency, and client-communication requirements differ by "
    "jurisdiction: an attorney must review and adapt this document, and confirm "
    "it against the applicable rules of professional conduct, before it is used "
    "with a client."
)


FEE_AGREEMENT = LibraryForm(
    slug="general-legal-services-fee-agreement",
    title="Fee Agreement — Legal Services (All Matter Types)",
    category="engagement_letter",
    description=(
        "Jurisdiction-neutral engagement agreement for any practice area. The "
        "fee section carries every common arrangement — hourly, flat, "
        "contingency, hybrid, and recurring — selected by checkbox, so one "
        "template serves the whole firm. Fields carry the platform bindings for "
        "firm, client, matter, rate, retainer, and venue. Fee and trust-account "
        "terms are jurisdiction-regulated: an attorney must review and approve "
        "the wording before it is sent."
    ),
    blocks=(
        H1("Agreement for Legal Services"),
        NOTE(REVIEW_NOTE),
        P(
            "This Agreement for Legal Services (the “Agreement”) is made "
            "between the law firm identified below (the “Firm”) and the "
            "client identified below (the “Client”). It states the work "
            "the Firm will do, what that work will cost, and what each party is "
            "responsible for. The Client should read it in full and ask about "
            "anything that is not clear before signing."
        ),
        H2("The parties"),
        ROW(
            Field("firm_name", "Firm", "firm.name", 2.2),
            Field("attorney_name", "Responsible attorney", "attorney.name", 1.8),
            Field("agreement_date", "Date of this Agreement", "", 1.0),
        ),
        ROW(
            Field("firm_address", "Firm address", "firm.address", 2.2),
            Field("firm_phone", "Firm phone", "firm.phone", 1.0),
            Field("firm_email", "Firm email", "firm.email", 1.4),
        ),
        ROW(
            Field("client_name", "Client (full legal name)", "client.name", 2.2),
            Field(
                "co_client_name",
                "Additional client, if the Firm represents more than one",
                "",
                2.2,
            ),
        ),
        ROW(
            Field("client_street", "Street address", "client.address.street", 2.4),
            Field("client_city", "City", "client.address.city", 1.2),
            Field("client_state", "State", "client.address.state", 0.5),
            Field("client_zip", "ZIP", "client.address.zip", 0.6),
        ),
        ROW(
            Field("client_phone", "Client phone", "client.phone", 1.0),
            Field("client_email", "Client email", "client.email", 1.6),
        ),
        H2("1. The matter and the scope of representation"),
        ROW(
            Field("matter_name", "Matter", "matter.name", 2.4),
            Field("matter_type", "Matter type", "matter.type", 1.4),
        ),
        CHECKS(
            "**Nature of the matter** (check all that apply):",
            (
                Field("practice_area_family", "Family law"),
                Field("practice_area_criminal", "Criminal defense"),
                Field("practice_area_injury", "Personal injury"),
                Field("practice_area_estate", "Estate planning / probate"),
                Field("practice_area_business", "Business / commercial"),
                Field("practice_area_real_estate", "Real estate"),
                Field("practice_area_immigration", "Immigration"),
                Field("practice_area_employment", "Employment"),
                Field("practice_area_litigation", "Civil litigation"),
                Field("practice_area_bankruptcy", "Bankruptcy / debt"),
                Field("practice_area_administrative", "Administrative / agency"),
                Field("practice_area_other", "Other (described below)"),
            ),
            3,
        ),
        ROW(
            Field("matter_jurisdiction", "Jurisdiction", "matter.jurisdiction", 1.2),
            Field("court", "Court or agency, if a case exists", "matter.court", 1.6),
            Field("case_number", "Case number", "matter.case_number", 1.2),
        ),
        ROW(
            Field("counterparty", "Other party or parties", "matter.counterparty", 2.4),
            Field("matter_role", "The Client's role or side", "matter.role", 1.4),
        ),
        BLOCK(
            Field(
                "matter_description",
                "Description of the matter",
                "matter.description",
                lines=3,
            )
        ),
        BLOCK(
            Field(
                "scope_of_representation",
                "Services the Firm agrees to provide in this matter",
                lines=4,
            )
        ),
        CHECKS(
            "**Stage of representation covered by this Agreement** "
            "(check all that apply):",
            (
                Field("scope_stage_advice", "Advice and counsel"),
                Field("scope_stage_negotiation", "Negotiation and settlement"),
                Field("scope_stage_drafting", "Drafting and review of documents"),
                Field("scope_stage_filing", "Filing and trial-court proceedings"),
                Field("scope_stage_hearing", "Contested hearing or trial"),
                Field("scope_stage_appeal", "Appeal"),
                Field("scope_stage_limited", "Limited scope (described below)"),
                Field("scope_stage_transaction", "Transaction or closing"),
                Field("scope_stage_administrative", "Administrative hearing"),
            ),
            3,
        ),
        BLOCK(
            Field(
                "limited_scope_terms",
                "If the representation is limited in scope, state exactly what the "
                "Firm will and will not do",
                lines=2,
            )
        ),
        BLOCK(
            Field(
                "excluded_matters",
                "Services this Agreement does not cover",
                lines=3,
            )
        ),
        P(
            "Appeals, enforcement or collection of a judgment or order, and any new "
            "or related matter are not covered unless this Agreement expressly says "
            "so. Work outside the scope stated above requires a separate written "
            "agreement or an amendment to this one signed by both parties. Other "
            "lawyers and staff of the Firm may work on the matter under the "
            "responsible attorney's supervision."
        ),
        H2("2. Fees"),
        P(
            "The Client agrees to pay for the Firm's services on the basis checked "
            "below. Only a checked arrangement applies to this matter; the "
            "subsections that are not checked are of no effect."
        ),
        CHECKS(
            "",
            (
                Field("fee_basis_hourly", "Hourly fee"),
                Field("fee_basis_flat", "Flat fee"),
                Field("fee_basis_contingency", "Contingency fee"),
                Field("fee_basis_hybrid", "Hybrid or other arrangement"),
                Field("fee_basis_recurring", "Recurring / subscription fee"),
            ),
            3,
        ),
        H3("2.1  Hourly fees"),
        ROW(
            Field(
                "hourly_rate", "Responsible attorney rate", "matter.hourly_rate", 1.2
            ),
            Field("attorney_rate_range", "Other attorneys of the Firm", "", 1.3),
            Field("staff_rate_range", "Paralegals and law clerks", "", 1.3),
        ),
        ROW(
            Field(
                "billing_increment",
                "Time is recorded in increments of",
                "",
                1.2,
                default="0.1 hour (six minutes)",
            ),
            Field(
                "minimum_time_charge",
                "Minimum charge for a call or email",
                "",
                1.2,
                default="0.1 hour",
            ),
            Field("rate_change_notice", "Notice before a rate change", "", 1.2),
        ),
        P(
            "Billed time includes calls, correspondence, drafting, review, legal "
            "research, negotiation, discovery, preparation, travel, and court or "
            "agency appearances. Time is rounded up to the nearest increment stated "
            "above."
        ),
        H3("2.2  Flat fee"),
        ROW(
            Field("flat_fee_amount", "Flat fee for the services in section 1", "", 1.4),
            Field("flat_fee_deposit", "Amount due at signing", "", 1.2),
        ),
        BLOCK(Field("flat_fee_payment_terms", "How the flat fee is paid", lines=2)),
        P(
            "A flat fee covers only the services described in section 1. If the "
            "representation ends before those services are complete, the Firm is "
            "entitled to the portion of the fee it has earned, measured by the work "
            "performed, and the Client is refunded the rest."
        ),
        H3("2.3  Contingency fee"),
        ROW(
            Field(
                "contingency_percentage",
                "Percentage before suit is filed",
                "matter.contingency_percentage",
                1.3,
            ),
            Field(
                "contingency_percentage_suit", "Percentage after suit is filed", "", 1.3
            ),
            Field("contingency_percentage_appeal", "Percentage if appealed", "", 1.3),
        ),
        CHECKS(
            "Costs and expenses are deducted from the recovery:",
            (
                Field("contingency_costs_before_fee", "Before the fee is calculated"),
                Field("contingency_costs_after_fee", "After the fee is calculated"),
            ),
            2,
        ),
        BLOCK(
            Field(
                "contingency_terms",
                "How the recovery and the fee are calculated, including any "
                "structured settlement, lien, or subrogation claim",
                lines=2,
            )
        ),
        P(
            "If there is no recovery, no attorney fee is owed. The Client remains "
            "responsible for costs and expenses under section 4 except as this "
            "Agreement states otherwise. Before any money is disbursed the Client "
            "will receive a written statement showing the amount recovered, the fee, "
            "and every cost deducted."
        ),
        H3("2.4  Hybrid or other arrangement"),
        BLOCK(
            Field(
                "hybrid_fee_terms",
                "State the arrangement in full, including any reduced hourly rate, "
                "earned-on-receipt term, or success fee",
                lines=3,
            )
        ),
        H3("2.5  Recurring or subscription fee"),
        ROW(
            Field("recurring_fee_amount", "Recurring fee", "", 1.2),
            Field("recurring_fee_period", "Billed every", "", 1.0),
            Field(
                "recurring_fee_notice",
                "Notice to end the recurring engagement",
                "",
                1.4,
                default="thirty (30) days",
            ),
        ),
        P(
            "The Firm has made no promise about the outcome of this matter, the total "
            "amount of fees, or how long the matter will take. Any estimate is a "
            "good-faith projection, not a cap."
        ),
        H2("3. Advance deposit and the client trust account"),
        ROW(
            Field(
                "retainer_amount",
                "Advance deposit (retainer)",
                "matter.retainer_amount",
                1.3,
            ),
            Field(
                "retainer_minimum_balance",
                "Replenishment threshold",
                "matter.retainer_minimum_balance",
                1.3,
            ),
            Field("retainer_due", "Deposit due", "", 1.2),
        ),
        P(
            "The Client will deposit the advance with the Firm before work begins. "
            "The Firm holds it in its client trust account and applies it to fees and "
            "costs as they are billed and earned. The Firm will tell the Client when "
            "the trust balance falls below the replenishment threshold, and the Client "
            "agrees to restore the deposit promptly; the Firm may stop work if it is "
            "not restored. Any unearned balance is refunded to the Client when the "
            "representation ends."
        ),
        BLOCK(
            Field(
                "trust_account_terms",
                "Trust-account and advance-fee terms required in this jurisdiction",
                lines=2,
            )
        ),
        H2("4. Costs and expenses"),
        P(
            "Costs and expenses are separate from fees and are the Client's "
            "responsibility. They include filing and court fees, service of process, "
            "court reporters and transcripts, records, expert and investigator fees, "
            "mediation and arbitration fees, electronic discovery, travel, and "
            "delivery charges."
        ),
        CHECKS(
            "Costs are:",
            (
                Field(
                    "costs_advanced_by_firm",
                    "Advanced by the Firm and billed to the Client",
                ),
                Field(
                    "costs_paid_by_client", "Paid by the Client as they are incurred"
                ),
            ),
            2,
        ),
        ROW(
            Field(
                "cost_approval_threshold",
                "The Firm will obtain the Client's approval before incurring any "
                "single cost above",
                "",
                1.6,
            ),
            Field("cost_deposit_amount", "Cost deposit, if any", "", 1.0),
        ),
        BLOCK(
            Field(
                "cost_authorization_terms",
                "Additional terms about costs",
                lines=2,
            )
        ),
        H2("5. Statements and payment"),
        ROW(
            Field("billing_cycle", "Statements are sent", "matter.billing_cycle", 1.2),
            Field(
                "payment_due_days",
                "Payment due after the statement date",
                "",
                1.4,
                default="fifteen (15) days",
            ),
            Field("late_charge_rate", "Late charge on an overdue balance", "", 1.4),
        ),
        P(
            "Each statement shows the work performed, the fees and costs charged, and "
            "any trust balance. The Client should review each statement promptly and "
            "tell the Firm of any question or disagreement within the time stated on "
            "it. The Firm may stop work, and may seek to withdraw, if a statement is "
            "not paid when due."
        ),
        H2("6. The Client's responsibilities"),
        P(
            "The Client agrees to be truthful and complete with the Firm; to provide "
            "requested documents and information promptly; to preserve documents, "
            "messages, recordings, and other records relating to the matter; to keep "
            "appointments and court dates; to report any change of address, telephone "
            "number, email address, or employment; and to make the decisions the law "
            "reserves to the Client, including whether to settle."
        ),
        H2("7. Communication and confidentiality"),
        P(
            "The Firm will keep the Client reasonably informed and will respond to "
            "inquiries within a reasonable time. Communications between the Client and "
            "the Firm about this matter are confidential and protected by the "
            "attorney-client privilege. Sharing them with anyone outside the "
            "representation can waive that protection."
        ),
        CHECKS(
            "The Client consents to receiving communications about this matter by:",
            (
                Field("consent_email", "Email"),
                Field("consent_text", "Text message"),
                Field("consent_phone", "Telephone"),
                Field("consent_portal", "Secure client portal"),
                Field("consent_mail", "Postal mail"),
                Field("consent_esignature", "Electronic signature"),
            ),
            3,
        ),
        ROW(
            Field(
                "authorized_disclosure_contacts",
                "People the Firm may discuss this matter with (naming someone here "
                "permits disclosure to them; leave blank for none)",
                "",
                3.0,
            ),
        ),
        H2("8. Payment by someone other than the Client"),
        ROW(
            Field("third_party_payor_name", "Third party paying fees, if any", "", 2.0),
            Field(
                "third_party_payor_relationship",
                "Relationship to the Client",
                "",
                1.4,
            ),
        ),
        P(
            "A third party who pays the Client's fees is not the Firm's client, has no "
            "right to direct the representation, and is not entitled to confidential "
            "information without the Client's written consent. The Client may withdraw "
            "that consent at any time. Time the Firm spends dealing with a third-party "
            "payor is billed to the Client."
        ),
        H2("9. Ending the representation"),
        P(
            "The Client may end this representation at any time by written notice. The "
            "Firm may withdraw to the extent the rules of professional conduct allow, "
            "including for non-payment or for a material misrepresentation by the "
            "Client, after reasonable notice and steps to protect the Client's "
            "interests. Withdrawal in a pending case requires court approval. If the "
            "representation ends, the Client remains responsible for fees earned and "
            "costs incurred through that date, and the Firm may apply trust funds to "
            "the outstanding balance."
        ),
        H2("10. The Firm's right to fees"),
        P(
            "To the extent the law allows, the Client grants the Firm a lien against "
            "funds held for the Client in the Firm's trust account and against any "
            "recovery in this matter, for fees earned and costs advanced. The lien is "
            "released when the balance is paid in full. Any award of attorney fees "
            "against another party does not make that party responsible to the Firm, "
            "and the Client remains responsible for the balance owed."
        ),
        H2("11. No guarantee of outcome"),
        P(
            "Nothing in this Agreement is a guarantee or prediction of any result. "
            "Legal matters are decided by courts, agencies, and opposing parties, "
            "whose decisions the Firm does not control. Any opinion the Firm gives "
            "about the matter is offered to help the Client evaluate it."
        ),
        H2("12. The file and its retention"),
        ROW(
            Field(
                "file_retention_period",
                "The Firm retains the closed file for",
                "",
                1.6,
            ),
            Field("file_delivery_format", "File delivered on request as", "", 1.4),
        ),
        P(
            "At the end of the representation the Client may request the file. After "
            "the retention period above the Firm may destroy it without further "
            "notice."
        ),
        H2("13. Disputes about this Agreement"),
        CHECKS(
            "A dispute about fees under this Agreement will first be submitted to:",
            (
                Field("fee_dispute_bar_arbitration", "Bar fee-dispute arbitration"),
                Field("fee_dispute_mediation", "Mediation"),
                Field("fee_dispute_court", "A court of competent jurisdiction"),
            ),
            3,
        ),
        ROW(
            Field(
                "venue", "Venue for an action under this Agreement", "matter.venue", 1.6
            ),
            Field("governing_law", "Governing law", "", 1.2),
        ),
        BLOCK(
            Field(
                "dispute_resolution_terms",
                "Dispute-resolution terms, including any notice or arbitration "
                "requirement",
                lines=2,
            )
        ),
        H2("14. Terms required in this jurisdiction"),
        BLOCK(
            Field(
                "jurisdiction_required_terms",
                "Statutory or ethical language the jurisdiction requires in a fee "
                "agreement",
                lines=3,
            )
        ),
        H2("15. Entire agreement"),
        P(
            "This document is the entire agreement between the Client and the Firm "
            "about this matter. It replaces any earlier discussion or understanding "
            "and may be changed only by a writing signed by both. If any provision is "
            "held unenforceable, the rest remains in effect."
        ),
        KEEP(300),
        RULE_(),
        P(
            "**By signing, the Client confirms having read this Agreement, having had "
            "the opportunity to ask questions about it and to consult another attorney "
            "about it, and agreeing to its terms. The Client is entitled to a signed "
            "copy.**"
        ),
        SIGN("Client signature"),
        ROW(
            Field("client_name", "Client printed name", "client.name", 2.0),
        ),
        SIGN("Additional client signature, if any"),
        ROW(
            Field("co_client_name", "Additional client printed name", "", 2.0),
        ),
        SIGN("Attorney signature, for the Firm"),
        ROW(
            Field("attorney_name", "Attorney printed name", "attorney.name", 1.6),
            Field("firm_name", "Firm", "firm.name", 1.6),
        ),
    ),
)


PROSPECTIVE_INTAKE = LibraryForm(
    slug="prospective-client-intake-form",
    title="Prospective Client Intake Form",
    category="intake",
    description=(
        "First-contact intake for a prospective client: identity, contact and "
        "safe-contact preferences, the kind of help sought, other parties for a "
        "conflict check, any existing case, deadlines, prior counsel, and "
        "referral source. States that completing it creates no attorney-client "
        "relationship. Fields carry the client and matter bindings, so a "
        "returned form opens the matter without retyping."
    ),
    blocks=(
        H1("Prospective Client Intake Form"),
        P(
            "Thank you for contacting our office. Please complete this form as "
            "accurately as possible. **Providing this information does not create an "
            "attorney-client relationship.** An attorney-client relationship is "
            "established only after the firm agrees to represent you and any required "
            "engagement agreement is completed."
        ),
        NOTE(REVIEW_NOTE),
        H2("Your information"),
        ROW(
            Field("client_name", "Full legal name", "client.name", 2.2),
            Field("client_other_names", "Previous or other names used", "", 2.0),
            Field("client_date_of_birth", "Date of birth", "", 1.0),
        ),
        ROW(
            Field("client_street", "Address", "client.address.street", 2.4),
            Field("client_city", "City", "client.address.city", 1.2),
            Field("client_state", "State", "client.address.state", 0.5),
            Field("client_zip", "ZIP", "client.address.zip", 0.6),
        ),
        ROW(
            Field("client_phone", "Phone", "client.phone", 1.2),
            Field("client_email", "Email", "client.email", 1.8),
        ),
        CHECKS(
            "**Preferred method of contact:**",
            (
                Field("contact_preference_phone", "Phone"),
                Field("contact_preference_email", "Email"),
                Field("contact_preference_text", "Text message"),
            ),
            3,
        ),
        RADIO(
            "Is it safe and confidential for us to contact you using the "
            "information above?",
            "safe_contact",
            (
                Choice("yes", "Yes"),
                Choice("no", "No"),
            ),
        ),
        ROW(
            Field(
                "safe_contact_explanation",
                "If no, please explain how we should reach you",
                "",
                3.0,
            ),
        ),
        H2("Matter information"),
        CHECKS(
            "**What type of legal assistance are you seeking?**",
            (
                Field("matter_type_divorce", "Divorce / separation"),
                Field("matter_type_custody", "Child custody / parenting time"),
                Field("matter_type_child_support", "Child support"),
                Field("matter_type_criminal", "Criminal matter"),
                Field("matter_type_estate", "Estate planning / probate"),
                Field("matter_type_business", "Business matter"),
                Field("matter_type_real_estate", "Real estate"),
                Field("matter_type_immigration", "Immigration"),
                Field("matter_type_litigation", "Civil litigation"),
                Field("matter_type_employment", "Employment"),
                Field("matter_type_bankruptcy", "Bankruptcy / debt"),
                Field("matter_type_other", "Other (described below)"),
            ),
            3,
        ),
        ROW(
            Field(
                "matter_type", "Type of matter, in your own words", "matter.type", 3.0
            ),
        ),
        BLOCK(
            Field(
                "matter_description",
                "Briefly describe what you need assistance with",
                "matter.description",
                lines=4,
            )
        ),
        H2("Other parties"),
        P(
            "Please identify every person or organization involved in this matter. "
            "This information may be used to perform a conflict-of-interest check."
        ),
        ROW(
            Field(
                "counterparty",
                "Other party / opposing party",
                "matter.counterparty",
                2.2,
            ),
            Field("counterparty_relationship", "Relationship to you", "", 1.6),
        ),
        ROW(
            Field(
                "counterparty_other_names", "Other names used by this person", "", 2.0
            ),
            Field("opposing_counsel", "Their attorney, if known", "", 2.0),
        ),
        BLOCK(
            Field(
                "other_parties",
                "Other involved persons or organizations, including businesses, "
                "agencies, insurers, and witnesses",
                lines=3,
            )
        ),
        H2("Existing court case"),
        RADIO(
            "Has a court case already been filed?",
            "existing_case",
            (
                Choice("yes", "Yes"),
                Choice("no", "No"),
                Choice("unsure", "Unsure"),
            ),
        ),
        ROW(
            Field("court", "Court / county", "matter.court", 1.8),
            Field("case_state", "State", "", 0.8),
            Field("case_number", "Case number", "matter.case_number", 1.4),
            Field("next_hearing_date", "Next hearing or court date", "", 1.4),
        ),
        H2("Deadlines and urgent issues"),
        RADIO(
            "Are you aware of any hearing, filing deadline, statute of limitations, "
            "response deadline, or other date requiring immediate attention?",
            "urgent_deadline",
            (
                Choice("yes", "Yes"),
                Choice("no", "No"),
                Choice("unsure", "Unsure"),
            ),
        ),
        BLOCK(
            Field(
                "urgent_risks",
                "If yes or unsure, explain",
                lines=3,
            )
        ),
        RADIO(
            "Have you been served with court papers or other legal documents?",
            "served",
            (
                Choice("yes", "Yes"),
                Choice("no", "No"),
            ),
        ),
        ROW(
            Field("date_served", "If yes, date served", "", 1.2),
            Field("served_document_type", "What you were served with", "", 2.0),
        ),
        H2("Current or previous attorneys"),
        RADIO(
            "Are you currently represented by another attorney regarding this "
            "matter?",
            "currently_represented",
            (
                Choice("yes", "Yes"),
                Choice("no", "No"),
            ),
        ),
        ROW(
            Field("current_attorney_firm", "If yes, attorney or firm", "", 3.0),
        ),
        RADIO(
            "Have you previously consulted or retained another attorney regarding "
            "this matter?",
            "prior_counsel_status",
            (
                Choice("yes", "Yes"),
                Choice("no", "No"),
            ),
        ),
        BLOCK(
            Field(
                "prior_counsel",
                "If yes, identify the attorney or firm and say whether that "
                "representation has ended",
                lines=2,
            )
        ),
        H2("How you found us"),
        CHECKS(
            "",
            (
                Field("referral_existing_client", "Existing client"),
                Field("referral_former_client", "Former client"),
                Field("referral_friend_family", "Friend / family referral"),
                Field("referral_attorney", "Attorney referral"),
                Field("referral_search", "Google / internet search"),
                Field("referral_social_media", "Social media"),
                Field("referral_other", "Other"),
            ),
            3,
        ),
        ROW(
            Field(
                "referral_source", "Name of referring person, if applicable", "", 2.0
            ),
            Field("referral_other_description", "If other, please describe", "", 2.0),
        ),
        H2("Initial documents"),
        P(
            "If available, please provide copies of documents relevant to your matter, "
            "particularly: court pleadings or orders; documents you have been served "
            "with; upcoming hearing notices; correspondence from attorneys; contracts "
            "or agreements relevant to the dispute; and any other document containing "
            "an important deadline."
        ),
        KEEP(230),
        H2("Acknowledgment"),
        P(
            "I understand that submitting this form does not mean that the firm has "
            "agreed to represent me. I understand that I should not assume the firm "
            "will protect my interests, appear in court, or take action regarding any "
            "deadline unless the firm expressly agrees to represent me. I certify that "
            "the information I have provided is accurate to the best of my knowledge."
        ),
        SIGN("Signature"),
        ROW(
            Field("client_name", "Printed name", "client.name", 2.0),
            Field("form_date", "Date completed", "", 1.0),
        ),
        H2("Firm use only"),
        ROW(
            Field(
                "conflict_check_by",
                "Conflict check completed by",
                "current_user.prepared_by",
                1.8,
            ),
            Field("conflict_check_date", "Date of conflict check", "", 1.2),
            Field("form_received_date", "Date received", "", 1.2),
        ),
        CHECKS(
            "Disposition:",
            (
                Field("disposition_consultation", "Consultation scheduled"),
                Field("disposition_declined", "Declined"),
                Field("disposition_referred", "Referred out"),
            ),
            3,
        ),
    ),
)


CLIENT_QUESTIONNAIRE = LibraryForm(
    slug="client-questionnaire",
    title="Client Questionnaire — All Matter Types",
    category="intake",
    description=(
        "Case-development questionnaire for any practice area: the parties, the "
        "narrative, the chronology, existing proceedings and orders, "
        "communications, evidence, witnesses, finances, objectives, and a "
        "preservation notice. Answer keys match the platform's shared intake "
        "questions, and identity fields carry the client and matter bindings."
    ),
    blocks=(
        H1("Client Questionnaire"),
        P(
            "Please complete this questionnaire as fully and accurately as possible. "
            "The information you provide will assist our office in evaluating, "
            "preparing, and handling your matter. If you do not know an answer, please "
            "indicate “Unknown.” If a question does not apply, indicate “N/A.”"
        ),
        NOTE(REVIEW_NOTE),
        H2("1. Client information"),
        ROW(
            Field("client_name", "Full legal name", "client.name", 2.2),
            Field("client_other_names", "Other / former names", "", 1.8),
            Field("client_date_of_birth", "Date of birth", "", 1.0),
        ),
        ROW(
            Field("client_street", "Address", "client.address.street", 2.4),
            Field("client_city", "City", "client.address.city", 1.2),
            Field("client_state", "State", "client.address.state", 0.5),
            Field("client_zip", "ZIP", "client.address.zip", 0.6),
        ),
        ROW(
            Field("client_phone", "Phone", "client.phone", 1.2),
            Field("client_email", "Email", "client.email", 1.6),
        ),
        ROW(
            Field("client_occupation", "Occupation", "", 1.4),
            Field("client_employer", "Employer", "", 1.6),
        ),
        BLOCK(
            Field(
                "contact_preferences",
                "How should we reach you, and are there times, numbers, or addresses "
                "we should avoid for privacy or safety reasons?",
                lines=2,
            )
        ),
        H2("2. Other parties"),
        ROW(
            Field(
                "counterparty",
                "Full name of the other party",
                "matter.counterparty",
                2.2,
            ),
            Field("counterparty_other_names", "Other / former names", "", 1.8),
            Field("counterparty_date_of_birth", "Date of birth, if known", "", 1.2),
        ),
        ROW(
            Field("counterparty_address", "Address, if known", "", 2.4),
            Field("counterparty_contact", "Phone / email, if known", "", 1.6),
        ),
        ROW(
            Field("counterparty_relationship", "Relationship to you", "", 1.4),
            Field("counterparty_employer", "Employer, if known", "", 1.4),
        ),
        ROW(
            Field("opposing_counsel", "Their attorney", "", 1.6),
            Field("opposing_counsel_firm", "That attorney's firm", "", 1.6),
        ),
        BLOCK(
            Field(
                "other_parties",
                "Any other individuals, businesses, witnesses, relatives, or "
                "organizations substantially involved in the matter",
                lines=3,
            )
        ),
        H2("3. Description of the matter"),
        BLOCK(
            Field(
                "matter_summary",
                "In your own words, describe what happened and why you are seeking "
                "legal assistance",
                lines=5,
            )
        ),
        ROW(
            Field("matter_start_date", "When did the issue first begin?", "", 1.4),
            Field(
                "matter_location",
                "Where did the relevant events occur?",
                "",
                2.0,
            ),
        ),
        BLOCK(
            Field(
                "desired_outcome",
                "What outcome are you hoping to achieve?",
                lines=3,
            )
        ),
        H2("4. Important events"),
        P("Please identify significant events in chronological order."),
        ROW(
            Field("event_1_date", "Date", "", 1.0),
            Field("event_1_description", "Event", "", 3.4),
        ),
        ROW(
            Field("event_2_date", "Date", "", 1.0),
            Field("event_2_description", "Event", "", 3.4),
        ),
        ROW(
            Field("event_3_date", "Date", "", 1.0),
            Field("event_3_description", "Event", "", 3.4),
        ),
        ROW(
            Field("event_4_date", "Date", "", 1.0),
            Field("event_4_description", "Event", "", 3.4),
        ),
        BLOCK(
            Field(
                "key_dates",
                "Additional events, filings, hearings, notices, agreements, or "
                "deadlines that matter in this case",
                lines=3,
            )
        ),
        H2("5. Existing legal proceedings"),
        CHECKS(
            "**Has a lawsuit, court proceeding, administrative proceeding, or other "
            "legal action relating to this matter already been started?**",
            (
                Field("existing_case_yes", "Yes"),
                Field("existing_case_no", "No"),
                Field("existing_case_unsure", "Unsure"),
            ),
            3,
        ),
        ROW(
            Field("case_name", "Case name", "", 2.2),
            Field("case_number", "Case number", "matter.case_number", 1.4),
        ),
        ROW(
            Field("court", "Court / agency", "matter.court", 1.8),
            Field("case_county", "County", "", 1.0),
            Field("case_state", "State", "", 0.8),
            Field("judge", "Judge, if known", "matter.judge", 1.4),
        ),
        ROW(
            Field("next_hearing_date", "Next hearing or deadline", "", 1.6),
        ),
        NOTE(
            "Please provide copies of all pleadings, orders, notices, and other "
            "documents you have received."
        ),
        H2("6. Previous agreements and orders"),
        CHECKS(
            "**Are there any existing:**",
            (
                Field("existing_court_orders", "Court orders"),
                Field("existing_judgments", "Judgments"),
                Field("existing_settlements", "Settlement agreements"),
                Field("existing_contracts", "Contracts"),
                Field("existing_parenting_agreements", "Parenting agreements"),
                Field("existing_protective_orders", "Protective / restraining orders"),
                Field("existing_written_agreements", "Other written agreements"),
                Field("existing_agreements_none", "None that I know of"),
            ),
            3,
        ),
        BLOCK(
            Field(
                "existing_agreements_description",
                "Please describe each one checked above",
                lines=3,
            )
        ),
        H2("7. Communications"),
        CHECKS(
            "**Have you communicated with the other party regarding this matter?**",
            (
                Field("communications_yes", "Yes"),
                Field("communications_no", "No"),
            ),
            2,
        ),
        CHECKS(
            "If yes, communications occurred through:",
            (
                Field("communication_text", "Text messages"),
                Field("communication_email", "Email"),
                Field("communication_phone", "Phone calls"),
                Field("communication_social", "Social media"),
                Field("communication_letters", "Letters"),
                Field("communication_apps", "Messaging applications"),
                Field("communication_in_person", "In person"),
                Field("communication_other", "Other"),
            ),
            3,
        ),
        CHECKS(
            "Do you still have these communications?",
            (
                Field("communications_retained_yes", "Yes"),
                Field("communications_retained_no", "No"),
                Field("communications_retained_some", "Some"),
            ),
            3,
        ),
        NOTE(
            "Please preserve potentially relevant communications. Do not delete or "
            "alter messages, emails, photographs, recordings, documents, or other "
            "information that may relate to your matter."
        ),
        H2("8. Evidence and documents"),
        CHECKS(
            "Please indicate which potentially relevant materials exist:",
            (
                Field("evidence_text_messages", "Text messages"),
                Field("evidence_emails", "Emails"),
                Field("evidence_photographs", "Photographs"),
                Field("evidence_videos", "Videos"),
                Field("evidence_audio", "Audio recordings"),
                Field("evidence_contracts", "Contracts / agreements"),
                Field("evidence_financial", "Financial records"),
                Field("evidence_bank", "Bank records"),
                Field("evidence_medical", "Medical records"),
                Field("evidence_police", "Police reports"),
                Field("evidence_employment", "Employment records"),
                Field("evidence_tax", "Tax returns"),
                Field("evidence_social_media", "Social media content"),
                Field("evidence_court", "Court documents"),
                Field("evidence_property", "Property records"),
                Field("evidence_other", "Other"),
            ),
            3,
        ),
        BLOCK(
            Field(
                "evidence_location",
                "Where are these materials currently stored, and who has access to "
                "them?",
                lines=2,
            )
        ),
        H2("9. Witnesses"),
        P("Please identify anyone who may have information relevant to this matter."),
        H3("Witness 1"),
        ROW(
            Field("witness_1_name", "Name", "", 2.0),
            Field("witness_1_contact", "Phone / email", "", 1.8),
            Field("witness_1_relationship", "Relationship to you", "", 1.4),
        ),
        BLOCK(
            Field(
                "witness_1_knowledge",
                "What information does this person have?",
                lines=2,
            )
        ),
        H3("Witness 2"),
        ROW(
            Field("witness_2_name", "Name", "", 2.0),
            Field("witness_2_contact", "Phone / email", "", 1.8),
            Field("witness_2_relationship", "Relationship to you", "", 1.4),
        ),
        BLOCK(
            Field(
                "witness_2_knowledge",
                "What information does this person have?",
                lines=2,
            )
        ),
        H2("10. Financial information"),
        P("Complete this section if financial issues may be relevant to your matter."),
        ROW(
            Field("client_employer", "Employer", "", 1.8),
            Field("client_occupation", "Occupation", "", 1.4),
            Field("gross_monthly_income", "Approximate gross monthly income", "", 1.6),
        ),
        ROW(
            Field("other_income", "Other income, and its source", "", 3.0),
        ),
        CHECKS(
            "Please indicate potentially relevant financial interests:",
            (
                Field("asset_bank_accounts", "Checking / savings accounts"),
                Field("asset_real_estate", "Real estate"),
                Field("asset_vehicles", "Vehicles"),
                Field("asset_retirement", "Retirement accounts"),
                Field("asset_investments", "Investments"),
                Field("asset_business", "Business interests"),
                Field("debt_loans", "Loans / mortgages"),
                Field("debt_credit_cards", "Credit card debt"),
                Field("asset_other", "Other assets"),
                Field("debt_other", "Other debts"),
            ),
            3,
        ),
        BLOCK(
            Field("financial_additional", "Additional financial information", lines=2)
        ),
        H2("11. Prior legal matters"),
        CHECKS(
            "**Have you previously been involved in a legal proceeding that may be "
            "relevant to this matter?**",
            (
                Field("prior_matters_yes", "Yes"),
                Field("prior_matters_no", "No"),
            ),
            2,
        ),
        BLOCK(
            Field(
                "related_proceedings",
                "If yes, describe the proceeding, its date, location, and outcome — "
                "with any other open case, claim, investigation, or bankruptcy "
                "involving you or the other parties",
                lines=3,
            )
        ),
        H2("12. Additional information"),
        BLOCK(
            Field(
                "additional_information",
                "Is there anything else you believe the attorney should know about "
                "your matter?",
                lines=3,
            )
        ),
        H2("13. Client objectives"),
        P(
            "What are the three most important outcomes you would like your attorney "
            "to pursue?"
        ),
        ROW(Field("objective_1", "Most important outcome", "", 3.0)),
        ROW(Field("objective_2", "Second most important outcome", "", 3.0)),
        ROW(Field("objective_3", "Third most important outcome", "", 3.0)),
        BLOCK(
            Field(
                "outcomes_to_avoid",
                "Are there outcomes or approaches that you specifically want to avoid?",
                lines=2,
            )
        ),
        H2("14. Documents to provide"),
        P(
            "Please provide all documents relevant to your matter. Depending on the "
            "type of case, our office may subsequently provide you with a more "
            "specific document checklist. **Do not alter, destroy, delete, or dispose "
            "of potentially relevant documents, messages, photographs, recordings, "
            "electronically stored information, or other evidence.**"
        ),
        KEEP(190),
        H2("Certification"),
        P(
            "I certify that the information provided in this questionnaire is complete "
            "and accurate to the best of my knowledge. I understand that incomplete or "
            "inaccurate information may affect the firm's ability to properly evaluate "
            "or handle my matter."
        ),
        SIGN("Client signature"),
        ROW(
            Field("client_name", "Printed name", "client.name", 2.0),
            Field("form_date", "Date completed", "", 1.0),
        ),
    ),
)


def _probate_blocks() -> tuple:
    """Print the probate practice's questions as a form the client can mail back.

    The question keys are the field names, so a returned PDF is read straight
    into the same facts the portal questionnaire fills. Yes/no questions are
    radio groups with ``yes``/``no`` export values; typed questions get a
    single box with a hint of the format; long answers get a paragraph box.
    Written for a client who may be filling it in by hand at a kitchen table:
    plain words, one question at a time, and room to write.
    """

    from app.services.practice_resolution import PROBATE_QUESTIONS, PROBATE_UPLOADS

    blocks: list = [
        H1("Probate Intake Questionnaire — North Dakota"),
        P(
            "We are sorry for your loss. This form gathers what the court needs "
            "to open the estate. Answer what you can; write “don't know” where "
            "you are not sure and we will help. You can fill it in on a computer "
            "or by hand and mail it back, or bring it to the office."
        ),
        NOTE(REVIEW_NOTE),
        H2("Your information"),
        ROW(
            Field("client_name", "Your full legal name", "client.name", 2.2),
            Field("client_phone", "Phone", "client.phone", 1.0),
            Field("client_email", "Email", "client.email", 1.4),
        ),
        ROW(
            Field("client_street", "Address", "client.address.street", 2.4),
            Field("client_city", "City", "client.address.city", 1.2),
            Field("client_state", "State", "client.address.state", 0.5),
            Field("client_zip", "ZIP", "client.address.zip", 0.6),
        ),
    ]
    sections = {
        "decedent_name": "About the person who died",
        "will_exists": "The will",
        "real_property_in_nd": "Property and value",
        "applicant_name": "About you, the person opening the estate",
        "heirs_list": "Family and heirs",
        "prior_appointment": "Court history",
        "assets_summary": "What they owned and owed",
    }
    for question in PROBATE_QUESTIONS:
        if question.key in sections:
            blocks.append(H2(sections[question.key]))
        label = (
            question.label if question.required else f"{question.label} (if you know)"
        )
        if question.kind == "yes_no":
            blocks.append(
                RADIO(label, question.key, (Choice("yes", "Yes"), Choice("no", "No")))
            )
        elif question.kind == "date":
            blocks.append(
                ROW(Field(question.key, f"{label} (month/day/year)", "", 2.0))
            )
        elif question.kind == "money":
            blocks.append(ROW(Field(question.key, f"{label} ($)", "", 2.0)))
        elif question.kind == "select":
            blocks.append(ROW(Field(question.key, label, "", 2.0)))
        elif question.key in {"heirs_list", "assets_summary", "debts_summary"}:
            blocks.append(BLOCK(Field(question.key, label, lines=5)))
        else:
            blocks.append(ROW(Field(question.key, label, "", 3.0)))
        if question.help:
            blocks.append(NOTE(question.help))
    blocks.extend(
        (
            H2("Papers to send with this form"),
            P(
                "If you have them, send a copy or a phone photo of: "
                + "; ".join(upload.label for upload in PROBATE_UPLOADS)
                + ". Bring the original will to the office — do not mail it."
            ),
            KEEP(120),
            P(
                "**The information above is true to the best of my knowledge. I "
                "understand the office will confirm it with me before anything is "
                "filed with the court.**"
            ),
            SIGN("Signature"),
            ROW(
                Field("client_name", "Printed name", "client.name", 2.0),
                Field("form_date", "Date completed", "", 1.0),
            ),
        )
    )
    return tuple(blocks)


PROBATE_INTAKE_ND = LibraryForm(
    slug="nd-probate-intake-questionnaire",
    title="Probate Intake Questionnaire — North Dakota",
    category="intake",
    description=(
        "The probate intake for the person opening a North Dakota estate: who "
        "died and when, whether there is a will, the property and its rough "
        "value, the applicant, the heirs, and any prior court history. Its "
        "answers decide which of the four probate tracks applies and pre-fill "
        "the court's informal-probate forms. Field names match the platform's "
        "probate questions, so a mailed paper copy carries the same answers as "
        "the portal."
    ),
    blocks=_probate_blocks(),
    jurisdictions=("North Dakota",),
)


FORMS: tuple[LibraryForm, ...] = (
    FEE_AGREEMENT,
    PROSPECTIVE_INTAKE,
    CLIENT_QUESTIONNAIRE,
    PROBATE_INTAKE_ND,
)


def build_form(form: LibraryForm, out_dir: Path) -> dict:
    """Render one form, write it into the seed tree, and return its manifest entry."""

    content = render(form)
    fields = discover_pdf_fields(content)
    discovered = {field["name"] for field in fields}
    declared = form.bindings()
    missing = sorted(set(declared) - discovered)
    if missing:
        raise SystemExit(
            f"{form.slug}: bindings declared for fields that are not in the PDF: "
            f"{', '.join(missing)}"
        )
    invalid = sorted(
        path for path in set(declared.values()) if not is_valid_binding(path)
    )
    if invalid:
        raise SystemExit(f"{form.slug}: unknown binding paths: {', '.join(invalid)}")
    # A field the source PDF marks required can never be weakened afterwards —
    # the save path ORs it and the renderer re-reads it from the live PDF — and
    # a required checkbox that is false refuses to generate. An authored form
    # must therefore carry no required field at all.
    required = sorted(field["name"] for field in fields if field["required"])
    if required:
        raise SystemExit(
            f"{form.slug}: fields marked required by the source PDF, which "
            f"blocks generation: {', '.join(required)}"
        )
    destination = out_dir / form.filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return {
        "category": form.category,
        "description": form.description,
        "field_count": len(fields),
        "filename": form.filename,
        "jurisdictions": list(form.jurisdictions),
        "origin": "authored",
        "bindings": dict(sorted(declared.items())),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "slug": form.slug,
        "title": form.title,
    }


def update_manifest(entries: list[dict], out_dir: Path) -> int:
    """Merge the authored entries into the library manifest, keeping the rest."""

    path = out_dir / "manifest.json"
    manifest = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else {"forms": []}
    )
    authored = {entry["slug"] for entry in entries}
    forms = [form for form in manifest.get("forms", []) if form["slug"] not in authored]
    forms.extend(entries)
    forms.sort(key=lambda form: (form["category"], form["title"].lower()))
    path.write_text(
        json.dumps({"forms": forms}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return len(forms)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=SEED_DIR,
        help="library directory to write into (default: the committed seed tree)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="SLUG",
        help="build only these forms (default: every authored form)",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    selected = [form for form in FORMS if not args.only or form.slug in args.only]
    entries = [build_form(form, args.out) for form in selected]
    total = update_manifest(entries, args.out)
    for entry in entries:
        print(
            f"{entry['filename']}: {entry['field_count']} fields, "
            f"{len(entry['bindings'])} bound, {entry['size_bytes']} bytes"
        )
    print(f"Library manifest now lists {total} forms -> {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
