"""Intake sends without a staff step, so a guessed plan goes on the timeline.

The E-Signature panel can hold a request until staff acknowledge a plan the
server had to guess at. Case Setup cannot: its requests are created already
sent, as part of kicking the matter off. So the same warnings are written to
the matter timeline instead, where the firm sees them before the client has
done anything with the document.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.contact import Contact
from app.models.plugin import Matter, MatterEvent
from app.schemas.matter_intake import IntakeStart
from app.services import matter_intake as service
from tests.esign_pdf_fixtures import blank_pdf, flat_agreement_pdf


async def _matter(db_session, test_user):
    user = SimpleNamespace(id=test_user.id, tenant_id=test_user.tenant_id, role="admin")
    contact = Contact(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        first_name="Jane",
        last_name="Smith",
        email="jane@example.com",
    )
    db_session.add(contact)
    await db_session.flush()
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.id,
        slug=f"intake-review-{uuid.uuid4().hex[:8]}",
        matter_name="Smith",
        client_contact_id=contact.id,
        status="open",
    )
    db_session.add(matter)
    await db_session.commit()
    return user, contact, matter


def _wire(monkeypatch):
    monkeypatch.setattr(
        service,
        "store_file",
        AsyncMock(
            return_value=SimpleNamespace(
                succeeded=True,
                storage_path="provider/path",
                provider="onedrive",
                backend="onedrive",
                provider_item_id="item",
                drive_id="drive",
                parent_id="parent",
            )
        ),
    )
    monkeypatch.setattr(
        service, "get_user_capabilities", AsyncMock(return_value={"manage_matters"})
    )
    monkeypatch.setattr(
        service,
        "send_client_email",
        AsyncMock(
            return_value=SimpleNamespace(
                delivery_certainty="confirmed_sent", provider="onedrive"
            )
        ),
    )
    monkeypatch.setattr(
        service, "now", lambda: datetime(2026, 9, 16, 14, tzinfo=timezone.utc)
    )


async def _review_events(db_session, matter_id):
    return (
        await db_session.scalars(
            select(MatterEvent).where(
                MatterEvent.matter_id == matter_id,
                MatterEvent.title == "Signature plan needs review",
            )
        )
    ).all()


@pytest.mark.asyncio
async def test_a_fee_agreement_with_no_signature_line_is_flagged_on_the_timeline(
    db_session, test_user, monkeypatch
):
    user, contact, matter = await _matter(db_session, test_user)
    _wire(monkeypatch)
    options = IntakeStart(
        email=contact.email,
        channels=["email"],
        include_questionnaire=True,
        questions=[dict(key="summary", label="Summary")],
        confirm_send=True,
    )

    await service.start_packet(
        db_session, user, matter, options, "Fee agreement.pdf", blank_pdf()
    )

    [event] = await _review_events(db_session, matter.id)
    assert event.content.startswith("Fee agreement.pdf: No signature line was found")
    assert "foot of the last page" in event.content
    assert event.note_type == "system"


@pytest.mark.asyncio
async def test_a_fee_agreement_with_its_line_printed_is_not_flagged(
    db_session, test_user, monkeypatch
):
    user, contact, matter = await _matter(db_session, test_user)
    _wire(monkeypatch)
    options = IntakeStart(
        email=contact.email,
        channels=["email"],
        include_questionnaire=True,
        questions=[dict(key="summary", label="Summary")],
        confirm_send=True,
    )

    await service.start_packet(
        db_session, user, matter, options, "Fee agreement.pdf", flat_agreement_pdf()
    )

    assert await _review_events(db_session, matter.id) == []


@pytest.mark.asyncio
async def test_the_request_itself_still_carries_the_review(
    db_session, test_user, monkeypatch
):
    from app.models.signature import SignatureRequest

    user, contact, matter = await _matter(db_session, test_user)
    _wire(monkeypatch)
    options = IntakeStart(
        email=contact.email,
        channels=["email"],
        include_questionnaire=True,
        questions=[dict(key="summary", label="Summary")],
        confirm_send=True,
    )

    await service.start_packet(
        db_session, user, matter, options, "Fee agreement.pdf", blank_pdf()
    )

    request = await db_session.scalar(
        select(SignatureRequest).where(SignatureRequest.matter_id == matter.id)
    )
    assert request.status == "sent"
    assert request.signing_plan["review_required"] is True
    assert [item["code"] for item in request.signing_plan["review"]] == ["fallback"]
