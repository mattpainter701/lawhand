"""How the estate record becomes the values on a North Dakota court form."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.probate import bindings
from app.services.probate.facts import HeirRow, ProbateFacts, to_json
from app.services.template_bindings import catalogue


def _estate(**overrides):
    base = dict(
        id=uuid4(),
        estate_name="Estate of Ole Olson",
        title="Estate of Ole Olson",
        grantor=None,
        date_of_death=date(2025, 1, 15),
        domicile_state="North Dakota",
        domicile_county="Cass",
        will_execution_date=None,
        court_name=None,
        case_number="09-2025-PR-00042",
        gross_estate_value=None,
        net_estate_value=None,
        probate_track="informal_testate",
        probate_facts={},
        probate_determination={},
        appointment_date=None,
        first_publication_date=None,
        letters_issued_date=None,
        closing_statement_filed_date=None,
        fiduciaries=[],
        beneficiaries=[],
        assets=[],
        liabilities=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_every_estate_alias_has_a_value_on_the_probe():
    values = bindings.estate_values(bindings.probe_estate())
    for entry in catalogue():
        if entry.path.startswith("estate."):
            assert values.get(entry.alias), entry.path
    rows = bindings.estate_candidates(bindings.probe_estate())
    assert {alias for alias, *_ in rows} == {
        entry.alias for entry in catalogue() if entry.path.startswith("estate.")
    }
    assert bindings.estate_candidates(None) == []


def test_decedent_name_falls_back_from_facts_to_grantor_to_the_estate_title():
    assert bindings.estate_values(_estate())["estate_decedent_name"] == "Ole Olson"
    assert (
        bindings.estate_values(_estate(grantor="O. Olson"))["estate_decedent_name"]
        == "O. Olson"
    )
    facts = to_json(ProbateFacts(decedent_name="Ole B. Olson"))
    assert (
        bindings.estate_values(_estate(grantor="O. Olson", probate_facts=facts))[
            "estate_decedent_name"
        ]
        == "Ole B. Olson"
    )


def test_heirs_table_prefers_beneficiary_rows_and_borrows_ages_from_facts():
    facts = to_json(
        ProbateFacts(heirs=(HeirRow("Ann Olson", "70", "spouse", "Fargo"),))
    )
    estate = _estate(
        probate_facts=facts,
        beneficiaries=[
            SimpleNamespace(
                name="Ann Olson", relationship_to_estate="spouse", address="1 Main St"
            ),
            SimpleNamespace(
                name="Bob Olson", relationship_to_estate="son", address=None
            ),
        ],
    )
    values = bindings.estate_values(estate)
    assert (
        values["estate_heirs_table"]
        == "Ann Olson — 70 — spouse — 1 Main St\nBob Olson — son"
    )
    assert values["estate_heir_names"] == "Ann Olson, Bob Olson"

    only_facts = bindings.estate_values(_estate(probate_facts=facts))
    assert only_facts["estate_heirs_table"] == "Ann Olson — 70 — spouse — Fargo"


def test_applicant_block_comes_from_facts_or_the_applicant_fiduciary():
    facts = to_json(
        ProbateFacts(
            applicant_name="Ann Olson",
            applicant_relationship="spouse",
            applicant_address="1 Main St, Fargo, ND 58102",
            applicant_phone="701-555-0100",
            will_exists=True,
            applicant_is_nominee=True,
        )
    )
    values = bindings.estate_values(_estate(probate_facts=facts))
    assert values["estate_applicant_interest"] == "Ann Olson, spouse of the decedent"
    assert values["estate_applicant_address"] == "1 Main St"
    assert values["estate_applicant_city_state_zip"] == "Fargo, ND 58102"
    assert values["estate_applicant_full_address"] == "1 Main St, Fargo, ND 58102"
    assert values["estate_pr_name"] == "Ann Olson"
    assert "Nominated" in values["estate_pr_priority"]

    fiduciary = SimpleNamespace(
        name="Carl Olson",
        role="applicant",
        is_primary=False,
        email="carl@example.com",
        phone="701-555-0199",
        notes="9 Oak St, Fargo, ND",
    )
    pr = SimpleNamespace(
        name="Dana Olson",
        role="personal_representative",
        is_primary=True,
        email=None,
        phone=None,
        notes=None,
    )
    values = bindings.estate_values(_estate(fiduciaries=[fiduciary, pr]))
    assert values["estate_applicant_name"] == "Carl Olson"
    assert values["estate_applicant_email"] == "carl@example.com"
    assert values["estate_pr_name"] == "Dana Olson"
    assert values["estate_pr_address"] == "9 Oak St, Fargo, ND"


def test_statements_read_none_when_the_answer_was_no_and_stay_blank_when_unknown():
    facts = to_json(
        ProbateFacts(
            prior_appointment=False,
            demand_for_notice=True,
            demand_for_notice_details="Filed by a creditor in Cass County",
        )
    )
    values = bindings.estate_values(_estate(probate_facts=facts))
    assert values["estate_prior_appointment"] == "None."
    assert values["estate_demand_for_notice"] == "Filed by a creditor in Cass County"
    assert bindings.estate_values(_estate())["estate_prior_appointment"] is None


def test_inventory_totals_count_only_verified_assets_and_split_by_ownership():
    estate = _estate(
        assets=[
            SimpleNamespace(
                name="Checking",
                category="bank_account",
                ownership_type="sole",
                date_of_death_value=Decimal("1000"),
                current_value=None,
                verification_status="verified",
            ),
            SimpleNamespace(
                name="Farmland",
                category="real_estate",
                ownership_type="joint tenancy",
                date_of_death_value=None,
                current_value=Decimal("200000"),
                verification_status="verified",
            ),
            SimpleNamespace(
                name="Boat",
                category="vehicle",
                ownership_type="sole",
                date_of_death_value=Decimal("5000"),
                current_value=None,
                verification_status="unverified",
            ),
        ],
        liabilities=[
            SimpleNamespace(claim_type="mortgage", amount=Decimal("50000")),
            SimpleNamespace(claim_type="debt", amount=Decimal("700")),
        ],
    )
    values = bindings.estate_values(estate)
    assert values["estate_inventory_personal_solely"] == "$1,000.00"
    assert values["estate_inventory_real_jointly"] == "$200,000.00"
    assert values["estate_inventory_real_solely"] == "$0.00"
    assert values["estate_inventory_total"] == "$201,000.00"
    assert values["estate_inventory_encumbrances"] == "$50,000.00"
    assert "Boat" not in (values["estate_inventory_personal_description"] or "")


def test_dates_print_the_way_a_clerk_expects_and_the_bar_date_follows_publication():
    estate = _estate(
        appointment_date=date(2025, 3, 31), first_publication_date=date(2025, 4, 7)
    )
    values = bindings.estate_values(estate)
    assert values["estate_date_of_death"] == "01/15/2025"
    assert values["estate_appointment_date"] == "03/31/2025"
    assert values["estate_claims_bar_date"] == "07/07/2025"
    assert values["estate_probate_track"].startswith("Informal probate")
