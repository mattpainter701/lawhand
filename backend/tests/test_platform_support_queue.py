"""The operator support queue: every tenant's support requests, one list."""

import os
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.datastructures import Headers

from app.models.operating_trust import SupportRequest
from app.models.tenant import Tenant
from app.routers import operating_trust
from app.services.operating_trust import utcnow
from tests.platform_auth_helpers import platform_headers

QUEUE = "/api/platform/operating-trust/support"


def _request(tenant_id, **overrides) -> SupportRequest:
    now = utcnow()
    values = {
        "tenant_id": tenant_id,
        "severity": "S3",
        "status": "open",
        "channel": "workspace",
        "subject": "Exports are slow",
        "safe_summary": "Matter exports take several minutes to finish.",
        "policy_version": "test-contract",
        "acknowledgement_objective_minutes": 240,
        "acknowledgement_due_at": now + timedelta(hours=4),
        "requested_by_email": "admin@firm.example",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SupportRequest(**values)


@pytest_asyncio.fixture
async def rival_tenant(db_session):
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Rival Legal LLP",
        domain="rival-queue.example",
        billing_tier="payg",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def seeded_queue(db_session, test_tenant, rival_tenant):
    """One overdue S1, one fresh S3, a rival S2 and a resolved S4."""

    now = utcnow()
    rows = {
        "overdue_s1": _request(
            test_tenant.id,
            severity="S1",
            subject="Nobody can sign in",
            acknowledgement_objective_minutes=60,
            acknowledgement_due_at=now - timedelta(minutes=5),
            requested_by_email="partner@testfirm.com",
        ),
        "fresh_s3": _request(test_tenant.id),
        "rival_s2": _request(
            rival_tenant.id,
            severity="S2",
            subject="Calendar sync stopped",
            requested_by_email="ops@rival.example",
        ),
        "resolved_s4": _request(
            test_tenant.id,
            severity="S4",
            status="resolved",
            subject="Typo in invoice footer",
            resolved_at=now - timedelta(days=1),
            resolution_summary="Corrected the template.",
        ),
    }
    db_session.add_all(rows.values())
    await db_session.commit()
    return {name: str(row.id) for name, row in rows.items()}


@pytest.mark.asyncio
async def test_queue_lists_active_requests_across_tenants_in_policy_order(
    client: AsyncClient, seeded_queue, test_tenant, rival_tenant
):
    response = await client.get(QUEUE, headers=platform_headers(["platform:read"]))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [
        seeded_queue["overdue_s1"],
        seeded_queue["rival_s2"],
        seeded_queue["fresh_s3"],
    ]
    first = body["items"][0]
    assert first["tenant_id"] == str(test_tenant.id)
    assert first["tenant_name"] == test_tenant.name
    assert first["requested_by_email"] == "partner@testfirm.com"
    assert first["overdue"] is True
    assert body["items"][1]["tenant_name"] == rival_tenant.name
    assert body["items"][1]["overdue"] is False
    assert body["total"] == 3
    assert body["counts"] == {
        "open": 3,
        "acknowledged": 0,
        "mitigated": 0,
        "resolved": 1,
        "overdue": 1,
    }


@pytest.mark.asyncio
async def test_queue_filters_by_tenant_severity_and_status(
    client: AsyncClient, seeded_queue, test_tenant, rival_tenant
):
    headers = platform_headers(["platform:read"])

    rival = await client.get(
        QUEUE, params={"tenant_id": str(rival_tenant.id)}, headers=headers
    )
    assert [item["id"] for item in rival.json()["items"]] == [seeded_queue["rival_s2"]]
    assert rival.json()["counts"]["open"] == 1

    severe = await client.get(QUEUE, params={"severity": "S1"}, headers=headers)
    assert [item["id"] for item in severe.json()["items"]] == [
        seeded_queue["overdue_s1"]
    ]

    resolved = await client.get(QUEUE, params={"status": "resolved"}, headers=headers)
    items = resolved.json()["items"]
    assert [item["id"] for item in items] == [seeded_queue["resolved_s4"]]
    assert items[0]["resolution_summary"] == "Corrected the template."
    assert items[0]["overdue"] is False

    everything = await client.get(QUEUE, params={"status": "all"}, headers=headers)
    assert everything.json()["total"] == 4
    assert everything.json()["items"][-1]["id"] == seeded_queue["resolved_s4"]

    limited = await client.get(QUEUE, params={"limit": 1}, headers=headers)
    assert [item["id"] for item in limited.json()["items"]] == [
        seeded_queue["overdue_s1"]
    ]
    assert limited.json()["total"] == 3


@pytest.mark.asyncio
async def test_a_request_leaves_the_active_queue_once_resolved(
    client: AsyncClient, test_tenant
):
    filed = await client.post(
        "/api/compliance/operating/support",
        json={
            "severity": "S2",
            "channel": "workspace",
            "subject": "Document upload fails",
            "safe_summary": "Uploads stop at 90 percent for every user.",
        },
    )
    assert filed.status_code == 200, filed.text
    request_id = filed.json()["id"]
    read = platform_headers(["platform:read"])

    queued = await client.get(QUEUE, headers=read)
    assert [item["id"] for item in queued.json()["items"]] == [request_id]
    assert queued.json()["items"][0]["requested_by_email"] == "attorney@testfirm.com"

    update_path = (
        f"/api/platform/operating-trust/tenants/{test_tenant.id}/support/{request_id}"
    )
    write = platform_headers(["platform:write"])
    for step in ("acknowledged", "resolved"):
        moved = await client.patch(
            update_path,
            headers=write,
            json={"status": step, "resolution_summary": "Storage quota raised."},
        )
        assert moved.status_code == 200, moved.text

    active = await client.get(QUEUE, headers=read)
    assert active.json()["items"] == []
    resolved = await client.get(QUEUE, params={"status": "resolved"}, headers=read)
    item = resolved.json()["items"][0]
    assert item["operator_actor_id"] == "test-operator"
    assert item["resolution_summary"] == "Storage quota raised."


SEVERE_REQUEST = {
    "severity": "S1",
    "channel": "workspace",
    "subject": "Nobody can sign in",
    "safe_summary": "Every user sees an error after entering their password.",
}


@pytest.mark.asyncio
async def test_filing_a_request_alerts_the_operator_inbox(
    client: AsyncClient, test_tenant, monkeypatch
):
    from app.services import support_alerts

    monkeypatch.setattr(
        support_alerts.get_settings(), "MARKETING_LEAD_EMAIL", "support@lawhand.example"
    )
    with patch(
        "app.services.email.email_service.send_email", new_callable=AsyncMock
    ) as send:
        filed = await client.post(
            "/api/compliance/operating/support", json=SEVERE_REQUEST
        )

    assert filed.status_code == 200, filed.text
    send.assert_awaited_once()
    recipients, subject, html_body, text_body = send.await_args.args
    assert recipients == ["support@lawhand.example"]
    assert subject == f"[S1] LawHand support request — {test_tenant.name}"
    assert "attorney@testfirm.com" in text_body
    assert filed.json()["id"] in text_body
    assert "Every user sees an error" in html_body


@pytest.mark.asyncio
async def test_an_alert_failure_never_fails_the_customers_request(
    client: AsyncClient, monkeypatch
):
    from app.services import support_alerts

    monkeypatch.setattr(
        support_alerts.get_settings(), "MARKETING_LEAD_EMAIL", "support@lawhand.example"
    )
    with patch(
        "app.services.email.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=RuntimeError("mail relay down"),
    ):
        filed = await client.post(
            "/api/compliance/operating/support", json=SEVERE_REQUEST
        )

    assert filed.status_code == 200, filed.text
    queued = await client.get(QUEUE, headers=platform_headers(["platform:read"]))
    assert [item["id"] for item in queued.json()["items"]] == [filed.json()["id"]]


@pytest.mark.asyncio
async def test_no_alert_is_attempted_without_an_operator_inbox(
    client: AsyncClient, monkeypatch
):
    from app.services import support_alerts

    monkeypatch.setattr(support_alerts.get_settings(), "MARKETING_LEAD_EMAIL", "")
    with patch(
        "app.services.email.email_service.send_email", new_callable=AsyncMock
    ) as send:
        filed = await client.post(
            "/api/compliance/operating/support", json=SEVERE_REQUEST
        )

    assert filed.status_code == 200, filed.text
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_requires_platform_read_and_a_known_tenant(
    client: AsyncClient, seeded_queue
):
    tenant_session = await client.get(QUEUE)
    assert tenant_session.status_code == 403

    wrong_scope = await client.get(
        QUEUE, headers=platform_headers(["platform:llm:read"])
    )
    assert wrong_scope.status_code == 403

    unknown = await client.get(
        QUEUE,
        params={"tenant_id": str(uuid.uuid4())},
        headers=platform_headers(["platform:read"]),
    )
    assert unknown.status_code == 404

    invalid = await client.get(
        QUEUE, params={"status": "closed"}, headers=platform_headers(["platform:read"])
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_queue_reads_each_tenant_under_the_runtime_rls_role(
    seeded_queue, test_tenant, rival_tenant
):
    url = os.getenv("RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RLS_TEST_DATABASE_URL is required for runtime-role integration")

    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path=QUEUE),
        headers=Headers(platform_headers(["platform:read"])),
        state=SimpleNamespace(),
        client=SimpleNamespace(host="127.0.0.1"),
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as runtime_db:
            body = await operating_trust.list_platform_support_requests(
                request, runtime_db, status="all"
            )
    finally:
        await engine.dispose()

    assert {item["tenant_id"] for item in body["items"]} == {
        str(test_tenant.id),
        str(rival_tenant.id),
    }
    assert body["total"] == 4
