"""Error summary figures the operator console's triage card relies on."""

import pytest
from httpx import AsyncClient

from app.models.error_log import ErrorLog
from tests.platform_auth_helpers import platform_headers


@pytest.mark.asyncio
async def test_unresolved_errors_are_split_by_severity(
    client: AsyncClient, db_session, test_tenant
):
    db_session.add_all(
        [
            ErrorLog(
                tenant_id=test_tenant.id,
                error_type="llm_error",
                severity="error",
                message="Gateway returned 502",
            ),
            ErrorLog(
                tenant_id=test_tenant.id,
                error_type="llm_error",
                severity="error",
                message="Handled already",
                is_resolved=True,
            ),
            ErrorLog(
                tenant_id=None,
                error_type="scheduler_error",
                severity="critical",
                message="Retention job overran",
            ),
            ErrorLog(
                tenant_id=test_tenant.id,
                error_type="api_error",
                severity="warning",
                message="401: Not authenticated",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/platform/logs/summary",
        params={"days": 1},
        headers=platform_headers(["platform:read"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unresolved"] == 3
    assert body["unresolved_by_severity"] == {"error": 1, "critical": 1, "warning": 1}
    assert body["by_severity"] == {"error": 2, "critical": 1, "warning": 1}
