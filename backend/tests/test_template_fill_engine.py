"""The Smart Fill engine: declared sources, parity with the router, lazy loads."""

import uuid
from types import SimpleNamespace

from app.services import template_fill_engine as engine
from app.services.template_fill_loaders import Loaders
from tests.fill_campaign import probe, scenarios


class TestVocabulary:
    def test_declared_vocabulary_equals_what_the_resolver_writes(self):
        """The old approval probe and the new declaration must agree exactly."""

        assert engine.vocabulary() == probe.probe_vocabulary()

    def test_every_source_declares_only_what_it_writes(self):
        records = probe.probe_records()
        for source in engine.SOURCES:
            index = engine.CandidateIndex()
            source.collect(index, records)
            written = frozenset(index)
            assert written <= source.aliases, source.key
            # A source may legitimately write nothing for a record it does
            # not find, but the probe carries every record, so declared
            # aliases the probe never produces would be dead vocabulary.
            assert source.aliases <= written | frozenset(), source.key
            assert source.aliases == written, source.key

    def test_role_instance_aliases_are_producible_but_not_in_the_vocabulary(self):
        """A second defendant fills through ``defendant_2_name``, yet the
        approval gate does not count that name as a source. Recorded as-is."""

        records = probe.probe_records(parties_per_role=2)
        index = engine.collect(records)
        assert "defendant_2_name" in index
        assert "defendant_2_name" not in engine.vocabulary()
        assert "defendant_2_name" in engine.source("matter_party").instance_aliases


class TestCandidateIndex:
    def test_first_writer_wins_and_the_loser_is_recorded(self):
        index = engine.CandidateIndex()
        assert index.add("x", "one", source_type="a", source_field="f") is True
        assert index.add("x", "two", source_type="b", source_field="g") is False
        assert index["x"].suggested_value == "one"
        (collision,) = index.collisions()
        assert collision.alias == "x"
        assert collision.winner["source_type"] == "a"
        assert collision.losers[0]["value"] == "two"

    def test_agreeing_writes_are_not_reported(self):
        index = engine.CandidateIndex()
        index.add("x", "same", source_type="a", source_field="f")
        index.add("x", "same", source_type="b", source_field="g")
        assert index.collisions() == []
        assert len(index.collisions(include_agreeing=True)) == 1

    def test_empty_values_are_never_written(self):
        index = engine.CandidateIndex()
        assert index.add("x", None, source_type="a", source_field="f") is False
        assert index.add("y", "   ", source_type="a", source_field="f") is False
        assert index == {}
        assert index.writes == []

    def test_plain_dict_callers_keep_setdefault_semantics(self):
        candidates: dict = {}
        engine.add_candidate(candidates, "x", "one", source_type="a", source_field="f")
        engine.add_candidate(candidates, "x", "two", source_type="b", source_field="g")
        assert candidates["x"].suggested_value == "one"

    def test_structured_party_beats_the_counterparty_column(self):
        records = scenarios.two_defendants()
        index = engine.collect(
            engine.FillRecords(
                matter=records.matter,
                parties=records.parties,
                current_user=scenarios.current_user(),
            )
        )
        assert index["defendant_name"].suggested_value == "Analytical Engines LLC"
        aliases = {c.alias for c in index.collisions()}
        assert aliases == {
            "defendant",
            "defendant_name",
            "defendants",
            "defendant_names",
        }


def _loaders(scenario, calls):
    async def matter(**_):
        calls.append("matter")
        return scenario.matter

    async def parties(**_):
        calls.append("parties")
        return list(scenario.parties)

    async def estate(**_):
        calls.append("estate")
        return scenario.estate

    async def retainer(**_):
        calls.append("retainer")
        return scenario.retainer

    return Loaders(matter=matter, parties=parties, estate=estate, retainer=retainer)


def _template(fields):
    return SimpleNamespace(id=uuid.uuid4(), body="", variable_schema={"fields": fields})


async def _prepare(scenario, fields, *, actor=None, calls=None):
    calls = calls if calls is not None else []
    from unittest.mock import patch

    from app.services import template_custom_fields, template_firm_fields

    async def none(*_args, **_kwargs):
        return {}

    with (
        patch.object(template_firm_fields, "suggestions", none),
        patch.object(template_custom_fields, "suggestions", none),
    ):
        return await engine.prepare_fill(
            SimpleNamespace(),
            template=_template(fields),
            tenant_id=uuid.uuid4(),
            matter_id=scenario.matter_id,
            actor=actor,
            loaders=_loaders(scenario, calls),
        )


class TestLazyLoading:
    async def test_estate_loads_for_an_unbound_field_named_after_it(self):
        """The one intentional behaviour change of the extraction."""

        calls = []
        prepared = await _prepare(
            scenarios.probate_estate(),
            [{"name": "estate_decedent_name", "type": "text"}],
            calls=calls,
        )
        assert "estate" in calls
        assert prepared.by_variable["estate_decedent_name"].suggested_value == (
            "Probe Decedent"
        )
        assert prepared.coverage.states["estate_decedent_name"] == "name_matched"
        assert "estate" in prepared.sources_loaded

    async def test_estate_and_retainer_stay_unloaded_when_nothing_asks(self):
        calls = []
        await _prepare(
            scenarios.probate_estate(),
            [{"name": "client_name", "type": "text"}],
            calls=calls,
        )
        assert calls == ["matter", "parties"]

    async def test_retainer_loads_for_a_binding(self):
        calls = []
        prepared = await _prepare(
            scenarios.individual_client(),
            [{"name": "deposit", "type": "text", "binding": "matter.retainer_amount"}],
            calls=calls,
        )
        assert "retainer" in calls
        assert prepared.by_variable["deposit"].suggested_value == "5000.00"


class TestPreparedFill:
    async def test_works_without_an_actor(self):
        prepared = await _prepare(
            scenarios.individual_client(),
            [
                {"name": "client_name", "type": "text", "required": True},
                {"name": "prepared_by", "type": "text", "required": True},
                {"name": "first_name", "type": "text", "required": True},
                {"name": "notes", "type": "text"},
                {"name": "sig", "field_type": "signature"},
                {"name": "hidden", "type": "text", "included": False},
            ],
        )
        assert prepared.values == {"client_name": "Ada Lovelace", "first_name": "Ada"}
        # ``first_name`` fills through a synonym, at reduced confidence.
        first = prepared.by_variable["first_name"]
        assert first.provenance["synonym_of"] == "client_first_name"
        assert first.confidence == 0.9
        assert first.review_required is True
        # No actor: the preparer family is empty and, being required, reported.
        assert prepared.missing_required == ["prepared_by"]
        assert prepared.coverage.states["first_name"] == "name_matched"
        assert prepared.coverage.states["sig"] == "signature"
        assert "hidden" not in prepared.coverage.states

    async def test_matter_may_be_supplied_directly(self):
        scenario = scenarios.individual_client()
        calls = []

        async def never(**_):  # pragma: no cover - must not be called
            raise AssertionError("matter loader called")

        loaders = _loaders(scenario, calls)
        from unittest.mock import patch

        from app.services import template_custom_fields, template_firm_fields

        async def none(*_args, **_kwargs):
            return {}

        with (
            patch.object(template_firm_fields, "suggestions", none),
            patch.object(template_custom_fields, "suggestions", none),
        ):
            prepared = await engine.prepare_fill(
                SimpleNamespace(),
                template=_template([{"name": "case_number", "type": "text"}]),
                tenant_id=uuid.uuid4(),
                matter=scenario.matter,
                loaders=Loaders(
                    matter=never,
                    parties=loaders.parties,
                    estate=loaders.estate,
                    retainer=loaders.retainer,
                ),
            )
        assert prepared.values == {"case_number": "08-2026-CV-00042"}
        assert calls == ["parties"]

    async def test_no_matter_fills_only_the_actor(self):
        scenario = scenarios.sparse()
        scenario.matter = None
        prepared = await _prepare(
            scenario,
            [
                {"name": "prepared_by", "type": "text"},
                {"name": "client_name", "type": "text"},
            ],
            actor=SimpleNamespace(
                id=uuid.uuid4(), full_name="Grace Hopper", email=None
            ),
        )
        assert prepared.matter_id is None
        assert prepared.values == {"prepared_by": "Grace Hopper"}
        assert prepared.sources_loaded == ()


class TestTemplateVariables:
    def test_body_placeholders_then_schema_fields_once_each(self):
        template = SimpleNamespace(
            body="Dear {{client_name}}, re {{case_number}} {{#if x}}{{/if}}",
            variable_schema={"fields": [{"name": "case_number"}, {"name": "court"}]},
        )
        assert engine.template_variables(template) == [
            "client_name",
            "case_number",
            "court",
        ]
