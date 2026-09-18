"""The North Dakota track rules, as a table.

Each case is a set of intake facts and the track the statute puts them on.
``as_of`` is pinned so the three-year and five-day clocks are exact.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.probate import determination as det
from app.services.probate.facts import HeirRow, ProbateFacts

TODAY = date(2026, 9, 18)


def _facts(**overrides) -> ProbateFacts:
    base = dict(
        decedent_name="Ole Olson",
        date_of_death=date(2025, 6, 1),
        domicile_state="North Dakota",
        domicile_county="Cass",
        will_exists=True,
        real_property_in_nd=True,
        probate_property_value=Decimal("250000"),
        applicant_name="Ann Olson",
        applicant_relationship="spouse",
        applicant_is_nominee=True,
    )
    base.update(overrides)
    return ProbateFacts(**base)


@pytest.mark.parametrize(
    "overrides,track",
    [
        ({}, det.INFORMAL_TESTATE),
        ({"will_exists": False}, det.INFORMAL_INTESTATE),
        ({"date_of_death": date(2023, 6, 1)}, det.FORMAL_TESTATE_LATE),
        (
            {"date_of_death": date(2023, 6, 1), "will_exists": False},
            det.FORMAL_INTESTATE_LATE,
        ),
        (
            {"probate_property_value": Decimal("80000"), "real_property_in_nd": False},
            det.SMALL_ESTATE_AFFIDAVIT,
        ),
        (
            {"domicile_state": "Minnesota", "real_property_in_nd": False},
            det.NOT_ND_DOMICILE,
        ),
        ({"date_of_death": None}, det.UNDETERMINED),
        ({"will_exists": None}, det.UNDETERMINED),
    ],
)
def test_the_four_tracks_and_the_off_ramps(overrides, track):
    result = det.determine(_facts(**overrides), as_of=TODAY)
    assert result.track == track
    assert result.label == det.TRACK_LABELS[track]
    assert result.reasons  # every conclusion says why


def test_informal_testate_lists_the_opening_forms_in_order():
    result = det.determine(_facts(), as_of=TODAY)
    assert result.forms == (2, 3, 4, 5, 7)
    assert 6 in result.optional_forms and 10 in result.optional_forms
    assert result.informal_eligible
    assert result.venue_county == "Cass"
    assert "domiciled in Cass County" in result.venue_basis


def test_informal_intestate_uses_the_intestacy_set():
    result = det.determine(_facts(will_exists=False), as_of=TODAY)
    assert result.forms == (5, 7, 17, 18, 19)


def test_three_years_is_an_exact_boundary():
    on_the_day = det.determine(_facts(date_of_death=date(2023, 9, 18)), as_of=TODAY)
    day_after = det.determine(_facts(date_of_death=date(2023, 9, 17)), as_of=TODAY)
    assert on_the_day.track == det.INFORMAL_TESTATE
    assert day_after.track == det.FORMAL_TESTATE_LATE
    assert day_after.forms == ()
    assert day_after.checklist == det.FORMAL_CHECKLIST
    assert any("30.1-12-08" in reason for reason in day_after.reasons)


def test_a_death_last_week_warns_about_the_five_day_wait():
    result = det.determine(_facts(date_of_death=date(2026, 9, 16)), as_of=TODAY)
    assert result.track == det.INFORMAL_TESTATE
    assert any("5 days" in warning for warning in result.warnings)


def test_small_estate_needs_thirty_days_and_no_real_property():
    early = det.determine(
        _facts(
            date_of_death=date(2026, 9, 1),
            probate_property_value=Decimal("50000"),
            real_property_in_nd=False,
        ),
        as_of=TODAY,
    )
    assert early.track == det.SMALL_ESTATE_AFFIDAVIT
    assert early.forms == (1,)
    assert any("30 days" in warning for warning in early.warnings)
    assert early.alternatives == (det.INFORMAL_TESTATE,)

    with_land = det.determine(
        _facts(probate_property_value=Decimal("50000"), real_property_in_nd=True),
        as_of=TODAY,
    )
    assert with_land.track == det.INFORMAL_TESTATE

    exactly_ceiling = det.determine(
        _facts(probate_property_value=Decimal("100000"), real_property_in_nd=False),
        as_of=TODAY,
    )
    assert exactly_ceiling.track == det.SMALL_ESTATE_AFFIDAVIT


def test_a_prior_appointment_keeps_a_small_estate_out_of_the_affidavit():
    result = det.determine(
        _facts(
            probate_property_value=Decimal("50000"),
            real_property_in_nd=False,
            prior_appointment=True,
        ),
        as_of=TODAY,
    )
    assert result.track == det.INFORMAL_TESTATE
    assert any("already appointed" in warning for warning in result.warnings)


def test_foreign_domicile_with_north_dakota_land_is_an_ancillary_case():
    result = det.determine(
        _facts(
            domicile_state="MN",
            domicile_county="Clay",
            real_property_in_nd=True,
            nd_property_counties=("Richland",),
        ),
        as_of=TODAY,
    )
    assert result.track == det.INFORMAL_TESTATE
    assert result.venue_county == "Richland"
    assert "30.1-13-01" in result.venue_basis
    assert any("ancillary" in warning for warning in result.warnings)


def test_waiver_is_required_when_someone_outranks_the_applicant():
    named = det.determine(
        _facts(persons_with_prior_or_equal_priority=("Bob Olson",)), as_of=TODAY
    )
    assert named.waiver_required
    assert 9 in named.forms

    not_nominee = det.determine(_facts(applicant_is_nominee=False), as_of=TODAY)
    assert not_nominee.waiver_required

    nominee = det.determine(_facts(), as_of=TODAY)
    assert not nominee.waiver_required
    assert 9 not in nominee.forms


def test_missing_facts_are_named_not_guessed():
    result = det.determine(
        ProbateFacts(date_of_death=date(2025, 1, 1), will_exists=False), as_of=TODAY
    )
    assert result.track == det.INFORMAL_INTESTATE
    assert "decedent_name" in result.missing_facts
    assert "domicile_state" in result.missing_facts
    assert "probate_property_value" in result.missing_facts
    assert "real_property_in_nd" in result.missing_facts


def test_warnings_cover_the_statements_the_application_must_make():
    result = det.determine(
        _facts(
            will_original_available=False,
            demand_for_notice=True,
            probate_opened_elsewhere=True,
        ),
        as_of=TODAY,
    )
    joined = " ".join(result.warnings)
    assert "original will" in joined
    assert "demand for notice" in joined
    assert "another court" in joined


def test_to_json_is_plain_data():
    result = det.determine(
        _facts(heirs=(HeirRow("Bob", "40", "son", "Fargo"),)), as_of=TODAY
    )
    data = result.to_json()
    assert data["as_of"] == "2026-09-18"
    assert isinstance(data["forms"], list)
    assert isinstance(data["reasons"], list)
    assert data["track"] == det.INFORMAL_TESTATE
