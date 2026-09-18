"""Parsing the probate intake into facts, and the JSON round trip."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.probate import facts as facts_module
from app.services.probate.facts import HeirRow, ProbateFacts


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("yes", True),
        ("Yes", True),
        ("NO", False),
        ("true", True),
        ("none", False),
        ("", None),
        (None, None),
        ("maybe", None),
        (True, True),
    ],
)
def test_parse_bool(raw, expected):
    assert facts_module.parse_bool(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2025-03-04", date(2025, 3, 4)),
        ("3/4/2025", date(2025, 3, 4)),
        ("03-04-2025", date(2025, 3, 4)),
        ("3/4/25", date(2025, 3, 4)),
        ("March 4, 2025", date(2025, 3, 4)),
        ("sometime in March", None),
        ("", None),
        (date(2025, 3, 4), date(2025, 3, 4)),
    ],
)
def test_parse_date(raw, expected):
    assert facts_module.parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$250,000", Decimal("250000.00")),
        ("250000", Decimal("250000.00")),
        ("about 80k", Decimal("80000.00")),
        ("1.2M", Decimal("1200000.00")),
        ("1,234.56", Decimal("1234.56")),
        ("", None),
        ("unknown", None),
        (Decimal("5"), Decimal("5")),
        (5, Decimal("5")),
    ],
)
def test_parse_money(raw, expected):
    assert facts_module.parse_money(raw) == expected


def test_parse_heirs_reads_one_person_per_line_with_any_separator():
    text = (
        "Ann Olson; 70; spouse; 1 Main St, Fargo ND 58102\n"
        "Bob Olson | 45 | son | 2 Elm St, Moorhead MN\n"
        "- Carol Olson — 41 — daughter\n"
        "Dan (grandson)\n"
    )
    rows = facts_module.parse_heirs(text)
    assert rows[0] == HeirRow("Ann Olson", "70", "spouse", "1 Main St, Fargo ND 58102")
    assert rows[1] == HeirRow("Bob Olson", "45", "son", "2 Elm St, Moorhead MN")
    assert rows[2] == HeirRow("Carol Olson", "41", "daughter", "")
    assert rows[3] == HeirRow("Dan (grandson)")
    assert rows[0].as_line() == "Ann Olson — 70 — spouse — 1 Main St, Fargo ND 58102"


def test_parse_heirs_accepts_structured_rows_and_ignores_blanks():
    rows = facts_module.parse_heirs(
        [{"name": "Ann", "age": 70, "relationship": "spouse"}, {"name": ""}, "none"]
    )
    assert rows == (HeirRow("Ann", "70", "spouse", ""),)
    assert facts_module.parse_heirs("none") == ()


def test_parse_list_splits_on_commas_newlines_and_semicolons():
    assert facts_module.parse_list("Cass, Richland; Burleigh") == (
        "Cass",
        "Richland",
        "Burleigh",
    )
    assert facts_module.parse_list("none") == ()
    assert facts_module.parse_list(["a", " b "]) == ("a", "b")


def test_from_json_types_every_field_and_keeps_unknown_keys_aside():
    facts = facts_module.from_json(
        {
            "decedent_name": "  Ole   Olson ",
            "date_of_death": "2025-01-15",
            "will_exists": "yes",
            "probate_property_value": "$250,000",
            "heirs": "Ann; 70; spouse",
            "nd_property_counties": "Cass, Richland",
            "age_at_death": "84 years",
            "inventory_open": "yes",
            "surprise": "kept",
        }
    )
    assert facts.decedent_name == "Ole Olson"
    assert facts.date_of_death == date(2025, 1, 15)
    assert facts.will_exists is True
    assert facts.probate_property_value == Decimal("250000.00")
    assert facts.heirs == (HeirRow("Ann", "70", "spouse", ""),)
    assert facts.nd_property_counties == ("Cass", "Richland")
    assert facts.age_at_death == 84
    assert facts.inventory_open is True
    assert facts.extra == {"surprise": "kept"}


def test_json_round_trip_is_stable():
    facts = facts_module.from_json(
        {
            "decedent_name": "Ole",
            "date_of_death": "2025-01-15",
            "probate_property_value": "10",
            "heirs": "Ann; 70; spouse; Fargo",
            "will_exists": "no",
        }
    )
    data = facts_module.to_json(facts)
    assert data["date_of_death"] == "2025-01-15"
    assert data["probate_property_value"] == "10.00"
    assert data["heirs"] == [
        {"name": "Ann", "age": "70", "relationship": "spouse", "address": "Fargo"}
    ]
    assert facts_module.from_json(data) == facts
    assert facts_module.from_json(None) == ProbateFacts()
    assert facts_module.is_blank(ProbateFacts())
    assert not facts_module.is_blank(facts)


def test_merge_fills_gaps_by_default_and_replaces_when_overwriting():
    base = ProbateFacts(decedent_name="Ole", will_exists=True, extra={"a": 1})
    incoming = ProbateFacts(
        decedent_name="Ole Olson",
        date_of_death=date(2025, 1, 1),
        extra={"a": 2, "b": 3},
    )
    filled = facts_module.merge(base, incoming)
    assert filled.decedent_name == "Ole"
    assert filled.date_of_death == date(2025, 1, 1)
    assert filled.will_exists is True
    assert filled.extra == {"a": 1, "b": 3}

    replaced = facts_module.merge(base, incoming, overwrite=True)
    assert replaced.decedent_name == "Ole Olson"
    assert replaced.will_exists is True  # incoming had nothing to say
    assert replaced.extra == {"a": 2, "b": 3}


def test_age_at_death_is_computed_from_the_two_dates():
    facts = ProbateFacts(
        date_of_birth=date(1940, 6, 15), date_of_death=date(2025, 6, 14)
    )
    assert facts.computed_age_at_death() == 84
    facts = ProbateFacts(
        date_of_birth=date(1940, 6, 15), date_of_death=date(2025, 6, 15)
    )
    assert facts.computed_age_at_death() == 85
    assert ProbateFacts(age_at_death=90).computed_age_at_death() == 90
    assert ProbateFacts().computed_age_at_death() is None


@pytest.mark.parametrize(
    "state,expected",
    [
        ("North Dakota", True),
        ("ND", True),
        ("n.d.", True),
        ("Minnesota", False),
        (None, None),
    ],
)
def test_domicile_recognises_north_dakota_in_any_spelling(state, expected):
    assert ProbateFacts(domicile_state=state).is_nd_domicile() is expected
