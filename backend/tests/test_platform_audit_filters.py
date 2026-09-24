"""Operator audit filters behind the console's tenant History view."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.tenant import Tenant
from tests.platform_auth_helpers import platform_headers

AUDIT = "/api/platform/audit"


def _debug():
    return platform_headers(["platform:debug"])


@pytest_asyncio.fixture
async def rival_tenant(db_session):
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Rival Audit LLP",
        domain="rival-audit.example",
        billing_tier="payg",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.mark.asyncio
async def test_tenant_history_includes_actions_recorded_against_other_resources(
    client: AsyncClient, test_tenant, rival_tenant
):
    write = platform_headers(["platform:write"])
    updated = await client.put(
        f"/api/platform/tenants/{test_tenant.id}", headers=write, json={"seat_count": 4}
    )
    assert updated.status_code == 200, updated.text
    other = await client.put(
        f"/api/platform/tenants/{rival_tenant.id}",
        headers=write,
        json={"seat_count": 2},
    )
    assert other.status_code == 200, other.text

    filed = await client.post(
        "/api/compliance/operating/support",
        json={
            "severity": "S3",
            "channel": "workspace",
            "subject": "Report export question",
            "safe_summary": "How do we export the monthly time report?",
        },
    )
    assert filed.status_code == 200, filed.text
    acknowledged = await client.patch(
        f"/api/platform/operating-trust/tenants/{test_tenant.id}/support/{filed.json()['id']}",
        headers=write,
        json={"status": "acknowledged"},
    )
    assert acknowledged.status_code == 200, acknowledged.text

    history = await client.get(
        AUDIT, params={"tenant_id": str(test_tenant.id)}, headers=_debug()
    )

    assert history.status_code == 200, history.text
    actions = {entry["action"] for entry in history.json()["entries"]}
    assert actions == {"tenant.updated", "support.acknowledged"}
    for entry in history.json()["entries"]:
        assert entry["resource_id"] == str(test_tenant.id) or entry["metadata"][
            "tenant_id"
        ] == str(test_tenant.id)


@pytest.mark.asyncio
async def test_request_rows_can_be_left_out(client: AsyncClient, test_tenant):
    await client.get("/api/platform/plans", headers=platform_headers())
    await client.put(
        f"/api/platform/tenants/{test_tenant.id}",
        headers=platform_headers(["platform:write"]),
        json={"seat_count": 3},
    )

    everything = await client.get(AUDIT, headers=_debug())
    assert any(e["action"] == "platform.request" for e in everything.json()["entries"])

    actions_only = await client.get(
        AUDIT, params={"exclude_requests": "true"}, headers=_debug()
    )
    assert actions_only.status_code == 200, actions_only.text
    entries = actions_only.json()["entries"]
    assert [e["action"] for e in entries] == ["tenant.updated"]
    assert actions_only.json()["total"] == 1


@pytest.mark.asyncio
async def test_tenant_filter_rejects_a_malformed_id(client: AsyncClient):
    response = await client.get(
        AUDIT, params={"tenant_id": "not-a-uuid"}, headers=_debug()
    )
    assert response.status_code == 422
