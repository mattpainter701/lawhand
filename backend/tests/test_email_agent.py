import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.email_agent import EmailAgent


@pytest.mark.asyncio
async def test_mailbox_sync_ignores_email_without_matter_contact() -> None:
    agent = EmailAgent()
    email = {
        "id": "firewall-log-1",
        "from": "alerts@firewall.example",
        "subject": "%%log.logdesc%%",
        "body_preview": "Blocked request",
    }

    with patch(
        "app.services.microsoft_mail.ms_read_mail_user",
        new=AsyncMock(return_value=[email]),
    ), patch(
        "app.services.email_agent._match_email_to_matters",
        new=AsyncMock(return_value=[]),
    ), patch.object(agent, "classify_email", new=AsyncMock()) as classify:
        result = await agent.process_emails(
            db=AsyncMock(),
            tenant_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            provider="microsoft",
            llm_service=AsyncMock(),
            tenant_name="Test Firm",
        )

    assert result == []
    classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_sender_match_prefers_the_matter_whose_case_number_is_named(
    db_session, test_tenant, test_user
) -> None:
    """A client with two open matters matches both by sender.

    The communication log and any tagged task go to the first matter returned,
    so a case number in the message must put its matter first (and alone).
    """
    from datetime import datetime, timedelta, timezone

    from app.models.contact import Contact
    from app.models.plugin import Matter
    from app.services.email_agent import _match_email_to_matters

    client = Contact(
        id=uuid.uuid4(), tenant_id=test_tenant.id, email="client@acme.example"
    )
    db_session.add(client)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    older = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"older-{uuid.uuid4().hex[:6]}",
        matter_name="Older matter",
        case_number="2024-CV-1234",
        client_contact_id=client.id,
        updated_at=now - timedelta(days=30),
    )
    newer = Matter(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        slug=f"newer-{uuid.uuid4().hex[:6]}",
        matter_name="Newer matter",
        case_number="2025-FA-0077",
        client_contact_id=client.id,
        updated_at=now,
    )
    db_session.add_all([older, newer])
    await db_session.commit()
    older_id, newer_id = older.id, newer.id

    named = await _match_email_to_matters(
        db_session,
        test_tenant.id,
        {"from": "Client <client@acme.example>", "subject": "Re: 2024 CV 1234"},
    )
    assert named == [older_id]

    unnamed = await _match_email_to_matters(
        db_session,
        test_tenant.id,
        {"from": "client@acme.example", "subject": "Quick question"},
    )
    assert unnamed == [newer_id, older_id]
