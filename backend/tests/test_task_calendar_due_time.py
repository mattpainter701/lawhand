"""A task's saved due time reaches the lawyer's calendar (issue #484).

Pushing a task to Outlook ignored the saved due time and created an all-day
event, so a deadline set for a specific hour arrived with the hour missing.
Both providers forced ``isAllDay`` / a date-only ``start``, and
``push_task_to_calendars`` never passed ``due_time`` at all.

The other half of the issue — the synced copy rendering beside the LawHand
task — is covered by the marker the read path now surfaces (see
``test_graph_task_marker_*`` below) and by the frontend merge tests in
``CalendarTaskDeduplication.test.jsx``.
"""

import uuid
from datetime import date, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.services import calendar_sync, google_calendar, microsoft_calendar
from app.services.google_calendar import _google_schedule
from app.services.microsoft_calendar import (
    CLARITY_TASK_PROP_ID,
    TASK_EVENT_DURATION,
    _graph_schedule,
)
from app.services import task_notifications

CHICAGO = "America/Chicago"


# ── Microsoft: a timed deadline is a timed event ─────────────────────────────


def test_graph_event_is_timed_when_the_task_has_a_due_time():
    schedule = _graph_schedule("2026-09-18", "14:30:00", CHICAGO)

    assert schedule["isAllDay"] is False
    assert schedule["start"]["dateTime"] == "2026-09-18T14:30:00"
    assert schedule["start"]["timeZone"] == CHICAGO


def test_graph_timed_event_carries_no_offset_of_its_own():
    # Graph pairs a timezone-less dateTime with a separate timeZone. An offset
    # on the value as well lets the provider read the instant and the wall
    # clock differently.
    schedule = _graph_schedule("2026-09-18", "14:30:00", CHICAGO)

    assert "+" not in schedule["start"]["dateTime"]
    assert not schedule["start"]["dateTime"].endswith("Z")


def test_graph_timed_event_ends_after_it_starts():
    schedule = _graph_schedule("2026-09-18", "14:30:00", CHICAGO)

    assert schedule["end"]["dateTime"] == "2026-09-18T15:00:00"
    assert TASK_EVENT_DURATION.total_seconds() == 1800


def test_graph_event_stays_all_day_without_a_due_time():
    schedule = _graph_schedule("2026-09-18", None, CHICAGO)

    assert schedule["isAllDay"] is True
    # All-day Graph events need an exclusive end date.
    assert schedule["start"]["dateTime"].startswith("2026-09-18")
    assert schedule["end"]["dateTime"].startswith("2026-09-19")


def test_graph_timed_event_across_a_dst_boundary_keeps_the_wall_clock():
    # 1 Nov 2026 is the day after US DST ends. The lawyer set 9am; 9am is what
    # has to appear, and the provider resolves the offset from the zone.
    schedule = _graph_schedule("2026-11-01", "09:00:00", CHICAGO)

    assert schedule["start"]["dateTime"] == "2026-11-01T09:00:00"
    assert schedule["start"]["timeZone"] == CHICAGO
    # The instant that wall clock means is genuinely CST, not CDT.
    resolved = ZoneInfo(CHICAGO).utcoffset(
        __import__("datetime").datetime(2026, 11, 1, 9, 0)
    )
    assert resolved.total_seconds() == -6 * 3600


# ── Google: the same, in its own shape ───────────────────────────────────────


def test_google_event_is_timed_when_the_task_has_a_due_time():
    schedule = _google_schedule("2026-09-18", "14:30:00", CHICAGO)

    assert schedule["start"] == {
        "dateTime": "2026-09-18T14:30:00",
        "timeZone": CHICAGO,
    }
    assert schedule["end"]["dateTime"] == "2026-09-18T15:00:00"


def test_google_event_stays_a_date_without_a_due_time():
    schedule = _google_schedule("2026-09-18", None, CHICAGO)

    assert schedule == {
        "start": {"date": "2026-09-18"},
        "end": {"date": "2026-09-18"},
    }


def test_an_empty_timezone_falls_back_to_utc_rather_than_crashing():
    assert _google_schedule("2026-09-18", "09:00:00", "")["start"]["timeZone"] == "UTC"
    assert _graph_schedule("2026-09-18", "09:00:00", "")["start"]["timeZone"] == "UTC"


# ── The push actually carries it ─────────────────────────────────────────────


def _task(**overrides):
    return SimpleNamespace(
        **{
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "matter_id": uuid.uuid4(),
            "title": "File response brief",
            "task_type": "follow_up",
            "status": "pending",
            "due_date": date(2026, 9, 18),
            "due_time": time(14, 30),
            "description": "",
            "assigned_to_user_id": None,
            "created_by_user_id": None,
            **overrides,
        }
    )


def test_push_sends_the_due_time_and_timezone_to_both_providers(monkeypatch):
    calls = []

    async def _upsert(**kwargs):
        calls.append(kwargs)
        return {"id": "event"}

    monkeypatch.setattr(google_calendar, "upsert_task_event", _upsert)
    monkeypatch.setattr(microsoft_calendar, "upsert_task_event", _upsert)
    # Run the coroutines the push fires so their kwargs are recorded.
    monkeypatch.setattr(
        task_notifications,
        "_fire_and_log",
        lambda coro, **kw: __import__("asyncio").run(coro),
    )

    task_notifications.push_task_to_calendars(
        _task(), "tenant-1", timezone_name=CHICAGO
    )

    assert len(calls) == 2
    assert all(call["due_time"] == "14:30:00" for call in calls)
    assert all(call["timezone_name"] == CHICAGO for call in calls)
    assert all(call["due_date"] == "2026-09-18" for call in calls)


def test_push_sends_no_due_time_for_a_date_only_task(monkeypatch):
    calls = []

    async def _upsert(**kwargs):
        calls.append(kwargs)
        return {"id": "event"}

    monkeypatch.setattr(google_calendar, "upsert_task_event", _upsert)
    monkeypatch.setattr(microsoft_calendar, "upsert_task_event", _upsert)
    monkeypatch.setattr(
        task_notifications,
        "_fire_and_log",
        lambda coro, **kw: __import__("asyncio").run(coro),
    )

    task_notifications.push_task_to_calendars(
        _task(due_time=None), "tenant-1", timezone_name=CHICAGO
    )

    assert all(call["due_time"] is None for call in calls)


def test_push_still_does_nothing_without_a_due_date(monkeypatch):
    calls = []
    monkeypatch.setattr(
        task_notifications, "_fire_and_log", lambda coro, **kw: calls.append(coro)
    )

    task_notifications.push_task_to_calendars(_task(due_date=None), "tenant-1")

    assert calls == []


# ── The marker that lets the copy be de-duplicated ───────────────────────────


def test_graph_task_marker_is_read_back_from_an_event_we_pushed():
    event = {
        "id": "AAMkAGI2",
        "singleValueExtendedProperties": [
            {"id": CLARITY_TASK_PROP_ID, "value": "task-uuid"}
        ],
    }
    assert calendar_sync._graph_task_id(event) == "task-uuid"


def test_graph_task_marker_is_absent_on_an_ordinary_meeting():
    assert calendar_sync._graph_task_id({"id": "AAMkAGI2"}) is None
    assert calendar_sync._graph_task_id({"singleValueExtendedProperties": []}) is None


def test_graph_task_marker_ignores_an_unrelated_extended_property():
    event = {
        "singleValueExtendedProperties": [
            {"id": "String {0000} Name something_else", "value": "no"}
        ]
    }
    assert calendar_sync._graph_task_id(event) is None


def test_graph_task_marker_treats_an_empty_value_as_absent():
    event = {
        "singleValueExtendedProperties": [{"id": CLARITY_TASK_PROP_ID, "value": ""}]
    }
    assert calendar_sync._graph_task_id(event) is None


# ── The marker must never cost us the calendar itself ────────────────────────


@pytest.mark.asyncio
async def test_calendar_read_falls_back_when_graph_rejects_the_expansion(monkeypatch):
    """De-duplication is worth less than the calendar view.

    ``$expand`` on an extended property is the only part of this read we cannot
    exercise against a real tenant here, so a rejection must degrade to a plain
    read rather than fail the whole calendar.
    """
    requests = []

    class _Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {"value": []}

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            requests.append(params)
            if "$expand" in (params or {}):
                return _Response(400)
            return _Response(200, {"value": [{"id": "evt-1", "subject": "Client call"}]})

    async def _token(*args, **kwargs):
        return "token"

    monkeypatch.setattr(calendar_sync.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(calendar_sync, "get_fresh_token", _token)
    monkeypatch.setattr(calendar_sync, "get_fresh_user_token", _token)
    monkeypatch.setattr(calendar_sync, "set_tenant_context", _token)

    events = await calendar_sync.calendar_sync.ms_get_events(None, "tenant-1")

    assert len(requests) == 2
    assert "$expand" in requests[0]
    assert "$expand" not in requests[1]
    assert [e["subject"] for e in events] == ["Client call"]
    # Without the marker there is nothing to collapse against, and that is fine.
    assert events[0]["task_id"] is None


@pytest.mark.asyncio
async def test_calendar_read_still_fails_loudly_when_graph_is_really_broken(monkeypatch):
    class _Response:
        status_code = 503

        def json(self):
            return {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return _Response()

    async def _token(*args, **kwargs):
        return "token"

    monkeypatch.setattr(calendar_sync.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(calendar_sync, "get_fresh_token", _token)
    monkeypatch.setattr(calendar_sync, "get_fresh_user_token", _token)
    monkeypatch.setattr(calendar_sync, "set_tenant_context", _token)

    with pytest.raises(ValueError, match="Microsoft calendar read failed"):
        await calendar_sync.calendar_sync.ms_get_events(None, "tenant-1")
