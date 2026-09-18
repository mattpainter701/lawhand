import asyncio
import uuid
from datetime import date, timedelta

import pytest

from app.models.contact import Contact
from app.models.plugin import Matter
from app.models.task import Task
from app.models.user import User
from app.services import task_notifications
from app.services.email import EmailDeliveryResult, EmailService
from app.services.task_notifications import _calendar_description


@pytest.mark.asyncio
async def test_notify_task_created_pushes_calendar_and_assignment_email(
    db_session, test_tenant
):
    assignee = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="partner@testfirm.com",
        full_name="Partner User",
        role="admin",
        is_active=True,
    )
    creator = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="reception@testfirm.com",
        full_name="Reception User",
        role="staff",
        is_active=True,
    )
    contact = Contact(
        tenant_id=test_tenant.id,
        first_name="Jane",
        last_name="Doe",
        phone="701-555-2222",
        created_by_user_id=creator.id,
    )
    db_session.add_all([assignee, creator])
    await db_session.flush()
    db_session.add(contact)
    await db_session.flush()

    task = Task(
        tenant_id=test_tenant.id,
        title="Urgent intake follow-up: Jane Doe",
        description="Call Jane Doe back.",
        task_type="follow_up",
        priority="urgent",
        due_date=date.today(),
        assigned_to_user_id=assignee.id,
        created_by_user_id=creator.id,
        contact_id=contact.id,
        source="intake_dashboard",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    calendar_calls = []
    email_calls = []

    async def fake_calendar_upsert(**kwargs):
        calendar_calls.append(kwargs)
        return {"id": "calendar-event"}

    async def fake_assignment_email(**kwargs):
        email_calls.append(kwargs)
        return True

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        task_notifications.google_calendar,
        "upsert_task_event",
        fake_calendar_upsert,
    )
    monkeypatch.setattr(
        task_notifications.microsoft_calendar,
        "upsert_task_event",
        fake_calendar_upsert,
    )
    monkeypatch.setattr(
        task_notifications.email_service,
        "send_task_assignment_alert",
        fake_assignment_email,
    )
    try:
        sent = await task_notifications.notify_task_created(
            db_session, task, str(test_tenant.id)
        )
        await asyncio.sleep(0)
    finally:
        monkeypatch.undo()

    assert sent is True
    assert len(email_calls) == 1
    assert email_calls[0]["to_email"] == "partner@testfirm.com"
    assert email_calls[0]["priority"] == "Urgent"
    assert email_calls[0]["task_type"] == "Follow up"
    assert email_calls[0]["assignee_name"] == "Partner User"
    assert email_calls[0]["created_by_name"] == "Reception User"
    assert email_calls[0]["customer_name"] == "Jane Doe"
    assert email_calls[0]["source"] == "Intake dashboard"
    assert email_calls[0]["description"] == "Call Jane Doe back."
    assert email_calls[0]["task_url"].endswith(f"/tasks/{task.id}")
    assert len(calendar_calls) == 2
    assert {call["user_id"] for call in calendar_calls} == {str(assignee.id)}
    assert all(
        "Created by: Reception User" in call["description"] for call in calendar_calls
    )
    assert all("Task link: " in call["description"] for call in calendar_calls)


@pytest.mark.asyncio
async def test_task_assignment_email_includes_ticket_fields_and_escapes_html():
    service = EmailService()
    sent = []

    async def fake_send_email(to_emails, subject, html_body, text_body):
        sent.append(
            {
                "to_emails": to_emails,
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body,
            }
        )
        return True

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "send_email", fake_send_email)
    try:
        ok = await service.send_task_assignment_alert(
            to_email="partner@testfirm.com",
            task_title="Urgent intake follow-up: Jane <Doe>",
            due_date="2026-06-17 15:30",
            priority="urgent",
            task_type="follow_up",
            description="Caller needs divorce help.\n<script>alert(1)</script>",
            assignee_name="Partner User",
            created_by_name="Reception User",
            created_at="June 17, 2026 15:01 UTC",
            customer_name="Jane Doe",
            matter_name="Jane Doe Intake",
            source="intake_dashboard",
            task_url="https://legalapp.example/tasks/123",
        )
    finally:
        monkeypatch.undo()

    assert ok is True
    assert len(sent) == 1
    html = sent[0]["html_body"]
    text = sent[0]["text_body"]
    assert "Created By" in html
    assert "Reception User" in html
    assert "Assigned To" in html
    assert "Partner User" in html
    assert "Client" in html
    assert "Jane Doe" in html
    assert "Task link" in html
    assert "https://legalapp.example/tasks/123" in html
    assert "Reason / Description" in html
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Created by: Reception User" in text
    assert "Client: Jane Doe" in text
    assert "Task link: https://legalapp.example/tasks/123" in text
    assert "Reason / Description:" in text


def test_calendar_description_includes_creator_customer_and_task_link():
    task = Task(
        id=uuid.uuid4(),
        title="Wanda Archer - Call back caller",
        description="Task detail: answered",
    )

    description = _calendar_description(
        task,
        creator_name="Reception User",
        customer_name="Wanda Archer",
        task_url=f"https://legalapp.example/tasks/{task.id}",
    )

    assert "Task detail: answered" in description
    assert "Created by: Reception User" in description
    assert "Customer: Wanda Archer" in description
    assert f"Task link: https://legalapp.example/tasks/{task.id}" in description


@pytest.mark.parametrize(
    "offset_days,expected",
    [
        (-3, "Overdue by 3 days"),
        (-1, "Overdue by 1 day"),
        (0, "Due today"),
        (1, "Due tomorrow"),
        (5, "Due in 5 days"),
    ],
)
def test_due_label_reads_as_urgency_not_a_date(offset_days, expected):
    today = date(2026, 9, 18)
    task = Task(
        id=uuid.uuid4(), title="t", due_date=today + timedelta(days=offset_days)
    )
    assert task_notifications.due_label(task, today=today) == expected


def test_due_label_without_a_due_date():
    assert (
        task_notifications.due_label(Task(id=uuid.uuid4(), title="t")) == "No due date"
    )


@pytest.mark.asyncio
async def test_task_reminder_email_identifies_the_work_and_escapes_html():
    service = EmailService()
    sent = []

    async def fake_send_email(to_emails, subject, html_body, text_body):
        sent.append({"subject": subject, "html": html_body, "text": text_body})
        return True

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "send_email", fake_send_email)
    try:
        ok = await service.send_task_reminder(
            to_email="partner@testfirm.com",
            task_title="Follow up on outstanding intake documents",
            due_date="2026-09-18",
            due_label="Due today",
            matter_name="Doe Estate Administration",
            assignee_name="Matt Painter",
            status="Pending",
            priority="High",
            task_type="Follow up",
            description="Chase the signed IRS 56.\n<script>alert(1)</script>",
            client_name="Jane <Doe>",
            attorney_name="Alex Reyes",
            created_at="September 11, 2026 14:02 UTC",
            created_by_name="Reception User",
            source="Intake dashboard",
            task_url="https://legalapp.example/tasks/abc",
        )
    finally:
        monkeypatch.undo()

    assert ok is True
    html, text = sent[0]["html"], sent[0]["text"]
    # The subject is the whole notification for anyone triaging on a phone.
    assert sent[0]["subject"] == (
        "Due today: Follow up on outstanding intake documents "
        "— Jane <Doe> · Doe Estate Administration"
    )
    for label in (
        "Created",
        "Due",
        "Assigned to",
        "Client",
        "Description",
        "Attorney assigned",
        "Matter",
        "Status",
        "Priority",
    ):
        assert label in html, label
    assert "Alex Reyes" in html
    assert "September 11, 2026 14:02 UTC" in html
    assert "https://legalapp.example/tasks/abc" in html
    assert "Open this task in LawHand" in html
    # Every interpolated value is escaped, in a message the firm cannot inspect.
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Jane &lt;Doe&gt;" in html
    assert "Client: Jane <Doe>" in text
    assert "Attorney assigned: Alex Reyes" in text
    assert "Open in LawHand: https://legalapp.example/tasks/abc" in text


@pytest.mark.asyncio
async def test_task_reminder_rejects_a_non_http_link():
    """A link is a clickable control in a message nobody can inspect first."""
    service = EmailService()
    sent = []

    async def fake_send_email(to_emails, subject, html_body, text_body):
        sent.append({"html": html_body, "text": text_body})
        return True

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "send_email", fake_send_email)
    try:
        await service.send_task_reminder(
            to_email="partner@testfirm.com",
            task_title="Review the filing",
            due_date="2026-09-18",
            task_url="javascript:alert(1)",
        )
    finally:
        monkeypatch.undo()

    assert "javascript:" not in sent[0]["html"]
    assert "javascript:" not in sent[0]["text"]


@pytest.mark.asyncio
async def test_send_task_due_reminder_resolves_client_matter_and_attorney(
    db_session, test_tenant
):
    attorney = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="attorney@testfirm.com",
        full_name="Alex Reyes",
        role="admin",
        is_active=True,
    )
    assignee = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="paralegal@testfirm.com",
        full_name="Matt Painter",
        role="staff",
        is_active=True,
    )
    creator = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="reception@testfirm.com",
        full_name="Reception User",
        role="staff",
        is_active=True,
    )
    db_session.add_all([attorney, assignee, creator])
    await db_session.flush()
    client = Contact(
        tenant_id=test_tenant.id,
        first_name="Jane",
        last_name="Doe",
        created_by_user_id=creator.id,
    )
    db_session.add(client)
    await db_session.flush()
    matter = Matter(
        tenant_id=test_tenant.id,
        user_id=creator.id,
        slug="doe-estate",
        matter_name="Doe Estate Administration",
        client_contact_id=client.id,
        attorney_of_record_id=attorney.id,
    )
    db_session.add(matter)
    await db_session.flush()
    task = Task(
        tenant_id=test_tenant.id,
        title="Follow up on outstanding intake documents",
        description="Chase the signed IRS 56.",
        task_type="follow_up",
        priority="high",
        status="pending",
        due_date=date.today(),
        matter_id=matter.id,
        assigned_to_user_id=assignee.id,
        created_by_user_id=creator.id,
        source="intake_dashboard",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    calls = []

    async def fake_reminder(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        task_notifications.email_service, "send_task_reminder", fake_reminder
    )
    try:
        sent = await task_notifications.send_task_due_reminder(db_session, task)
    finally:
        monkeypatch.undo()

    assert sent is True
    assert len(calls) == 1
    call = calls[0]
    assert call["to_email"] == "paralegal@testfirm.com"
    assert call["due_label"] == "Due today"
    assert call["client_name"] == "Jane Doe"
    assert call["matter_name"] == "Doe Estate Administration"
    assert call["attorney_name"] == "Alex Reyes"
    assert call["assignee_name"] == "Matt Painter"
    assert call["created_by_name"] == "Reception User"
    assert call["description"] == "Chase the signed IRS 56."
    assert call["priority"] == "High"
    assert call["task_type"] == "Follow up"
    assert call["status"] == "Pending"
    assert call["source"] == "Intake dashboard"
    assert call["created_at"]
    assert call["task_url"].endswith(f"/tasks/{task.id}")
    assert call["details_withheld"] is False


@pytest.mark.asyncio
async def test_send_task_due_reminder_withholds_sms_task_details(
    db_session, test_tenant
):
    """SMS review content stays in LawHand; the deadline still gets through."""
    assignee = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email="paralegal@testfirm.com",
        full_name="Matt Painter",
        role="staff",
        is_active=True,
    )
    db_session.add(assignee)
    await db_session.flush()
    contact = Contact(
        tenant_id=test_tenant.id,
        first_name="Jane",
        last_name="Doe",
        created_by_user_id=assignee.id,
    )
    db_session.add(contact)
    await db_session.flush()
    task = Task(
        tenant_id=test_tenant.id,
        title="Approve text to client",
        description="Body awaiting approval",
        due_date=date.today(),
        contact_id=contact.id,
        assigned_to_user_id=assignee.id,
        pending_action={"type": "sms_client", "body": "Your hearing moved"},
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    calls = []

    async def fake_reminder(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        task_notifications.email_service, "send_task_reminder", fake_reminder
    )
    try:
        await task_notifications.send_task_due_reminder(db_session, task)
    finally:
        monkeypatch.undo()

    call = calls[0]
    assert call["details_withheld"] is True
    assert call["description"] is None
    assert call["client_name"] is None
    assert call["matter_name"] is None
    assert call["attorney_name"] is None
    assert call["due_label"] == "Due today"


@pytest.mark.asyncio
async def test_send_task_due_reminder_without_a_deliverable_assignee(
    db_session, test_tenant
):
    task = Task(
        tenant_id=test_tenant.id,
        title="Unassigned deadline",
        due_date=date.today(),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    result = await task_notifications.send_task_due_reminder(db_session, task)
    assert result is EmailDeliveryResult.INVALID_RECIPIENT
