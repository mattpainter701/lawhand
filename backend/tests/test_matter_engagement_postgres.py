"""Recording an existing engagement: signed copy on file, no copy, no agreement.

Every path here runs against the real database, sends nothing, and creates no
portal invitation or signature request.
"""

import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response, UploadFile
from sqlalchemy import func, select

from app.models.client_portal import ClientPortalInvite
from app.models.contact import Contact
from app.models.matter_document import MatterDocument
from app.models.plugin import Matter, MatterEvent
from app.models.signature import SignatureRequest
from app.routers import matter_intake as routes
from app.schemas.matter_intake import IntakeReceipt, IntakeStart
from app.services import matter_engagement
from app.services import matter_intake as service

PDF = b"%PDF-1.4 signed fee agreement"


def staff(test_user):
    return SimpleNamespace(
        id=test_user.id,
        tenant_id=test_user.tenant_id,
        role="admin",
        full_name="Test Attorney",
        email=test_user.email,
    )


async def make_matter(db_session, user, **overrides):
    contact = Contact(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        first_name="Jane",
        last_name="Smith",
        email=f"jane-{uuid.uuid4().hex[:6]}@example.com",
    )
    db_session.add(contact)
    await db_session.flush()
    fields = dict(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.id,
        slug=f"engaged-{uuid.uuid4().hex[:8]}",
        matter_name="Smith transfer",
        client_contact_id=contact.id,
        status="open",
    )
    fields.update(overrides)
    matter = Matter(**fields)
    db_session.add(matter)
    await db_session.commit()
    return matter


def stored(monkeypatch, succeeded=True):
    mock = AsyncMock(
        return_value=SimpleNamespace(
            succeeded=succeeded,
            storage_path="provider/signed.pdf",
            provider="onedrive",
            backend="onedrive",
            provider_item_id="item",
            drive_id="drive",
            parent_id="parent",
        )
    )
    monkeypatch.setattr(service, "store_file", mock)
    return mock


async def record(db_session, user, matter_id, options, content=None, filename="signed.pdf"):
    response = Response()
    upload = (
        UploadFile(file=io.BytesIO(content), filename=filename)
        if content is not None
        else None
    )
    result = await routes.record_engagement(
        matter_id,
        response,
        options=json.dumps({"confirm": True, **options}, default=str),
        agreement=upload,
        db=db_session,
        user=user,
    )
    return response.status_code, result


async def count(db_session, model, matter_id):
    return await db_session.scalar(
        select(func.count()).select_from(model).where(model.matter_id == matter_id)
    )


@pytest.mark.asyncio
async def test_signed_copy_upload_files_document_and_activates_matter(
    db_session, test_user, monkeypatch
):
    user = staff(test_user)
    matter = await make_matter(db_session, user, stage="Transfer / Review Required")
    store = stored(monkeypatch)

    status, result = await record(
        db_session,
        user,
        matter.id,
        {"status": "signed_on_file", "signed_on": "2025-03-01", "note": "From prior firm"},
        PDF,
    )

    assert status == 201
    assert result["stage"] == "Active"
    engagement = result["engagement"]
    assert engagement["status"] == "signed_on_file"
    assert engagement["signed_on"] == date(2025, 3, 1)
    assert engagement["document_name"] == "signed.pdf"
    assert engagement["recorded_by"] == str(user.id)
    assert engagement["recorded_by_name"] == "Test Attorney"
    assert store.await_args.kwargs["category"] == "contract"

    document = await db_session.get(MatterDocument, uuid.UUID(engagement["document_id"]))
    assert document.matter_id == matter.id
    assert document.document_category == "contract"
    assert document.document_role == "filed_copy"
    assert document.document_status == "filed"
    assert document.portal_visible is False
    assert "signed 2025-03-01" in document.description
    assert len(document.document_sha256) == 64

    await db_session.refresh(matter)
    assert matter.engagement_document_id == document.id
    assert matter.engagement_recorded_at is not None
    event = await db_session.scalar(
        select(MatterEvent).where(
            MatterEvent.matter_id == matter.id,
            MatterEvent.title == "Signed fee agreement recorded",
        )
    )
    assert "No messages sent" in event.content and "From prior firm" in event.content
    # Nothing that touches the client exists.
    assert await count(db_session, ClientPortalInvite, matter.id) == 0
    assert await count(db_session, SignatureRequest, matter.id) == 0


@pytest.mark.asyncio
async def test_existing_matter_document_can_be_the_signed_copy(
    db_session, test_user, monkeypatch
):
    user = staff(test_user)
    matter = await make_matter(db_session, user)
    store = stored(monkeypatch)
    document = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        matter_id=matter.id,
        filename="scan.pdf",
        content_type="application/pdf",
        storage_path="provider/scan.pdf",
        storage_provider="onedrive",
        storage_backend="onedrive",
    )
    db_session.add(document)
    await db_session.commit()

    status, result = await record(
        db_session,
        user,
        matter.id,
        {"status": "signed_on_file", "document_id": str(document.id)},
    )

    assert status == 201
    assert result["engagement"]["document_id"] == str(document.id)
    assert result["engagement"]["document_name"] == "scan.pdf"
    assert result["engagement"]["signed_on"] is None
    store.assert_not_awaited()
    assert await count(db_session, MatterDocument, matter.id) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_value, title",
    [
        ("signed_no_copy", "Engagement recorded without agreement copy"),
        ("no_agreement", "Matter opened without a fee agreement"),
    ],
)
async def test_engagement_without_a_document_is_recorded_and_tracked(
    db_session, test_user, monkeypatch, status_value, title
):
    user = staff(test_user)
    matter = await make_matter(db_session, user)
    store = stored(monkeypatch)
    options = {"status": status_value, "note": "Legacy retainer arrangement from 2019"}
    if status_value == "signed_no_copy":
        options["signed_on"] = "2019-06-01"

    status, result = await record(db_session, user, matter.id, options)

    assert status == 201
    assert result["engagement"]["status"] == status_value
    assert result["engagement"]["document_id"] is None
    assert result["engagement"]["note"] == "Legacy retainer arrangement from 2019"
    assert result["stage"] == "Active"
    store.assert_not_awaited()
    assert await count(db_session, MatterDocument, matter.id) == 0
    event = await db_session.scalar(
        select(MatterEvent).where(
            MatterEvent.matter_id == matter.id, MatterEvent.title == title
        )
    )
    assert "Legacy retainer arrangement" in event.content


@pytest.mark.asyncio
async def test_missing_note_or_document_is_refused(db_session, test_user, monkeypatch):
    user = staff(test_user)
    matter = await make_matter(db_session, user)
    stored(monkeypatch)

    for options, content, message in (
        ({"status": "no_agreement"}, None, "why this matter has no fee agreement"),
        ({"status": "signed_no_copy"}, None, "where the agreement was signed"),
        ({"status": "signed_on_file"}, None, "Upload the signed fee agreement"),
        ({"status": "no_agreement", "note": "x", "signed_on": "2020-01-01"}, None, "no signing date"),
        ({"status": "no_agreement", "note": "x"}, PDF, "only belongs with"),
        ({"status": "signed_on_file"}, b"not a pdf", "as a PDF"),
        ({"status": "signed_on_file", "signed_on": "2999-01-01"}, PDF, "future"),
    ):
        with pytest.raises(HTTPException) as caught:
            await record(db_session, user, matter.id, options, content)
        assert caught.value.status_code == 422
        assert message in caught.value.detail

    with pytest.raises(HTTPException) as caught:
        await record(db_session, user, matter.id, {"status": "bogus"})
    assert caught.value.status_code == 422

    await db_session.refresh(matter)
    assert matter.engagement_status is None
    assert matter.stage is None


@pytest.mark.asyncio
async def test_closed_matter_and_unknown_document_are_refused(
    db_session, test_user, monkeypatch
):
    user = staff(test_user)
    stored(monkeypatch)
    closed = await make_matter(db_session, user, status="closed", is_closed=True)
    with pytest.raises(HTTPException) as caught:
        await record(db_session, user, closed.id, {"status": "no_agreement", "note": "x"})
    assert caught.value.status_code == 409

    matter = await make_matter(db_session, user)
    with pytest.raises(HTTPException) as caught:
        await record(
            db_session,
            user,
            matter.id,
            {"status": "signed_on_file", "document_id": str(uuid.uuid4())},
        )
    assert caught.value.status_code == 404

    with pytest.raises(HTTPException) as caught:
        await record(db_session, user, uuid.uuid4(), {"status": "no_agreement", "note": "x"})
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_repeat_submission_is_a_no_op_and_copy_can_be_added_later(
    db_session, test_user, monkeypatch
):
    user = staff(test_user)
    matter = await make_matter(db_session, user)
    store = stored(monkeypatch)

    first = await record(
        db_session, user, matter.id, {"status": "no_agreement", "note": "Pro bono"}
    )
    again = await record(
        db_session, user, matter.id, {"status": "no_agreement", "note": "Pro bono"}
    )
    assert first[0] == 201 and again[0] == 200
    assert again[1]["engagement"]["recorded_at"] == first[1]["engagement"]["recorded_at"]

    # The copy turned up: upgrading is allowed without replace.
    status, result = await record(
        db_session,
        user,
        matter.id,
        {"status": "signed_on_file", "signed_on": "2024-01-15"},
        PDF,
    )
    assert status == 201 and result["engagement"]["status"] == "signed_on_file"
    document_id = result["engagement"]["document_id"]

    # Uploading the same bytes again files nothing new.
    status, result = await record(
        db_session,
        user,
        matter.id,
        {"status": "signed_on_file", "signed_on": "2024-01-15"},
        PDF,
    )
    assert status == 200 and result["engagement"]["document_id"] == document_id
    assert store.await_count == 1
    assert await count(db_session, MatterDocument, matter.id) == 1

    # Contradicting a filed signed agreement needs explicit consent.
    with pytest.raises(HTTPException) as caught:
        await record(
            db_session, user, matter.id, {"status": "no_agreement", "note": "Mistake"}
        )
    assert caught.value.status_code == 409
    status, result = await record(
        db_session,
        user,
        matter.id,
        {"status": "no_agreement", "note": "Mistake", "replace": True},
    )
    assert status == 201 and result["engagement"]["status"] == "no_agreement"
    replaced = await db_session.scalar(
        select(MatterEvent).where(
            MatterEvent.matter_id == matter.id,
            MatterEvent.title == "Matter opened without a fee agreement",
            MatterEvent.content.contains("Replaces the earlier record"),
        )
    )
    assert replaced is not None
    events = await count(db_session, MatterEvent, matter.id)
    assert events == 3


@pytest.mark.asyncio
async def test_hand_set_stage_and_pending_copy_transitions(
    db_session, test_user, monkeypatch
):
    user = staff(test_user)
    stored(monkeypatch)
    matter = await make_matter(db_session, user, stage="Discovery")
    status, result = await record(
        db_session, user, matter.id, {"status": "signed_no_copy", "note": "Signed in office"}
    )
    assert status == 201 and result["stage"] == "Discovery"

    # A pending copy (as an importer records it) resolves either way.
    pending = await make_matter(db_session, user)
    matter_engagement.apply_engagement(
        pending,
        status="pending_copy",
        signed_on=date(2023, 5, 5),
        note=None,
        document_id=None,
        user_id=user.id,
    )
    await db_session.commit()
    status, result = await record(
        db_session,
        user,
        pending.id,
        {"status": "no_agreement", "note": "Turned out there never was one"},
    )
    assert status == 201 and result["engagement"]["status"] == "no_agreement"
    assert matter_engagement.transition_allowed("pending_copy", "signed_on_file", replace=False)
    assert not matter_engagement.transition_allowed("signed_no_copy", "no_agreement", replace=False)
    assert matter_engagement.transition_allowed("signed_no_copy", "no_agreement", replace=True)


@pytest.mark.asyncio
async def test_packet_waiting_on_fee_agreement_wins(db_session, test_user, monkeypatch):
    user = staff(test_user)
    matter = await make_matter(db_session, user)
    stored(monkeypatch)
    monkeypatch.setattr(
        service,
        "get_packet",
        AsyncMock(
            return_value=SimpleNamespace(
                status="awaiting_documents",
                requirements={"fee_agreement": {"completed": False}},
            )
        ),
    )
    with pytest.raises(HTTPException) as caught:
        await record(db_session, user, matter.id, {"status": "signed_on_file"}, PDF)
    assert caught.value.status_code == 409
    assert "Review received documents" in caught.value.detail


@pytest.mark.asyncio
async def test_storage_failure_records_nothing(db_session, test_user, monkeypatch):
    user = staff(test_user)
    matter = await make_matter(db_session, user)
    stored(monkeypatch, succeeded=False)
    with pytest.raises(HTTPException) as caught:
        await record(db_session, user, matter.id, {"status": "signed_on_file"}, PDF)
    assert caught.value.status_code == 503
    await db_session.rollback()
    await db_session.refresh(matter)
    assert matter.engagement_status is None
    assert await count(db_session, MatterDocument, matter.id) == 0


@pytest.mark.asyncio
async def test_verified_intake_receipt_marks_agreement_on_file(
    db_session, test_user, monkeypatch
):
    user = staff(test_user)
    matter = await make_matter(db_session, user)
    stored(monkeypatch)
    monkeypatch.setattr(
        service, "get_user_capabilities", AsyncMock(return_value={"manage_matters"})
    )
    contact = await db_session.get(Contact, matter.client_contact_id)
    options = IntakeStart(
        email=contact.email,
        channels=["email"],
        include_questionnaire=True,
        questions=[dict(key="summary", label="Summary")],
        confirm_send=True,
    )
    packet = await service.start_packet(
        db_session, user, matter, options, "fee.pdf", b"%PDF-reviewed"
    )
    assert packet.requirements["fee_agreement"]["completed"] is False
    signed = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        matter_id=matter.id,
        filename="signed-by-hand.pdf",
        storage_path="provider/path",
        storage_provider="onedrive",
        storage_backend="onedrive",
    )
    db_session.add(signed)
    await db_session.commit()

    await routes.receipt(
        matter.id,
        IntakeReceipt(
            requirement="fee_agreement",
            document_id=signed.id,
            note="Client dropped off the signed copy",
        ),
        db_session,
        user,
    )

    await db_session.refresh(matter)
    assert matter.engagement_status == "signed_on_file"
    assert matter.engagement_document_id == signed.id
    assert matter.engagement_note == "Client dropped off the signed copy"
    event = await db_session.scalar(
        select(MatterEvent).where(
            MatterEvent.matter_id == matter.id,
            MatterEvent.title == "Signed fee agreement recorded",
        )
    )
    assert "intake document receipt" in event.content


def test_engagement_payload_is_none_without_a_record():
    matter = SimpleNamespace(engagement_status=None)
    assert matter_engagement.engagement_payload(matter) is None
    recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
    matter = SimpleNamespace(
        engagement_status="signed_no_copy",
        engagement_signed_on=date(2020, 2, 2),
        engagement_document_id=None,
        engagement_document=None,
        engagement_note="Signed at the courthouse",
        engagement_recorded_at=recorded,
        engagement_recorded_by=None,
        engagement_recorder=None,
    )
    payload = matter_engagement.engagement_payload(matter)
    assert payload["status"] == "signed_no_copy"
    assert payload["document_name"] is None and payload["recorded_by_name"] is None
    assert payload["recorded_at"] == recorded
    assert recorded + timedelta(0) == recorded
