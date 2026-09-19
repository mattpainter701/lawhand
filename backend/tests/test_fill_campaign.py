"""Pinned quirks of Smart Fill over mock matters and mock documents.

Each assertion here records how the resolver behaves today, verified by
rendering through the production PDF/DOCX writers and reading the page back.
A fix that changes one of these is expected to flip the assertion in the
same change, so this file doubles as the regression fence for the fill
engine work.  ``scripts/rehearse_smart_fill.py`` prints the same campaign as
a report.
"""

import pytest

from tests.fill_campaign import documents, runner, scenarios
from tests.fill_campaign.runner import BLANK, CHOICE_MISMATCH, FILLED, SIGNATURE

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def convention_pdf():
    return documents.convention_pdf()


@pytest.fixture(scope="module")
def convention_docx():
    return documents.convention_docx()


async def _pdf(scenario, pdf, *, bound):
    schema = documents.schema_for_pdf(
        pdf, bindings=documents.CONVENTION_BINDINGS if bound else None
    )
    return await runner.run_case(
        scenario,
        document="pdf/bound" if bound else "pdf/unbound",
        schema=schema,
        source=pdf,
        fmt="pdf",
    )


async def _docx(scenario, built, *, bound):
    source, names = built
    schema = documents.schema_for_docx(
        names, bindings=documents.DOCX_BINDINGS if bound else None
    )
    return await runner.run_case(
        scenario,
        document="docx/bound" if bound else "docx/unbound",
        schema=schema,
        source=source,
        fmt="docx",
    )


class TestNamingConventions:
    """Name matching is exact after folding; nothing else is tried."""

    async def test_only_the_hardcoded_spelling_fills_without_a_binding(
        self, convention_pdf
    ):
        result = await _pdf(scenarios.individual_client(), convention_pdf, bound=False)
        assert result.errors == []
        assert result.state("client_name") == FILLED
        assert result.by_name()["client_name"].value == "Ada Lovelace"
        # ``client_full_name`` is the most common customer spelling.
        assert result.state("client_full_name") == BLANK
        # ``ClientName`` folds to ``clientname`` and matches nothing.
        assert result.state("clientname") == BLANK
        # ``Client Name`` folds to ``client_name``, collides with the field of
        # that exact name on the same form, and is discovered as
        # ``client_name_2`` which no longer matches anything.
        assert result.state("client_name_2") == BLANK
        assert result.by_name()["client_name_2"].provenance_status == (
            "no_deterministic_source"
        )

    async def test_a_binding_fills_every_spelling(self, convention_pdf):
        result = await _pdf(scenarios.individual_client(), convention_pdf, bound=True)
        assert result.errors == []
        for name in ("client_full_name", "clientname", "client_name_2"):
            outcome = result.by_name()[name]
            assert outcome.state == FILLED, name
            assert outcome.value == "Ada Lovelace"
            assert outcome.binding == "client.name"
            assert outcome.coverage_state == "bound"

    async def test_word_keeps_spaced_names_and_loses_camel_case(self, convention_docx):
        result = await _docx(
            scenarios.individual_client(), convention_docx, bound=False
        )
        assert result.errors == []
        # A Word placeholder keeps its spelling, so ``{{Client Name}}`` folds
        # to the alias and fills where the PDF's suffixed copy did not.
        assert result.state("Client Name") == FILLED
        assert result.state("ClientName") == BLANK
        assert result.state("client_full_name") == BLANK


class TestUnreachableRecords:
    """Columns the matter and contact carry but Smart Fill never reads."""

    @pytest.mark.parametrize(
        "name",
        ["first_name", "last_name", "matter_number", "opened_on"],
    )
    async def test_column_has_no_source_bound_or_not(self, convention_pdf, name):
        scenario = scenarios.individual_client()
        assert getattr(scenario.matter, "matter_number") == "LOV0001"
        assert scenario.matter.client.first_name == "Ada"
        for bound in (False, True):
            result = await _pdf(scenario, convention_pdf, bound=bound)
            outcome = result.by_name()[name]
            assert outcome.state == BLANK, (name, bound)
            assert outcome.provenance_status == "no_deterministic_source"
            assert outcome.coverage_state == "unbound"

    async def test_family_caption_roles_have_no_source(self, convention_pdf):
        scenario = scenarios.family_petitioner()
        assert [party.role for party in scenario.parties] == [
            "petitioner",
            "respondent",
        ]
        for bound in (False, True):
            result = await _pdf(scenario, convention_pdf, bound=bound)
            assert result.state("petitioner_name") == BLANK
            assert result.state("respondent_name") == BLANK
            # Not a plaintiff either: the role is not translated.
            assert result.state("plaintiff_name") == BLANK
            assert result.state("client_name") == FILLED


class TestCaptionInference:
    async def test_plaintiff_side_matter_infers_caption_from_client(
        self, convention_pdf
    ):
        result = await _pdf(scenarios.individual_client(), convention_pdf, bound=False)
        plaintiff = result.by_name()["plaintiff_name"]
        defendant = result.by_name()["defendant_name"]
        assert plaintiff.state == FILLED
        assert plaintiff.value == "Ada Lovelace"
        assert plaintiff.confidence == 0.75
        assert plaintiff.review_required is True
        assert defendant.value == "Analytical Engines LLC"
        assert defendant.source_type == "matter"

    async def test_defendant_side_entity_swaps_the_caption(self, convention_pdf):
        result = await _pdf(scenarios.entity_client(), convention_pdf, bound=False)
        assert result.by_name()["defendant_name"].value == "Babbage Holdings LLC"
        assert result.by_name()["plaintiff_name"].value == "Luigi Menabrea"

    async def test_structured_parties_beat_the_counterparty_column(
        self, convention_pdf
    ):
        scenario = scenarios.two_defendants()
        result = await _pdf(scenario, convention_pdf, bound=True)
        defendant = result.by_name()["defendant_name"]
        assert defendant.value == "Analytical Engines LLC"
        assert defendant.source_type == "matter_party"
        assert defendant.confidence == 1.0
        assert defendant.review_required is False
        # The losing write is recorded, not silently dropped.
        aliases = {collision["alias"] for collision in result.collisions}
        assert {
            "defendant",
            "defendant_name",
            "defendants",
            "defendant_names",
        } <= aliases
        losers = {
            loser["value"]
            for collision in result.collisions
            for loser in collision["losers"]
        }
        assert losers == {"Ignored Counterparty"}

    async def test_second_defendant_needs_a_binding(self, convention_pdf):
        scenario = scenarios.two_defendants()
        bound = await _pdf(scenario, convention_pdf, bound=True)
        assert bound.by_name()["defendant_2_full_name"].value == "Charles Babbage"
        unbound = await _pdf(scenario, convention_pdf, bound=False)
        # The instance alias is ``defendant_2_name``; a field named after the
        # card field (``full_name``) does not match by name.
        assert unbound.state("defendant_2_full_name") == BLANK


class TestFormattingAndRendering:
    async def test_decimal_and_choice_values_are_raw(self, convention_pdf):
        result = await _pdf(scenarios.individual_client(), convention_pdf, bound=True)
        assert result.by_name()["hourly_rate"].value == "250.00"
        assert result.by_name()["retainer_amount"].value == "5000.00"
        state = result.by_name()["client_state"]
        assert state.state == CHOICE_MISMATCH
        assert state.value == "ND"
        assert "North Dakota" in (state.note or "")

    async def test_signature_fields_are_never_filled(
        self, convention_pdf, convention_docx
    ):
        pdf = await _pdf(scenarios.individual_client(), convention_pdf, bound=True)
        assert pdf.state("client_signature") == SIGNATURE
        docx = await _docx(scenarios.individual_client(), convention_docx, bound=True)
        assert docx.state("client_signature") == SIGNATURE
        assert docx.errors == []

    async def test_word_and_pdf_agree_on_every_shared_field(
        self, convention_pdf, convention_docx
    ):
        scenario = scenarios.individual_client()
        pdf = await _pdf(scenario, convention_pdf, bound=True)
        docx = await _docx(scenario, convention_docx, bound=True)
        pdf_states = pdf.by_name()
        for name, outcome in docx.by_name().items():
            if name in pdf_states and pdf_states[name].state != CHOICE_MISMATCH:
                assert outcome.state == pdf_states[name].state, name

    async def test_a_bare_matter_fills_only_the_preparer(self, convention_pdf):
        result = await _pdf(scenarios.sparse(), convention_pdf, bound=False)
        assert result.errors == []
        filled = [o.name for o in result.outcomes if o.state == FILLED]
        assert filled == ["prepared_by"]


class TestCoverageParity:
    """``template_fill_coverage`` predicts the fill; where it cannot, say so."""

    async def test_estate_alias_is_reported_as_filling_but_never_loads(
        self, convention_pdf
    ):
        scenario = scenarios.probate_estate()
        unbound = await _pdf(scenario, convention_pdf, bound=False)
        outcome = unbound.by_name()["estate_decedent_name"]
        assert outcome.coverage_state == "name_matched"
        assert outcome.state == BLANK
        assert outcome.provenance_status == "no_deterministic_source"
        bound = await _pdf(scenario, convention_pdf, bound=True)
        assert bound.by_name()["estate_decedent_name"].value == "Probe Decedent"

    async def test_bound_to_a_record_the_matter_lacks_is_reported(self, convention_pdf):
        result = await _pdf(scenarios.individual_client(), convention_pdf, bound=True)
        outcome = result.by_name()["estate_decedent_name"]
        assert outcome.coverage_state == "bound"
        assert outcome.state == BLANK
        assert outcome.provenance_status == "binding_unresolved"


class TestPrecedence:
    """Firm profile > custom field > declared binding > name match > manual."""

    async def test_source_order_for_one_field_name(self):
        scenario = scenarios.individual_client()
        scenario.custom_fields["custom.matter.11111111-1111-1111-1111-111111111111"] = (
            "From custom field"
        )

        async def resolve_with(binding):
            fields = [{"name": "client_name", "type": "text"}]
            if binding:
                fields[0]["binding"] = binding
            suggestions, _ = await runner.resolve(scenario, {"fields": fields})
            return suggestions["client_name"]

        firm = await resolve_with("firm.name")
        assert (firm.source_type, firm.suggested_value) == (
            "firm_profile",
            "Hopper & Byron LLP",
        )
        custom = await resolve_with(
            "custom.matter.11111111-1111-1111-1111-111111111111"
        )
        assert (custom.source_type, custom.suggested_value) == (
            "custom_field",
            "From custom field",
        )
        bound = await resolve_with("client.name")
        assert (bound.source_type, bound.suggested_value) == ("contact", "Ada Lovelace")
        assert bound.provenance["binding"] == "client.name"
        by_name = await resolve_with(None)
        assert (by_name.source_type, by_name.suggested_value) == (
            "contact",
            "Ada Lovelace",
        )
        assert "binding" not in by_name.provenance
        manual = await resolve_with("manual")
        assert manual.suggested_value is None
        assert manual.provenance["status"] == "manual_entry"

    async def test_a_binding_never_falls_back_to_the_name(self):
        scenario = scenarios.individual_client()
        fields = [{"name": "client_name", "type": "text", "binding": "matter.judge"}]
        suggestions, _ = await runner.resolve(scenario, {"fields": fields})
        assert suggestions["client_name"].suggested_value == "Hon. A. Turing"
