"""Smart Fill over the shipped sample forms that carry bindings.

The manifest ships authored and curated forms with a ``bindings`` map. Each is
discovered exactly as template creation discovers it, bound from the manifest,
resolved against a campaign scenario, rendered, and read back. Every bound
field whose record the scenario carries must come back with a value; the
short list of bound-but-blank fields is pinned so it cannot grow unnoticed.
"""

import pytest

from tests.fill_campaign import documents, runner, scenarios
from tests.fill_campaign.runner import BLANK, FILLED

pytestmark = pytest.mark.asyncio

#: Bound fields that legitimately stay blank for the scenario used: the
#: record exists on the catalogue but not on this matter.
EXPECTED_BOUND_BLANK = {
    "general-legal-services-fee-agreement": {"contingency_percentage"},
    # A business-name box, bound to the client's organization name, stays
    # blank for the individual client the scenario carries.
    "alaska-motor-vehicle-power-of-attorney-847": {"company_name_if_applicable"},
    "hawaii-tax-power-of-attorney-n-848": {"110"},
}


def _scenario_for(form):
    if any(path.startswith("estate.") for path in form["bindings"].values()):
        return scenarios.probate_estate()
    return scenarios.individual_client()


@pytest.mark.parametrize(
    "form", documents.seed_forms_with_bindings(), ids=lambda form: form["slug"]
)
async def test_every_bound_field_fills_from_the_scenario(form):
    source = documents.seed_pdf(form)
    schema = documents.schema_for_pdf(source, bindings=form["bindings"])
    discovered = {field["name"] for field in schema["fields"]}
    # The manifest binds by discovered name; a stale key would bind nothing.
    assert set(form["bindings"]) <= discovered

    result = await runner.run_case(
        _scenario_for(form),
        document=form["slug"],
        schema=schema,
        source=source,
        fmt="pdf",
    )
    assert result.errors == []
    bound = [o for o in result.outcomes if o.coverage_state == "bound"]
    # ``manual`` is a binding that deliberately names no record: the field is
    # typed by a person rather than filled by name from an unrelated one.
    manual = {name for name, path in form["bindings"].items() if path == "manual"}
    assert len(bound) == len(form["bindings"]) - len(manual)
    by_name = {o.name: o for o in result.outcomes}
    for name in manual:
        assert by_name[name].state == BLANK, name
    blank = {o.name for o in bound if o.state != FILLED}
    assert blank == EXPECTED_BOUND_BLANK.get(form["slug"], set())
    for outcome in bound:
        if outcome.state == FILLED:
            assert outcome.value, outcome.name
            assert outcome.binding, outcome.name


async def test_the_guidebook_fills_from_the_estate_alone():
    form = next(
        item
        for item in documents.seed_forms_with_bindings()
        if item["slug"] == "nd-informal-probate-guidebook"
    )
    source = documents.seed_pdf(form)
    schema = documents.schema_for_pdf(source, bindings=form["bindings"])
    result = await runner.run_case(
        scenarios.probate_estate(),
        document=form["slug"],
        schema=schema,
        source=source,
        fmt="pdf",
    )
    sources = {o.source_type for o in result.outcomes if o.state == FILLED}
    assert sources == {"estate"}
    unbound = [o for o in result.outcomes if o.coverage_state == "unbound"]
    # Every unbound field on the packet is typed by hand; none matches a name.
    assert all(o.state == BLANK for o in unbound)
    assert len(unbound) == 340 - len(form["bindings"])
