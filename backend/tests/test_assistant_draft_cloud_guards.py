"""Assistant Word drafts keep cloud edits and formatting when saved or refreshed.

These call the task pending-action routes directly with the database and the
tenant-cloud provider faked at the materializer boundary. They pin three
rules:

* D34: a LawHand text save never silently orphans edits made in Word Online
  or Google Docs. A changed cloud copy is a 409 ``cloud_copy_changed`` unless
  the reviewer explicitly discards those edits, which is recorded.
* D09: a draft whose working copy came from real DOCX bytes is never
  regenerated from its extracted text, and a truncated preview is never saved.
* ``Refresh edits from cloud`` re-verifies an unchanged copy and adopts a
  changed one byte for byte as an office snapshot.
"""

import hashlib
import io
import uuid
from types import SimpleNamespace as NS

import pytest
from docx import Document
from fastapi import HTTPException

from app.routers import tasks as routes
from app.schemas.task import PendingActionCloudSync, PendingActionEdit
from app.services import cloud_artifact_materialization as materialization
from app.services.matter_file_store import MatterFileNotFound, MatterFileTooLarge
from app.services.provider_http import ProviderError


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


RECORDED = _docx("Engagement letter, as LawHand saved it")
EDITED = _docx("Engagement letter, edited in Word Online")


class FakeDB:
    """Just enough of an AsyncSession for the pending-action routes."""

    def __init__(self, *, task, scalars=(), office_events=()):
        self.task = task
        self.scalar_values = list(scalars)
        self.office_events = list(office_events)
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _statement):
        return NS(scalar_one_or_none=lambda: self.task)

    async def scalar(self, _statement):
        return self.scalar_values.pop(0)

    async def scalars(self, _statement):
        return NS(all=lambda: self.office_events)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _value):
        return None


class FakeMaterializer:
    """The tenant-cloud working copy as the routes see it."""

    def __init__(self, cloud_bytes: bytes = RECORDED):
        self.cloud_bytes = cloud_bytes
        self.read_error: Exception | None = None
        self.reads = 0
        self.materialized: list[dict] = []

    async def read_current_cloud_bytes(self, *, tenant_id, document):
        self.reads += 1
        if self.read_error:
            raise self.read_error
        return self.cloud_bytes

    async def materialize(self, **kwargs):
        self.materialized.append(kwargs)
        content = kwargs.get("source_docx_bytes") or b"rendered revision"
        document = NS(
            id=uuid.uuid4(),
            storage_backend="onedrive",
            provider_object_id="item-2",
            provider_etag='"{E},2"',
            provider_version_id="2",
        )
        return NS(
            document=document, sha256=_sha(content), operation=NS(id=uuid.uuid4())
        )


def _binding(*, backend="onedrive", preview_truncated=False, edit_mode=None):
    tenant_id, matter_id = uuid.uuid4(), uuid.uuid4()
    artifact_id, revision_id, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    pending_action = {
        "type": "matter_document_draft",
        "matter_id": str(matter_id),
        "title": "Engagement letter",
        "body": "Engagement letter, as LawHand saved it",
        "artifact_id": str(artifact_id),
        "artifact_revision_id": str(revision_id),
        "artifact_revision_no": 1,
        "artifact_sha256": "a" * 64,
        "document_id": str(document_id),
        "document_sha256": _sha(RECORDED),
        "document_storage_backend": backend,
        "document_provider_etag": '"{E},1"',
        "document_preview_truncated": preview_truncated,
    }
    if edit_mode:
        pending_action["document_edit_mode"] = edit_mode
    task = NS(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        matter_id=matter_id,
        status="review",
        version=3,
        pending_action=pending_action,
    )
    document = NS(
        id=document_id,
        filename="engagement-letter-r1.docx",
        storage_backend=backend,
        provider_object_id="item-1",
        provider_etag='"{E},1"',
        provider_version_id="1",
        document_sha256=_sha(RECORDED),
        document_role="working_copy",
        document_status="in_review",
        storage_state="verified",
        storage_verified_at=None,
    )
    user = NS(id=uuid.uuid4(), tenant_id=tenant_id)
    return task, document, user


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeMaterializer()
    events: list[dict] = []
    task_events: list[dict] = []

    async def noop(*_args, **_kwargs):
        return None

    async def response(_db, task, _user):
        return {"version": task.version, "pending_action": task.pending_action}

    async def integrity_event(_db, **kwargs):
        events.append(kwargs)

    async def new_revision(_db, **kwargs):
        return NS(
            id=uuid.uuid4(),
            revision_no=kwargs["expected_revision_no"] + 1,
            content_text=kwargs["content_text"],
            content_sha256="d" * 64,
        )

    def bump(task):
        task.version += 1

    monkeypatch.setattr(routes, "set_tenant_context", noop)
    monkeypatch.setattr(routes, "_require_sms_task_access", noop)
    monkeypatch.setattr(routes, "_require_action_reviewer_or_approver", noop)
    monkeypatch.setattr(routes, "_task_response_with_delivery", response)
    monkeypatch.setattr(routes, "append_document_integrity_event", integrity_event)
    monkeypatch.setattr(routes, "create_generated_artifact_revision", new_revision)
    monkeypatch.setattr(routes, "cloud_artifact_materializer", fake)
    monkeypatch.setattr(routes, "reset_staged_review_after_edit", lambda _t: True)
    monkeypatch.setattr(routes, "increment_task_version", bump)
    monkeypatch.setattr(
        routes, "append_task_event", lambda _db, _t, **kw: task_events.append(kw)
    )
    monkeypatch.setattr(routes, "TaskCloudSyncResponse", lambda **kw: kw)
    return NS(materializer=fake, events=events, task_events=task_events)


async def _save(task, document, user, *, discard=False, office_events=()):
    db = FakeDB(task=task, scalars=[document], office_events=office_events)
    payload = PendingActionEdit(
        body="Engagement letter, revised in LawHand",
        expected_version=task.version,
        discard_cloud_edits=discard,
    )
    result = await routes.update_pending_action(
        task.id, payload, current_user=user, db=db
    )
    return result, db


# --- D34: a LawHand text save must not orphan cloud edits -------------------


@pytest.mark.asyncio
async def test_unchanged_cloud_copy_saves_a_new_revision(cloud):
    task, document, user = _binding()

    result, db = await _save(task, document, user)

    assert cloud.materializer.reads == 1
    assert cloud.materializer.materialized[0]["supersedes_document_id"] == document.id
    assert cloud.materializer.materialized[0].get("source_docx_bytes") is None
    assert result["pending_action"]["body"] == "Engagement letter, revised in LawHand"
    assert result["pending_action"]["document_edit_mode"] == "lawhand_text"
    assert db.commits == 1
    assert cloud.events == []


@pytest.mark.asyncio
async def test_cloud_edits_since_the_last_revision_block_the_save(cloud):
    task, document, user = _binding()
    cloud.materializer.cloud_bytes = EDITED
    before = dict(task.pending_action)

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "cloud_copy_changed"
    assert "Refresh edits from cloud" in caught.value.detail["message"]
    assert cloud.materializer.materialized == []
    assert task.pending_action == before
    assert cloud.events == []


@pytest.mark.asyncio
async def test_a_cloud_copy_grown_past_the_limit_counts_as_changed(cloud):
    task, document, user = _binding(backend="google_drive")
    cloud.materializer.read_error = MatterFileTooLarge("too large")

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "cloud_copy_changed"
    assert cloud.materializer.materialized == []


@pytest.mark.asyncio
async def test_discarding_cloud_edits_saves_and_records_an_integrity_event(cloud):
    task, document, user = _binding(backend="sharepoint")
    cloud.materializer.cloud_bytes = EDITED

    result, db = await _save(task, document, user, discard=True)

    assert db.commits == 1
    assert result["pending_action"]["body"] == "Engagement letter, revised in LawHand"
    assert cloud.materializer.materialized[0]["supersedes_document_id"] == document.id
    [event] = cloud.events
    assert event["event_type"] == "cloud_edits_discarded"
    assert event["actor_type"] == "user"
    assert event["actor_user_id"] == user.id
    assert event["document_id"] == document.id
    assert event["content_sha256"] == _sha(EDITED)
    assert event["metadata"] == {
        "storage_backend": "sharepoint",
        "recorded_sha256": _sha(RECORDED),
        "observed_sha256": _sha(EDITED),
        "check": "changed",
    }


@pytest.mark.asyncio
async def test_discard_on_an_unchanged_copy_records_nothing(cloud):
    task, document, user = _binding()

    await _save(task, document, user, discard=True)

    assert cloud.events == []
    assert len(cloud.materializer.materialized) == 1


@pytest.mark.asyncio
async def test_an_unreadable_cloud_copy_is_not_assumed_unchanged(cloud):
    task, document, user = _binding()
    cloud.materializer.read_error = ProviderError("Graph is down")

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user)

    assert caught.value.status_code == 503
    assert cloud.materializer.materialized == []


@pytest.mark.asyncio
async def test_discard_proceeds_past_an_unreadable_copy_and_says_so(cloud):
    task, document, user = _binding()
    cloud.materializer.read_error = MatterFileNotFound("gone")

    await _save(task, document, user, discard=True)

    [event] = cloud.events
    assert event["content_sha256"] is None
    assert event["metadata"]["check"] == "unreadable"
    assert event["metadata"]["observed_sha256"] is None


@pytest.mark.asyncio
async def test_a_missing_bound_document_refuses_the_save(cloud):
    task, _document, user = _binding()

    with pytest.raises(HTTPException) as caught:
        await _save(task, None, user)

    assert caught.value.status_code == 409
    assert cloud.materializer.reads == 0


@pytest.mark.asyncio
async def test_a_copy_with_no_cloud_object_skips_the_read(cloud):
    task, document, user = _binding()
    document.provider_object_id = None

    await _save(task, document, user)

    assert cloud.materializer.reads == 0
    assert len(cloud.materializer.materialized) == 1


# --- D09: formatted DOCX drafts are never re-rendered from text -------------


@pytest.mark.asyncio
async def test_office_snapshot_drafts_refuse_text_saves(cloud):
    task, document, user = _binding(edit_mode="office_snapshot")

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user)

    assert caught.value.status_code == 409
    assert "cloud DOCX" in caught.value.detail
    assert cloud.materializer.reads == 0
    assert cloud.materializer.materialized == []


@pytest.mark.asyncio
async def test_truncated_previews_refuse_text_saves(cloud):
    task, document, user = _binding(preview_truncated=True)

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user)

    assert caught.value.status_code == 409
    assert "cut off" in caught.value.detail
    assert cloud.materializer.materialized == []


@pytest.mark.asyncio
async def test_legacy_text_mode_drafts_with_docx_bytes_refuse_text_saves(cloud):
    # Pending before D09 was fixed: the action says lawhand_text, but the
    # working copy was verified from real DOCX bytes.
    task, document, user = _binding()
    office = [{"source_mode": "external_cloud_docx_snapshot"}]

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user, office_events=office)

    assert caught.value.status_code == 409
    assert "cloud DOCX" in caught.value.detail
    assert cloud.materializer.reads == 0
    assert cloud.materializer.materialized == []


@pytest.mark.asyncio
async def test_discard_does_not_bypass_the_office_snapshot_guard(cloud):
    task, document, user = _binding(edit_mode="office_snapshot")

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user, discard=True)

    assert caught.value.status_code == 409
    assert cloud.events == []


@pytest.mark.asyncio
async def test_discard_flag_alone_is_not_an_edit(cloud):
    task, _document, user = _binding()
    db = FakeDB(task=task)
    payload = PendingActionEdit(expected_version=task.version, discard_cloud_edits=True)

    result = await routes.update_pending_action(
        task.id, payload, current_user=user, db=db
    )

    assert result["version"] == 3
    assert db.commits == 0
    assert cloud.materializer.reads == 0


@pytest.mark.asyncio
async def test_document_has_office_source_reads_the_verification_events():
    db = FakeDB(
        task=None,
        office_events=[
            {"source_mode": "lawhand_text_renderer"},
            None,
            {"source_mode": "external_cloud_docx_snapshot"},
        ],
    )
    assert await materialization.document_has_office_source(
        db, tenant_id=uuid.uuid4(), document_id=uuid.uuid4()
    )
    db.office_events = [{"source_mode": "lawhand_text_renderer"}]
    assert not await materialization.document_has_office_source(
        db, tenant_id=uuid.uuid4(), document_id=uuid.uuid4()
    )


@pytest.mark.asyncio
async def test_materializer_refuses_to_render_text_over_an_office_snapshot():
    tenant_id, matter_id, task_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    artifact = NS(
        id=uuid.uuid4(),
        matter_id=matter_id,
        current_revision_no=2,
        task_id=task_id,
        title="Engagement letter",
    )
    revision = NS(id=uuid.uuid4(), revision_no=2, content_text="Flattened text")
    task = NS(id=task_id)
    matter = NS(
        id=matter_id,
        cloud_folder={"onedrive": {"subfolders": {"documents": "folder-1"}}},
    )
    settings = NS(primary_cloud_provider="onedrive")
    db = FakeDB(
        task=None,
        scalars=[artifact, revision, task, matter, settings],
        office_events=[{"source_mode": "external_cloud_docx_snapshot"}],
    )

    with pytest.raises(materialization.OfficeSnapshotTextRenderRefused) as caught:
        await materialization.CloudArtifactMaterializer(
            file_store=object(), provider_db_factory=object()
        ).materialize(
            db=db,
            tenant_id=tenant_id,
            artifact_id=artifact.id,
            revision_id=revision.id,
            task_id=task_id,
            uploaded_by_user_id=uuid.uuid4(),
            supersedes_document_id=uuid.uuid4(),
        )

    assert caught.value.code == "office_snapshot_text_render_refused"
    assert isinstance(caught.value, materialization.CloudIntegrityError)


# --- Refresh edits from cloud ------------------------------------------------


async def _sync(task, document, user):
    db = FakeDB(task=task, scalars=[task, document])
    result = await routes.sync_pending_action_from_cloud(
        task.id,
        PendingActionCloudSync(expected_version=task.version),
        current_user=user,
        db=db,
    )
    return result, db


@pytest.mark.asyncio
async def test_sync_cloud_reverifies_an_unchanged_copy(cloud):
    task, document, user = _binding()
    before = dict(task.pending_action)

    result, db = await _sync(task, document, user)

    assert result["changed"] is False
    assert task.pending_action == before
    assert task.version == 3
    assert document.storage_state == "verified"
    assert document.storage_verified_at is not None
    assert cloud.materializer.materialized == []
    [event] = cloud.events
    assert event["event_type"] == "cloud_working_copy_reverified"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_sync_cloud_adopts_changed_bytes_as_an_office_snapshot(cloud):
    task, document, user = _binding()
    cloud.materializer.cloud_bytes = EDITED

    result, db = await _sync(task, document, user)

    assert result["changed"] is True
    [call] = cloud.materializer.materialized
    assert call["source_docx_bytes"] == EDITED
    assert call["supersedes_document_id"] == document.id
    action = task.pending_action
    assert action["document_edit_mode"] == "office_snapshot"
    assert action["document_sha256"] == _sha(EDITED)
    assert action["artifact_revision_no"] == 2
    assert "edited in Word Online" in action["body"]
    assert document.storage_state == "conflict"
    assert task.version == 4
    [event] = cloud.events
    assert event["event_type"] == "external_cloud_edit_adopted"
    assert event["metadata"]["previous_sha256"] == _sha(RECORDED)
    assert cloud.task_events[0]["event_type"] == "cloud_revision_adopted"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_after_adopting_cloud_edits_a_text_save_is_refused(cloud):
    task, document, user = _binding()
    cloud.materializer.cloud_bytes = EDITED
    await _sync(task, document, user)

    with pytest.raises(HTTPException) as caught:
        await _save(task, document, user)

    assert caught.value.status_code == 409
    assert len(cloud.materializer.materialized) == 1


@pytest.mark.asyncio
async def test_sync_cloud_surfaces_provider_outages(cloud):
    task, document, user = _binding()
    cloud.materializer.read_error = ProviderError("Graph is down")

    with pytest.raises(HTTPException) as caught:
        await _sync(task, document, user)

    assert caught.value.status_code == 503
    assert cloud.events == []
