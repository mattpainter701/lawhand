"""Push-sync tasks and matter key-dates to Google Calendar."""

from datetime import date, datetime, timedelta
import logging

import httpx

from app.config import get_settings
from app.database import async_session_maker
from app.services.token_vault import get_fresh_token, get_fresh_user_token

settings = get_settings()
logger = logging.getLogger(__name__)

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


async def _get_token(
    tenant_id: str,
    user_id: str | None = None,
    *,
    exact_user: bool = False,
) -> str | None:
    try:
        async with async_session_maker() as db:
            if user_id:
                token = await get_fresh_user_token(db, tenant_id, user_id, "google")
                if token or exact_user:
                    return token
            return await get_fresh_token(db, tenant_id, "google")
    except Exception:
        logger.warning(
            "Failed to get Google token for tenant %s user %s",
            tenant_id,
            user_id,
            exc_info=True,
        )
        return None


#: How long a deadline occupies on a calendar. A task is a point in time, not
#: a meeting, but a zero-length event is invisible in most calendar views.
TASK_EVENT_DURATION = timedelta(minutes=30)


def _google_schedule(due_date: str, due_time: str | None, timezone_name: str) -> dict:
    """The start/end pair Google needs, timed or all-day.

    Google pairs a timezone-less ``dateTime`` with a separate IANA ``timeZone``,
    so the wall-clock value must not carry an offset of its own.

    A date-only task is an all-day event. Google treats ``end.date`` as
    exclusive, so a one-day event ends on the following day; an end equal to
    the start is an empty range that Google rejects (``timeRangeEmpty``).
    """
    if not due_time:
        start_day = date.fromisoformat(due_date)
        return {
            "start": {"date": start_day.isoformat()},
            "end": {"date": (start_day + timedelta(days=1)).isoformat()},
        }

    start = datetime.fromisoformat(f"{due_date}T{due_time}")
    end = start + TASK_EVENT_DURATION
    zone = timezone_name or "UTC"
    return {
        "start": {"dateTime": start.isoformat(), "timeZone": zone},
        "end": {"dateTime": end.isoformat(), "timeZone": zone},
    }


def _google_patch_schedule(schedule: dict) -> dict:
    """``schedule`` made safe for a PATCH of an existing event.

    Google's PATCH merges nested objects, so switching an event between timed
    and all-day has to null out the form it no longer uses. Otherwise a task
    whose due time was cleared would keep its stale ``dateTime`` next to the
    new ``date``, and Google would reject the mixed pair.
    """
    patched = {}
    for edge in ("start", "end"):
        value = dict(schedule[edge])
        if "date" in value:
            value.update(dateTime=None, timeZone=None)
        else:
            value["date"] = None
        patched[edge] = value
    return patched


async def upsert_task_event(
    tenant_id: str,
    task_id: str,
    title: str,
    due_date: str,
    *,
    due_time: str | None = None,
    timezone_name: str = "UTC",
    description: str = "",
    matter_name: str = "",
    is_completed: bool = False,
    user_id: str | None = None,
) -> dict | None:
    """Create or update a Google Calendar event for a task.

    Uses an extended-property marker ``clarity_task_id`` to find existing events
    so we don't create duplicates on re-sync.

    A task with a saved ``due_time`` becomes a timed event in
    ``timezone_name``; without one it stays an all-day date, which is what a
    date-only deadline is.
    """
    if not title:
        return None

    token = await _get_token(tenant_id, user_id)
    if not token:
        logger.warning(
            "No Google token for tenant %s — skipping calendar push", tenant_id
        )
        return None

    headers = {"Authorization": f"Bearer {token}"}
    event_id = None

    # Search for existing event via extended property
    async with httpx.AsyncClient() as client:
        search_resp = await client.get(
            f"{CALENDAR_BASE}/calendars/primary/events",
            headers=headers,
            params={
                "privateExtendedProperty": f"clarity_task_id={task_id}",
                "showDeleted": "false",
            },
        )
        if search_resp.status_code == 200:
            items = search_resp.json().get("items", [])
            if items:
                event_id = items[0]["id"]

    # Build event body
    if is_completed:
        summary = f"[DONE] {title}"
    elif matter_name:
        summary = f"{title} — {matter_name}"
    else:
        summary = title

    schedule = _google_schedule(due_date, due_time, timezone_name)
    event_body = {
        "summary": summary,
        "description": description or title,
        **schedule,
        "extendedProperties": {
            "private": {
                "clarity_task_id": task_id,
            }
        },
    }

    if is_completed:
        event_body["colorId"] = "10"  # green in Google Calendar

    async with httpx.AsyncClient() as client:
        if event_id:
            resp = await client.patch(
                f"{CALENDAR_BASE}/calendars/primary/events/{event_id}",
                headers=headers,
                json={**event_body, **_google_patch_schedule(schedule)},
            )
        else:
            resp = await client.post(
                f"{CALENDAR_BASE}/calendars/primary/events",
                headers=headers,
                json=event_body,
            )

        if resp.status_code in (200, 201):
            result = resp.json()
            logger.info(
                "Google Calendar %s event %s for task %s",
                "updated" if event_id else "created",
                result.get("id", "?"),
                task_id,
            )
            return result
        else:
            logger.warning(
                "Google Calendar push failed for task %s: %s %s",
                task_id,
                resp.status_code,
                resp.text[:200],
            )
            return None


async def delete_task_event(
    tenant_id: str,
    task_id: str,
    user_id: str | None = None,
    *,
    require_exact_user: bool = False,
) -> bool:
    """Remove the Google Calendar event for a cancelled/deleted task."""
    if require_exact_user and not user_id:
        raise RuntimeError("Google Calendar exact-user principal is required")
    token = await _get_token(tenant_id, user_id, exact_user=require_exact_user)
    if not token:
        if require_exact_user:
            raise RuntimeError("Google Calendar exact-user token is unavailable")
        return False

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        search_resp = await client.get(
            f"{CALENDAR_BASE}/calendars/primary/events",
            headers=headers,
            params={
                "privateExtendedProperty": f"clarity_task_id={task_id}",
                "showDeleted": "false",
            },
        )
        if search_resp.status_code != 200:
            raise RuntimeError("Google Calendar task-event lookup failed")
        items = search_resp.json().get("items", [])
        for item in items:
            delete_resp = await client.delete(
                f"{CALENDAR_BASE}/calendars/primary/events/{item['id']}",
                headers=headers,
            )
            if delete_resp.status_code not in (200, 204, 404):
                raise RuntimeError("Google Calendar task-event deletion failed")
            logger.info(
                "Deleted Google Calendar event %s for task %s",
                item["id"],
                task_id,
            )
        # A successful exact-principal lookup with no matching event is verified
        # absence, not a cleanup failure.
        return True
