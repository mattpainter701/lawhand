"""Which North Dakota probate proceeding an estate needs.

A pure function over :class:`ProbateFacts`. The output is advisory: each
conclusion carries the statute it rests on so an attorney can check it, and
the attorney changes the answer by correcting a fact, never by editing the
determination.

Rules encoded (N.D.C.C. Title 30.1 and the State Court Administrator's
*Informal Administration of an Estate* guidebook, Rev. Aug 2025):

* informal proceedings may begin five days after death (30.1-14-01);
* no informal proceeding, and no formal testacy or appointment proceeding
  other than the exceptions in 30.1-12-08, may be commenced more than three
  years after death; a proceeding to determine heirs is never time-barred;
* an estate of $100,000 or less with no real property may be collected by
  affidavit thirty days after death without opening a case (30.1-23-01);
* venue is the county of domicile, or any county holding the decedent's
  property when the decedent was not domiciled here (30.1-13-01);
* anyone with equal or higher priority for appointment must waive
  (30.1-13-03; guidebook Form 9).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.services.probate.facts import ProbateFacts

# Tracks
INFORMAL_TESTATE = "informal_testate"
INFORMAL_INTESTATE = "informal_intestate"
FORMAL_TESTATE_LATE = "formal_testate_late"
FORMAL_INTESTATE_LATE = "formal_intestate_late"
SMALL_ESTATE_AFFIDAVIT = "small_estate_affidavit"
NOT_ND_DOMICILE = "not_nd_domicile"
UNDETERMINED = "undetermined"

TRACKS: tuple[str, ...] = (
    INFORMAL_TESTATE,
    INFORMAL_INTESTATE,
    FORMAL_TESTATE_LATE,
    FORMAL_INTESTATE_LATE,
    SMALL_ESTATE_AFFIDAVIT,
    NOT_ND_DOMICILE,
    UNDETERMINED,
)

TRACK_LABELS: dict[str, str] = {
    INFORMAL_TESTATE: "Informal probate of will and appointment of personal representative",
    INFORMAL_INTESTATE: "Informal appointment of personal representative (no will)",
    FORMAL_TESTATE_LATE: "Formal testacy proceeding (more than three years after death)",
    FORMAL_INTESTATE_LATE: "Formal adjudication of intestacy / determination of heirs (more than three years after death)",
    SMALL_ESTATE_AFFIDAVIT: "Small estate — collection by affidavit, no court case",
    NOT_ND_DOMICILE: "Not a North Dakota estate — domiciled elsewhere, no North Dakota property",
    UNDETERMINED: "Not enough facts to determine the track yet",
}

SMALL_ESTATE_CEILING = Decimal("100000")
SMALL_ESTATE_WAIT_DAYS = 30
INFORMAL_WAIT_DAYS = 5
LIMITATION_YEARS = 3

# NDPC form numbers by role. Optional forms are listed separately so the
# workbench can show them as "when needed" rather than as filing requirements.
_TESTATE_OPENING = (2, 3, 4)
_INTESTATE_OPENING = (17, 18, 19)
_AFTER_APPOINTMENT = (5, 7)
_OPTIONAL = (6, 8, 10, 11, 12, 13, 14, 15, 16)
_WAIVER = 9

FORMAL_CHECKLIST: tuple[str, ...] = (
    "Petition (formal testacy or adjudication of intestacy and determination of heirs)",
    "Notice of hearing to interested persons (30.1-15-03)",
    "Proof of service / declaration of mailing",
    "Proposed order (probating the will / determining heirs; limited letters if title must be confirmed)",
    "Letters, if a personal representative is appointed to confirm title (30.1-12-08)",
    "Closing statement or order of complete settlement",
)


@dataclass(frozen=True)
class ProbateDetermination:
    track: str
    label: str
    informal_eligible: bool
    forms: tuple[int, ...]
    optional_forms: tuple[int, ...]
    checklist: tuple[str, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_facts: tuple[str, ...]
    alternatives: tuple[str, ...]
    days_since_death: int | None
    venue_county: str | None
    venue_basis: str | None
    waiver_required: bool
    as_of: date

    def to_json(self) -> dict:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        for key in (
            "forms",
            "optional_forms",
            "checklist",
            "reasons",
            "warnings",
            "missing_facts",
            "alternatives",
        ):
            data[key] = list(data[key])
        return data


def _venue(facts: ProbateFacts) -> tuple[str | None, str | None, list[str]]:
    """County and the reason venue lies there, with any warnings."""

    warnings: list[str] = []
    if facts.is_nd_domicile():
        county = facts.domicile_county
        return (
            county,
            (
                f"the decedent was domiciled in {county} County, North Dakota at death"
                if county
                else "the decedent was domiciled in North Dakota at death"
            ),
            warnings,
        )
    if facts.real_property_in_nd and facts.nd_property_counties:
        county = facts.nd_property_counties[0]
        warnings.append(
            "The decedent was not domiciled in North Dakota. Venue rests on property "
            "located here (30.1-13-01); confirm whether a domiciliary proceeding "
            "exists or is needed in the home state and whether this is ancillary."
        )
        return (
            county,
            (
                f"the decedent was not domiciled in North Dakota and owned property "
                f"located in {county} County (30.1-13-01)"
            ),
            warnings,
        )
    if facts.real_property_in_nd:
        warnings.append(
            "Venue must be a county where the decedent's North Dakota property is "
            "located; the county was not given."
        )
    return None, None, warnings


def determine(
    facts: ProbateFacts, *, as_of: date | None = None
) -> ProbateDetermination:  # noqa: C901
    """Decide the track from the facts as of ``as_of`` (default: today)."""

    today = as_of or date.today()
    reasons: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    alternatives: list[str] = []

    if facts.date_of_death is None:
        missing.append("date_of_death")
    if facts.will_exists is None:
        missing.append("will_exists")
    if not facts.decedent_name:
        missing.append("decedent_name")
    if facts.is_nd_domicile() is None:
        missing.append("domicile_state")

    days = (today - facts.date_of_death).days if facts.date_of_death else None
    venue_county, venue_basis, venue_warnings = _venue(facts)
    warnings.extend(venue_warnings)

    waiver_required = bool(facts.persons_with_prior_or_equal_priority) or (
        facts.will_exists is True and facts.applicant_is_nominee is False
    )

    def _result(
        track: str, *, informal: bool, forms=(), optional=(), checklist=()
    ) -> ProbateDetermination:
        return ProbateDetermination(
            track=track,
            label=TRACK_LABELS[track],
            informal_eligible=informal,
            forms=tuple(forms),
            optional_forms=tuple(optional),
            checklist=tuple(checklist),
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            missing_facts=tuple(missing),
            alternatives=tuple(alternatives),
            days_since_death=days,
            venue_county=venue_county,
            venue_basis=venue_basis,
            waiver_required=waiver_required,
            as_of=today,
        )

    if facts.date_of_death is None or facts.will_exists is None:
        reasons.append(
            "The date of death and whether a will exists decide every track."
        )
        return _result(UNDETERMINED, informal=False)

    if days is not None and days < 0:
        warnings.append("The date of death is in the future; check the entry.")

    if facts.is_nd_domicile() is False and not facts.real_property_in_nd:
        reasons.append(
            "The decedent was not domiciled in North Dakota and owned no North "
            "Dakota property, so no North Dakota proceeding is needed (30.1-13-01)."
        )
        if facts.real_property_in_nd is None:
            missing.append("real_property_in_nd")
        return _result(NOT_ND_DOMICILE, informal=False)

    if days is not None and 0 <= days < INFORMAL_WAIT_DAYS:
        warnings.append(
            f"Informal proceedings may not start until {INFORMAL_WAIT_DAYS} days after "
            f"death (30.1-14-01); {INFORMAL_WAIT_DAYS - days} day(s) remain."
        )

    if facts.will_exists and facts.will_original_available is False:
        warnings.append(
            "The original will is not in hand. Informal probate requires the "
            "original or an authenticated copy (30.1-14-01); a lost or destroyed "
            "will needs a formal testacy proceeding (30.1-15-02)."
        )
    if facts.prior_appointment:
        warnings.append(
            "A personal representative was already appointed somewhere. The "
            "application must disclose it (30.1-14-01) and the appointment may bar a "
            "new informal one."
        )
    if facts.probate_opened_elsewhere:
        warnings.append(
            "A probate case was opened in another court. Confirm whether this is an "
            "ancillary proceeding before filing."
        )
    if facts.demand_for_notice:
        warnings.append(
            "A demand for notice is on file (30.1-13-04). The demanding party must "
            "be notified before any order or filing."
        )

    # Small estate off-ramp — only when the facts affirmatively fit it.
    if (
        facts.probate_property_value is not None
        and facts.probate_property_value <= SMALL_ESTATE_CEILING
        and facts.real_property_in_nd is False
        and not facts.probate_opened_elsewhere
        and not facts.prior_appointment
    ):
        reasons.append(
            f"Probate property of ${facts.probate_property_value:,.2f} is within the "
            f"${SMALL_ESTATE_CEILING:,.0f} ceiling and there is no real property, so "
            "the successor may collect by affidavit without a court case (30.1-23-01)."
        )
        if days is not None and days < SMALL_ESTATE_WAIT_DAYS:
            warnings.append(
                f"The affidavit may be presented only {SMALL_ESTATE_WAIT_DAYS} days after "
                f"death; {SMALL_ESTATE_WAIT_DAYS - days} day(s) remain."
            )
        alternatives.append(
            INFORMAL_TESTATE if facts.will_exists else INFORMAL_INTESTATE
        )
        return _result(SMALL_ESTATE_AFFIDAVIT, informal=True, forms=(1,), optional=(8,))

    if facts.probate_property_value is None:
        missing.append("probate_property_value")
    if facts.real_property_in_nd is None:
        missing.append("real_property_in_nd")

    late = facts.date_of_death + relativedelta(years=LIMITATION_YEARS) < today
    if late:
        reasons.append(
            f"More than {LIMITATION_YEARS} years have passed since death "
            f"({facts.date_of_death.isoformat()}), so informal probate and appointment "
            "are barred (30.1-12-08; 30.1-14-01)."
        )
        if facts.will_exists:
            reasons.append(
                "A formal testacy proceeding may still be brought under the "
                "30.1-12-08 exceptions; a personal representative appointed now has "
                "no power beyond what confirming title in the successors requires."
            )
            track = FORMAL_TESTATE_LATE
        else:
            reasons.append(
                "A proceeding to determine heirs is not subject to the three-year "
                "limit (30.1-12-08); a formal adjudication of intestacy is the route."
            )
            track = FORMAL_INTESTATE_LATE
        reasons.append(
            "The court publishes no forms for formal proceedings; the firm's own "
            "petition, notice, and order templates are used."
        )
        return _result(track, informal=False, checklist=FORMAL_CHECKLIST)

    if facts.will_exists:
        reasons.append(
            "A will exists and less than three years have passed, so the will may be "
            "informally probated and a personal representative appointed by "
            "application to the clerk (30.1-14-01)."
        )
        opening = _TESTATE_OPENING
        track = INFORMAL_TESTATE
    else:
        reasons.append(
            "No will and less than three years since death: a personal representative "
            "may be appointed informally in intestacy (30.1-14-01)."
        )
        opening = _INTESTATE_OPENING
        track = INFORMAL_INTESTATE
    forms = list(opening) + list(_AFTER_APPOINTMENT)
    if waiver_required:
        forms.append(_WAIVER)
        reasons.append(
            "Someone with an equal or higher right to appointment must sign a waiver "
            "before the applicant can be appointed (30.1-13-03; Form 9)."
        )
    return _result(track, informal=True, forms=sorted(forms), optional=_OPTIONAL)
