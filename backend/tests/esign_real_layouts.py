"""Signature blocks copied from real paperwork, rebuilt with reportlab.

The starter forms the firm generates print "Client signature" under every
line, and detection was tuned on them. Documents from outside the firm do
not: a referral fee agreement captions the client's line "Client:" and the
firm's "By:", an Ohio parenting plan puts the date left of the signature and
the party's name under it, a North Dakota stipulation exports with a margin
number ahead of every line and a wrapped placeholder under each rule. Each
fixture here reproduces one of those documents' execution blocks -- and the
fill-in blanks around them that were mistaken for signature lines -- at the
coordinates the real PDF had, with no real names.
"""

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

FONT = "Helvetica"


def _document(pages, *, font_size=11):
    """``pages`` is a list of lists of ``(x, y, text)`` strings to draw."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    for page in pages:
        pdf.setFont(FONT, font_size)
        for x, y, text in page:
            pdf.drawString(x, y, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def referral_fee_agreement_pdf() -> bytes:
    """A firm's fee agreement referred through a legal plan: three pages.

    The execution block is two columns and staggered -- "Dated:" on the left,
    "Client:" on the right and a line lower -- and the firm's own block is
    split by the page break: its "Dated:" at the foot of page 2, its "By:" at
    the top of page 3. The client's line names no signature word at all.
    """
    return _document(
        [
            [
                (90, 700, "The undersigned (\"Client\") hereby retains and employs the Firm"),
                (90, 684, "for representation in a Divorce Matter (\"case\")."),
                (90, 650, "2. Retainer/Attorney Fees"),
                (90, 634, "Client agrees to pay a retainer. Client is responsible for all invoices."),
            ],
            [
                (90, 616, "Client understands and acknowledges that the Firm has not represented"),
                (90, 600, "or advised that the case will succeed."),
                (90, 262, "Client acknowledges having received a copy of this Agreement, read it"),
                (90, 246, "in full, and agrees to its terms."),
                (90, 211, "Dated: __________________________"),
                (306, 187, "Client: __________________________"),
                (90, 136, "The Firm accepts responsibility to represent Client on the terms and"),
                (90, 120, "conditions set forth above."),
                (90, 94, "Dated: __________________________"),
            ],
            [
                (306, 695, "By: __________________________"),
            ],
        ]
    )


def parenting_plan_pdf() -> bytes:
    """A shared parenting plan: fill-in blanks everywhere, then two blocks.

    Word wraps a blank to the start of a line wherever a sentence names a
    parent to be chosen later ("________ shall be designated the residential
    parent"), and prints a bare rule after "as follows:". Thirteen of those
    read as signature lines before the parties' own blocks were reached. Each
    party signs on the long blank of a "Date:" line -- the date on the left --
    with "______________, MOTHER" printed as the name line beneath, and a
    notary block under that.
    """
    fill_ins = [
        (74, 625, "between  _________ (hereinafter  \"Mother\") and  ____________ (hereinafter"),
        (74, 611, "\"Father\")."),
        (74, 500, "minor child ___________ (DOB _________), born of the relationship and for whom"),
        (110, 132, "________ shall be designated the residential parent of the minor child for school"),
        (74, 118, "enrollment purposes."),
    ]
    support = [
        (104, 710, "_______ has reasonably available through his/her employment coverage to provide"),
        (73, 669, "an effective date of _____________."),
        (110, 641, "________ will maintain health insurance for the minor child so long as it is"),
        (73, 579, "_________ shall be designated the health insurance obligor. Additionally, all medical,"),
        (73, 517, "insurance shall be paid as follows: ___% each unless otherwise agreed or until further"),
        (110, 427, "________ shall be responsible for seeing that the child receives regular check-ups,"),
        (104, 249, "_________ shall be the Obligor for Child Support for the minor child and ______ shall"),
        (104, 202, "The parties agree that effective as of the date of the final decree, _______ shall pay to"),
        (68, 181, "________ the amount of $____ per month as and for child support for the minor child, in"),
        (68, 119, "guideline calculation of child support, which is $_______ per month. The parties have agreed"),
    ]
    tax = [
        (110, 568, "Commencing with the tax year 2026, the parties shall alternate the tax dependency"),
        (73, 548, "exemption/child tax credit for the minor child as follows:"),
        (73, 527, "________________________________________"),
        (109, 500, "o. Clothing and Miscellaneous Child Expenses"),
    ]

    def block(party, top):
        return [
            (68, top, "Date: ____________________"),
            (284, top, "_________________________________"),
            (284, top - 14, f"______________, {party}"),
            (104, top - 69, "Sworn to and subscribed before me, a Notary Public in the state of Ohio, on this ______"),
            (68, top - 83, "day of ________, 2026, by __________, who provided photo identification and who"),
            (284, top - 152, "______________________________"),
            (284, top - 166, "Notary Public"),
        ]

    return _document([fill_ins, support, tax, block("MOTHER", 587), block("FATHER", 600)])


def stipulation_pdf(*, wrapped_caption: bool = True) -> bytes:
    """A divorce stipulation exported with a margin number ahead of each line.

    The number ("[96]") is its own text run at the margin, so the rule after
    it has a label that is not a label. Under the rule the party is captioned
    with a bracketed placeholder that, at this export's metrics, wraps: the
    rule, a three-underscore tail, "[PLAINTIFF'S FULL", then "NAME] ,
    Plaintiff" 41 points down. ``wrapped_caption=False`` prints the caption
    on one line as Word itself lays it out.
    """

    def block(number, placeholder, party, top):
        rows = [
            (108, top, f"[{number}]"),
            (342, top, "Agreed to and dated this _______ day of __________________, 20____."),
            (342, top - 41, f"[{number + 2}]"),
            (396, top - 41, "________________________"),
        ]
        if wrapped_caption:
            rows += [
                (360, top - 55, "___"),
                (360, top - 69, f"[{placeholder}"),
                (360, top - 83, f"NAME] , {party}"),
            ]
        else:
            rows += [(360, top - 55, f"[{placeholder} NAME], {party}")]
        rows += [
            (108, top - 110, f"[{number + 5}]"),
            (342, top - 110, "STATE OF NORTH DAKOTA )"),
            (108, top - 138, f"[{number + 7}]"),
            (342, top - 138, "COUNTY OF ________________ )"),
            (108, top - 166, f"[{number + 9}]"),
            (342, top - 166, "On this _____ day of ______________, 20____, before me personally appeared"),
            (342, top - 262, f"[{number + 11}]"),
            (396, top - 262, "________________________"),
            (360, top - 276, "______"),
            (342, top - 290, f"[{number + 12}]"),
            (396, top - 290, "Notary Public"),
        ]
        return rows

    return _document(
        [
            [(108, 700, "[1]"), (342, 700, "STIPULATION FOR DIVORCE AND MARITAL SETTLEMENT AGREEMENT")],
            block(94, "PLAINTIFF'S FULL", "Plaintiff", 688),
            block(135, "DEFENDANT'S FULL", "Defendant", 661),
        ]
    )


def cover_sheet_pdf() -> bytes:
    """A matter cover sheet: labelled values and nothing to sign."""
    return _document(
        [
            [
                (72, 720, "Matter cover sheet"),
                (72, 690, "Firm: Example Firm LLP"),
                (72, 672, "Email: office@example.test"),
                (72, 654, "Matter: Example v. Example"),
                (72, 636, "Client: Example Client"),
                (72, 618, "Practice area: Family"),
                (72, 600, "Status: Open"),
                (72, 582, "Prepared by: Example Staff"),
                (72, 564, "Review note: none"),
            ]
        ]
    )
