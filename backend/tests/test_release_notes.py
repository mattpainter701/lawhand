from datetime import date, timedelta

import pytest

from app.release_notes import RECENT_RELEASE_DAYS, build_release_catalog
from app.main import app_version


LATEST_RELEASE_ID = "2026.09.26.01"
LATEST_RELEASE_DATE = date(2026, 9, 26)


def test_release_catalog_returns_latest_release_and_history():
    catalog = build_release_catalog(today=LATEST_RELEASE_DATE)

    latest = catalog["latest_release"]
    assert latest["id"] == LATEST_RELEASE_ID
    assert latest["version"] == LATEST_RELEASE_ID
    assert latest["is_recent"] is True
    assert len(latest["highlights"]) == 4
    assert latest["title"] == "Smoother PDF review and safer packet retries"
    assert latest["highlights"][0]["title"] == "Fit the whole PDF page"
    assert latest["highlights"][2]["title"] == "Global imports are clearer"
    assert latest["highlights"][3]["title"] == "Packet retries avoid stale writes"
    history_ids = [release["id"] for release in catalog["release_notes"]]
    assert history_ids[:5] == [
        LATEST_RELEASE_ID,
        "2026.09.25.09",
        "2026.09.25.08",
        "2026.09.25.07",
        "2026.09.25.06",
    ]
    assert all(f"2026.09.07.{n}" in history_ids for n in (7, 8, 9))
    assert "2026.09.07.6" in history_ids
    assert "2026.09.07.5" in history_ids
    assert catalog["release_notes"][0] == latest


def test_release_catalog_stops_marking_old_releases_recent():
    catalog = build_release_catalog(
        today=LATEST_RELEASE_DATE + timedelta(days=RECENT_RELEASE_DAYS + 1)
    )

    assert catalog["latest_release"]["is_recent"] is False


@pytest.mark.asyncio
async def test_version_endpoint_payload_includes_release_notes():
    payload = await app_version()

    assert payload["status"] == "ok"
    assert payload["latest_release"] == payload["release_notes"][0]
    assert payload["latest_release"]["highlights"]
