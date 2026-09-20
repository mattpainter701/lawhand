"""The billing-page MCP estimate covers every metered credential class."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.mcp_product import MCPUsageEvent
from app.models.workspace_mcp_grant import WorkspaceMCPGrant


@pytest.mark.asyncio
async def test_billing_status_includes_research_oauth_usage(
    client, db_session, test_tenant, test_user
):
    grant = WorkspaceMCPGrant(
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        client_id="research.claude-desktop",
        client_name="Claude Research",
        scopes=["research:read"],
        consent_version="research-v1",
        consent_sha256="r" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(grant)
    await db_session.flush()
    db_session.add_all(
        [
            MCPUsageEvent(
                tenant_id=test_tenant.id,
                oauth_grant_id=grant.id,
                user_id=test_user.id,
                auth_type="research_oauth",
                transport="streamable_http",
                tool_name="search_caselaw",
                status_code=200,
                result_count=2,
            ),
            # An internal JWT read is not metered and must stay out of the total.
            MCPUsageEvent(
                tenant_id=test_tenant.id,
                auth_type="jwt",
                transport="rest",
                tool_name="search_caselaw",
                status_code=200,
                result_count=1,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/billing/status")
    assert response.status_code == 200, response.text
    usage = response.json()["mcp_usage"]
    assert usage["calls_30d"] == 1
    assert usage["oauth_calls_30d"] == 1
    assert usage["estimated_charges_usd_30d"] == 0.45
