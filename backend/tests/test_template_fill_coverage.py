"""Where a template field's value comes from, and how much of a form fills.

The same classification is implemented twice — once here and once in
``frontend/src/components/templates/fillCoverage.js`` — because the editors
have to recompute it live over a schema nobody has saved yet, while the library
list needs the saved truth without loading an editor. Both suites pin the
shared fixture in ``tests/fixtures/fill_coverage_contract.json``, so the two
implementations cannot drift apart silently.
"""

import json
from pathlib import Path

import pytest

from app.routers.document_templates import (
    _fill_coverage_response,
    _smart_fill_alias_vocabulary,
)
from app.services import template_fill_coverage as coverage_service
from app.services.template_fill_coverage import (
    BOUND,
    MANUAL,
    NAME_MATCHED,
    SIGNATURE,
    UNBOUND,
    UNRESOLVED,
    classify_field,
    coverage,
    normalize_variable_name,
)

CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures" / "fill_coverage_contract.json").read_text()
)


@pytest.fixture(scope="module")
def vocabulary():
    return _smart_fill_alias_vocabulary()


class TestSharedContract:
    """The fixture the JavaScript implementation pins to the same numbers."""

    def test_the_split_matches_the_recorded_expectation(self, vocabulary):
        split = coverage(CONTRACT["variable_schema"], vocabulary=vocabulary)
        expected = CONTRACT["expected"]
        assert split.total == expected["total"]
        assert split.fills == expected["fills"]
        assert split.counts == {
            key: value
            for key, value in expected.items()
            if key not in {"total", "fills"}
        }

    def test_every_field_lands_in_the_recorded_state(self, vocabulary):
        split = coverage(CONTRACT["variable_schema"], vocabulary=vocabulary)
        assert split.states == CONTRACT["expected_states"]

    def test_the_buckets_account_for_every_counted_field(self, vocabulary):
        split = coverage(CONTRACT["variable_schema"], vocabulary=vocabulary)
        assert sum(split.counts.values()) == split.total


class TestCatalogueSliceIsFaithful:
    """The JavaScript side classifies against a slice of the real catalogue.

    It cannot read the server's vocabulary from a unit test, so the fixture
    carries the handful of paths and names it needs. Every one is checked here
    against the real thing: a slice that stopped describing the server would
    let both suites agree on an answer the product does not give.
    """

    def test_every_listed_path_still_resolves(self):
        for path in CONTRACT["catalogue"]["binding_paths"]:
            assert coverage_service.binding_is_resolvable(path), path

    def test_every_listed_card_path_still_resolves(self):
        # Card paths are a superset of the flat catalogue and are what the card
        # rail actually emits, so the JavaScript side has to accept them too.
        for path in CONTRACT["catalogue"]["card_paths"]:
            assert coverage_service.binding_is_resolvable(path), path

    def test_every_path_listed_as_absent_still_is(self):
        for path in CONTRACT["catalogue"]["absent_binding_paths"]:
            assert not coverage_service.binding_is_resolvable(path), path

    def test_every_listed_name_is_one_smart_fill_produces(self, vocabulary):
        for name in CONTRACT["catalogue"]["smart_fill_names"]:
            assert name in vocabulary, name

    def test_every_name_listed_as_absent_still_is(self, vocabulary):
        for name in CONTRACT["catalogue"]["absent_smart_fill_names"]:
            assert name not in vocabulary, name


class TestClassification:
    def test_a_declared_binding_never_falls_back_to_name_matching(self, vocabulary):
        # The field is named after a resolvable alias *and* bound to a path the
        # catalogue no longer describes. Reading it as name-matched would show a
        # firm a green field that renders blank, which is the exact surprise
        # bindings exist to remove.
        field = {"name": "case_number", "field_type": "text"}
        assert classify_field(field, binding=None, vocabulary=vocabulary) == NAME_MATCHED
        assert (
            classify_field(field, binding="matter.gone", vocabulary=vocabulary)
            == UNRESOLVED
        )

    def test_manual_suppresses_a_name_that_would_otherwise_match(self, vocabulary):
        field = {"name": "client_email", "field_type": "text"}
        assert classify_field(field, binding=None, vocabulary=vocabulary) == NAME_MATCHED
        assert classify_field(field, binding="manual", vocabulary=vocabulary) == MANUAL

    def test_a_signing_field_is_signed_whatever_it_is_bound_to(self, vocabulary):
        signature = {"name": "client_name", "field_type": "signature"}
        assert (
            classify_field(signature, binding="client.name", vocabulary=vocabulary)
            == SIGNATURE
        )

    def test_a_date_is_signed_only_when_it_carries_a_signer_role(self, vocabulary):
        dated = {"name": "effective_date", "field_type": "date"}
        assert classify_field(dated, binding=None, vocabulary=vocabulary) == UNBOUND
        assert (
            classify_field(
                {**dated, "signer_role": "client"}, binding=None, vocabulary=vocabulary
            )
            == SIGNATURE
        )

    def test_a_card_path_resolves_the_way_the_fill_resolves_it(self, vocabulary):
        # `client.full_name` is not in the flat catalogue; the card resolver
        # maps it to the same `client_name` alias the fill uses. Classifying it
        # as unresolved would show a firm a broken field that fills correctly.
        field = {"name": "who", "field_type": "text"}
        for binding in ("client.full_name", "defendant.2.full_name"):
            assert classify_field(field, binding=binding, vocabulary=vocabulary) == BOUND

    def test_item_and_custom_bindings_fill_without_a_catalogue_alias(self, vocabulary):
        field = {"name": "anything", "field_type": "text"}
        for binding in (
            "item.party_name",
            "custom.matter.11111111-2222-3333-4444-555555555555",
            "custom.contact.11111111-2222-3333-4444-555555555555",
        ):
            assert classify_field(field, binding=binding, vocabulary=vocabulary) == BOUND


class TestWhatCounts:
    def test_an_excluded_field_is_not_part_of_the_template(self, vocabulary):
        schema = {
            "fields": [
                {"name": "kept", "field_type": "text"},
                {"name": "dropped", "field_type": "text", "included": False},
            ]
        }
        assert coverage(schema, vocabulary=vocabulary).total == 1

    def test_a_field_that_copies_another_is_not_separately_answered(self, vocabulary):
        # Counting it would report one answer twice and quietly inflate the
        # denominator every time an author reuses a value.
        schema = {
            "fields": [
                {"name": "signer", "field_type": "text"},
                {"name": "signer_again", "field_type": "text", "value_from": "signer"},
            ]
        }
        assert coverage(schema, vocabulary=vocabulary).total == 1

    def test_a_schema_saved_before_bindings_existed_still_reads(self, vocabulary):
        for schema in (None, {}, {"fields": None}, {"fields": ["not a field"]}):
            assert coverage(schema, vocabulary=vocabulary).total == 0


class TestVocabularyContract:
    def test_every_served_name_classifies_as_a_name_match(self, vocabulary):
        # The editor is handed this list and decides from it alone. Any name in
        # it that the classifier disagrees with is a field the read-out would
        # call unbound while Smart Fill fills it.
        for name in vocabulary:
            assert (
                classify_field(
                    {"name": name, "field_type": "text"},
                    binding=None,
                    vocabulary=vocabulary,
                )
                == NAME_MATCHED
            )

    def test_the_router_resolves_names_through_the_shared_rule(self):
        # The fill path and the read-out must normalise identically or a field
        # named "Client Name" fills but reads as unbound.
        from app.routers import document_templates

        assert document_templates._normalize_variable_name is normalize_variable_name
        assert (
            document_templates._binding_is_resolvable
            is coverage_service.binding_is_resolvable
        )

    def test_normalisation_folds_punctuation_and_case(self):
        assert normalize_variable_name("Client Name") == "client_name"
        assert normalize_variable_name("client-name!") == "client_name"
        assert normalize_variable_name("__Client__Name__") == "client_name"


class TestTemplateResponse:
    def test_a_template_read_carries_its_split(self):
        response = _fill_coverage_response(CONTRACT["variable_schema"])
        expected = CONTRACT["expected"]
        assert response.model_dump() == expected

    def test_a_template_with_no_schema_reports_zero_rather_than_nothing(self):
        # A template nobody has added fields to has 0 of 0 filling, which is a
        # true statement. Omitting the block would make the library render an
        # empty space where every other row carries a number.
        assert _fill_coverage_response(None).total == 0
