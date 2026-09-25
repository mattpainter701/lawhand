"""Every staff route under ``/api/matters`` refuses a client-portal login.

A portal client is a real ``User`` (``role="client"``) whose token
``get_current_user`` accepts. Most matter routers scope by tenant only, so a
replayed portal token could otherwise read or change any matter in the firm.
Clients use ``/api/portal/...``. This walks the live route table, so a route
added later without a staff guard fails here.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException
from jose import jwt as jose_jwt
from sqlalchemy import func, select

from app.config import get_settings
from app.main import app
from app.models.plugin import Matter
from app.models.user import User
from app.services.access_control import require_firm_staff_user

API = "/api/matters"


def _matter_routes() -> list[tuple[str, str]]:
    """(method, path) for every registered route under /api/matters."""
    found: set[tuple[str, str]] = set()

    def walk(routes, prefix=""):
        for route in routes:
            if type(route).__name__ == "_IncludedRouter":
                walk(
                    route.original_router.routes, prefix + route.include_context.prefix
                )
            elif hasattr(route, "endpoint") and hasattr(route, "methods"):
                path = prefix + route.path
                if path == API or path.startswith(API + "/"):
                    for method in route.methods - {"HEAD", "OPTIONS"}:
                        found.add((method, path))

    walk(app.routes)
    return sorted(found)


MATTER_ROUTES = _matter_routes()


@pytest_asyncio.fixture
async def matter(db_session, test_tenant, test_user):
    row = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"staff-only-{uuid.uuid4().hex[:8]}",
        matter_name="Atlas acquisition",
        matter_number="2026-0042",
        matter_type="corporate",
        status="open",
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


@pytest_asyncio.fixture
async def client_headers(db_session, test_tenant) -> dict[str, str]:
    portal_user = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="client@example.test",
        full_name="Portal Client",
        role="client",
        is_active=True,
    )
    db_session.add(portal_user)
    await db_session.commit()
    settings = get_settings()
    token = jose_jwt.encode(
        {
            "sub": str(portal_user.id),
            "tenant_id": str(test_tenant.id),
            "role": "client",
            "email": "client@example.test",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


def _fill(path: str, matter_id: uuid.UUID) -> str:
    path = path.replace("{matter_id}", str(matter_id))
    path = path.replace("{matter_number}", "2026-0042")
    path = path.replace("{provider}", "onedrive")
    path = path.replace("{kind}", "docx")
    return re.sub(r"\{[^}]+\}", lambda _m: str(uuid.uuid4()), path)


def test_route_table_covers_the_matter_routers():
    # Guard the walker itself: an empty or truncated list would pass vacuously.
    assert len(MATTER_ROUTES) > 100
    paths = {path for _method, path in MATTER_ROUTES}
    for expected in (
        API,
        f"{API}/{{matter_id}}",
        f"{API}/{{matter_id}}/signatures",
        f"{API}/{{matter_id}}/parties",
        f"{API}/{{matter_id}}/correspondence",
        f"{API}/{{matter_id}}/brief-checks",
        f"{API}/{{matter_id}}/research-workspaces",
        f"{API}/{{matter_id}}/portal/invites",
    ):
        assert expected in paths, expected


@pytest.mark.parametrize(("method", "path"), MATTER_ROUTES)
async def test_client_portal_login_is_refused(
    client, matter, client_headers, method, path
):
    resp = await client.request(method, _fill(path, matter), headers=client_headers)
    assert (
        resp.status_code == 403
    ), f"{method} {path}: {resp.status_code} {resp.text[:300]}"


async def test_client_writes_to_a_matter_change_nothing(
    client, db_session, matter, client_headers
):
    patched = await client.patch(
        f"{API}/{matter}",
        json={"matter_name": "Renamed by client"},
        headers=client_headers,
    )
    assert patched.status_code == 403
    assert patched.json()["detail"]["code"] == "staff_only"
    closed = await client.delete(f"{API}/{matter}", headers=client_headers)
    assert closed.status_code == 403

    db_session.expire_all()
    row = await db_session.get(Matter, matter)
    assert row.matter_name == "Atlas acquisition"
    assert row.status == "open"
    count = await db_session.scalar(select(func.count()).select_from(Matter))
    assert count == 1


async def test_firm_staff_still_use_the_matters_api(client, matter):
    for path in (
        API,
        f"{API}/{matter}",
        f"{API}/{matter}/parties",
        f"{API}/{matter}/signatures",
        f"{API}/{matter}/correspondence/rules",
        f"{API}/{matter}/documents",
    ):
        resp = await client.get(path)
        assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:300]}"

    renamed = await client.patch(
        f"{API}/{matter}", json={"matter_name": "Atlas merger"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["matter_name"] == "Atlas merger"


async def test_require_firm_staff_user_returns_staff_and_refuses_clients():
    staff = type("U", (), {"role": "admin"})()
    assert await require_firm_staff_user(staff) is staff
    with pytest.raises(HTTPException) as exc:
        await require_firm_staff_user(type("U", (), {"role": "client"})())
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "staff_only"
