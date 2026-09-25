"""Personal-matter paging: bounded pages, scoped totals and SQL filtering (S3.01/S3.02)."""

import uuid
from datetime import datetime, timezone

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


async def _add_named_matter(db_session, tenant_id, user_id, name, status="open"):
    matter = Matter(
        tenant_id=tenant_id,
        user_id=user_id,
        slug=f"paging-{uuid.uuid4().hex[:16]}",
        matter_name=name,
        status=status,
    )
    db_session.add(matter)
    await db_session.flush()
    db_session.add(
        MatterAssignment(
            tenant_id=tenant_id,
            matter_id=matter.id,
            user_id=user_id,
            role="associate",
        )
    )
    await db_session.flush()
    return matter


@pytest.mark.asyncio
async def test_my_matters_page_reports_total_and_paginates(
    client, db_session, test_tenant, test_user
):
    created = await _add_assigned_matters(db_session, test_tenant.id, test_user.id, 3)
    created_ids = {str(m.id) for m in created}

    first = await client.get("/api/matters/my/page", params={"page": 1, "page_size": 2})
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

    # Two pages cover the whole set exactly once: no skips, no repeats.
    seen = [i["id"] for i in first.json()["items"]] + [
        i["id"] for i in second.json()["items"]
    ]
    assert len(seen) == len(set(seen)) == 3
    assert set(seen) == created_ids


@pytest.mark.asyncio
async def test_my_matters_page_reaches_past_the_legacy_cap(
    client, db_session, test_tenant, test_user
):
    created = await _add_assigned_matters(db_session, test_tenant.id, test_user.id, 105)
    created_ids = {str(m.id) for m in created}

    # The legacy capped endpoint is retired; the page reaches past #100.
    retired = await client.get("/api/matters/my")
    assert retired.status_code == 404

    seen = []
    for page in (1, 2, 3):
        response = await client.get(
            "/api/matters/my/page", params={"page": page, "page_size": 50}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 105
        seen.extend(i["id"] for i in body["items"])

    # Every matter past the old #100 cap is reachable, exactly once.
    assert len(seen) == 105
    assert len(set(seen)) == 105
    assert set(seen) == created_ids


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
    other_user_matters = await _add_assigned_matters(
        db_session, test_tenant.id, other_user.id, 2
    )

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
    other_tenant_matters = await _add_assigned_matters(
        db_session, other_tenant.id, test_user.id, 2
    )

    mine = await _add_assigned_matters(db_session, test_tenant.id, test_user.id, 1)

    response = await client.get(
        "/api/matters/my/page", params={"page": 1, "page_size": 50}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1

    returned = {i["id"] for i in body["items"]}
    assert returned == {str(mine[0].id)}
    forbidden = {str(m.id) for m in other_user_matters + other_tenant_matters}
    assert returned.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_my_matters_page_filters_by_query_and_status(
    client, db_session, test_tenant, test_user
):
    await _add_named_matter(db_session, test_tenant.id, test_user.id, "Alpha case")
    await _add_named_matter(db_session, test_tenant.id, test_user.id, "Beta case")
    gamma = await _add_named_matter(
        db_session, test_tenant.id, test_user.id, "Gamma case", status="pending"
    )

    by_query = await client.get(
        "/api/matters/my/page", params={"page": 1, "page_size": 50, "q": "Alpha"}
    )
    assert by_query.status_code == 200, by_query.text
    query_body = by_query.json()
    assert query_body["total"] == 1
    assert query_body["items"][0]["matter_name"] == "Alpha case"

    by_status = await client.get(
        "/api/matters/my/page", params={"page": 1, "page_size": 50, "status": "pending"}
    )
    assert by_status.status_code == 200, by_status.text
    status_body = by_status.json()
    assert status_body["total"] == 1
    assert status_body["items"][0]["id"] == str(gamma.id)


@pytest.mark.asyncio
async def test_all_matters_pages_do_not_overlap_when_sort_values_tie(
    client, db_session, test_tenant, test_user
):
    """Every row shares ``updated_at``, so only the ``id`` tie-break orders them."""
    tied = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    created = await _add_assigned_matters(db_session, test_tenant.id, test_user.id, 7)
    for matter in created:
        matter.matter_name = f"Tied Sort {matter.matter_name}"
        matter.updated_at = tied
    await db_session.flush()
    created_ids = {str(m.id) for m in created}

    seen: list[str] = []
    for page in (1, 2, 3):
        resp = await client.get(
            "/api/matters",
            params={"search": "Tied Sort", "page": page, "page_size": 3},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 7
        seen.extend(item["id"] for item in body["items"])

    assert len(seen) == 7
    assert set(seen) == created_ids
    assert seen == sorted(seen, key=uuid.UUID)


@pytest.mark.asyncio
async def test_matter_lists_sort_by_an_allowed_column(
    client, db_session, test_tenant, test_user
):
    for name in ("Sortable Bravo", "Sortable Alpha", "Sortable Charlie"):
        await _add_named_matter(db_session, test_tenant.id, test_user.id, name)

    everyone = await client.get(
        "/api/matters",
        params={"search": "Sortable", "sort_by": "matter_name", "sort_dir": "asc"},
    )
    assert everyone.status_code == 200, everyone.text
    assert [m["matter_name"] for m in everyone.json()["items"]] == [
        "Sortable Alpha",
        "Sortable Bravo",
        "Sortable Charlie",
    ]

    mine = await client.get(
        "/api/matters/my/page",
        params={"q": "Sortable", "sort_by": "matter_name", "sort_dir": "desc"},
    )
    assert mine.status_code == 200, mine.text
    assert [m["matter_name"] for m in mine.json()["items"]] == [
        "Sortable Charlie",
        "Sortable Bravo",
        "Sortable Alpha",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/matters", "/api/matters/my/page"])
@pytest.mark.parametrize(
    "params",
    [
        {"sort_by": "assignments"},
        {"sort_by": "memory_content"},
        {"sort_by": "no_such_column"},
        {"sort_by": "updated_at", "sort_dir": "sideways"},
    ],
)
async def test_matter_lists_refuse_unknown_sort(client, path, params):
    resp = await client.get(path, params=params)
    assert resp.status_code == 422, resp.text
