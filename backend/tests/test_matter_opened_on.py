"""The matter open date and the engagement filter on the matter API."""

import uuid
from datetime import date, timedelta

import pytest

from app.models.plugin import Matter, MatterEvent
from app.services.matter_engagement import apply_engagement


@pytest.mark.asyncio
async def test_open_date_defaults_to_today_and_drives_retention(client, db_session):
    resp = await client.post("/api/matters", json={"matter_name": "Fresh matter"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["opened_on"] == date.today().isoformat()
    assert data["engagement"] is None
    assert data["retention_until"] == (
        date.today() + timedelta(days=365 * 7)
    ).isoformat()


@pytest.mark.asyncio
async def test_backdated_open_date_is_kept_listed_and_evented(client, db_session):
    resp = await client.post(
        "/api/matters",
        json={"matter_name": "Transferred matter", "opened_on": "2025-03-01"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["opened_on"] == "2025-03-01"
    assert data["retention_until"] == "2032-02-28"

    event = (
        await db_session.execute(
            MatterEvent.__table__.select().where(
                MatterEvent.__table__.c.matter_id == uuid.UUID(data["id"])
            )
        )
    ).one()
    assert "Opened on 2025-03-01" in event.content

    listed = await client.get("/api/matters", params={"sort_by": "opened_on"})
    assert listed.status_code == 200
    items = {item["id"]: item for item in listed.json()["items"]}
    assert items[data["id"]]["opened_on"] == "2025-03-01"
    assert items[data["id"]]["engagement_status"] is None

    detail = await client.get(f"/api/matters/{data['id']}")
    assert detail.json()["opened_on"] == "2025-03-01"

    mine = await client.get("/api/matters/my")
    assert mine.status_code == 200
    assert {m["opened_on"] for m in mine.json()} == {"2025-03-01"}


@pytest.mark.asyncio
async def test_open_date_can_be_corrected_but_not_set_in_the_future(client):
    created = await client.post("/api/matters", json={"matter_name": "Typo matter"})
    matter_id = created.json()["id"]

    patched = await client.patch(
        f"/api/matters/{matter_id}", json={"opened_on": "2024-12-31"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["opened_on"] == "2024-12-31"

    future = (date.today() + timedelta(days=30)).isoformat()
    assert (
        await client.post(
            "/api/matters", json={"matter_name": "Future", "opened_on": future}
        )
    ).status_code == 422
    assert (
        await client.patch(f"/api/matters/{matter_id}", json={"opened_on": future})
    ).status_code == 422
    assert (
        await client.patch(
            f"/api/matters/{matter_id}", json={"opened_on": "1899-12-31"}
        )
    ).status_code == 422
    # Engagement columns are not writable through the generic update.
    patched = await client.patch(
        f"/api/matters/{matter_id}", json={"engagement_status": "no_agreement"}
    )
    assert patched.status_code == 200
    assert patched.json()["engagement"] is None


@pytest.mark.asyncio
async def test_engagement_filter_finds_unusual_engagements(
    client, db_session, test_user
):
    ids = {}
    for name in ("plain", "no-agreement", "no-copy"):
        resp = await client.post("/api/matters", json={"matter_name": name})
        ids[name] = uuid.UUID(resp.json()["id"])
    for name, status in (("no-agreement", "no_agreement"), ("no-copy", "signed_no_copy")):
        matter = await db_session.get(Matter, ids[name])
        apply_engagement(
            matter,
            status=status,
            signed_on=None,
            note="legacy",
            document_id=None,
            user_id=test_user.id,
        )
    await db_session.commit()

    async def listed(**params):
        resp = await client.get("/api/matters", params=params)
        assert resp.status_code == 200, resp.text
        return {item["matter_name"]: item["engagement_status"] for item in resp.json()["items"]}

    assert await listed(engagement_status="no_agreement") == {"no-agreement": "no_agreement"}
    assert await listed(engagement_status="any") == {
        "no-agreement": "no_agreement",
        "no-copy": "signed_no_copy",
    }
    assert await listed(engagement_status="none") == {"plain": None}
    assert set(await listed()) == {"plain", "no-agreement", "no-copy"}
    assert (
        await client.get("/api/matters", params={"engagement_status": "bogus"})
    ).status_code == 422

    detail = await client.get(f"/api/matters/{ids['no-copy']}")
    assert detail.json()["engagement"]["status"] == "signed_no_copy"
    assert detail.json()["engagement"]["note"] == "legacy"
