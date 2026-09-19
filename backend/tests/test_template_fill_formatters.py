"""Values shaped to the field that holds them: choice, checkbox, date."""

from datetime import date, datetime, timezone

import pytest

from app.schemas.document_template import DocumentTemplateVariableSuggestion
from app.services import template_fill_formatters as fmt


class TestChoice:
    def test_exact_export_value_passes_through(self):
        assert fmt.choice_value("TX", {"options": ["TX", "OK"]}) == "TX"

    def test_matches_a_label_ignoring_case(self):
        spec = {
            "options": [
                {"value": "hrly", "label": "Hourly"},
                {"value": "flat", "label": "Flat fee"},
            ]
        }
        assert fmt.choice_value("hourly", spec) == "hrly"
        assert fmt.choice_value("FLAT FEE", spec) == "flat"

    @pytest.mark.parametrize(
        ("value", "options", "expected"),
        [
            ("ND", ["North Dakota", "Minnesota"], "North Dakota"),
            ("nd", ["North Dakota", "Minnesota"], "North Dakota"),
            ("North Dakota", ["ND", "MN"], "ND"),
            ("Minnesota", ["ND", "MN"], "MN"),
        ],
    )
    def test_state_codes_and_names_select_each_other(self, value, options, expected):
        assert fmt.choice_value(value, {"options": options}) == expected

    def test_no_match_returns_none(self):
        assert fmt.choice_value("Ontario", {"options": ["North Dakota"]}) is None

    def test_no_options_means_any_value(self):
        assert fmt.choice_value("anything", {"options": []}) == "anything"


class TestCheckbox:
    @pytest.mark.parametrize("value", ["true", "Yes", "X", "1", "checked"])
    def test_truthy(self, value):
        assert fmt.checkbox_value(value) == "true"

    @pytest.mark.parametrize("value", ["false", "No", "0", "", "  "])
    def test_falsy(self, value):
        assert fmt.checkbox_value(value) == "false"

    def test_other_text_is_not_a_checkbox_value(self):
        assert fmt.checkbox_value("Ada Lovelace") is None


class TestDate:
    def test_iso_date_becomes_form_style(self):
        assert fmt.date_value("2026-03-04") == "03/04/2026"

    def test_iso_datetime_keeps_the_date(self):
        assert fmt.date_value("2026-03-04T15:30:00Z") == "03/04/2026"

    def test_human_text_is_left_alone(self):
        assert fmt.date_value("4th day of March, 2026") == "4th day of March, 2026"

    def test_iso_shaped_nonsense_is_rejected(self):
        assert fmt.date_value("2026-13-45") is None

    def test_as_text_for_date_objects(self):
        assert fmt.as_text(date(2026, 3, 4)) == "03/04/2026"
        assert fmt.as_text(datetime(2026, 3, 4, tzinfo=timezone.utc)) == "03/04/2026"
        assert fmt.as_text("2026-03-04") is None


def _suggestion(value):
    return DocumentTemplateVariableSuggestion(
        variable="f",
        suggested_value=value,
        source_type="contact",
        source_field="address.state",
        provenance={"source_type": "contact"},
        confidence=1.0,
        review_required=False,
    )


class TestFormatSuggestion:
    def test_text_fields_are_untouched(self):
        original = _suggestion("250.00")
        assert fmt.format_suggestion(original, {"type": "text"}) is original

    def test_empty_values_are_untouched(self):
        original = _suggestion(None)
        assert (
            fmt.format_suggestion(original, {"field_type": "choice", "options": ["a"]})
            is original
        )

    def test_no_spec_is_untouched(self):
        original = _suggestion("ND")
        assert fmt.format_suggestion(original, None) is original

    def test_a_matched_choice_records_what_it_came_from(self):
        shaped = fmt.format_suggestion(
            _suggestion("ND"), {"field_type": "choice", "options": ["North Dakota"]}
        )
        assert shaped.suggested_value == "North Dakota"
        assert shaped.provenance["formatted_from"] == "ND"
        assert shaped.provenance["format_note"] == "matched to an option"
        assert shaped.review_required is False

    def test_an_unmatched_choice_is_withdrawn_for_review(self):
        shaped = fmt.format_suggestion(
            _suggestion("Ontario"), {"field_type": "radio", "options": ["A", "B"]}
        )
        assert shaped.suggested_value is None
        assert shaped.review_required is True
        assert shaped.provenance["unformatted_value"] == "Ontario"
        assert "not one of this field's options" in shaped.provenance["format_warning"]
        # Provenance of the source is kept so the reviewer sees where it came from.
        assert shaped.provenance["source_type"] == "contact"

    def test_checkbox_and_date_fields(self):
        assert (
            fmt.format_suggestion(
                _suggestion("Yes"), {"type": "checkbox"}
            ).suggested_value
            == "true"
        )
        assert (
            fmt.format_suggestion(
                _suggestion("2026-03-04"), {"type": "date"}
            ).suggested_value
            == "03/04/2026"
        )
        withdrawn = fmt.format_suggestion(_suggestion("Ada"), {"type": "checkbox"})
        assert withdrawn.suggested_value is None
