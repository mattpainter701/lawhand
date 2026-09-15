"""Exercise persisted import transactions against the CI PostgreSQL fixture."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.models.communication_log import CommunicationLog
from app.models.external_import import ExternalRecordLink
from app.models.matter_document import MatterDocument
from app.routers import matter_imports as routes
from app.services.matter_import_manifest import file_manifest


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["onedrive", "google_drive"])
async def test_persisted_import_retry_and_correspondence(
    db_session, test_user, monkeypatch, provider
):
    user = SimpleNamespace(id=test_user.id, tenant_id=test_user.tenant_id, role="admin")
    content = b"From: lawyer@former.example\r\nTo: client@example.com\r\nSubject: Historic case\r\n\r\nPreserved body"
    plan = routes.ImportPlan(
        id=uuid.uuid4(),
        files=[dict(file_manifest("Smith/mail.eml", content), group="Smith")],
    )
    await routes.plan(plan, db_session, user)
    approval = routes.Approval(
        confirm=True,
        mappings=[
            dict(
                group="Smith",
                first_name="Jane",
                last_name="Smith",
                matter_name="Smith case",
                intake="existing",
            )
        ],
    )
    approved = await routes.approve(plan.id, approval, db_session, user)
    assert await routes.approve(plan.id, approval, db_session, user) == approved
    monkeypatch.setattr(
        routes.MatterFileStore,
        "store_matter_file_result",
        AsyncMock(
            return_value=SimpleNamespace(
                succeeded=True,
                storage_path="provider/path",
                provider=provider,
                backend=provider,
                provider_item_id="object",
                drive_id="drive",
                parent_id="parent",
            )
        ),
    )
    first = await routes.ingest(db_session, user, plan.id, "Smith/mail.eml", content)
    assert (
        await routes.ingest(db_session, user, plan.id, "Smith/mail.eml", content)
        == first
    )
    assert (await routes.status(plan.id, db_session, user))["status"] == "complete"
    log = await db_session.scalar(
        select(CommunicationLog).where(
            CommunicationLog.document_id == uuid.UUID(first["document_id"])
        )
    )
    assert log.subject == "Historic case" and log.status == "logged"
    assert log.participants["from"] == "lawyer@former.example"
    doc = await db_session.get(MatterDocument, uuid.UUID(first["document_id"]))
    assert doc.storage_provider == provider and not doc.portal_visible
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ExternalRecordLink)
            .where(ExternalRecordLink.import_run_id == plan.id)
        )
        == 1
    )
    second = routes.ImportPlan(id=uuid.uuid4(), files=plan.files)
    await routes.plan(second, db_session, user)
    await routes.approve(
        second.id,
        routes.Approval(
            confirm=True, mappings=[dict(group="Smith", matter_id=first["matter_id"])]
        ),
        db_session,
        user,
    )
    assert (
        await routes.ingest(db_session, user, second.id, "Smith/mail.eml", content)
    )["status"] == "duplicate"


@pytest.mark.asyncio
async def test_another_user_cannot_read_or_upload_batch(db_session, test_user):
    user = SimpleNamespace(id=test_user.id, tenant_id=test_user.tenant_id, role="admin")
    plan = routes.ImportPlan(
        id=uuid.uuid4(), files=[dict(file_manifest("case.txt", b"case"), group="Case")]
    )
    await routes.plan(plan, db_session, user)
    other = SimpleNamespace(id=uuid.uuid4(), tenant_id=user.tenant_id, role="user")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await routes.get_run(db_session, other, plan.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_import_mapping_records_open_date_and_engagement(db_session, test_user):
    from datetime import date

    from app.models.plugin import Matter, MatterEvent

    user = SimpleNamespace(id=test_user.id, tenant_id=test_user.tenant_id, role="admin")
    content = b"historic scan"
    plan = routes.ImportPlan(
        id=uuid.uuid4(),
        files=[
            dict(file_manifest("Smith/scan.pdf", content), group="Smith"),
            dict(file_manifest("Jones/scan.pdf", content), group="Jones"),
        ],
    )
    await routes.plan(plan, db_session, user)
    approval = routes.Approval(
        confirm=True,
        mappings=[
            dict(
                group="Smith",
                first_name="Jane",
                last_name="Smith",
                matter_name="Smith case",
                intake="existing",
                opened_on="2024-02-10",
                agreement_signed_on="2024-02-01",
            ),
            dict(
                group="Jones",
                organization_name="Jones LLC",
                matter_name="Jones retainer",
                intake="existing",
                agreement="no_agreement",
                agreement_note="Handshake arrangement predating the firm",
            ),
        ],
    )
    approved = await routes.approve(plan.id, approval, db_session, user)
    smith = await db_session.get(Matter, uuid.UUID(approved["destinations"]["Smith"]))
    jones = await db_session.get(Matter, uuid.UUID(approved["destinations"]["Jones"]))

    assert smith.opened_on == date(2024, 2, 10)
    assert smith.retention_until == date(2031, 2, 8)
    # A signed date without the file means the copy is still to be uploaded.
    assert smith.engagement_status == "pending_copy"
    assert smith.engagement_signed_on == date(2024, 2, 1)
    assert smith.engagement_recorded_by == user.id

    assert jones.opened_on == date.today()
    assert jones.engagement_status == "no_agreement"
    assert jones.engagement_note == "Handshake arrangement predating the firm"
    titles = set(
        (
            await db_session.execute(
                select(MatterEvent.title).where(MatterEvent.matter_id == jones.id)
            )
        ).scalars()
    )
    assert titles == {"Existing matter imported", "Matter opened without a fee agreement"}

    for bad in (
        dict(group="X", matter_name="X", first_name="a", last_name="b", intake="review", agreement="no_agreement", agreement_note="n"),
        dict(group="X", matter_name="X", first_name="a", last_name="b", intake="existing", agreement="signed_no_copy"),
        dict(group="X", matter_name="X", first_name="a", last_name="b", intake="existing", opened_on="2999-01-01"),
        dict(group="X", matter_name="X", first_name="a", last_name="b", intake="existing", agreement="no_agreement", agreement_note="n", agreement_signed_on="2020-01-01"),
    ):
        with pytest.raises(ValueError):
            routes.Mapping(**bad)
