from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.workspace_mcp import ProposeTaskUpdateArgs
from app.services import task_automation
from app.services.automation_capabilities import CapabilityContext, CapabilityError
from app.services.chat_tools import handlers
from app.services.task_workflow import TaskWorkflowError


def _task(**overrides) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "matter_id": uuid.uuid4(),
        "title": "File the motion",
        "status": "pending",
        "priority": "medium",
        "due_date": None,
        "assigned_to_user_id": None,
        "version": 1,
        "pending_action": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _context(db) -> CapabilityContext:
    return CapabilityContext(
        db=db,
        user=SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4()),
        channel="workspace_mcp",
        granted_scopes=frozenset({"matters:read", "tasks:propose"}),
    )


@pytest.mark.asyncio
async def test_propose_task_update_stages_a_reviewable_change(monkeypatch) -> None:
    target = _task()
    db = SimpleNamespace(scalar=AsyncMock(return_value=target))
    context = _context(db)
    target.tenant_id = context.tenant_id

    captured: dict = {}

    async def fake_create(_context, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=uuid.uuid4(),
            version=1,
            title=kwargs["title"],
            status="review",
            matter_id=kwargs["matter_id"],
        )

    monkeypatch.setattr(handlers, "_create_proposed_task", fake_create)

    result = await handlers.propose_task_update(
        context,
        ProposeTaskUpdateArgs(
            matter_id=target.matter_id,
            task_id=target.id,
            status="completed",
            note="Filed at the counter",
        ),
    )

    assert result["status"] == "review"
    assert result["target_task_id"] == str(target.id)
    assert result["action_type"] == "task_update"
    assert captured["pending_action"]["type"] == "task_update"
    assert captured["pending_action"]["target_task_id"] == str(target.id)
    assert captured["pending_action"]["status"] == "completed"


@pytest.mark.asyncio
async def test_propose_task_update_fails_closed(monkeypatch) -> None:
    context = _context(SimpleNamespace(scalar=AsyncMock(return_value=None)))

    with pytest.raises(CapabilityError) as missing:
        await handlers.propose_task_update(
            context,
            ProposeTaskUpdateArgs(
                matter_id=uuid.uuid4(), task_id=uuid.uuid4(), priority="high"
            ),
        )
    assert missing.value.code == "task_not_found"

    pending = _task(pending_action={"type": "email_client"})
    pending.tenant_id = context.tenant_id
    context.db.scalar = AsyncMock(return_value=pending)
    with pytest.raises(CapabilityError) as awaiting:
        await handlers.propose_task_update(
            context,
            ProposeTaskUpdateArgs(
                matter_id=pending.matter_id, task_id=pending.id, priority="high"
            ),
        )
    assert awaiting.value.code == "task_awaiting_review"

    fresh = _task()
    fresh.tenant_id = context.tenant_id
    context.db.scalar = AsyncMock(return_value=fresh)
    with pytest.raises(CapabilityError) as needs_reason:
        await handlers.propose_task_update(
            context,
            ProposeTaskUpdateArgs(
                matter_id=fresh.matter_id, task_id=fresh.id, status="waiting"
            ),
        )
    assert needs_reason.value.code == "reason_required"

    def foreign_assignee(*_args, **_kwargs):
        raise TaskWorkflowError("Assigned user not found", status_code=404)

    monkeypatch.setattr(
        handlers, "require_task_references_for_tenant", foreign_assignee
    )
    with pytest.raises(CapabilityError) as foreign:
        await handlers.propose_task_update(
            context,
            ProposeTaskUpdateArgs(
                matter_id=fresh.matter_id,
                task_id=fresh.id,
                assigned_to_user_id=uuid.uuid4(),
            ),
        )
    assert foreign.value.code == "invalid_task_reference"


@pytest.mark.asyncio
async def test_run_task_update_applies_fields_and_records_an_event(monkeypatch) -> None:
    review_task = _task()
    target = _task(tenant_id=review_task.tenant_id, matter_id=review_task.matter_id)
    db = SimpleNamespace(scalar=AsyncMock(return_value=target))
    events: list[dict] = []
    monkeypatch.setattr(
        task_automation, "append_task_event", lambda *_a, **_k: events.append(_k)
    )

    result = await task_automation._run_task_update(
        db,
        review_task,
        {
            "type": "task_update",
            "matter_id": str(target.matter_id),
            "target_task_id": str(target.id),
            "priority": "high",
            "due_date": "2030-01-02",
            "note": "Please handle today",
        },
        uuid.uuid4(),
    )

    assert result.succeeded is True
    assert target.priority == "high"
    assert target.due_date == date(2030, 1, 2)
    assert target.version == 2
    assert events and events[0]["event_type"] == "assistant_update"


@pytest.mark.asyncio
async def test_run_task_update_uses_the_transition_rule_for_status(monkeypatch) -> None:
    review_task = _task()
    target = _task(tenant_id=review_task.tenant_id, matter_id=review_task.matter_id)
    db = SimpleNamespace(scalar=AsyncMock(return_value=target))
    calls: dict = {}
    events: list[dict] = []

    def fake_transition(_db, task, **kwargs):
        calls.update(kwargs)
        task.status = kwargs["to_status"]
        return True

    monkeypatch.setattr(task_automation, "transition_task", fake_transition)
    monkeypatch.setattr(
        task_automation, "append_task_event", lambda *_a, **_k: events.append(_k)
    )

    result = await task_automation._run_task_update(
        db,
        review_task,
        {
            "type": "task_update",
            "matter_id": str(target.matter_id),
            "target_task_id": str(target.id),
            "status": "completed",
            "reason": "Filed",
        },
        uuid.uuid4(),
    )

    assert result.succeeded is True
    assert target.status == "completed"
    assert calls["to_status"] == "completed"
    assert events[0]["from_status"] == "pending"
    assert events[0]["to_status"] == "completed"


@pytest.mark.asyncio
async def test_run_task_update_refuses_invalid_or_unavailable_targets(monkeypatch) -> None:
    review_task = _task()
    db = SimpleNamespace(scalar=AsyncMock(return_value=None))

    invalid = await task_automation._run_task_update(
        db, review_task, {"type": "task_update"}, None
    )
    assert invalid.succeeded is False

    self_target = await task_automation._run_task_update(
        db,
        review_task,
        {
            "type": "task_update",
            "matter_id": str(review_task.matter_id),
            "target_task_id": str(review_task.id),
            "status": "completed",
        },
        None,
    )
    assert self_target.succeeded is False

    missing = await task_automation._run_task_update(
        db,
        review_task,
        {
            "type": "task_update",
            "matter_id": str(review_task.matter_id),
            "target_task_id": str(uuid.uuid4()),
            "status": "completed",
        },
        None,
    )
    assert missing.succeeded is False

    target = _task(tenant_id=review_task.tenant_id, matter_id=review_task.matter_id)
    db.scalar = AsyncMock(return_value=target)

    async def foreign_assignee(*_args, **_kwargs):
        raise TaskWorkflowError("Assigned user not found", status_code=404)

    monkeypatch.setattr(
        task_automation, "require_task_references_for_tenant", foreign_assignee
    )
    foreign = await task_automation._run_task_update(
        db,
        review_task,
        {
            "type": "task_update",
            "matter_id": str(target.matter_id),
            "target_task_id": str(target.id),
            "assigned_to_user_id": str(uuid.uuid4()),
        },
        None,
    )
    assert foreign.succeeded is False


@pytest.mark.asyncio
async def test_run_task_update_records_a_note_without_field_changes(monkeypatch) -> None:
    review_task = _task()
    target = _task(
        tenant_id=review_task.tenant_id,
        matter_id=review_task.matter_id,
        priority="high",
    )
    db = SimpleNamespace(scalar=AsyncMock(return_value=target))
    events: list[dict] = []
    monkeypatch.setattr(
        task_automation, "append_task_event", lambda *_a, **_k: events.append(_k)
    )

    result = await task_automation._run_task_update(
        db,
        review_task,
        {
            "type": "task_update",
            "matter_id": str(target.matter_id),
            "target_task_id": str(target.id),
            "note": "Called the firm back; no change needed",
        },
        uuid.uuid4(),
    )

    assert result.succeeded is True
    assert target.version == 1
    assert events[0]["event_type"] == "assistant_note"
