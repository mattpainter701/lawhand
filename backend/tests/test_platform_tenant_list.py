"""Operator tenant list: server-side search and lifecycle views."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.datastructures import Headers

from app.models.tenant import Tenant, TenantSettings
from app.routers import platform
from app.services.trials import SIGNUP_APPROVED, SIGNUP_PENDING, SIGNUP_STATUS_KEY
from tests.platform_auth_helpers import platform_headers

TENANTS = "/api/platform/tenants"


def _headers():
    return platform_headers(["platform:read"])


@pytest_asyncio.fixture
async def lifecycle(db_session):
    """One firm per lifecycle view, plus a paid firm with a contract end."""

    now = datetime.now(timezone.utc)
    specs = {
        "trial_soon": dict(expires_at=now + timedelta(days=5), trial=True),
        "trial_later": dict(expires_at=now + timedelta(days=60), trial=True),
        "contract_end": dict(expires_at=now + timedelta(days=10), trial=False),
        "lapsed": dict(expires_at=now - timedelta(days=2), trial=True),
        "pending": dict(is_active=False, signup=SIGNUP_PENDING),
        "deactivated": dict(is_active=False, signup=SIGNUP_APPROVED),
        "demo": dict(billing_tier="demo", expires_at=now + timedelta(hours=2)),
    }
    ids = {}
    for index, (name, spec) in enumerate(specs.items()):
        tenant = Tenant(
            id=uuid.uuid4(),
            name=f"{name.replace('_', ' ').title()} Law",
            domain=f"{name}.lifecycle.example",
            billing_tier=spec.get("billing_tier", "payg"),
            is_active=spec.get("is_active", True),
            expires_at=spec.get("expires_at"),
            created_at=now - timedelta(days=30 - index),
        )
        db_session.add(tenant)
        await db_session.flush()
        config = {}
        if spec.get("trial"):
            config["trial"] = True
        if spec.get("signup"):
            config[SIGNUP_STATUS_KEY] = spec["signup"]
        if config:
            db_session.add(TenantSettings(tenant_id=tenant.id, custom_config=config))
        ids[name] = str(tenant.id)
    await db_session.commit()
    return ids


def _ids(response) -> list[str]:
    return [item["id"] for item in response.json()["tenants"]]


@pytest.mark.asyncio
async def test_every_view_is_counted_for_the_console_queues(
    client: AsyncClient, lifecycle, test_tenant
):
    response = await client.get(TENANTS, headers=_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    # test_tenant (from the client fixture) is an active paid firm.
    assert body["counts"] == {
        "all": 8,
        "platform": 7,
        "pending": 1,
        "active": 4,
        "trial": 2,
        "expiring": 2,
        "expired": 1,
        "inactive": 1,
        "demo": 1,
    }
    assert body["status"] == "all"
    assert body["total"] == 8


@pytest.mark.asyncio
async def test_each_view_returns_only_its_firms_in_working_order(
    client: AsyncClient, lifecycle, test_tenant
):
    async def view(status):
        response = await client.get(
            TENANTS, params={"status": status}, headers=_headers()
        )
        assert response.status_code == 200, response.text
        return response

    pending = await view("pending")
    assert _ids(pending) == [lifecycle["pending"]]
    assert pending.json()["tenants"][0]["signup_status"] == SIGNUP_PENDING

    assert _ids(await view("inactive")) == [lifecycle["deactivated"]]
    # Soonest first: that is the order to reach out in.
    assert _ids(await view("expiring")) == [
        lifecycle["trial_soon"],
        lifecycle["contract_end"],
    ]
    # A paid firm with a contract end is not a trial.
    assert set(_ids(await view("trial"))) == {
        lifecycle["trial_soon"],
        lifecycle["trial_later"],
    }
    assert _ids(await view("expired")) == [lifecycle["lapsed"]]
    assert _ids(await view("demo")) == [lifecycle["demo"]]
    assert lifecycle["demo"] not in _ids(await view("platform"))
    assert set(_ids(await view("active"))) == {
        str(test_tenant.id),
        lifecycle["trial_soon"],
        lifecycle["trial_later"],
        lifecycle["contract_end"],
    }


@pytest.mark.asyncio
async def test_search_matches_name_domain_and_a_pasted_tenant_id(
    client: AsyncClient, lifecycle
):
    by_name = await client.get(TENANTS, params={"q": "LAPSED"}, headers=_headers())
    assert _ids(by_name) == [lifecycle["lapsed"]]
    assert by_name.json()["counts"]["all"] == 1

    by_domain = await client.get(
        TENANTS, params={"q": "contract_end.lifecycle"}, headers=_headers()
    )
    assert _ids(by_domain) == [lifecycle["contract_end"]]

    by_id = await client.get(
        TENANTS, params={"q": lifecycle["pending"]}, headers=_headers()
    )
    assert _ids(by_id) == [lifecycle["pending"]]

    # SQL wildcards are matched literally rather than widening the search.
    wildcard = await client.get(TENANTS, params={"q": "%"}, headers=_headers())
    assert _ids(wildcard) == []

    combined = await client.get(
        TENANTS, params={"q": "trial", "status": "expiring"}, headers=_headers()
    )
    assert _ids(combined) == [lifecycle["trial_soon"]]


@pytest.mark.asyncio
async def test_views_paginate_after_filtering(client: AsyncClient, lifecycle):
    first = await client.get(
        TENANTS, params={"status": "expiring", "limit": 1}, headers=_headers()
    )
    second = await client.get(
        TENANTS,
        params={"status": "expiring", "limit": 1, "page": 2},
        headers=_headers(),
    )
    assert _ids(first) == [lifecycle["trial_soon"]]
    assert _ids(second) == [lifecycle["contract_end"]]
    assert first.json()["total"] == second.json()["total"] == 2


@pytest.mark.asyncio
async def test_unknown_view_is_rejected(client: AsyncClient):
    response = await client.get(TENANTS, params={"status": "vip"}, headers=_headers())
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pending_view_reads_settings_under_the_runtime_rls_role(lifecycle):
    url = os.getenv("RLS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RLS_TEST_DATABASE_URL is required for runtime-role integration")

    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path=TENANTS),
        headers=Headers(_headers()),
        state=SimpleNamespace(),
        client=SimpleNamespace(host="127.0.0.1"),
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as runtime_db:
            body = await platform.list_tenants(
                request, runtime_db, page=1, limit=50, status="pending"
            )
    finally:
        await engine.dispose()

    assert [tenant.id for tenant in body["tenants"]] == [lifecycle["pending"]]
    assert body["counts"]["trial"] == 2


@pytest.mark.asyncio
async def test_usage_ranks_the_busiest_firms_across_every_tenant(
    client: AsyncClient, db_session, lifecycle, test_tenant, test_user
):
    from decimal import Decimal

    from app.models.conversation import UsageRecord

    busy = [
        (lifecycle["trial_later"], 3),
        (str(test_tenant.id), 1),
        (lifecycle["lapsed"], 2),
    ]
    for tenant_id, count in busy:
        for _ in range(count):
            db_session.add(
                UsageRecord(
                    tenant_id=uuid.UUID(tenant_id),
                    user_id=test_user.id,
                    tokens_in=10,
                    tokens_out=5,
                    cost_usd=Decimal("0.5"),
                )
            )
    await db_session.commit()

    response = await client.get("/api/platform/usage", headers=_headers())

    assert response.status_code == 200, response.text
    top = response.json()["top_tenants"]
    assert [item["id"] for item in top] == [
        lifecycle["trial_later"],
        lifecycle["lapsed"],
        str(test_tenant.id),
    ]
    assert top[0]["requests_30d"] == 3
    assert top[0]["cost_usd_30d"] == pytest.approx(1.5)
    assert top[0]["name"] == "Trial Later Law"
