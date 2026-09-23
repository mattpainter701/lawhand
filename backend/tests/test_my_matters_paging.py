"""Personal-matter paging: bounded pages and scoped totals (S3.01/S3.02)."""

import uuid

import pytest

from app.models.matter_assignment import MatterAssignment
from app.models.plugin import Matter
from app.models.tenant import Tenant
from app.models.user import User


async def _add_assigned_matters(db_session, tenant_id, user_id, count, start=0):
    """Create ``count`` open matters assigned to ``user_id`` in one tenant."""
    matters = []
    for offset in range(count):
        matter = Matter(
            tenant_id=tenant_id,
            user_id=user_id,
            slug=f"paging-{uuid.uuid4().hex[:16]}",
            matter_name=f"Paging Matter {start + offset:04d}",
        )
        db_session.add(matter)
        matters.append(matter)
    await db_session.flush()
    for matter in matters:
        db_session.add(
            MatterAssignment(
                tenant_id=tenant_id,
                matter_id=matter.id,
                user_id=user_id,
                role="associate",
            )
        )
    await db_session.flush()
    return matters


@pytest.mark.asyncio
async def test_my_matters_page_reports_total_and_paginates(
    client, db_session, test_tenant, test_user
):
    await _add_assigned_matters(db_session, test_tenant.id, test_user.id, 3)

    first = await client.get(
        "/api/matters/my/page", params={"page": 1, "page_size": 2}
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2

    second = await client.get(
        "/api/matters/my/page", params={"page": 2, "page_size": 2}
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 1


@pytest.mark.asyncio
async def test_my_matters_page_reaches_past_the_legacy_cap(
    client, db_session, test_tenant, test_user
):
    await _add_assigned_matters(db_session, test_tenant.id, test_user.id, 105)

    # The legacy capped endpoint is retired; the page reaches past #100.
    retired = await client.get("/api/matters/my")
    assert retired.status_code == 404

    last = await client.get(
        "/api/matters/my/page", params={"page": 3, "page_size": 50}
    )
    assert last.status_code == 200, last.text
    body = last.json()
    assert body["total"] == 105
    assert len(body["items"]) == 5


@pytest.mark.asyncio
async def test_my_matters_page_is_scoped_to_the_user_and_tenant(
    client, db_session, test_tenant, test_user
):
    other_user = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="other@testfirm.com",
        full_name="Other Attorney",
        role="associate",
        oauth_provider="google",
        oauth_subject="google-sub-other",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()
    await _add_assigned_matters(db_session, test_tenant.id, other_user.id, 2)

    other_tenant = Tenant(
        id=uuid.uuid4(),
        name="Other Firm",
        domain="otherfirm.com",
        billing_tier="payg",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()
    # Same user, different tenant: must not leak into this tenant's total.
    await _add_assigned_matters(db_session, other_tenant.id, test_user.id, 2)

    await _add_assigned_matters(db_session, test_tenant.id, test_user.id, 1)

    response = await client.get(
        "/api/matters/my/page", params={"page": 1, "page_size": 50}
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
