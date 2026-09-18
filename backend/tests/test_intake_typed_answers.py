"""Typed questionnaire answers are checked against their question's kind."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.matter_intake import IntakeQuestion
from app.services.matter_intake import validate_answers

QUESTIONS = [
    {
        "key": "date_of_death",
        "label": "Date of death",
        "required": True,
        "kind": "date",
    },
    {
        "key": "will_exists",
        "label": "Did they leave a will?",
        "required": True,
        "kind": "yes_no",
    },
    {"key": "value", "label": "Rough value", "required": False, "kind": "money"},
    {"key": "heirs", "label": "Heirs", "required": False, "kind": "number"},
    {
        "key": "domicile_state",
        "label": "State",
        "required": True,
        "kind": "select",
        "options": ["North Dakota", "Minnesota"],
    },
    {"key": "story", "label": "Anything else", "required": False},
]


def test_a_well_typed_submission_passes():
    validate_answers(
        QUESTIONS,
        {
            "date_of_death": "2025-01-15",
            "will_exists": "Yes",
            "value": "$250,000",
            "heirs": "3",
            "domicile_state": "North Dakota",
            "story": "",
        },
    )


@pytest.mark.parametrize(
    "answers,message",
    [
        ({"date_of_death": "Jan 15"}, "YYYY-MM-DD"),
        ({"date_of_death": "2025-01-15", "will_exists": "sure"}, "yes or no"),
        (
            {
                "date_of_death": "2025-01-15",
                "will_exists": "no",
                "domicile_state": "Mars",
            },
            "listed options",
        ),
        (
            {
                "date_of_death": "2025-01-15",
                "will_exists": "no",
                "domicile_state": "Minnesota",
                "value": "lots",
            },
            "Enter a number",
        ),
        (
            {"will_exists": "no", "domicile_state": "Minnesota"},
            "Complete: Date of death",
        ),
        ({"date_of_death": "2025-01-15", "not_a_question": "x"}, "unknown"),
    ],
)
def test_bad_answers_are_refused_with_a_plain_message(answers, message):
    with pytest.raises(HTTPException) as excinfo:
        validate_answers(QUESTIONS, answers)
    assert excinfo.value.status_code == 422
    assert message in excinfo.value.detail


def test_optional_typed_questions_may_be_left_blank():
    validate_answers(
        QUESTIONS,
        {
            "date_of_death": "2025-01-15",
            "will_exists": "no",
            "domicile_state": "Minnesota",
            "value": " ",
        },
    )


def test_questions_without_a_kind_behave_as_before():
    validate_answers([{"key": "q", "label": "Q", "required": True}], {"q": "anything"})
    with pytest.raises(HTTPException):
        validate_answers([{"key": "q", "label": "Q", "required": True}], {"q": " "})


def test_the_schema_defaults_to_text_and_ties_options_to_select():
    plain = IntakeQuestion(key="q", label="Q")
    assert plain.kind == "text" and plain.options == []
    select = IntakeQuestion(key="s", label="S", kind="select", options=["a", "b"])
    assert select.options == ["a", "b"]
    with pytest.raises(ValidationError):
        IntakeQuestion(key="s", label="S", kind="select", options=["only one"])
    with pytest.raises(ValidationError):
        IntakeQuestion(key="d", label="D", kind="date", options=["a", "b"])
