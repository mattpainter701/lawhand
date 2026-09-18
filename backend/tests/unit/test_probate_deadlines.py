"""The North Dakota probate clock: every rule, from its anchor."""

from datetime import date

from app.services.probate import deadlines

DEATH = date(2025, 1, 31)
APPOINTMENT = date(2025, 3, 31)
PUBLICATION = date(2025, 4, 7)


def _due(plan, deadline_type):
    return next(
        item.due_date for item in plan.deadlines if item.deadline_type == deadline_type
    )


def test_every_rule_runs_when_every_anchor_is_present():
    plan = deadlines.compute(
        date_of_death=DEATH,
        appointment_date=APPOINTMENT,
        first_publication_date=PUBLICATION,
        closing_statement_filed_date=date(2025, 10, 1),
    )
    assert {item.deadline_type for item in plan.deadlines} == set(deadlines.RULE_TYPES)
    assert plan.waiting_on == {}
    assert _due(plan, "notice_heirs") == date(2025, 4, 30)
    assert _due(plan, "creditor_bar") == date(2025, 7, 7)
    assert _due(plan, "claims_disallowance") == date(2025, 9, 5)
    assert _due(plan, "tax_706") == date(2025, 10, 31)
    assert _due(plan, "nd_estate_tax") == date(2026, 4, 30)
    assert _due(plan, "closing_earliest") == date(2025, 7, 7)
    assert _due(plan, "pr_termination") == date(2026, 10, 1)


def test_inventory_is_the_later_of_six_months_after_appointment_or_nine_after_death():
    late_appointment = deadlines.compute(
        date_of_death=DEATH, appointment_date=date(2025, 9, 1)
    )
    assert _due(late_appointment, "inventory") == date(2026, 3, 1)
    early_appointment = deadlines.compute(
        date_of_death=DEATH, appointment_date=date(2025, 2, 10)
    )
    assert _due(early_appointment, "inventory") == date(2025, 10, 31)


def test_elective_share_is_the_later_of_its_two_anchors():
    plan = deadlines.compute(date_of_death=DEATH, appointment_date=APPOINTMENT)
    assert _due(plan, "elective_share") == date(2025, 10, 31)
    plan = deadlines.compute(date_of_death=DEATH, appointment_date=date(2025, 8, 1))
    assert _due(plan, "elective_share") == date(2026, 2, 1)


def test_month_arithmetic_lands_on_the_last_day_when_the_month_is_shorter():
    plan = deadlines.compute(date_of_death=date(2025, 5, 31))
    assert _due(plan, "tax_706") == date(2026, 2, 28)


def test_rules_wait_for_their_anchors_and_say_so():
    plan = deadlines.compute(date_of_death=DEATH)
    types = {item.deadline_type for item in plan.deadlines}
    assert types == {"tax_706", "nd_estate_tax"}
    assert set(plan.waiting_on) == {
        "appointment_date",
        "first_publication_date",
        "closing_statement_filed_date",
    }
    assert "notice_heirs" in plan.waiting_on["appointment_date"]
    assert "creditor_bar" in plan.waiting_on["first_publication_date"]


def test_a_missing_date_of_death_computes_nothing_from_it():
    plan = deadlines.compute(date_of_death=None, appointment_date=APPOINTMENT)
    assert _due(plan, "notice_heirs") == date(2025, 4, 30)
    assert "inventory" in plan.waiting_on["date_of_death"]


def test_plan_json_is_sorted_by_due_date_and_cites_the_statute():
    plan = deadlines.compute(date_of_death=DEATH, appointment_date=APPOINTMENT)
    data = plan.to_json()
    dates = [item["due_date"] for item in data["deadlines"]]
    assert dates == sorted(dates)
    assert all(item["statute"] for item in data["deadlines"])
    assert data["deadlines"][0]["anchor_used"] == "appointment_date"
