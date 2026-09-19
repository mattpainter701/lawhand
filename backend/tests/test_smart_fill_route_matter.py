"""Smart Fill through the real route, against persisted matter rows.

Every other smart-fill test replaces the loaders with in-memory records. This
one writes a campaign scenario to the database and asks the preview route for
the same fields, so the loaders, tenant scoping and the response contract are
exercised together.
"""

import uuid

import pytest

from tests.fill_campaign import documents, scenarios
from tests.test_document_templates import _grant_manage_documents

pytestmark = pytest.mark.asyncio

ROUTE = "/api/templates/{}/smart-fill-preview"


async def _template(db_session, tenant_id, schema):
    from app.models.document_template import DocumentTemplate

    template = DocumentTemplate(
        tenant_id=tenant_id,
        title="Campaign form",
        body="",
        format="pdf",
        category="other",
        variable_schema=schema,
        is_active=True,
    )
    db_session.add(template)
    await db_session.commit()
    return str(template.id)


async def test_individual_client_fills_from_persisted_rows(
    client, db_session, test_tenant, test_user
):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    scenario = scenarios.individual_client()
    ids = await scenario_persist(db_session, test_tenant.id, test_user.id, scenario)
    pdf = documents.convention_pdf()
    schema = documents.schema_for_pdf(pdf, bindings=documents.CONVENTION_BINDINGS)
    template_id = await _template(db_session, test_tenant.id, schema)

    response = await client.post(
        ROUTE.format(template_id), json={"matter_id": ids["matter_id"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matter_id"] == ids["matter_id"]
    by_name = {item["variable"]: item for item in body["variables"]}

    # Name-matched and bound fields resolve to the persisted contact/matter.
    assert by_name["client_name"]["suggested_value"] == "Ada Lovelace"
    assert by_name["client_name"]["provenance"]["record_id"] == str(
        scenario.matter.client.id
    )
    assert by_name["client_full_name"]["suggested_value"] == "Ada Lovelace"
    assert by_name["client_full_name"]["provenance"]["binding"] == "client.name"
    assert by_name["case_number"]["suggested_value"] == "08-2026-CV-00042"
    assert by_name["retainer_amount"]["suggested_value"] == "5000.00"
    assert by_name["retainer_amount"]["source_type"] == "retainer"
    # The matter's plaintiff-side role infers the caption from the client.
    assert by_name["plaintiff_name"]["suggested_value"] == "Ada Lovelace"
    assert by_name["plaintiff_name"]["review_required"] is True
    # Unreachable columns stay unreachable through the route too.
    for name in ("first_name", "last_name", "matter_number", "opened_on"):
        assert by_name[name]["suggested_value"] is None
        assert by_name[name]["provenance"]["status"] == "no_deterministic_source"
    # No branding is configured for the test tenant, and the firm profile
    # falls back to the tenant's name rather than reporting the value missing.
    assert by_name["firm_name"]["source_type"] == "firm_profile"
    assert by_name["firm_name"]["suggested_value"] == test_tenant.name


async def test_family_caption_roles_resolve_nothing(
    client, db_session, test_tenant, test_user
):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    scenario = scenarios.family_petitioner()
    ids = await scenario_persist(db_session, test_tenant.id, test_user.id, scenario)
    pdf = documents.convention_pdf()
    template_id = await _template(
        db_session, test_tenant.id, documents.schema_for_pdf(pdf)
    )

    response = await client.post(
        ROUTE.format(template_id), json={"matter_id": ids["matter_id"]}
    )
    assert response.status_code == 200, response.text
    by_name = {item["variable"]: item for item in response.json()["variables"]}
    assert by_name["client_name"]["suggested_value"] == "Mary Somerville"
    # Two party rows exist, yet neither caption role has a source.
    assert by_name["petitioner_name"]["suggested_value"] is None
    assert by_name["respondent_name"]["suggested_value"] is None
    assert by_name["plaintiff_name"]["suggested_value"] is None


async def test_another_tenants_matter_is_not_found(
    client, db_session, test_tenant, test_user
):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    pdf = documents.convention_pdf()
    template_id = await _template(
        db_session, test_tenant.id, documents.schema_for_pdf(pdf)
    )
    response = await client.post(
        ROUTE.format(template_id), json={"matter_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


async def scenario_persist(db_session, tenant_id, user_id, scenario):
    return await scenarios.persist(db_session, tenant_id, user_id, scenario)
