"""Smart Fill draws the ``estate.*`` group from the estate linked to the matter."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routers import document_templates
from app.services.probate import bindings


def _matter():
    return SimpleNamespace(
        id=uuid.uuid4(),
        matter_name="Estate of Probe Decedent",
        matter_type="probate",
        description=None,
        status="open",
        stage="intake",
        jurisdiction="North Dakota",
        case_number=None,
        court=None,
        judge=None,
        billing_method="hourly",
        billing_cycle="monthly",
        hourly_rate=Decimal("250.00"),
        budget_amount=None,
        role=None,
        counterparty=None,
        client=SimpleNamespace(
            id=uuid.uuid4(),
            display_name="Probe Applicant",
            email="probe@example.com",
            phone="555-0100",
            address={"city": "Fargo", "state": "ND", "zip": "58102"},
        ),
        attorney_of_record=None,
    )


@pytest.mark.asyncio
async def test_estate_bindings_fill_from_the_linked_estate(monkeypatch):
    matter = _matter()
    estate = bindings.probe_estate()
    loaded = {}

    async def fake_load_matter_context(**kwargs):
        return matter

    async def fake_load_matter_parties(**kwargs):
        return []

    async def fake_load_estate(**kwargs):
        loaded["matter_id"] = kwargs["matter"].id
        return estate

    monkeypatch.setattr(
        document_templates, "_load_matter_context", fake_load_matter_context
    )
    monkeypatch.setattr(
        document_templates, "_load_matter_parties", fake_load_matter_parties
    )
    monkeypatch.setattr(document_templates, "_load_estate_for_matter", fake_load_estate)

    template = SimpleNamespace(
        id=uuid.uuid4(),
        body="",
        variable_schema={
            "version": 1,
            "fields": [
                {"name": "court_of_f2", "binding": "estate.venue_county"},
                {"name": "estate_of_f2", "binding": "estate.decedent_name"},
                {"name": "heirs_app", "binding": "estate.heirs_table"},
                {"name": "sta_phone", "binding": "estate.applicant_phone"},
                {"name": "client_name", "binding": "client.name"},
            ],
        },
    )
    _, suggestions = await document_templates.build_variable_suggestions(
        template=template,
        requested_variables=None,
        matter_id=str(matter.id),
        tenant_id=uuid.uuid4(),
        current_user=SimpleNamespace(
            id=uuid.uuid4(), full_name="Staff", email="s@x.com"
        ),
        db=SimpleNamespace(),
    )
    by_variable = {item.variable: item for item in suggestions}
    assert loaded["matter_id"] == matter.id
    assert by_variable["court_of_f2"].suggested_value == "Cass"
    assert by_variable["court_of_f2"].source_type == "estate"
    assert by_variable["estate_of_f2"].suggested_value == "Probe Decedent"
    assert by_variable["heirs_app"].suggested_value.startswith(
        "Probe Spouse — 80 — spouse"
    )
    assert by_variable["sta_phone"].suggested_value == "701-555-0100"
    assert by_variable["client_name"].suggested_value == "Probe Applicant"
    assert by_variable["client_name"].source_type == "contact"


@pytest.mark.asyncio
async def test_the_estate_is_not_loaded_when_no_field_binds_to_it(monkeypatch):
    matter = _matter()
    calls = []

    async def fake_load_matter_context(**kwargs):
        return matter

    async def fake_load_matter_parties(**kwargs):
        return []

    async def fake_load_estate(**kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(
        document_templates, "_load_matter_context", fake_load_matter_context
    )
    monkeypatch.setattr(
        document_templates, "_load_matter_parties", fake_load_matter_parties
    )
    monkeypatch.setattr(document_templates, "_load_estate_for_matter", fake_load_estate)
    template = SimpleNamespace(
        id=uuid.uuid4(),
        body="{{client_name}}",
        variable_schema={
            "version": 1,
            "fields": [{"name": "client_name", "binding": "client.name"}],
        },
    )
    _, suggestions = await document_templates.build_variable_suggestions(
        template=template,
        requested_variables=None,
        matter_id=str(matter.id),
        tenant_id=uuid.uuid4(),
        current_user=SimpleNamespace(
            id=uuid.uuid4(), full_name="Staff", email="s@x.com"
        ),
        db=SimpleNamespace(),
    )
    assert calls == []
    assert suggestions[0].suggested_value == "Probe Applicant"


def test_the_approval_vocabulary_lists_every_estate_alias():
    from app.services.template_bindings import catalogue

    vocabulary = document_templates._smart_fill_alias_vocabulary()
    for entry in catalogue():
        if entry.path.startswith("estate."):
            assert entry.alias in vocabulary, entry.path
