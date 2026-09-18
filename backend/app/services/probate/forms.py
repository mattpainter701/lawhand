"""The North Dakota probate form registry and the guidebook's field map.

The State Court Administrator publishes the informal-probate forms as one
fillable PDF, *Informal Administration of an Estate* (NDPC Forms 1–19). The
platform ships that PDF whole in the sample library, so this module answers
three questions about it:

* which forms each probate track needs (``forms_for``);
* which pages each form occupies, so staff print only those (``page_ranges``
  reads the headers from the PDF itself; the registry's ``pages`` is checked
  against that at build and test time rather than trusted);
* which ``estate.*`` binding each of the guidebook's 340 fields draws from
  (``GUIDEBOOK_BINDINGS``, hand-authored from the printed form text, keyed by
  the field name Template Studio discovers).

A field left out of the map is filled by hand in the studio. A field mapped
here still shows its value for review before anything is generated.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Iterable

GUIDEBOOK_SLUG = "nd-informal-probate-guidebook"
GUIDEBOOK_TITLE = "ND Informal Administration of an Estate — Probate Forms 1–19"

#: Sample slugs the installer copies into a firm, with the ``kind`` tag and
#: description each copy carries.
PACK_SAMPLES: tuple[tuple[str, str, str], ...] = (
    (
        GUIDEBOOK_SLUG,
        "probate_court_form",
        "North Dakota informal probate forms (NDPC 1–19) in one fillable packet. "
        "Generate once from the estate; print only the pages the form needs.",
    ),
    (
        "nd-probate-declaration-of-service-mail",
        "probate_court_form",
        "Declaration of service by mail for probate filings (N.D.C.C. 30.1-03).",
    ),
    (
        "nd-probate-declaration-of-service-personal",
        "probate_court_form",
        "Declaration of service by personal delivery for probate filings (N.D.C.C. 30.1-03).",
    ),
    (
        "nd-probate-claim-against-estate",
        "probate_court_form",
        "Claim against estate form and self-help guide (N.D.C.C. 30.1-19).",
    ),
    (
        "nd-document-return-request",
        "probate_court_form",
        "Clerk of court document return request (original wills and codicils).",
    ),
)


@dataclass(frozen=True)
class NdProbateForm:
    number: int
    title: str
    phase: str
    pages: tuple[int, int]
    #: Tracks that file this form as part of the required set.
    tracks: frozenset[str]
    optional: bool = False
    statute: str = ""

    @property
    def key(self) -> str:
        return f"form_{self.number:02d}"


_INFORMAL = frozenset({"informal_testate", "informal_intestate"})
_TESTATE = frozenset({"informal_testate"})
_INTESTATE = frozenset({"informal_intestate"})
_SMALL = frozenset({"small_estate_affidavit"})

ND_PROBATE_FORMS: tuple[NdProbateForm, ...] = (
    NdProbateForm(
        1,
        "Affidavit for Collection of Personal Property of the Decedent",
        "opening",
        (22, 23),
        _SMALL,
        statute="30.1-23-01",
    ),
    NdProbateForm(
        2,
        "Application for Informal Probate of Will and Appointment of a Personal Representative",
        "opening",
        (26, 28),
        _TESTATE,
        statute="30.1-14-01",
    ),
    NdProbateForm(
        3,
        "Statement of Informal Probate of Will and Appointment of a Personal Representative",
        "opening",
        (29, 30),
        _TESTATE,
        statute="30.1-14-03; 30.1-14-08",
    ),
    NdProbateForm(
        4,
        "Letters Testamentary (Informal Probate)",
        "opening",
        (31, 31),
        _TESTATE,
        statute="30.1-14-01",
    ),
    NdProbateForm(
        5,
        "Notice and Information to Heirs and Devisees",
        "after_appointment",
        (32, 33),
        _INFORMAL,
        statute="30.1-18-05",
    ),
    NdProbateForm(
        6,
        "Notice to Creditors",
        "after_appointment",
        (34, 34),
        _INFORMAL,
        optional=True,
        statute="30.1-19-01",
    ),
    NdProbateForm(
        7,
        "Affidavit Forwarding Copy of Application to Health and Human Services",
        "after_appointment",
        (35, 35),
        _INFORMAL,
        statute="50-06.3-07; 50-24.1-07",
    ),
    NdProbateForm(
        8,
        "Affidavit for Access to Safe Deposit Box",
        "opening",
        (36, 36),
        frozenset(),
        optional=True,
        statute="30.1-23-05",
    ),
    NdProbateForm(
        9,
        "Waiver of Right to Appointment",
        "opening",
        (37, 37),
        frozenset(),
        optional=True,
        statute="30.1-13-03",
    ),
    NdProbateForm(
        10,
        "Inventory and Appraisement",
        "administration",
        (38, 40),
        _INFORMAL,
        optional=True,
        statute="30.1-18-06",
    ),
    NdProbateForm(
        11,
        "Personal Representative's Deed of Distribution",
        "distribution",
        (43, 44),
        frozenset(),
        optional=True,
    ),
    NdProbateForm(
        12,
        "Personal Representative's Deed (Sale of Real Property)",
        "distribution",
        (47, 48),
        frozenset(),
        optional=True,
    ),
    NdProbateForm(
        13,
        "Personal Representative's Assignment",
        "distribution",
        (49, 50),
        frozenset(),
        optional=True,
    ),
    NdProbateForm(
        14,
        "Record of Receipts and Disbursements",
        "administration",
        (51, 51),
        frozenset(),
        optional=True,
    ),
    NdProbateForm(
        15,
        "Personal Representative's Verified Statement to Close the Estate",
        "closing",
        (52, 53),
        _INFORMAL,
        optional=True,
        statute="30.1-21-03",
    ),
    NdProbateForm(
        16,
        "Sworn Statement of Personal Representative to Close a Small Estate",
        "closing",
        (54, 55),
        frozenset(),
        optional=True,
        statute="30.1-23-03; 30.1-23-04",
    ),
    NdProbateForm(
        17,
        "Application for Informal Appointment of Personal Representative in Intestacy",
        "opening",
        (58, 60),
        _INTESTATE,
        statute="30.1-14-01",
    ),
    NdProbateForm(
        18,
        "Statement of Informal Appointment of a Personal Representative — Intestacy",
        "opening",
        (61, 62),
        _INTESTATE,
        statute="30.1-14-08",
    ),
    NdProbateForm(
        19,
        "Letters of Administration",
        "opening",
        (63, 63),
        _INTESTATE,
        statute="30.1-14-07",
    ),
)

_BY_NUMBER = {form.number: form for form in ND_PROBATE_FORMS}


def form(number: int) -> NdProbateForm | None:
    return _BY_NUMBER.get(number)


def forms_for(track: str | None) -> tuple[NdProbateForm, ...]:
    """Required forms for a track, in filing order."""

    if not track:
        return ()
    return tuple(
        item for item in ND_PROBATE_FORMS if track in item.tracks and not item.optional
    )


_HEADER = re.compile(
    r"(?:ND\s*Probate\s*Code\s*Form\s*(\d+)\b|NDPC\s*Form\s*(\d+)\s*/)", re.IGNORECASE
)
_INSTRUCTIONS = re.compile(r"Form[s]?\s*[\d, ]+\s*Instructions", re.IGNORECASE)


def page_ranges(content: bytes) -> dict[int, tuple[int, int]]:
    """Read ``{form number: (first page, last page)}`` from the PDF's headers.

    Instruction pages carry the form number too but say "Instructions"; they
    are not part of the form a clerk receives, so they are excluded.
    """

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content), strict=False)
    found: dict[int, list[int]] = {}
    for index, page in enumerate(reader.pages, start=1):
        head = (page.extract_text() or "")[:300]
        if _INSTRUCTIONS.search(head):
            continue
        match = _HEADER.search(head)
        if not match:
            continue
        number = int(match.group(1) or match.group(2))
        found.setdefault(number, []).append(index)
    return {number: (pages[0], pages[-1]) for number, pages in found.items()}


# ── Field map ─────────────────────────────────────────────────────────────────
#
# Keys are the names Template Studio discovers (``_normalize_variable`` of the
# widget's /T). Grouped by form in page order. The caption trio on every form
# is the venue county, the decedent, and the probate number.

_CAPTION = {
    2: ("court_of_f2", "estate_of_f2", "no_f2"),
    3: ("court_of_f3", "estate_of_f3", "no_f3"),
    4: ("county_name_f4", "deceased_name_f4", "case_no_f4"),
    5: ("court_of_f5", "estate_of_f5", "no_f5"),
    6: ("court_of_f6", "estate_of_f6", "no_f6"),
    7: ("court_of_f7", "estate_off7", "no_f7"),
    8: ("court_of_f8", "estate_of_f8", "no_f8"),
    9: ("court_of_f9", "estate_of_f9", "no_f9"),
    10: ("court_of_f10", "estate_of", "no_f10"),
    13: ("court_of_f13", "estate_of_f13", "no_f13"),
    15: ("court_of_f15", "estate_of_f15", "probate_no"),
    16: ("court_of_f16", "estate_of_f16", "no_f16"),
    17: ("court_of_f17", "estate_of_f17", "no_f17"),
    18: ("court_of_f18", "estate_of_f18", "no_f18"),
    19: ("name_of_county_f19", "deceased_s_name_f19", "case_number_f19"),
}

GUIDEBOOK_BINDINGS: dict[str, str] = {}
for _number, (_court, _estate, _case) in _CAPTION.items():
    GUIDEBOOK_BINDINGS[_court] = "estate.venue_county"
    GUIDEBOOK_BINDINGS[_estate] = "estate.decedent_name"
    GUIDEBOOK_BINDINGS[_case] = "estate.case_number"

GUIDEBOOK_BINDINGS.update(
    {
        # Form 1 — small estate affidavit (the successor is the applicant).
        "in_the_matter_of_the_estate_of": "estate.decedent_name",
        "being_duly_sworn_states_the_following": "estate.applicant_name",
        "1_i_am_the_successor_of_deceased_person": "estate.decedent_name",
        "who_died_on_date_of_death": "estate.date_of_death",
        "affiant_address": "estate.applicant_address",
        "city_state_zip_code": "estate.applicant_city_state_zip",
        "phone_number": "estate.applicant_phone",
        "email_address": "estate.applicant_email",
        # Form 2 — application, testate.
        "a_1_i_am_the_state_name_and_interest_of_applicant": "estate.applicant_name_and_interest",
        "dod_f2": "estate.date_of_death",
        "age_f2": "estate.age_at_death",
        "years_at_the_time_of_death_the_decedent_was_domiciled_in": "estate.domicile_county",
        "state_1": "estate.domicile_state",
        "heirs_app": "estate.heirs_table",
        "3_venue_for_this_case_is_in_this_county_because_1": "estate.venue_basis",
        "terminated_except": "estate.prior_appointment_statement",
        "5_i_have_not_received_any_demand_for_notice_and_am_unaware_of_a_demand_for_notice_of": "estate.demand_for_notice_statement",
        "will_f2": "estate.will_execution_date",
        "sought_is_as_follows_1": "estate.pr_name",
        "sought_is_as_follows_2": "estate.pr_priority_statement",
        "sta_add": "estate.applicant_full_address",
        "sta_phone": "estate.applicant_phone",
        "undefined_3": "estate.applicant_email",
        "pr_f2": "estate.applicant_name",
        # Form 3 — statement of informal probate (clerk's order; the names are ours).
        "pr_f3": "estate.applicant_name",
        "decedent_f3": "estate.decedent_name",
        "dod_f3": "estate.date_of_death",
        "decedent_f3_p2": "estate.decedent_name",
        "will": "estate.will_execution_date",
        "pr_f3_p2": "estate.applicant_name",
        "decedent_f3_p2_2": "estate.decedent_name",
        "deceased_without_bond_or_upon_giving_bond_in_the_amount_of": "estate.bond_amount",
        "pr_f3_p2_2": "estate.applicant_name",
        # Form 4 — letters testamentary.
        "personal_representative_name_f4": "estate.pr_name",
        # Form 5 — notice to heirs and devisees.
        "decedent_f5": "estate.decedent_name",
        "dod_f5": "estate.date_of_death",
        "pr_f5": "estate.pr_name",
        "address_nhd": "estate.pr_address",
        "apptd_on": "estate.appointment_date",
        "if_no": "estate.bond_amount",
        "ndcounty": "estate.venue_county",
        "prnd": "estate.pr_address",
        "pr_hone": "estate.pr_phone",
        "pr_nd_email": "estate.pr_email",
        # Form 6 — notice to creditors.
        "pr_f6": "estate.pr_name",
        "nc_mailing": "estate.pr_address",
        "pr_add_nc": "estate.pr_address",
        "prnc_phone": "estate.pr_phone",
        "prncemail": "estate.pr_email",
        # Form 7 — affidavit forwarding application to HHS.
        "aff_co": "estate.pr_name",
        "pr_f7": "estate.pr_name",
        "decedent_f7": "estate.decedent_name",
        "aff_for_dhhs": "estate.pr_address",
        "phoneddds": "estate.pr_phone",
        # Form 8 — safe deposit box.
        "1_lessees_name": "estate.decedent_name",
        "dod": "estate.date_of_death",
        # Form 9 — waiver of right to appointment (the waiving heir signs; the
        # nominee is ours).
        "pr_f9": "estate.pr_name",
        # Form 10 — inventory and appraisement.
        "pr_f10": "estate.pr_name",
        "dod_f10": "estate.date_of_death",
        "rp_solely": "estate.inventory_real_description",
        "rps": "estate.inventory_real_solely",
        "rpj": "estate.inventory_real_jointly",
        "ppsolely": "estate.inventory_personal_description",
        "pps": "estate.inventory_personal_solely",
        "ppj": "estate.inventory_personal_jointly",
        "lme_2": "estate.inventory_encumbrances",
        "totalia": "estate.inventory_total",
        "pria": "estate.pr_name",
        "priaadd": "estate.pr_address",
        "priaph": "estate.pr_phone",
        "priae": "estate.pr_email",
        "pr_f10_pg3": "estate.pr_name",
        # Forms 11–13 — deeds and assignment.
        "pr": "estate.pr_name",
        "decedent": "estate.decedent_name",
        "decedent_f11": "estate.decedent_name",
        "decedent_f11_p2": "estate.decedent_name",
        "pr_f12": "estate.pr_name",
        "decedentf12_1": "estate.decedent_name",
        "decedent_f12": "estate.decedent_name",
        "decedent_f12_p2": "estate.decedent_name",
        "prf13": "estate.pr_name",
        "decedent_f13": "estate.decedent_name",
        "decedent_f13_2": "estate.decedent_name",
        "decedent_f13_p2": "estate.decedent_name",
        # Form 15 — verified statement to close.
        "pr_f15": "estate.pr_name",
        "pr_f15_p2": "estate.pr_name",
        "prvs_address": "estate.pr_address",
        "prvsphone": "estate.pr_phone",
        # Form 16 — small estate closing statement.
        "pr_f16": "estate.pr_name",
        "pr_appt": "estate.appointment_date",
        "prssname": "estate.pr_name",
        "prssaddress": "estate.pr_address",
        "prssphone": "estate.pr_phone",
        "prssemail": "estate.pr_email",
        # Form 17 — application, intestate.
        "ainest_app": "estate.applicant_name_and_interest",
        "dod_f17": "estate.date_of_death",
        "age": "estate.age_at_death",
        "domaint": "estate.domicile_county",
        "domaint22": "estate.domicile_state",
        "appintheir": "estate.heirs_table",
        "3_venue_for_this_case_is_in_this_county_because": "estate.venue_basis",
        "ainstexcept": "estate.prior_appointment_statement",
        "appintescept": "estate.demand_for_notice_statement",
        "appintnot_being": "estate.unprobated_instrument_statement",
        "appint_prio": "estate.pr_priority_statement",
        "appintn": "estate.pr_prior_priority_persons",
        "appintrequest": "estate.pr_name",
        "appintc": "estate.applicant_name",
        "appaddressint": "estate.applicant_address",
        "appcityint": "estate.applicant_city_state_zip",
        "appintestcity": "estate.applicant_phone",
        "appintestemail": "estate.applicant_email",
        # Form 18 — statement of informal appointment.
        "appstatein": "estate.applicant_name",
        "dod_f18": "estate.date_of_death",
        "pr_f18": "estate.applicant_name",
        "decedent_f18": "estate.decedent_name",
        "appin_0": "estate.bond_amount",
        "lettersadmin": "estate.applicant_name",
        # Form 19 — letters of administration.
        "applicant_s_name_f19": "estate.pr_name",
    }
)

#: Fields that must accept several lines (the heirs table and inventory
#: descriptions) but are single-line in the court's PDF. The build script sets
#: the multiline flag on these so a filled value wraps instead of overflowing.
MULTILINE_FIELDS: tuple[str, ...] = (
    "following_persons_who_are_the_surviving_spouse_children_heirs_and_devisees_of_the",
    "heirs_app",
    "appintheir",
    "rp_solely",
    "rp_jtly",
    "ppsolely",
    "ppjt",
)


def bound_fields() -> frozenset[str]:
    return frozenset(GUIDEBOOK_BINDINGS)


def registry_json() -> list[dict[str, Any]]:
    return [
        {
            "number": item.number,
            "key": item.key,
            "title": item.title,
            "phase": item.phase,
            "pages": list(item.pages),
            "tracks": sorted(item.tracks),
            "optional": item.optional,
            "statute": item.statute,
        }
        for item in ND_PROBATE_FORMS
    ]


async def forms_state(
    db, tenant_id, *, track: str | None = None
) -> list[dict[str, Any]]:
    """The registry joined with the tenant's copies of the pack.

    Each row says whether the guidebook template is installed and published,
    which is what the Probate tab needs to enable "Generate", and which pages
    to print for the form.
    """

    from app.services import sample_import

    templates: dict[str, Any] = {}
    for slug, _kind, _description in PACK_SAMPLES:
        template = await sample_import.find_import(db, tenant_id, slug)
        if template is not None:
            templates[slug] = template
    guidebook = templates.get(GUIDEBOOK_SLUG)
    required = {item.number for item in forms_for(track)}
    rows: list[dict[str, Any]] = []
    for item in ND_PROBATE_FORMS:
        rows.append(
            {
                **registry_json()[item.number - 1],
                "required": item.number in required,
                "slug": GUIDEBOOK_SLUG,
                "template_id": str(guidebook.id) if guidebook else None,
                "template_status": guidebook.status if guidebook else None,
                "published": bool(guidebook.is_active) if guidebook else False,
            }
        )
    for slug, kind, description in PACK_SAMPLES[1:]:
        template = templates.get(slug)
        rows.append(
            {
                "number": None,
                "key": slug,
                "title": template.title if template else slug.replace("-", " ").title(),
                "phase": "service",
                "pages": None,
                "tracks": [],
                "optional": True,
                "statute": "",
                "required": False,
                "slug": slug,
                "template_id": str(template.id) if template else None,
                "template_status": template.status if template else None,
                "published": bool(template.is_active) if template else False,
                "description": description,
            }
        )
    return rows


def formal_checklist(track: str | None) -> tuple[dict[str, str], ...]:
    """Slots the firm fills with its own pleadings for a formal track."""

    if track not in {"formal_testate_late", "formal_intestate_late"}:
        return ()
    testate = track == "formal_testate_late"
    return (
        {
            "slot": "petition",
            "title": "Petition for formal probate of will and appointment"
            if testate
            else "Petition for adjudication of intestacy and determination of heirs",
            "kind": "probate_formal_petition",
            "statute": "30.1-15-02; 30.1-12-08"
            if testate
            else "30.1-15-02; 30.1-12-08",
        },
        {
            "slot": "notice_of_hearing",
            "title": "Notice of hearing on petition",
            "kind": "probate_formal_notice",
            "statute": "30.1-15-03; 30.1-03-06",
        },
        {
            "slot": "proof_of_service",
            "title": "Declaration of service (mail or personal)",
            "kind": "probate_court_form",
            "statute": "30.1-03-06",
        },
        {
            "slot": "order",
            "title": "Order admitting will and appointing personal representative"
            if testate
            else "Order determining heirs and appointing personal representative",
            "kind": "probate_formal_order",
            "statute": "30.1-15-09",
        },
        {
            "slot": "letters",
            "title": "Letters (limited to confirming title in successors after three years)",
            "kind": "probate_formal_letters",
            "statute": "30.1-12-08(4)",
        },
        {
            "slot": "closing",
            "title": "Closing statement or petition for order of complete settlement",
            "kind": "probate_formal_closing",
            "statute": "30.1-21-01; 30.1-21-03",
        },
    )


def iter_bound(fields: Iterable[dict[str, Any]]) -> list[tuple[str, str]]:
    """``(field name, binding)`` for the discovered fields that have a map entry."""

    return [
        (field["name"], GUIDEBOOK_BINDINGS[field["name"]])
        for field in fields
        if field.get("name") in GUIDEBOOK_BINDINGS
    ]
