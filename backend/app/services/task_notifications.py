"""Task notification helpers shared by task and intake flows."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Coroutine

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.contact import Contact
from app.models.plugin import Matter
from app.models.task import Task
from app.models.tenant import Tenant
from app.models.user import User
from app.services import google_calendar, microsoft_calendar
from app.services.email import EmailDeliveryResult, email_service
from app.services.matter_followups import matter_timezone
from app.services.task_visibility import task_contains_sms

logger = logging.getLogger(__name__)
settings = get_settings()


async def _demo_notifications_disabled(db: AsyncSession, tenant_id: str) -> bool:
    """Keep task-created calendar/email notifications inside demo workspaces."""
    billing_tier = await db.scalar(
        select(Tenant.billing_tier).where(Tenant.id == tenant_id)
    )
    return billing_tier == "demo"


def _fire_and_log(coro: Coroutine, *, task_id: str, action: str) -> None:
    """Run notification work in the background and log failures."""

    async def _run() -> None:
        try:
            await coro
        except Exception as exc:
            logger.warning(
                "Task notification failed for task %s (action=%s): %s",
                task_id,
                action,
                exc,
            )

    asyncio.create_task(_run())


def task_calendar_user_id(task: Task) -> str | None:
    user_id = task.assigned_to_user_id or task.created_by_user_id
    return str(user_id) if user_id else None


def _user_label(user: User | None) -> str | None:
    if not user:
        return None
    return user.full_name or user.email


def _format_task_created_at(task: Task) -> str:
    if not task.created_at:
        return "Unknown"
    return task.created_at.strftime("%B %d, %Y %H:%M UTC")


def _format_task_due(task: Task) -> str:
    if not task.due_date:
        return "No due date"
    due = task.due_date.isoformat()
    if task.due_time:
        due = f"{due} {task.due_time.strftime('%H:%M')}"
    return due


def _task_url(task: Task) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/tasks/{task.id}"


def _calendar_description(
    task: Task,
    *,
    creator_name: str | None = None,
    customer_name: str | None = None,
    task_url: str | None = None,
) -> str:
    lines = [task.description or ""]
    metadata = [
        f"Created by: {creator_name}" if creator_name else "",
        f"Customer: {customer_name}" if customer_name else "",
        f"Task link: {task_url}" if task_url else "",
    ]
    metadata = [line for line in metadata if line]
    if metadata:
        if lines[0]:
            lines.append("")
        lines.extend(metadata)
    return "\n".join(line for line in lines if line)


async def _load_task_context(
    db: AsyncSession, task: Task
) -> tuple[User | None, Contact | None, Matter | None]:
    creator = None
    if task.created_by_user_id:
        creator = (
            await db.execute(
                select(User).where(
                    User.id == task.created_by_user_id,
                    User.tenant_id == task.tenant_id,
                )
            )
        ).scalar_one_or_none()
    contact = None
    if task.contact_id:
        contact = (
            await db.execute(
                select(Contact).where(
                    Contact.id == task.contact_id,
                    Contact.tenant_id == task.tenant_id,
                )
            )
        ).scalar_one_or_none()
    matter = None
    if task.matter_id:
        matter = (
            await db.execute(
                select(Matter).where(
                    Matter.id == task.matter_id,
                    Matter.tenant_id == task.tenant_id,
                )
            )
        ).scalar_one_or_none()
    return creator, contact, matter


def _humanize(value: str | None) -> str | None:
    """``follow_up`` -> ``Follow up``: stored enum values are not inbox English."""
    if not value:
        return None
    return str(value).replace("_", " ").strip().capitalize() or None


def due_label(task: Task, *, today: date | None = None) -> str:
    """How urgent this is, in the words a reader needs in a subject line.

    "2026-09-18" tells a reader nothing without a calendar in the other hand.
    "Due today" and "Overdue by 3 days" are the same fact, already triaged.
    """
    if not task.due_date:
        return "No due date"
    reference = today or datetime.now(timezone.utc).date()
    days = (task.due_date - reference).days
    if days < 0:
        overdue = abs(days)
        unit = "day" if overdue == 1 else "days"
        return f"Overdue by {overdue} {unit}"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    return f"Due in {days} days"


async def _matter_client_and_attorney(
    db: AsyncSession, matter: Matter | None
) -> tuple[Contact | None, User | None]:
    """The matter's client contact and attorney of record.

    Loaded with explicit queries rather than through the relationships: those
    are ``lazy="select"`` and would raise on attribute access under the async
    session.
    """
    if matter is None:
        return None, None
    client = None
    if matter.client_contact_id:
        client = await db.scalar(
            select(Contact).where(
                Contact.id == matter.client_contact_id,
                Contact.tenant_id == matter.tenant_id,
            )
        )
    attorney = None
    if matter.attorney_of_record_id:
        attorney = await db.scalar(
            select(User).where(
                User.id == matter.attorney_of_record_id,
                User.tenant_id == matter.tenant_id,
            )
        )
    return client, attorney


async def send_task_due_reminder(
    db: AsyncSession,
    task: Task,
    *,
    assignee: User | None = None,
    today: date | None = None,
) -> EmailDeliveryResult:
    """Email the assignee a reminder that identifies the task it is about.

    Every caller -- the nightly sweep and the manual "remind" button -- goes
    through here so a reminder reads the same wherever it came from, and so
    the context (client, matter, attorney of record, who raised it) is
    resolved once rather than per call site.

    A task carrying client SMS content sends a reminder stripped of that
    context: SMS review stays in LawHand, and the assignee still needs to know
    the deadline exists.
    """
    if assignee is None and task.assigned_to_user_id:
        assignee = await db.scalar(
            select(User).where(
                User.id == task.assigned_to_user_id,
                User.tenant_id == task.tenant_id,
            )
        )
    if not assignee or not (assignee.email or "").strip():
        return EmailDeliveryResult.INVALID_RECIPIENT

    withhold = await task_contains_sms(db, task)
    creator, contact, matter = await _load_task_context(db, task)
    matter_client, attorney = await _matter_client_and_attorney(db, matter)
    client = contact or matter_client

    return await email_service.send_task_reminder(
        to_email=assignee.email,
        task_title=task.title,
        due_date=_format_task_due(task),
        due_label=due_label(task, today=today),
        matter_name=None if withhold else (matter.matter_name if matter else None),
        assignee_name=_user_label(assignee),
        status=_humanize(task.status),
        priority=_humanize(task.priority),
        task_type=_humanize(task.task_type),
        description=None if withhold else task.description,
        client_name=None if withhold else (client.display_name if client else None),
        attorney_name=None if withhold else _user_label(attorney),
        created_at=_format_task_created_at(task),
        created_by_name=_user_label(creator),
        source=_humanize(task.source),
        task_url=_task_url(task),
        details_withheld=withhold,
    )


async def _task_timezone(db: AsyncSession, task: Task) -> str:
    """The timezone a task's ``due_time`` wall clock is meant in.

    ``due_time`` is stored naive, so it needs one. The matter's intake timezone
    is the only per-matter value we hold and is already what follow-up due
    times are written in, which keeps a deadline meaning the same thing on the
    calendar as it does in LawHand. A task with no matter falls back to UTC
    rather than guessing an office location.
    """
    if not task.matter_id:
        return "UTC"
    try:
        return await matter_timezone(db, task.tenant_id, task.matter_id)
    except Exception:  # noqa: BLE001 - a calendar push must not fail a task
        logger.exception("Resolving the timezone for task %s failed", task.id)
        return "UTC"


def push_task_to_calendars(
    task: Task,
    tenant_id: str,
    *,
    creator_name: str | None = None,
    customer_name: str | None = None,
    task_url: str | None = None,
    timezone_name: str = "UTC",
) -> None:
    """Fire-and-forget upsert of a task's event to Google and Microsoft.

    A task with a saved ``due_time`` propagates as a timed event in
    ``timezone_name``; one without stays all-day, which is what a date-only
    deadline actually is. Dropping the time — as this did for every task —
    puts a lawyer's 9am filing deadline on their calendar as a day with no
    hour in it.
    """
    if not task.due_date:
        return
    task_id = str(task.id)
    is_completed = task.status == "completed"
    user_id = task_calendar_user_id(task)
    kwargs = dict(
        tenant_id=tenant_id,
        task_id=task_id,
        title=task.title or task.task_type or "",
        due_date=task.due_date.isoformat(),
        due_time=task.due_time.isoformat() if task.due_time else None,
        timezone_name=timezone_name,
        description=_calendar_description(
            task,
            creator_name=creator_name,
            customer_name=customer_name,
            task_url=task_url,
        ),
        is_completed=is_completed,
        user_id=user_id,
    )
    _fire_and_log(
        google_calendar.upsert_task_event(**kwargs),
        task_id=task_id,
        action="google-calendar-upsert",
    )
    _fire_and_log(
        microsoft_calendar.upsert_task_event(**kwargs),
        task_id=task_id,
        action="microsoft-calendar-upsert",
    )


def remove_task_from_calendars(
    task_id: str, tenant_id: str, user_id: str | None = None
) -> None:
    """Fire-and-forget removal of a task's event from Google and Microsoft."""
    _fire_and_log(
        google_calendar.delete_task_event(
            tenant_id=tenant_id, task_id=task_id, user_id=user_id
        ),
        task_id=task_id,
        action="google-calendar-delete",
    )
    _fire_and_log(
        microsoft_calendar.delete_task_event(
            tenant_id=tenant_id, task_id=task_id, user_id=user_id
        ),
        task_id=task_id,
        action="microsoft-calendar-delete",
    )


async def remove_task_from_calendars_now(
    task_id: str, tenant_id: str, user_id: str | None = None
) -> tuple[object, object]:
    """Synchronously remove calendar copies before revoking task access."""
    results = await asyncio.gather(
        google_calendar.delete_task_event(
            tenant_id=tenant_id,
            task_id=task_id,
            user_id=user_id,
            require_exact_user=True,
        ),
        microsoft_calendar.delete_task_event(
            tenant_id=tenant_id,
            task_id=task_id,
            user_id=user_id,
            require_exact_user=True,
        ),
        return_exceptions=True,
    )
    failures: list[Exception] = []
    for provider, result in zip(("google", "microsoft"), results, strict=True):
        if isinstance(result, Exception) or result is not True:
            failure = (
                result
                if isinstance(result, Exception)
                else RuntimeError("Calendar cleanup was not verified")
            )
            failures.append(failure)
            logger.warning(
                "%s calendar cleanup failed for SMS task %s (%s)",
                provider,
                task_id,
                type(failure).__name__,
            )
    if failures:
        raise RuntimeError("External calendar cleanup did not complete") from failures[
            0
        ]
    return results[0], results[1]


async def send_task_assignment_alert(
    db: AsyncSession, task: Task, assignment_note: str | None = None
) -> EmailDeliveryResult | bool:
    """Send an immediate email alert when a task is assigned to a user."""
    if await _demo_notifications_disabled(db, str(task.tenant_id)):
        return EmailDeliveryResult.NOT_REQUIRED
    if not task.assigned_to_user_id:
        return EmailDeliveryResult.NOT_REQUIRED
    if await task_contains_sms(db, task):
        logger.info(
            "Task %s assignment alert skipped: SMS review content stays in LawHand",
            task.id,
        )
        return EmailDeliveryResult.NOT_REQUIRED
    assignee = (
        await db.execute(
            select(User).where(
                User.id == task.assigned_to_user_id,
                User.tenant_id == task.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not assignee or not assignee.email:
        logger.info("Task %s assignment alert skipped: assignee has no email", task.id)
        return EmailDeliveryResult.INVALID_RECIPIENT
    creator = None
    if task.created_by_user_id:
        creator = (
            await db.execute(
                select(User).where(
                    User.id == task.created_by_user_id,
                    User.tenant_id == task.tenant_id,
                )
            )
        ).scalar_one_or_none()
    contact = None
    if task.contact_id:
        contact = (
            await db.execute(
                select(Contact).where(
                    Contact.id == task.contact_id,
                    Contact.tenant_id == task.tenant_id,
                )
            )
        ).scalar_one_or_none()
    matter = None
    if task.matter_id:
        matter = (
            await db.execute(
                select(Matter).where(
                    Matter.id == task.matter_id,
                    Matter.tenant_id == task.tenant_id,
                )
            )
        ).scalar_one_or_none()
    matter_client, attorney = await _matter_client_and_attorney(db, matter)
    client = contact or matter_client

    return await email_service.send_task_assignment_alert(
        to_email=assignee.email,
        task_title=task.title,
        due_date=_format_task_due(task),
        priority=_humanize(task.priority),
        task_type=_humanize(task.task_type),
        description=task.description,
        assignee_name=assignee.full_name or assignee.email,
        created_by_name=_user_label(creator),
        created_at=_format_task_created_at(task),
        customer_name=client.display_name if client else None,
        matter_name=matter.matter_name if matter else None,
        source=_humanize(task.source),
        assigner_note=assignment_note,
        task_url=_task_url(task),
        attorney_name=_user_label(attorney),
        status=_humanize(task.status),
    )


async def notify_task_created(
    db: AsyncSession,
    task: Task,
    tenant_id: str,
    assignment_note: str | None = None,
) -> EmailDeliveryResult | bool:
    """Notify external systems and assignee after a new task is created."""
    if await _demo_notifications_disabled(db, tenant_id):
        return EmailDeliveryResult.NOT_REQUIRED
    if await task_contains_sms(db, task):
        # SMS proposals contain phone/body and are intentionally never copied to
        # assignment email or third-party calendars. Review stays in LawHand.
        return EmailDeliveryResult.NOT_REQUIRED
    creator, contact, _matter = await _load_task_context(db, task)
    push_task_to_calendars(
        task,
        tenant_id,
        creator_name=_user_label(creator),
        customer_name=contact.display_name if contact else None,
        task_url=_task_url(task),
        timezone_name=await _task_timezone(db, task),
    )
    if task.assigned_to_user_id:
        return await send_task_assignment_alert(db, task, assignment_note)
    return EmailDeliveryResult.NOT_REQUIRED


async def notify_task_updated(
    db: AsyncSession,
    task: Task,
    tenant_id: str,
    *,
    calendar_changed: bool,
    assignment_changed: bool,
    previous_calendar_user_id: str | None = None,
    assignment_note: str | None = None,
) -> EmailDeliveryResult | bool:
    """Notify external systems after a task update."""
    if await _demo_notifications_disabled(db, tenant_id):
        return EmailDeliveryResult.NOT_REQUIRED
    if await task_contains_sms(db, task):
        # New SMS proposals never create calendar copies. Ordinary task updates
        # must not return a false 500 after their state/run commit because a
        # legacy provider cleanup failed; access revocation owns the explicit,
        # fail-closed legacy cleanup boundary.
        return EmailDeliveryResult.NOT_REQUIRED
    if calendar_changed:
        if assignment_changed and previous_calendar_user_id:
            remove_task_from_calendars(
                str(task.id), tenant_id, previous_calendar_user_id
            )
        if task.status == "cancelled" or not task.due_date:
            remove_task_from_calendars(
                str(task.id), tenant_id, task_calendar_user_id(task)
            )
        else:
            push_task_to_calendars(
                task, tenant_id, timezone_name=await _task_timezone(db, task)
            )
    if assignment_changed and task.assigned_to_user_id:
        return await send_task_assignment_alert(db, task, assignment_note)
    return EmailDeliveryResult.NOT_REQUIRED
