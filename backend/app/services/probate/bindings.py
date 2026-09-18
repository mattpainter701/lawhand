"""Smart Fill candidates for the ``estate.*`` bindings.

Every value a probate court form can draw from the estate record, keyed by
the catalogue alias in ``template_bindings``. Pure over the loaded ORM rows
(or any object with the same attributes), so the composition rules — how the
heirs table is laid out, what "None." means, which assets count toward an
inventory total — are unit-tested without a database.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from app.services.probate import deadlines, determination
from app.services.probate.facts import ProbateFacts, from_json


def _date(value: date | None) -> str | None:
    return value.strftime("%m/%d/%Y") if value else None


def _money(value: Decimal | int | float | None) -> str | None:
    if value is None:
        return None
    return f"${Decimal(value):,.2f}"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", (), []):
            return value
    return None


def _decedent_name(estate, facts: ProbateFacts) -> str | None:
    name = _first(facts.decedent_name, getattr(estate, "grantor", None))
    if name:
        return _clean(name)
    label = _clean(
        getattr(estate, "estate_name", None) or getattr(estate, "title", None)
    )
    if label and label.lower().startswith("estate of "):
        return label[len("estate of ") :].strip() or None
    return label


def _fiduciary(estate, roles: Iterable[str]):
    rows = list(getattr(estate, "fiduciaries", None) or [])
    for role in roles:
        for row in rows:
            if (getattr(row, "role", "") or "").lower() == role:
                return row
    primary = next((row for row in rows if getattr(row, "is_primary", False)), None)
    return primary


def _split_address(address: str | None) -> tuple[str | None, str | None]:
    """Street on one line, city/state/ZIP on the next, when both are present."""

    if not address:
        return None, None
    parts = [
        part.strip() for part in address.replace("\n", ",").split(",") if part.strip()
    ]
    if len(parts) >= 3:
        return parts[0], ", ".join(parts[1:])
    if len(parts) == 2:
        return parts[0], parts[1]
    return address.strip(), None


def _heir_rows(estate, facts: ProbateFacts) -> list[str]:
    """One line per heir/devisee: name — age — relationship — address."""

    lines: list[str] = []
    ages = {row.name.casefold(): row.age for row in facts.heirs if row.age}
    beneficiaries = list(getattr(estate, "beneficiaries", None) or [])
    if beneficiaries:
        for row in beneficiaries:
            name = _clean(getattr(row, "name", None))
            if not name:
                continue
            parts = [
                name,
                ages.get(name.casefold(), ""),
                _clean(getattr(row, "relationship_to_estate", None)) or "",
                _clean(getattr(row, "address", None)) or "",
            ]
            lines.append(" — ".join(part for part in parts if part))
        return lines
    return [row.as_line() for row in facts.heirs if row.name]


def _statement(
    flag: bool | None, details: str | None, *, none_text: str = "None."
) -> str | None:
    if flag is None and not details:
        return None
    if not flag:
        return none_text
    return _clean(details) or "Yes — see attached statement."


def _priority_statement(
    facts: ProbateFacts, determination_json: dict | None
) -> str | None:
    if facts.will_exists and facts.applicant_is_nominee:
        return "Nominated as personal representative in the decedent's will (N.D.C.C. 30.1-13-03(1))."
    if facts.applicant_relationship:
        rel = facts.applicant_relationship.strip().lower()
        if "spouse" in rel or "husband" in rel or "wife" in rel:
            return (
                "Surviving spouse of the decedent (N.D.C.C. 30.1-13-03)."
                if not facts.will_exists
                else "Surviving spouse of the decedent and devisee under the will (N.D.C.C. 30.1-13-03)."
            )
        return f"{facts.applicant_relationship.strip().capitalize()} of the decedent and an heir (N.D.C.C. 30.1-13-03)."
    return None


def _inventory(estate) -> dict[str, Any]:
    real_solely = Decimal(0)
    real_jointly = Decimal(0)
    personal_solely = Decimal(0)
    personal_jointly = Decimal(0)
    real_lines: list[str] = []
    personal_lines: list[str] = []
    for asset in getattr(estate, "assets", None) or []:
        if (
            getattr(asset, "verification_status", "verified") or "verified"
        ) != "verified":
            continue
        value = _first(
            getattr(asset, "date_of_death_value", None),
            getattr(asset, "current_value", None),
        )
        amount = Decimal(value) if value is not None else Decimal(0)
        ownership = (getattr(asset, "ownership_type", None) or "").lower()
        joint = any(
            word in ownership for word in ("joint", "tenants in common", "tic", "co-")
        )
        category = (getattr(asset, "category", None) or "").lower()
        real = category in {
            "real_estate",
            "real_property",
            "land",
            "mineral_rights",
            "real estate",
        }
        line = f"{_clean(getattr(asset, 'name', None)) or 'Asset'}: {_money(amount)}"
        if real:
            real_lines.append(line)
            if joint:
                real_jointly += amount
            else:
                real_solely += amount
        else:
            personal_lines.append(line)
            if joint:
                personal_jointly += amount
            else:
                personal_solely += amount
    encumbrances = Decimal(0)
    for claim in getattr(estate, "liabilities", None) or []:
        claim_type = (getattr(claim, "claim_type", None) or "").lower()
        if claim_type in {"mortgage", "lien", "secured", "encumbrance"}:
            encumbrances += Decimal(getattr(claim, "amount", 0) or 0)
    total = real_solely + real_jointly + personal_solely + personal_jointly
    return {
        "estate_inventory_real_solely": _money(real_solely) if real_lines else None,
        "estate_inventory_real_jointly": _money(real_jointly) if real_lines else None,
        "estate_inventory_personal_solely": _money(personal_solely)
        if personal_lines
        else None,
        "estate_inventory_personal_jointly": _money(personal_jointly)
        if personal_lines
        else None,
        "estate_inventory_encumbrances": _money(encumbrances) if encumbrances else None,
        "estate_inventory_total": _money(total)
        if (real_lines or personal_lines)
        else None,
        "estate_inventory_real_description": "\n".join(real_lines) or None,
        "estate_inventory_personal_description": "\n".join(personal_lines) or None,
    }


def estate_values(estate) -> dict[str, str | None]:
    """``{alias: value}`` for every ``estate.*`` binding, from one estate."""

    facts = from_json(getattr(estate, "probate_facts", None) or {})
    det = getattr(estate, "probate_determination", None) or {}
    applicant = _fiduciary(estate, ("applicant",))
    pr = _fiduciary(estate, ("personal_representative", "executor", "administrator"))
    applicant_name = _first(
        facts.applicant_name,
        getattr(applicant, "name", None),
        getattr(pr, "name", None),
    )
    applicant_address = _first(
        facts.applicant_address, getattr(applicant, "notes", None)
    )
    street, city_line = _split_address(applicant_address)
    pr_name = _first(getattr(pr, "name", None), applicant_name)
    interest = None
    if applicant_name:
        interest = applicant_name
        if facts.applicant_relationship:
            interest = f"{applicant_name}, {facts.applicant_relationship.strip()} of the decedent"
    date_of_death = _first(facts.date_of_death, getattr(estate, "date_of_death", None))
    plan = deadlines.plan_for_estate(estate, getattr(estate, "probate_track", None))
    claims_bar = next(
        (
            item.due_date
            for item in plan.deadlines
            if item.deadline_type == "creditor_bar"
        ),
        None,
    )
    venue_county = _first(
        det.get("venue_county"),
        facts.domicile_county,
        getattr(estate, "domicile_county", None),
    )
    values: dict[str, str | None] = {
        "estate_decedent_name": _decedent_name(estate, facts),
        "estate_decedent_aka": _clean(facts.decedent_aka),
        "estate_date_of_death": _date(date_of_death),
        "estate_age_at_death": (
            str(facts.computed_age_at_death())
            if facts.computed_age_at_death() is not None
            else None
        ),
        "estate_domicile_state": _clean(
            _first(facts.domicile_state, getattr(estate, "domicile_state", None))
        ),
        "estate_domicile_county": _clean(
            _first(facts.domicile_county, getattr(estate, "domicile_county", None))
        ),
        "estate_venue_county": _clean(venue_county),
        "estate_venue_basis": _clean(det.get("venue_basis")),
        "estate_court": _clean(getattr(estate, "court_name", None)),
        "estate_case_number": _clean(getattr(estate, "case_number", None)),
        "estate_will_date": _date(
            _first(
                facts.will_execution_date, getattr(estate, "will_execution_date", None)
            )
        ),
        "estate_gross_value": _money(
            _first(
                getattr(estate, "gross_estate_value", None),
                facts.probate_property_value,
            )
        ),
        "estate_net_value": _money(getattr(estate, "net_estate_value", None)),
        "estate_probate_track": determination.TRACK_LABELS.get(
            getattr(estate, "probate_track", None) or "", None
        ),
        "estate_heirs_table": "\n".join(_heir_rows(estate, facts)) or None,
        "estate_heir_names": ", ".join(
            line.split(" — ")[0] for line in _heir_rows(estate, facts)
        )
        or None,
        "estate_applicant_name": _clean(applicant_name),
        "estate_applicant_interest": _clean(interest),
        "estate_applicant_address": _clean(street),
        "estate_applicant_city_state_zip": _clean(city_line),
        "estate_applicant_full_address": _clean(applicant_address),
        "estate_applicant_phone": _clean(
            _first(facts.applicant_phone, getattr(applicant, "phone", None))
        ),
        "estate_applicant_email": _clean(
            _first(facts.applicant_email, getattr(applicant, "email", None))
        ),
        "estate_pr_name": _clean(pr_name),
        "estate_pr_address": _clean(
            _first(getattr(pr, "notes", None), applicant_address)
        ),
        "estate_pr_phone": _clean(
            _first(getattr(pr, "phone", None), facts.applicant_phone)
        ),
        "estate_pr_email": _clean(
            _first(getattr(pr, "email", None), facts.applicant_email)
        ),
        "estate_pr_priority": _priority_statement(facts, det),
        "estate_pr_prior_persons": ", ".join(facts.persons_with_prior_or_equal_priority)
        or (
            "None."
            if facts.persons_with_prior_or_equal_priority == () and facts.applicant_name
            else None
        ),
        "estate_prior_appointment": _statement(
            facts.prior_appointment, facts.prior_appointment_details
        ),
        "estate_demand_for_notice": _statement(
            facts.demand_for_notice, facts.demand_for_notice_details
        ),
        "estate_unprobated_instrument": (
            "No unrevoked testamentary instrument is known to exist."
            if facts.will_exists is False
            else None
        ),
        "estate_bond_amount": _money(facts.bond_amount)
        if facts.bond_amount is not None
        else None,
        "estate_appointment_date": _date(getattr(estate, "appointment_date", None)),
        "estate_letters_date": _date(getattr(estate, "letters_issued_date", None)),
        "estate_first_publication": _date(
            getattr(estate, "first_publication_date", None)
        ),
        "estate_claims_bar_date": _date(claims_bar),
        "estate_closing_date": _date(
            getattr(estate, "closing_statement_filed_date", None)
        ),
    }
    values.update(_inventory(estate))
    return values


def estate_candidates(estate) -> list[tuple[str, str, str, Any]]:
    """``(alias, value, source_field, record_id)`` rows for Smart Fill."""

    if estate is None:
        return []
    record_id = getattr(estate, "id", None)
    rows: list[tuple[str, str, str, Any]] = []
    for alias, value in estate_values(estate).items():
        if value in (None, ""):
            continue
        rows.append((alias, str(value), alias.removeprefix("estate_"), record_id))
    return rows


def probe_estate():
    """A fully populated stand-in estate, for the approval-time alias probe.

    Every ``estate.*`` alias must appear in the Smart Fill vocabulary or a
    template bound to it could never be approved, so the probe carries a value
    for each field the resolver reads.
    """

    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.probate.facts import HeirRow, ProbateFacts, to_json

    facts = ProbateFacts(
        decedent_name="Probe Decedent",
        decedent_aka="P. Decedent",
        date_of_death=date(2025, 1, 2),
        date_of_birth=date(1940, 1, 2),
        domicile_state="North Dakota",
        domicile_county="Cass",
        real_property_in_nd=True,
        nd_property_counties=("Cass",),
        probate_property_value=Decimal("250000"),
        will_exists=False,
        will_original_available=True,
        will_execution_date=date(2010, 5, 6),
        applicant_name="Probe Applicant",
        applicant_relationship="daughter",
        applicant_is_nominee=False,
        applicant_address="1 Probe St, Fargo, ND 58102",
        applicant_phone="701-555-0100",
        applicant_email="probe@example.com",
        persons_with_prior_or_equal_priority=("Probe Spouse",),
        heirs=(HeirRow("Probe Spouse", "80", "spouse", "1 Probe St, Fargo, ND"),),
        probate_opened_elsewhere=False,
        prior_appointment=True,
        prior_appointment_details="Probe County, MN, 01/01/2024",
        demand_for_notice=True,
        demand_for_notice_details="Probe Creditor, Cass County",
        bond_amount=Decimal("0"),
    )
    asset = SimpleNamespace(
        name="Probe account",
        category="bank_account",
        ownership_type="sole",
        date_of_death_value=Decimal("1000"),
        current_value=None,
        verification_status="verified",
    )
    land = SimpleNamespace(
        name="Probe farmland",
        category="real_estate",
        ownership_type="joint",
        date_of_death_value=Decimal("2000"),
        current_value=None,
        verification_status="verified",
    )
    lien = SimpleNamespace(claim_type="mortgage", amount=Decimal("500"))
    return SimpleNamespace(
        id=uuid4(),
        estate_name="Estate of Probe Decedent",
        title="Estate of Probe Decedent",
        grantor="Probe Decedent",
        date_of_death=date(2025, 1, 2),
        domicile_state="North Dakota",
        domicile_county="Cass",
        will_execution_date=date(2010, 5, 6),
        court_name="Cass County District Court",
        case_number="08-2025-PR-00001",
        gross_estate_value=Decimal("250000"),
        net_estate_value=Decimal("240000"),
        probate_track="informal_intestate",
        probate_facts=to_json(facts),
        probate_determination={
            "venue_county": "Cass",
            "venue_basis": "the decedent was domiciled in Cass County",
        },
        appointment_date=date(2025, 3, 1),
        first_publication_date=date(2025, 3, 10),
        letters_issued_date=date(2025, 3, 1),
        closing_statement_filed_date=date(2025, 9, 1),
        fiduciaries=[
            SimpleNamespace(
                name="Probe PR",
                role="personal_representative",
                is_primary=True,
                email="pr@example.com",
                phone="701-555-0101",
                notes="2 Probe Ave, Fargo, ND 58103",
            )
        ],
        beneficiaries=[
            SimpleNamespace(
                name="Probe Spouse",
                relationship_to_estate="spouse",
                address="1 Probe St, Fargo, ND",
            )
        ],
        assets=[asset, land],
        liabilities=[lien],
    )
