"""Someone is told when a signed document cannot be filed (issue #492).

Filing the executed copy is retried every five minutes with no cap. Automatic
recovery proves the retry path works; it does not establish that a human would
be told if retries never succeeded, and a signed document that never reaches
durable storage is silent data loss.

These tests drive the retry path to exhaustion and assert that an owner exists,
that the escalation is raised once rather than once per retry, and that a later
success both clears the failure run and closes the task.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.plugin import MatterEvent
import app.services.esign.service as esign_service
from app.services.esign.service import (
    COMPLETION_ESCALATION_ATTEMPTS,
    COMPLETION_ESCALATION_WINDOW,
    STORAGE_ESCALATION_EVENT_TITLE,
    _record_completion_failure,
    completion_retries_exhausted,
    escalate_completion_failure,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def _request(**overrides):
    request = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        matter_id=uuid.uuid4(),
        source_document_filename="Fee agreement.pdf",
        created_by_user_id=uuid.uuid4(),
        completion_error=None,
        completion_attempted_at=None,
        completion_failure_count=0,
        completion_first_failed_at=None,
        completion_escalated_at=None,
    )
    for key, value in overrides.items():
        setattr(request, key, value)
    return request


def _matter():
    return SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4(), user_id=uuid.uuid4())


class _DB:
    """Records what the escalation would write, without a database."""

    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None

    @property
    def events(self):
        return [row for row in self.added if isinstance(row, MatterEvent)]


def _exhausted_request(**overrides):
    """A request that has been failing long enough and often enough."""
    return _request(
        **{
            "completion_error": "storage unreachable",
            "completion_failure_count": COMPLETION_ESCALATION_ATTEMPTS,
            "completion_first_failed_at": NOW - COMPLETION_ESCALATION_WINDOW,
            **overrides,
        }
    )


@pytest.fixture
def captured(monkeypatch):
    """Capture the follow-up task and notification the escalation raises."""
    calls = SimpleNamespace(tasks=[], notified=[])

    async def _ensure(db, **kwargs):
        task = SimpleNamespace(id=uuid.uuid4(), **kwargs)
        calls.tasks.append(kwargs)
        return task

    async def _notify(db, task, tenant_id, *args, **kwargs):
        calls.notified.append(tenant_id)
        return True

    async def _timezone(db, tenant_id, matter_id):
        return "America/Chicago"

    monkeypatch.setattr(esign_service, "ensure_followup_task", _ensure)
    monkeypatch.setattr(esign_service, "notify_task_created", _notify)
    monkeypatch.setattr(esign_service, "matter_timezone", _timezone)
    return calls


# ── Counting the failure run ─────────────────────────────────────────────────


def test_each_failure_counts_and_the_first_one_starts_the_window():
    db, request, matter = _DB(), _request(), _matter()

    _record_completion_failure(db, request, matter, "storage unreachable")
    first_failed = request.completion_first_failed_at
    assert request.completion_failure_count == 1
    assert first_failed is not None

    _record_completion_failure(db, request, matter, "storage unreachable")
    assert request.completion_failure_count == 2
    # The window is measured from the start of the run, not the last attempt.
    assert request.completion_first_failed_at == first_failed


# ── When retrying alone stops being an answer ────────────────────────────────


def test_a_short_outage_does_not_escalate():
    request = _request(
        completion_error="storage unreachable",
        completion_failure_count=COMPLETION_ESCALATION_ATTEMPTS,
        completion_first_failed_at=NOW - timedelta(minutes=5),
    )
    assert completion_retries_exhausted(request, now=NOW) is False


def test_a_long_outage_with_few_attempts_does_not_escalate():
    request = _request(
        completion_error="storage unreachable",
        completion_failure_count=2,
        completion_first_failed_at=NOW - timedelta(days=1),
    )
    assert completion_retries_exhausted(request, now=NOW) is False


def test_enough_failures_over_a_long_enough_window_is_exhaustion():
    assert completion_retries_exhausted(_exhausted_request(), now=NOW) is True


def test_a_request_that_is_no_longer_failing_is_not_exhausted():
    request = _exhausted_request(completion_error=None)
    assert completion_retries_exhausted(request, now=NOW) is False


def test_an_already_escalated_request_is_not_exhausted_again():
    request = _exhausted_request(completion_escalated_at=NOW)
    assert completion_retries_exhausted(request, now=NOW) is False


def test_a_naive_first_failure_timestamp_is_read_as_utc():
    request = _exhausted_request(
        completion_first_failed_at=(NOW - COMPLETION_ESCALATION_WINDOW).replace(
            tzinfo=None
        )
    )
    assert completion_retries_exhausted(request, now=NOW) is True


# ── The escalation itself ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exhaustion_raises_one_assigned_task_to_the_requester(captured):
    db, request, matter = _DB(), _exhausted_request(), _matter()

    task = await escalate_completion_failure(db, request, matter, now=NOW)

    assert task is not None
    assert len(captured.tasks) == 1
    raised = captured.tasks[0]
    # Owned by whoever asked for the signature, on the matter it belongs to.
    assert raised["owner_id"] == request.created_by_user_id
    assert raised["matter_id"] == request.matter_id
    assert raised["tenant_id"] == request.tenant_id
    assert raised["priority"] == "high"
    assert "Fee agreement.pdf" in raised["title"]
    # Keyed so a repeat pass cannot mint a second task.
    assert raised["namespace"] == request.id
    assert raised["kind"] == "signature_filing_failed"
    assert captured.notified == [str(request.tenant_id)]


@pytest.mark.asyncio
async def test_the_task_says_what_failed_and_that_retrying_continues(captured):
    db, request, matter = _DB(), _exhausted_request(), _matter()

    await escalate_completion_failure(db, request, matter, now=NOW)

    description = captured.tasks[0]["description"]
    assert "storage unreachable" in description
    assert str(COMPLETION_ESCALATION_ATTEMPTS) in description
    assert "still being retried" in description


@pytest.mark.asyncio
async def test_escalation_is_visible_on_the_matter_timeline(captured):
    db, request, matter = _DB(), _exhausted_request(), _matter()

    await escalate_completion_failure(db, request, matter, now=NOW)

    assert [event.title for event in db.events] == [STORAGE_ESCALATION_EVENT_TITLE]
    assert db.events[0].matter_id == matter.id


@pytest.mark.asyncio
async def test_a_second_pass_does_not_escalate_again(captured):
    db, request, matter = _DB(), _exhausted_request(), _matter()

    await escalate_completion_failure(db, request, matter, now=NOW)
    again = await escalate_completion_failure(
        db, request, matter, now=NOW + timedelta(hours=6)
    )

    assert again is None
    assert len(captured.tasks) == 1
    assert len(db.events) == 1


@pytest.mark.asyncio
async def test_no_task_before_the_thresholds_are_crossed(captured):
    db, matter = _DB(), _matter()
    request = _request(
        completion_error="storage unreachable",
        completion_failure_count=1,
        completion_first_failed_at=NOW - timedelta(minutes=5),
    )

    assert await escalate_completion_failure(db, request, matter, now=NOW) is None
    assert captured.tasks == []
    assert db.events == []


@pytest.mark.asyncio
async def test_escalation_survives_a_failing_notification(captured, monkeypatch):
    # The assigned task is the escalation; a bounced email must not undo it.
    async def _boom(db, task, tenant_id, *args, **kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(esign_service, "notify_task_created", _boom)
    db, request, matter = _DB(), _exhausted_request(), _matter()

    task = await escalate_completion_failure(db, request, matter, now=NOW)

    assert task is not None
    assert request.completion_escalated_at == NOW


@pytest.mark.asyncio
async def test_escalation_falls_back_to_the_matter_owner_on_the_timeline(captured):
    db, matter = _DB(), _matter()
    request = _exhausted_request(created_by_user_id=None)

    await escalate_completion_failure(db, request, matter, now=NOW)

    assert db.events[0].created_by == matter.user_id


@pytest.mark.asyncio
async def test_an_unnamed_document_still_escalates(captured):
    db, matter = _DB(), _matter()
    request = _exhausted_request(source_document_filename=None)

    await escalate_completion_failure(db, request, matter, now=NOW)

    assert "document" in captured.tasks[0]["title"]


# ── Recovery ─────────────────────────────────────────────────────────────────


def test_a_later_unrelated_outage_starts_counting_from_zero():
    # _finalize clears the run on success. Without that, the next single
    # failure would inherit an old count and escalate immediately.
    db, matter = _DB(), _matter()
    request = _exhausted_request()
    request.completion_failure_count = 0
    request.completion_first_failed_at = None
    request.completion_error = None

    _record_completion_failure(db, request, matter, "storage unreachable")

    assert request.completion_failure_count == 1
    assert completion_retries_exhausted(request, now=NOW) is False


@pytest.mark.asyncio
async def test_a_successful_filing_closes_the_escalation(monkeypatch):
    """The person told about the failure is owed the resolution too."""
    closed = []

    async def _close_followup(db, *, tenant_id, namespace, kind, reason, actor_user_id):
        closed.append((namespace, kind, reason))
        return SimpleNamespace(id=uuid.uuid4())

    async def _noop(*args, **kwargs):
        return None

    import app.services.esign.followups as followups
    import app.services.matter_intake as matter_intake

    monkeypatch.setattr(followups, "close_followup_task", _close_followup)
    monkeypatch.setattr(esign_service, "close_signature_followup", _noop)
    # after_completion imports matter_intake inside the function, so patch the
    # module it actually reaches rather than a name on esign_service.
    monkeypatch.setattr(matter_intake, "get_packet", _noop)

    request = _exhausted_request(completion_escalated_at=NOW)
    await esign_service.after_completion(_DB(), request)

    assert closed == [(request.id, "signature_filing_failed", "Signed copy filed")]


@pytest.mark.asyncio
async def test_closing_the_escalation_does_not_depend_on_a_due_date(monkeypatch):
    # The signature chase task is skipped for an undated request; an undated
    # request can still fail to file, so this close must not be skipped with it.
    closed = []

    async def _close_followup(db, *, kind, **kwargs):
        closed.append(kind)
        return None

    import app.services.esign.followups as followups

    monkeypatch.setattr(followups, "close_followup_task", _close_followup)
    request = _exhausted_request(due_at=None)

    await followups.close_filing_escalation(_DB(), request)

    assert closed == ["signature_filing_failed"]
