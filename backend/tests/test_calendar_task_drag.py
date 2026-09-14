"""Rescheduling a task from the calendar, and blocking working time for one.

Covers the two intents a calendar drop can carry: move the deadline (which has
to re-arm the due-date reminder) or block time to work on the task (which has
to leave the deadline alone).
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models.task import Task


async def _make_task(db_session, tenant_id, user_id, **overrides):
    values = dict(
        tenant_id=tenant_id,
        title="File the motion",
        task_type="filing",
        status="pending",
        priority="high",
        due_date=date.today() + timedelta(days=7),
        assigned_to_user_id=user_id,
    )
    values.update(overrides)
    task = Task(**values)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_task_event_carries_its_version_and_all_day_window(
    client, db_session, test_tenant, test_user
):
    task = await _make_task(db_session, test_tenant.id, test_user.id)

    resp = await client.get(
        "/api/calendar/events",
        params={"start": task.due_date.isoformat(), "end": task.due_date.isoformat()},
    )

    assert resp.status_code == 200
    event = next(e for e in resp.json()["events"] if e["event_type"] == "task_due")
    assert event["task_id"] == str(task.id)
    # The version travels with the chip so a drop can reschedule exactly the
    # revision the calendar rendered.
    assert event["task_version"] == task.version
    # No due time means the deadline stays an all-day chip.
    assert event["start"] is None
    assert event["end"] is None


@pytest.mark.asyncio
async def test_task_event_with_a_due_time_lands_in_the_time_grid(
    client, db_session, test_tenant, test_user
):
    task = await _make_task(
        db_session, test_tenant.id, test_user.id, due_time=time(14, 30)
    )

    resp = await client.get(
        "/api/calendar/events",
        params={"start": task.due_date.isoformat(), "end": task.due_date.isoformat()},
    )

    event = next(e for e in resp.json()["events"] if e["event_type"] == "task_due")
    # Emitted without an offset: the browser reads the firm's own wall clock,
    # the same time the task form captured.
    assert event["start"] == f"{task.due_date.isoformat()}T14:30:00"
    assert event["end"] == f"{task.due_date.isoformat()}T15:00:00"


@pytest.mark.asyncio
async def test_moving_a_due_date_re_arms_the_reminder(
    client, db_session, test_tenant, test_user
):
    """A reminder already sent for the old date must not silence the new one."""
    task = await _make_task(
        db_session,
        test_tenant.id,
        test_user.id,
        due_date=date.today() + timedelta(days=10),
        reminder_sent_at=datetime.now(timezone.utc),
    )
    new_due = date.today() + timedelta(days=1)

    resp = await client.patch(
        f"/api/tasks/{task.id}",
        json={
            "due_date": new_due.isoformat(),
            "due_time": "09:00",
            "expected_version": task.version,
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["due_date"] == new_due.isoformat()
    await db_session.refresh(task)
    assert task.reminder_sent_at is None


@pytest.mark.asyncio
async def test_an_unrelated_edit_keeps_the_reminder_guard(
    client, db_session, test_tenant, test_user
):
    sent_at = datetime.now(timezone.utc)
    task = await _make_task(
        db_session, test_tenant.id, test_user.id, reminder_sent_at=sent_at
    )

    resp = await client.patch(
        f"/api/tasks/{task.id}",
        json={"priority": "urgent", "expected_version": task.version},
    )

    assert resp.status_code == 200, resp.text
    await db_session.refresh(task)
    # The deadline did not move, so the dedup guard still applies.
    assert task.reminder_sent_at is not None


@pytest.mark.asyncio
async def test_closing_a_task_does_not_re_arm_a_reminder(
    client, db_session, test_tenant, test_user
):
    task = await _make_task(
        db_session,
        test_tenant.id,
        test_user.id,
        reminder_sent_at=datetime.now(timezone.utc),
    )

    resp = await client.patch(
        f"/api/tasks/{task.id}",
        json={
            "status": "completed",
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
            "expected_version": task.version,
        },
    )

    assert resp.status_code == 200, resp.text
    await db_session.refresh(task)
    # Nothing left to remind anyone about.
    assert task.reminder_sent_at is not None


@pytest.mark.asyncio
async def test_work_block_links_the_task_and_leaves_the_due_date_alone(
    client, db_session, test_tenant, test_user
):
    task = await _make_task(db_session, test_tenant.id, test_user.id)
    original_due = task.due_date
    start = datetime.combine(
        date.today() + timedelta(days=2), time(9, 0), tzinfo=timezone.utc
    )

    resp = await client.post(
        "/api/calendar/scheduled-events",
        json={
            "title": f"Work block: {task.title}",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "timezone": "America/Chicago",
            "task_id": str(task.id),
            "calendar_provider": None,
            "meeting_provider": "none",
        },
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["task_id"] == str(task.id)

    events_resp = await client.get(
        "/api/calendar/events",
        params={"start": start.date().isoformat(), "end": start.date().isoformat()},
    )
    block = next(
        e for e in events_resp.json()["events"] if e["event_type"] == "scheduled_event"
    )
    assert block["task_id"] == str(task.id)

    await db_session.refresh(task)
    assert task.due_date == original_due


@pytest.mark.asyncio
async def test_work_block_rejects_a_task_outside_the_tenant(client):
    start = datetime.now(timezone.utc) + timedelta(days=2)

    resp = await client.post(
        "/api/calendar/scheduled-events",
        json={
            "title": "Work block: someone else's task",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "task_id": "00000000-0000-0000-0000-000000000123",
            "meeting_provider": "none",
        },
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


@pytest.mark.asyncio
async def test_dragging_a_work_block_keeps_its_task_link(
    client, db_session, test_tenant, test_user
):
    """Moving the block only moves the time — it stays the same task's block."""
    task = await _make_task(db_session, test_tenant.id, test_user.id)
    start = datetime.combine(
        date.today() + timedelta(days=2), time(9, 0), tzinfo=timezone.utc
    )
    created = await client.post(
        "/api/calendar/scheduled-events",
        json={
            "title": f"Work block: {task.title}",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "task_id": str(task.id),
            "meeting_provider": "none",
        },
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    moved_start = start + timedelta(days=1, hours=2)

    resp = await client.patch(
        f"/api/calendar/scheduled-events/{event_id}",
        json={
            "start_at": moved_start.isoformat(),
            "end_at": (moved_start + timedelta(hours=1)).isoformat(),
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["task_id"] == str(task.id)
    assert resp.json()["start_at"].startswith(moved_start.date().isoformat())


@pytest.mark.asyncio
async def test_relinking_a_block_to_an_unknown_task_is_rejected(
    client, db_session, test_tenant, test_user
):
    task = await _make_task(db_session, test_tenant.id, test_user.id)
    start = datetime.combine(
        date.today() + timedelta(days=2), time(9, 0), tzinfo=timezone.utc
    )
    created = await client.post(
        "/api/calendar/scheduled-events",
        json={
            "title": f"Work block: {task.title}",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "task_id": str(task.id),
            "meeting_provider": "none",
        },
    )
    event_id = created.json()["id"]

    resp = await client.patch(
        f"/api/calendar/scheduled-events/{event_id}",
        json={"task_id": "00000000-0000-0000-0000-000000000123"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"
