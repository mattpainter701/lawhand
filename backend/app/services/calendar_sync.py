import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import set_tenant_context
from app.services.microsoft_calendar import CLARITY_TASK_PROP_ID
from app.services.token_vault import get_fresh_token, get_fresh_user_token

settings = get_settings()
logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GOOGLE_CAL_BASE = "https://www.googleapis.com/calendar/v3"


def _provider_local_datetime(value: datetime, timezone_name: str) -> str:
    """Return the wall-clock value required by calendar-provider APIs.

    Microsoft Graph and Google Calendar pair a timezone-less ``dateTime`` with a
    separate IANA ``timeZone`` value. Passing an ISO string with a UTC offset
    as well as a timezone can make the provider interpret the instant and the
    wall-clock value differently. Scheduled events are stored as instants, so
    convert them back to the requested local wall-clock time at this boundary.
    """
    if value.tzinfo is None:
        # Preserve the legacy API contract for callers that supplied a local
        # wall-clock value without an offset.
        return value.isoformat()
    return (
        value.astimezone(ZoneInfo(timezone_name or "UTC"))
        .replace(tzinfo=None)
        .isoformat()
    )


def _graph_task_id(event: dict) -> str | None:
    """The LawHand task an Outlook event is a copy of, if it is one.

    We stamp ``clarity_task_id`` on every event we push, which is what makes
    the push an upsert. Reading it back is what lets the calendar collapse the
    synced copy into the task itself instead of showing both.
    """
    for prop in event.get("singleValueExtendedProperties") or []:
        if prop.get("id") == CLARITY_TASK_PROP_ID:
            return prop.get("value") or None
    return None


def _graph_event_datetime(value: object | None, *, is_all_day: bool) -> str | None:
    """Normalize Graph timed values to explicit UTC, preserving all-day dates."""
    if not isinstance(value, dict):
        return None

    raw = value.get("dateTime")
    if not isinstance(raw, str) or not raw:
        return None
    if is_all_day:
        return raw.split("T", 1)[0]

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        timezone_name = value.get("timeZone")
        if not isinstance(timezone_name, str) or timezone_name.upper() != "UTC":
            return None
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class CalendarSyncService:
    async def ms_get_events(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str | None = None,
        days_ahead: int = 30,
    ) -> list[dict]:
        if user_id:
            token = await get_fresh_user_token(db, tenant_id, user_id, "microsoft")
        else:
            token = await get_fresh_token(db, tenant_id, "microsoft")

        if not token:
            logger.warning(
                "ms_get_events: no Microsoft token for user_id=%s tenant_id=%s",
                user_id,
                tenant_id,
            )
            raise ValueError(
                "No Microsoft calendar token. Open Calendar and choose Connect Calendar."
            )

        cal_url = f"{GRAPH_BASE}/me/calendarview"
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=days_ahead)

        params = {
            "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "$select": "id,subject,start,end,isAllDay,location,bodyPreview,organizer,attendees",
            "$top": 100,
            "$orderby": "start/dateTime",
            # Surface the marker we stamp on events we pushed. Without it the
            # UI cannot tell a task's synced copy from an unrelated meeting, so
            # the task and its own calendar entry render side by side.
            "$expand": (
                "singleValueExtendedProperties("
                f"$filter=id eq '{CLARITY_TASK_PROP_ID}')"
            ),
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": 'outlook.timezone="UTC"',
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(cal_url, headers=headers, params=params)
            if resp.status_code != 200 and "$expand" in params:
                # The marker is what lets a task's synced copy be collapsed into
                # the task, but it is worth strictly less than the calendar
                # itself. If Graph will not serve the expansion, read without it
                # and lose the de-duplication rather than the whole view.
                logger.warning(
                    "Microsoft calendar read with the task marker failed (HTTP %s); "
                    "retrying without it",
                    resp.status_code,
                )
                params = {k: v for k, v in params.items() if k != "$expand"}
                resp = await client.get(cal_url, headers=headers, params=params)
            if resp.status_code != 200:
                raise ValueError(
                    f"Microsoft calendar read failed (HTTP {resp.status_code}). Open Calendar and choose Connect Calendar."
                )

            events = []
            for evt in resp.json().get("value", []):
                is_all_day = bool(evt.get("isAllDay"))
                events.append(
                    {
                        "id": evt.get("id"),
                        "provider": "microsoft",
                        "task_id": _graph_task_id(evt),
                        "subject": evt.get("subject", ""),
                        "start": _graph_event_datetime(
                            evt.get("start"), is_all_day=is_all_day
                        ),
                        "end": _graph_event_datetime(
                            evt.get("end"), is_all_day=is_all_day
                        ),
                        "location": (evt.get("location", {}) or {}).get(
                            "displayName", ""
                        ),
                        "body": (evt.get("bodyPreview") or "")[:500],
                        "organizer": (evt.get("organizer", {}) or {})
                        .get("emailAddress", {})
                        .get("name", ""),
                        "attendees": [
                            {
                                "name": a.get("emailAddress", {}).get("name", ""),
                                "email": a.get("emailAddress", {}).get("address", ""),
                            }
                            for a in (evt.get("attendees") or [])
                        ],
                    }
                )
            return events

    async def ms_create_event(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str | None,
        subject: str,
        start_dt: datetime,
        end_dt: datetime,
        body: str = "",
        location: str = "",
        attendees: list[str] | None = None,
        timezone_name: str = "UTC",
    ) -> dict | None:
        if user_id:
            token = await get_fresh_user_token(db, tenant_id, user_id, "microsoft")
        else:
            token = await get_fresh_token(db, tenant_id, "microsoft")

        if not token:
            return None

        event = {
            "subject": subject,
            "start": {
                "dateTime": _provider_local_datetime(start_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
            "end": {
                "dateTime": _provider_local_datetime(end_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
        }
        if body:
            event["body"] = {"contentType": "text", "content": body}
        if location:
            event["location"] = {"displayName": location}
        if attendees:
            event["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees
            ]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GRAPH_BASE}/me/events",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=event,
            )
            if resp.status_code not in (200, 201):
                logger.warning(
                    "MS Calendar create event failed: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            return resp.json()

    async def ms_create_scheduled_event(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str | None,
        *,
        subject: str,
        start_dt: datetime,
        end_dt: datetime,
        timezone_name: str = "UTC",
        body: str = "",
        location: str = "",
        attendees: list[str] | None = None,
        teams_online: bool = False,
    ) -> dict | None:
        """Create a timed Outlook calendar event, optionally as a Teams meeting."""
        token = (
            await get_fresh_user_token(db, tenant_id, user_id, "microsoft")
            if user_id
            else await get_fresh_token(db, tenant_id, "microsoft")
        )
        if not token:
            raise ValueError(
                "No Microsoft calendar token. Open Calendar and choose Connect Calendar."
            )

        event = {
            "subject": subject,
            "start": {
                "dateTime": _provider_local_datetime(start_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
            "end": {
                "dateTime": _provider_local_datetime(end_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
        }
        if body:
            event["body"] = {"contentType": "text", "content": body}
        if location:
            event["location"] = {"displayName": location}
        if attendees:
            event["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees
            ]
        if teams_online:
            event["isOnlineMeeting"] = True
            event["onlineMeetingProvider"] = "teamsForBusiness"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GRAPH_BASE}/me/events",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=event,
            )
            if resp.status_code not in (200, 201):
                raise ValueError(
                    f"Microsoft calendar event create failed (HTTP {resp.status_code})."
                )
            return resp.json()

    async def ms_delete_event(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str | None,
        event_id: str | None,
    ) -> bool:
        if not event_id:
            return False
        token = (
            await get_fresh_user_token(db, tenant_id, user_id, "microsoft")
            if user_id
            else await get_fresh_token(db, tenant_id, "microsoft")
        )
        if not token:
            return False
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{GRAPH_BASE}/me/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        return resp.status_code in (200, 202, 204, 404)

    async def google_get_events(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        days_ahead: int = 30,
    ) -> list[dict]:
        token = await get_fresh_user_token(db, tenant_id, user_id, "google")
        if not token:
            logger.warning(
                "google_get_events: no Google token for user_id=%s tenant_id=%s",
                user_id,
                tenant_id,
            )
            raise ValueError(
                "No Google calendar token. Open Calendar and choose Connect Calendar."
            )

        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": 100,
            "singleEvents": "true",
            "orderBy": "startTime",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GOOGLE_CAL_BASE}/calendars/primary/events",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if resp.status_code != 200:
                raise ValueError(
                    f"Google Calendar read failed (HTTP {resp.status_code}). Open Calendar and choose Connect Calendar."
                )

            events = []
            for evt in resp.json().get("items", []):
                events.append(
                    {
                        "id": evt.get("id"),
                        "provider": "google",
                        "task_id": (
                            (evt.get("extendedProperties") or {}).get("private") or {}
                        ).get("clarity_task_id"),
                        "subject": evt.get("summary", ""),
                        "start": evt.get("start", {}).get("dateTime")
                        or evt.get("start", {}).get("date"),
                        "end": evt.get("end", {}).get("dateTime")
                        or evt.get("end", {}).get("date"),
                        "location": evt.get("location", ""),
                        "body": (evt.get("description") or "")[:500],
                        "organizer": (evt.get("organizer", {}) or {}).get(
                            "displayName", ""
                        ),
                        "attendees": [
                            {
                                "name": a.get("displayName", ""),
                                "email": a.get("email", ""),
                            }
                            for a in (evt.get("attendees") or [])
                        ],
                    }
                )
            return events

    async def google_create_event(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        subject: str,
        start_dt: datetime,
        end_dt: datetime,
        body: str = "",
        location: str = "",
        attendees: list[str] | None = None,
        timezone_name: str = "UTC",
    ) -> dict | None:
        token = await get_fresh_user_token(db, tenant_id, user_id, "google")
        if not token:
            return None

        event = {
            "summary": subject,
            "start": {
                "dateTime": _provider_local_datetime(start_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
            "end": {
                "dateTime": _provider_local_datetime(end_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
        }
        if body:
            event["description"] = body
        if location:
            event["location"] = location
        if attendees:
            event["attendees"] = [{"email": a} for a in attendees]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GOOGLE_CAL_BASE}/calendars/primary/events",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=event,
            )
            if resp.status_code not in (200, 201):
                logger.warning(
                    "Google Calendar create event failed: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            return resp.json()

    async def google_create_scheduled_event(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        *,
        subject: str,
        start_dt: datetime,
        end_dt: datetime,
        timezone_name: str = "UTC",
        body: str = "",
        location: str = "",
        attendees: list[str] | None = None,
    ) -> dict | None:
        """Create a timed Google Calendar event."""
        token = await get_fresh_user_token(db, tenant_id, user_id, "google")
        if not token:
            raise ValueError(
                "No Google calendar token. Open Calendar and choose Connect Calendar."
            )

        event = {
            "summary": subject,
            "start": {
                "dateTime": _provider_local_datetime(start_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
            "end": {
                "dateTime": _provider_local_datetime(end_dt, timezone_name),
                "timeZone": timezone_name or "UTC",
            },
        }
        if body:
            event["description"] = body
        if location:
            event["location"] = location
        if attendees:
            event["attendees"] = [{"email": a} for a in attendees]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GOOGLE_CAL_BASE}/calendars/primary/events",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=event,
            )
            if resp.status_code not in (200, 201):
                raise ValueError(
                    f"Google Calendar event create failed (HTTP {resp.status_code})."
                )
            return resp.json()

    async def google_delete_event(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        event_id: str | None,
    ) -> bool:
        if not event_id:
            return False
        token = await get_fresh_user_token(db, tenant_id, user_id, "google")
        if not token:
            return False
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{GOOGLE_CAL_BASE}/calendars/primary/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        return resp.status_code in (200, 202, 204, 410)

    async def _existing_synced_keys(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        provider: str,
        days_ahead: int,
    ) -> set[tuple[str, str]]:
        """Index what this calendar already holds, as (subject, start date).

        Without it every sync creates the same deadline again, so the calendar
        ends up showing a LawHand task beside its own synced copy. Reading the
        provider is how the identity stays stable across syncs: nothing local
        records which events a previous run created.
        """
        if provider == "microsoft":
            existing = await self.ms_get_events(
                db, tenant_id, user_id, days_ahead=days_ahead
            )
        else:
            existing = await self.google_get_events(
                db, tenant_id, user_id, days_ahead=days_ahead
            )
        keys: set[tuple[str, str]] = set()
        for event in existing:
            subject = (event.get("subject") or "").strip()
            start = str(event.get("start") or "")[:10]
            if subject and start:
                keys.add((subject, start))
        return keys

    async def sync_deadlines_to_calendar(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        provider: str,
        timezone_name: str = "UTC",
    ) -> dict:
        from app.models.plugin import Matter

        await set_tenant_context(db, tenant_id)
        result = await db.execute(
            select(Matter).where(
                Matter.tenant_id == tenant_id,
                ~Matter.is_closed,
            )
        )
        matters = result.scalars().all()

        created = 0
        skipped = 0
        today = date.today()
        window_days = 90
        cutoff = today + timedelta(days=window_days)
        already_synced = await self._existing_synced_keys(
            db, tenant_id, user_id, provider, window_days
        )

        for matter in matters:
            key_dates = matter.key_dates or {}
            for label, date_val in key_dates.items():
                if not date_val:
                    continue
                try:
                    if isinstance(date_val, str):
                        d = date.fromisoformat(date_val)
                    elif isinstance(date_val, date):
                        d = date_val
                    else:
                        continue
                except ValueError:
                    continue

                if today <= d <= cutoff:
                    start_dt = datetime(d.year, d.month, d.day, 9, 0, 0)
                    end_dt = datetime(d.year, d.month, d.day, 9, 30, 0)
                    subject = f"[LawHand] {label}: {matter.matter_name}"
                    body = f"Matter: {matter.matter_name}\nType: {matter.matter_type}\nStatus: {matter.status}\nDeadline: {label}"

                    if (subject, d.isoformat()) in already_synced:
                        skipped += 1
                        continue

                    try:
                        if provider == "microsoft":
                            result_ev = await self.ms_create_event(
                                db,
                                tenant_id,
                                user_id,
                                subject,
                                start_dt,
                                end_dt,
                                body,
                                timezone_name=timezone_name,
                            )
                        else:
                            result_ev = await self.google_create_event(
                                db,
                                tenant_id,
                                user_id,
                                subject,
                                start_dt,
                                end_dt,
                                body,
                                timezone_name=timezone_name,
                            )
                        if result_ev:
                            created += 1
                            already_synced.add((subject, d.isoformat()))
                    except Exception as exc:
                        logger.warning(
                            "Failed to create calendar event for matter %s: %s",
                            matter.id,
                            exc,
                        )

        return {"created": created, "skipped": skipped, "provider": provider}


calendar_sync = CalendarSyncService()
