from datetime import date, timedelta

import pytest

from app.release_notes import RECENT_RELEASE_DAYS, build_release_catalog
from app.main import app_version


LATEST_RELEASE_ID = "2026.09.24.01"
LATEST_RELEASE_DATE = date(2026, 9, 24)


def test_release_catalog_returns_latest_release_and_history():
    catalog = build_release_catalog(today=LATEST_RELEASE_DATE)

    latest = catalog["latest_release"]
    assert latest["id"] == LATEST_RELEASE_ID
    assert latest["version"] == LATEST_RELEASE_ID
    assert latest["is_recent"] is True
    assert len(latest["highlights"]) == 4
    assert latest["title"] == "Clearer Microsoft 365 and Google connections"
    assert latest["highlights"][0]["title"] == "Connect with a clear picture"
    assert latest["highlights"][1]["title"] == "See and fix missing permissions"
    assert latest["highlights"][2]["title"] == "Your own connected accounts"
    assert latest["highlights"][3]["title"] == "Microsoft account type and Teams"
    history_ids = [release["id"] for release in catalog["release_notes"]]
    assert history_ids[:4] == [LATEST_RELEASE_ID, "2026.09.23.02", "2026.09.23.01", "2026.09.22.08"]
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
