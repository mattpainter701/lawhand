#!/usr/bin/env python3
"""Author the W.C. Black Legal Services client questionnaire and fee agreement.

Tenant-scoped: this is one firm's own paperwork, converted from the Word
original (``WCBLS_Client_Questionnaire_8.26.26.docx``) into a fillable
AcroForm for import into that firm's LawHand tenant. It is deliberately NOT
registered in ``backend/seed/sample_templates/manifest.json`` — that manifest
seeds the global library every tenant sees, and this agreement belongs to one
firm.

The layout follows ``backend/scripts/build_library_intake_forms.py`` so an
imported field behaves the same way the authored library samples do, with
three deliberate differences:

* checkbox and radio widgets pass explicit ``fieldFlags`` so they are NOT
  marked required.  reportlab defaults ``checkbox`` to ``'required'`` and
  ``radio`` to ``'noToggleToOff required radio'``; the library builder never
  overrides that, and the renderer refuses to generate a document while a
  required checkbox is false, so a form carrying the default cannot be
  generated at all.  See ``docs/template-studio-acroform-parity.md``.
* a ``RADIO`` block, for the mutually exclusive "___ Yes ___ No" choices the
  Word original writes as blanks.  The library DSL has checkboxes only.
* the fee-agreement prose is reproduced verbatim from the firm's Word source,
  including its bold emphasis and the printed $400.00 hourly rate.  These are
  the firm's own regulated terms; nothing here rewords them.

Run:  python wcbls_form.py --out DIR
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_OUT = REPO_ROOT / "docs" / "tenant-forms" / "wcbls"

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
MARGIN = 48.0
BODY = ("Helvetica", 8.6)
BODY_BOLD = ("Helvetica-Bold", 8.6)
LEADING = 11.0
LABEL_SIZE = 6.8
BOX_HEIGHT = 13.0
BOX_LINE = 11.5
CHECK_SIZE = 9.0
FIELD_BORDER = Color(0.45, 0.50, 0.58)
FIELD_FILL = Color(0.95, 0.96, 0.98)
LABEL_INK = Color(0.36, 0.40, 0.46)
RULE = Color(0.78, 0.80, 0.84)
MAXLEN = 2000

FIRM_NAME = "W.C. Black Legal Services PLLP"
FIRM_EMAIL = "info@wcblegalservices.com"
FIRM_PHONE = "(701) 818-1099"

#: reportlab marks checkboxes and radios required by default; a required
#: checkbox that is false blocks generation outright, so both are declared
#: optional here. 'radio' is kept because it is what makes the group mutually
#: exclusive; 'noToggleToOff' is dropped so a mis-click can be cleared.
CHECKBOX_FLAGS = ""
RADIO_FLAGS = "radio"


@dataclass(frozen=True)
class Field:
    """One AcroForm field and the platform variable it carries.

    ``binding`` is a path from ``app.services.template_bindings``. It is
    ``"manual"`` for a value that must never be auto-filled — a Social
    Security number or a card number should not be resolved by a coincidental
    name match — and empty where no record holds the answer but name matching
    may still legitimately find one.
    """

    name: str
    label: str
    binding: str = ""
    weight: float = 1.0
    lines: int = 0
    default: str = ""


@dataclass(frozen=True)
class Choice:
    """One option within a radio group."""

    value: str
    label: str


def H1(text):
    return ("h1", text)


def H2(text):
    return ("h2", text)


def P(text):
    return ("p", text)


def BULLET(text):
    return ("bullet", text)


def NOTE(text):
    return ("note", text)


def CENTER(text):
    return ("center", text)


def RULE_():
    return ("rule",)


def ROW(*fields):
    return ("row", fields)


def BLOCK(field):
    return ("block", field)


def RADIO(prompt, name, choices, binding="", inline_field=None):
    return ("radio", prompt, name, choices, binding, inline_field)


def QUESTION(prompt, field):
    return ("question", prompt, field)


def SIGN(label):
    return ("sign", label)


def KEEP(height):
    return ("keep", height)


def GAP(height):
    return ("gap", height)


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
        self.canvas.setStrokeColor(RULE)
        self.canvas.setLineWidth(0.6)
        self.canvas.line(MARGIN, MARGIN - 14, PAGE_WIDTH - MARGIN, MARGIN - 14)
        self.canvas.setFont("Helvetica", 7.0)
        self.canvas.setFillColor(LABEL_INK)
        self.canvas.drawString(
            MARGIN, MARGIN - 24, f"{FIRM_NAME}  ·  {FIRM_EMAIL}  ·  {FIRM_PHONE}"
        )
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

    def masthead(self) -> None:
        """The firm mark and document title, as the Word original's header table."""

        top = self.y
        # Stacked "WCB / LS" mark. The source sets it in Georgia, which is not
        # a PDF base-14 face; Times-Bold is the nearest serif that embeds free.
        self.canvas.setFont("Times-Bold", 16.0)
        self.canvas.drawString(MARGIN, top - 13, "WCB")
        self.canvas.drawString(MARGIN, top - 28, "LS")
        self.canvas.setFont("Helvetica-Bold", 8.0)
        self.canvas.drawString(MARGIN + 34, top - 28, FIRM_NAME.upper())

        self.canvas.setFont("Helvetica-Bold", 15.0)
        right = PAGE_WIDTH - MARGIN
        self.canvas.drawRightString(right, top - 13, "Client Questionnaire")
        self.canvas.drawRightString(right, top - 30, "and Fee Agreement")

        self.y = top - 40
        self.canvas.setStrokeColor(Color(0.20, 0.24, 0.30))
        self.canvas.setLineWidth(1.1)
        self.canvas.line(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y)
        self.y -= 4

    def rule(self, gap: float = 8.0) -> None:
        self.space(gap + 6)
        self.y -= gap
        self.canvas.setStrokeColor(RULE)
        self.canvas.setLineWidth(0.6)
        self.canvas.line(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y)
        self.y -= gap

    def title_block(self, text: str) -> None:
        self.space(34)
        self.y -= 20
        self.canvas.setFont("Helvetica-Bold", 13.0)
        self.canvas.drawCentredString(PAGE_WIDTH / 2, self.y, text.upper())
        self.y -= 7

    def heading(self, text: str) -> None:
        self.space(30)
        self.y -= 17
        self.canvas.setFont("Helvetica-Bold", 9.4)
        self.canvas.setFillColor(Color(0.20, 0.24, 0.30))
        self.canvas.drawString(MARGIN, self.y, text.upper())
        width = self.canvas.stringWidth(text.upper(), "Helvetica-Bold", 9.4)
        self.canvas.setStrokeColor(Color(0.20, 0.24, 0.30))
        self.canvas.setLineWidth(0.7)
        self.canvas.line(MARGIN, self.y - 3.5, MARGIN + width, self.y - 3.5)
        self.canvas.setFillColor(black)
        self.y -= 6

    def centered(self, text: str) -> None:
        self.space(24)
        self.y -= 15
        self.canvas.setFont("Helvetica-BoldOblique", 9.0)
        self.canvas.drawCentredString(PAGE_WIDTH / 2, self.y, text)
        self.y -= 3

    def paragraph(
        self,
        text: str,
        *,
        indent: float = 0.0,
        small: bool = False,
        bold: bool = False,
        gap: float = 4.0,
        bullet: str = "",
    ) -> None:
        """Wrap one paragraph, honouring ``**bold**`` runs."""

        font = ("Helvetica", 7.6) if small else BODY
        bold_font = ("Helvetica-Bold", 7.6) if small else BODY_BOLD
        if bold:
            font, bold_font = bold_font, font
        leading = 9.8 if small else LEADING
        left = MARGIN + indent
        limit = PAGE_WIDTH - MARGIN
        self.space(leading * 2)
        self.y -= leading
        if bullet:
            self.canvas.setFont(*bold_font if bold else font)
            self.canvas.drawString(MARGIN, self.y, bullet)
        x = left
        emphasis = False
        if small:
            self.canvas.setFillColor(LABEL_INK)
        for chunk in text.split("**"):
            for word in chunk.split():
                active = bold_font if emphasis else font
                advance = self.canvas.stringWidth(word + " ", *active)
                if x + advance > limit and x > left:
                    self.y -= leading
                    self.space(leading)
                    x = left
                self.canvas.setFont(*active)
                self.canvas.drawString(x, self.y, word + " ")
                x += advance
            emphasis = not emphasis
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
            tooltip=entry.label,
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

    def radio_group(
        self,
        prompt: str,
        name: str,
        choices: tuple[Choice, ...],
        inline_field: Field | None,
    ) -> None:
        """A prompt and its mutually exclusive options, on one line if they fit.

        The Word original writes these as "___ Yes    ___ No", which is one
        answer, not two independent boxes. A radio group is the AcroForm shape
        that says so: the reader enforces the exclusivity, and the engine
        reports a single field carrying ``options``.
        """

        option_width = 14.0 + CHECK_SIZE
        options_width = sum(
            option_width + self.canvas.stringWidth(c.label, "Helvetica", 8.4)
            for c in choices
        )
        prompt_width = self.canvas.stringWidth(prompt, *BODY)
        trailing = 0.0
        if inline_field is not None:
            trailing = (
                150.0
                + 6
                + self.canvas.stringWidth(inline_field.label, "Helvetica", LABEL_SIZE)
            )
        one_line = prompt_width + 12 + options_width + trailing <= self.width

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
                tooltip=prompt,
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

        if inline_field is not None:
            x += 10
            box_width = min(180.0, PAGE_WIDTH - MARGIN - x)
            self._caption(inline_field.label, x, self.y + CHECK_SIZE + 3.5)
            self._textfield(inline_field, x, self.y - 1.5, box_width, BOX_HEIGHT)
        self.y -= 6

    def question(self, prompt: str, entry: Field) -> None:
        """A numbered question in body type with a full-width answer box.

        A ``ROW`` would set the prompt in the small grey caption face, which
        makes question 2 look subordinate to question 1 next to it.
        """

        height = max(1, entry.lines or 1) * BOX_LINE + 4
        self.space(height + 22)
        self.paragraph(prompt, gap=2.0)
        self.y -= height
        self._textfield(
            entry, MARGIN, self.y, self.width, height, multiline=entry.lines > 1
        )
        self.y -= 4

    def signature(self, label: str) -> None:
        """A ruled line to sign on.

        Printed as a rule with a "Signature"/"Date" caption rather than a
        signature widget: that is the shape the portal's signature-line
        detection looks for, so an electronically signed copy lands on the same
        line a hand-signed copy does.
        """

        self.space(58)
        self.y -= 28
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


YES_NO = (Choice("yes", "Yes"), Choice("no", "No"))

# ── The form ────────────────────────────────────────────────────────────────
# Every label and every sentence below is the firm's own wording, carried over
# from the Word source. The questionnaire's combined "City, State, Zip" cells
# are split into three fields so each one can carry its own binding and be
# filled from the client record; nothing else about the questions changed.

BLOCKS = (
    ("masthead",),
    CENTER("Please complete this form in its entirety."),
    H2("Client information"),
    ROW(
        # "M.I." not "Middle Initial": the portal's signing planner classifies
        # any text field whose name or tooltip matches /\binitials?\b/ as an
        # initials block to be signed, which would turn the client's name box
        # into a signing widget. See check_signing_classifier() below.
        Field("client_name", "Last Name, First Name, M.I.", "client.name", 2.7),
        Field("client_date_of_birth", "Date of Birth", "manual", 1.0),
        Field("client_ssn", "Social Security Number", "manual", 1.3),
    ),
    ROW(
        Field("client_street", "Street Address", "client.address.street", 2.5),
        Field("client_city", "City", "client.address.city", 1.2),
        Field("client_state", "State", "client.address.state", 0.5),
        Field("client_zip", "Zip", "client.address.zip", 0.7),
    ),
    ROW(
        Field(
            "mailing_street",
            "Mailing Address (if different from street address)",
            "",
            2.5,
        ),
        Field("mailing_city", "City", "", 1.2),
        Field("mailing_state", "State", "", 0.5),
        Field("mailing_zip", "Zip", "", 0.7),
    ),
    ROW(
        Field("client_phone", "Phone Number", "client.phone", 1.0),
        Field("client_cell_phone", "Cell Phone Number", "", 1.0),
        Field("client_fax", "Fax Number", "", 1.0),
    ),
    ROW(
        Field("client_email", "E-mail Address", "client.email", 1.7),
        Field("spouse_name", "Spouse's Full Name", "", 1.3),
    ),
    ROW(
        Field("best_contact_method", "Best method to reach you", "", 1.0),
        Field("best_contact_time", "Best time to reach you", "", 1.0),
    ),
    H2("Employment"),
    ROW(
        Field("employer_name", "Employer's Name", "", 1.5),
        Field("employer_street", "Employer's Address", "", 1.7),
        Field("employer_city", "City", "", 1.0),
        Field("employer_state", "State", "", 0.45),
        Field("employer_zip", "Zip", "", 0.6),
    ),
    ROW(
        Field("work_phone", "Work Phone Number", "", 1.0),
        Field("work_fax", "Work Fax", "", 1.0),
        Field("work_cell", "Work Cell", "", 1.0),
    ),
    H2("Emergency contact"),
    ROW(
        Field("emergency_contact_name", "Emergency Contact Name", "", 1.5),
        Field("emergency_contact_street", "Contact's Address", "", 1.7),
        Field("emergency_contact_city", "City", "", 1.0),
        Field("emergency_contact_state", "State", "", 0.45),
        Field("emergency_contact_zip", "Zip", "", 0.6),
    ),
    ROW(
        Field("emergency_contact_phone", "Contact's Phone Number", "", 1.0),
    ),
    RADIO(
        "May we leave confidential messages with your emergency contact?",
        "emergency_contact_messages",
        YES_NO,
    ),
    H2("About your inquiry"),
    RADIO(
        "1.  Has our firm assisted you before?",
        "prior_representation",
        YES_NO,
        inline_field=Field(
            "prior_attorney", "If yes, please specify attorney", "", 1.0
        ),
    ),
    QUESTION(
        "2.  How did you find out about our firm?",
        Field("referral_source", "How did you find out about our firm?", "", lines=2),
    ),
    KEEP(230.0),
    H1("Fee Agreement"),
    BULLET(
        "A refundable retainer (advance deposit) or payment of a flat fee will be "
        "required at the outset as determined by the attorney, considering such "
        "factors as the complexity of your matter, risk of non-payment, anticipated "
        "duration, and anticipated expenses. Your fees, costs, and expenses will be "
        "applied against the retainer. If your retainer does not cover your fees, "
        "costs, and expenses, you will be responsible for payment of the excess. "
        "Additional retainers may also be required during the course of your "
        "representation."
    ),
    BULLET(
        "Except when a flat fee is charged or by prior written contract (contingency "
        "fee case), you will be responsible for the payment of all fees at the "
        "applicable hourly rate for services provided on your behalf. William Black's "
        "hourly rate is $400.00. The applicable hourly rate may increase during your "
        "representation. If other attorneys, law clerks, or legal assistants provide "
        "services on your matter, you will be responsible for their applicable fees."
    ),
    BULLET(
        "Except when a flat fee is charged or by prior written contract (contingency "
        "fee case), you will be charged for all time spent on your behalf, including "
        "but not limited to office visits (including your initial visit), telephone "
        "calls, all writings (including letters and emails), legal and factual "
        "research, investigation, preparation, review of your file, court appearances, "
        "travel, etc."
    ),
    BULLET(
        "You will be responsible for all reasonable expenses, including but not "
        "limited to court filing fees, deed recording fees, consultants, appraisers, "
        "photocopying, travel, meals, accommodations, long-distance telephone calls, "
        "postage, facsimile, on-line computer legal research, acquisition of "
        "documents, expert witnesses, and depositions."
    ),
    BULLET(
        "You will be billed on a monthly basis and will be assessed a late payment "
        "charge of 1.5% per month if not paid when due."
    ),
    BULLET(
        "W.C. Black Legal Services PLLP may withdraw from representation at any time "
        "if you fail to honor this billing policy, fail to cooperate in the "
        "preparation of your case, fail to make a complete and full disclosure of the "
        "facts and circumstances relating to your case, or take any action which "
        "impedes the firm's ability to provide adequate and ethical representation."
    ),
    BULLET(
        "The outcome of your case cannot be guaranteed. An unfavorable outcome does "
        "not relieve you of your obligation to pay the fees, costs, and expenses "
        "incurred."
    ),
    BULLET(
        "If you are executing this document on behalf of another person or entity and "
        "that person or entity fails to make any payments or otherwise fails to "
        "perform hereunder, you unconditionally agree and promise to make all payments "
        "to W.C. Black Legal Services PLLP due hereunder in the same manner as if you "
        "were a principal to this agreement. You further waive notice of acceptance of "
        "this guaranty, presentment and demand for payment, protest and notice of "
        "dishonor or default to you or to any other party, and all other notices to "
        "which you might otherwise be entitled."
    ),
    BULLET(
        "A credit card convenience fee of 3% will be added to your payment when paying "
        "by credit card."
    ),
    BULLET(
        "This agreement shall be governed by the laws of the State of North Dakota and "
        "any dispute arising hereunder may only be brought before the courts of the "
        "State of North Dakota."
    ),
    KEEP(190.0),
    H2("Payment authorization"),
    RADIO(
        "May we bill all payments due to your credit card?",
        "card_on_file",
        YES_NO,
    ),
    RADIO(
        "Credit Card:",
        "card_brand",
        (
            Choice("visa", "VISA"),
            Choice("mastercard", "MasterCard"),
            Choice("discover", "Discover"),
        ),
    ),
    ROW(
        Field("credit_card_number", "Credit Card Number", "manual", 2.2),
        Field("credit_card_expiration", "Expiration Date", "manual", 1.0),
        Field("credit_card_security_code", "Three Digit Security Code", "manual", 1.0),
    ),
    GAP(6.0),
    P(
        "**I hereby acknowledge that I have read, understand, approve of, and agree to "
        "the foregoing:**"
    ),
    SIGN("Signature"),
)


SLUG = "wcbls-client-questionnaire-fee-agreement"
TITLE = "Client Questionnaire and Fee Agreement — W.C. Black Legal Services PLLP"


def form_fields() -> list[Field]:
    """Every ``Field`` the form places, in document order."""

    found: list[Field] = []
    for block in BLOCKS:
        kind = block[0]
        if kind == "row":
            found.extend(block[1])
        elif kind == "block":
            found.append(block[1])
        elif kind == "question":
            found.append(block[2])
        elif kind == "radio" and block[5] is not None:
            found.append(block[5])
    return found


def declared_bindings() -> dict[str, str]:
    """``{field name: binding path}`` for every field and radio that declares one."""

    bindings = {entry.name: entry.binding for entry in form_fields() if entry.binding}
    for block in BLOCKS:
        if block[0] == "radio" and block[4]:
            bindings[block[2]] = block[4]
    return bindings


#: The portal's signing planner (``app/services/esign/plan.py``) reads an
#: AcroForm text field's name and tooltip and promotes it to a signing widget
#: when either matches. A questionnaire label like "Middle Initial" or a
#: "Signature Date" column trips these by accident, so the form is checked
#: against the same patterns it will be read with.
_SIGNING_INITIALS = re.compile(r"(?i)\binitials?\b|_initials?(_|$)")
_SIGNING_DATE = re.compile(
    r"(?i)(date[_ -]?(of[_ -]?)?sign|sign(ature|ed)?[_ -]?date|date[_ -]?signed)"
)


def check_signing_classifier() -> list[str]:
    """Return every field the portal would mistake for a signing widget."""

    problems = []
    for entry in form_fields():
        haystack = f"{entry.name} {entry.label}"
        for kind, pattern in (("initials", _SIGNING_INITIALS), ("date", _SIGNING_DATE)):
            if pattern.search(haystack):
                problems.append(
                    f"{entry.name}: label {entry.label!r} reads as a signing "
                    f"{kind} field to app/services/esign/plan.py"
                )
    return problems


def render() -> bytes:
    sheet = Sheet(TITLE)
    for block in BLOCKS:
        kind = block[0]
        if kind == "masthead":
            sheet.masthead()
        elif kind == "h1":
            sheet.title_block(block[1])
        elif kind == "h2":
            sheet.heading(block[1])
        elif kind == "center":
            sheet.centered(block[1])
        elif kind == "p":
            sheet.paragraph(block[1])
        elif kind == "bullet":
            sheet.paragraph(block[1], indent=12.0, bold=True, gap=3.0, bullet="•")
        elif kind == "note":
            sheet.paragraph(block[1], small=True)
        elif kind == "rule":
            sheet.rule()
        elif kind == "row":
            sheet.row(block[1])
        elif kind == "block":
            sheet.block(block[1])
        elif kind == "radio":
            sheet.radio_group(block[1], block[2], block[3], block[5])
        elif kind == "question":
            sheet.question(block[1], block[2])
        elif kind == "sign":
            sheet.signature(block[1])
        elif kind == "keep":
            sheet.space(block[1])
        elif kind == "gap":
            sheet.y -= block[1]
        else:  # pragma: no cover - a typo in the form definition
            raise ValueError(f"Unknown block: {kind}")
    return _strip_metadata(sheet.save())


def _strip_metadata(content: bytes) -> bytes:
    """Remove the producer/creator identity reportlab writes into the file."""

    reader = PdfReader(io.BytesIO(content), strict=False)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer._info = None
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"directory to write into (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    problems = check_signing_classifier()
    if problems:
        raise SystemExit(
            "field labels that the signing planner would misread:\n  "
            + "\n  ".join(problems)
        )

    bindings = declared_bindings()
    invalid = sorted(p for p in set(bindings.values()) if not is_valid_binding(p))
    if invalid:
        raise SystemExit(f"unknown binding paths: {', '.join(invalid)}")

    content = render()
    fields = discover_pdf_fields(content)
    discovered = {field["name"] for field in fields}
    orphans = sorted(set(bindings) - discovered)
    if orphans:
        raise SystemExit(
            f"bindings declared for fields that are not in the PDF: {', '.join(orphans)}"
        )

    required = sorted(field["name"] for field in fields if field["required"])
    if required:
        # A required checkbox the renderer cannot satisfy makes the template
        # ungeneratable; see docs/template-studio-acroform-parity.md.
        raise SystemExit(
            "fields marked required by the source PDF: " + ", ".join(required)
        )

    for field in fields:
        binding = bindings.get(field["name"])
        if binding:
            field["binding"] = binding

    pdf_path = args.out / f"{SLUG}.pdf"
    pdf_path.write_bytes(content)
    schema_path = args.out / f"{SLUG}.variable_schema.json"
    schema_path.write_text(
        json.dumps(
            {"version": 1, "source": "reviewed_upload", "fields": fields},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    kinds: dict[str, int] = {}
    for field in fields:
        kinds[field["field_type"]] = kinds.get(field["field_type"], 0) + 1
    auto = sum(1 for path in bindings.values() if path != "manual")
    print(f"{pdf_path}: {len(content):,} bytes")
    print(f"  fields    {len(fields)} {kinds}")
    print(f"  bindings  {auto} auto-fill, {len(bindings) - auto} pinned manual")
    print(f"  schema    {schema_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
