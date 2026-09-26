"""Resumable fill sessions: owned, encrypted, resumable, and saved in the background."""

import uuid
import asyncio

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import set_tenant_context
from app.models.document_fill_session import DocumentFillSession
from app.models.matter_document import MatterDocument
from app.models.plugin import Matter
from app.models.user import User
from app.schemas.fill_session import FillSessionWrite
from app.services import fill_sessions
from tests.test_document_templates import _grant_manage_documents

pytestmark = pytest.mark.asyncio


async def _matter(db_session, tenant_id, user_id):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        slug=f"fs-{uuid.uuid4().hex[:8]}",
        matter_name="Session matter",
    )
    db_session.add(matter)
    await db_session.commit()
    return matter


def test_answers_round_trip_through_the_vault_and_digest_deterministically():
    answers = {"defendant.full_name": "Ada Lovelace", "manual:x:note": "typed"}
    sealed = fill_sessions.encrypt_answers(answers)
    # Fernet tokens are base64url, so a short name can appear in one by chance;
    # a space, a dot or a quote cannot, which makes these plaintext checks exact.
    assert (
        sealed and "Ada Lovelace" not in sealed and "defendant.full_name" not in sealed
    )
    assert fill_sessions.decrypt_answers(sealed) == answers
    assert fill_sessions.decrypt_answers("") == {}
    assert fill_sessions.decrypt_answers("not-a-token") == {}
    assert fill_sessions._digest(answers) == fill_sessions._digest(
        dict(reversed(list(answers.items())))
    )


async def test_a_session_is_created_resumed_listed_without_answers_and_owned(
    client, db_session, test_tenant, test_user
):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    set_id = uuid.uuid4()
    created = await client.post(
        "/api/fill-sessions",
        json={
            "matter_id": str(matter.id),
            "set_id": str(set_id),
            "title": "Motion packet",
            "versions": {"a": 2},
            "answers": {"defendant.full_name": "Ada"},
            "verified": ["defendant.full_name"],
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert (
        body["status"] == "open"
        and body["answers"] is None
        and body["verified"] == ["defendant.full_name"]
    )
    session_id = body["id"]

    read = await client.get(f"/api/fill-sessions/{session_id}")
    assert read.status_code == 200, read.text
    assert read.json()["answers"] == {"defendant.full_name": "Ada"}
    assert read.json()["versions"] == {"a": 2}

    updated = await client.post(
        "/api/fill-sessions",
        json={
            "id": session_id,
            "matter_id": str(matter.id),
            "set_id": str(set_id),
            "title": "Motion packet",
            "answers": {"defendant.full_name": "Ada", "manual:b:hearing": "2026-10-01"},
            "verified": [],
        },
    )
    assert updated.status_code == 200 and updated.json()["id"] == session_id
    assert (await client.get(f"/api/fill-sessions/{session_id}")).json()["answers"][
        "manual:b:hearing"
    ] == "2026-10-01"

    listed = await client.get(f"/api/matters/{matter.id}/fill-sessions")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [session_id]
    assert listed.json()["items"][0]["answers"] is None

    # The stored answers are ciphertext, and the row belongs to its owner only.
    await set_tenant_context(db_session, str(test_tenant.id))
    row = await db_session.scalar(
        select(DocumentFillSession).where(
            DocumentFillSession.id == uuid.UUID(session_id)
        )
    )
    assert (
        '"Ada"' not in row.answers_ciphertext
        and "defendant.full_name" not in row.answers_ciphertext
    )
    other = SimpleNamespace(id=uuid.uuid4(), tenant_id=test_tenant.id)
    with pytest.raises(HTTPException) as caught:
        await fill_sessions._own_session(db_session, other, uuid.UUID(session_id))
    assert caught.value.status_code == 404

    both = await client.post(
        "/api/fill-sessions",
        json={"template_id": str(uuid.uuid4()), "set_id": str(set_id)},
    )
    assert both.status_code == 422

    gone = await client.delete(f"/api/fill-sessions/{session_id}")
    assert gone.status_code == 204
    assert (await client.get(f"/api/fill-sessions/{session_id}")).status_code == 200
    assert (await client.get(f"/api/matters/{matter.id}/fill-sessions")).json()[
        "items"
    ] == []


async def test_a_finished_session_is_not_reopened_by_a_later_write(
    client, db_session, test_tenant, test_user
):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    set_id = uuid.uuid4()
    created = await client.post(
        "/api/fill-sessions",
        json={
            "matter_id": str(matter.id),
            "set_id": str(set_id),
            "title": "Packet",
            "answers": {"q": "v"},
            "verified": ["q"],
        },
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]

    # The background save finished; a later autosave must not reopen the
    # session or erase the per-member outcomes.
    await set_tenant_context(db_session, str(test_tenant.id))
    row = await db_session.scalar(
        select(DocumentFillSession).where(
            DocumentFillSession.id == uuid.UUID(session_id)
        )
    )
    row.status = "saved"
    row.members_json = [
        {"template_id": "t", "status": "saved", "output_filename": "x.pdf"}
    ]
    await db_session.commit()

    again = await client.post(
        "/api/fill-sessions",
        json={
            "id": session_id,
            "matter_id": str(matter.id),
            "set_id": str(set_id),
            "answers": {"q": "v2"},
            "verified": [],
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "saved"
    assert again.json()["members"][0]["status"] == "saved"
    assert (await client.get(f"/api/fill-sessions/{session_id}")).json()["answers"] == {
        "q": "v"
    }


async def test_single_session_complete_validates_document_binding_and_is_idempotent(
    client, db_session, test_tenant, test_user
):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    await set_tenant_context(db_session, str(test_tenant.id))
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    template_id = uuid.uuid4()
    owner = SimpleNamespace(id=test_user.id, tenant_id=test_tenant.id)
    session = await fill_sessions.upsert(
        db_session,
        owner,
        FillSessionWrite(
            matter_id=matter.id, template_id=template_id, answers={"q": "v"}
        ),
    )
    wrong_matter = await _matter(db_session, test_tenant.id, test_user.id)
    other_user = User(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        email=f"other-{uuid.uuid4().hex[:8]}@testfirm.com",
        full_name="Other Attorney",
        role="admin",
        oauth_provider="google",
        oauth_subject=f"google-other-{uuid.uuid4().hex}",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()
    wrong_matter_doc = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=wrong_matter.id,
        uploaded_by_user_id=test_user.id,
        filename="wrong-matter.pdf",
        generation_summary={"template_id": str(template_id)},
    )
    wrong_template_doc = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=matter.id,
        uploaded_by_user_id=test_user.id,
        filename="wrong-template.pdf",
        generation_summary={"template_id": str(uuid.uuid4())},
    )
    wrong_session_doc = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=matter.id,
        uploaded_by_user_id=test_user.id,
        filename="wrong-session.pdf",
        generation_summary={
            "template_id": str(template_id),
            "fill_session_id": str(uuid.uuid4()),
        },
    )
    wrong_owner_doc = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=matter.id,
        uploaded_by_user_id=other_user.id,
        filename="wrong-owner.pdf",
        generation_summary={"template_id": str(template_id)},
    )
    valid_doc = MatterDocument(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        matter_id=matter.id,
        uploaded_by_user_id=test_user.id,
        filename="valid.pdf",
        generation_summary={
            "template_id": str(template_id),
            "fill_session_id": str(session.id),
        },
    )
    db_session.add_all(
        [
            wrong_matter_doc,
            wrong_template_doc,
            wrong_session_doc,
            wrong_owner_doc,
            valid_doc,
        ]
    )
    await db_session.commit()
    for document_id in (
        wrong_matter_doc.id,
        wrong_template_doc.id,
        wrong_session_doc.id,
        wrong_owner_doc.id,
    ):
        with pytest.raises(HTTPException) as caught:
            await fill_sessions.complete(db_session, owner, session.id, document_id)
        assert caught.value.status_code == 409
    session.status = "saving"
    await db_session.commit()
    with pytest.raises(HTTPException) as caught:
        await fill_sessions.complete(db_session, owner, session.id, valid_doc.id)
    assert caught.value.status_code == 409
    session.status = "open"
    await db_session.commit()
    completed_response = await client.post(
        f"/api/fill-sessions/{session.id}/complete",
        json={"matter_document_id": str(valid_doc.id)},
    )
    assert completed_response.status_code == 200, completed_response.text
    assert completed_response.json()["status"] == "saved"
    assert completed_response.json()["members"][0]["matter_document_id"] == str(
        valid_doc.id
    )
    repeated = await fill_sessions.complete(db_session, owner, session.id, valid_doc.id)
    assert repeated.status == "saved"
    with pytest.raises(HTTPException) as caught:
        await fill_sessions.complete(
            db_session, owner, session.id, wrong_template_doc.id
        )
    assert caught.value.status_code == 409
    late = await fill_sessions.upsert(
        db_session,
        owner,
        FillSessionWrite(
            id=session.id,
            matter_id=matter.id,
            template_id=template_id,
            answers={"q": "late"},
        ),
    )
    assert late.status == "saved"
    assert fill_sessions.decrypt_answers(late.answers_ciphertext) == {"q": "v"}


async def test_single_session_complete_rejects_a_foreign_tenant_user(
    db_session, test_tenant, test_user
):
    await set_tenant_context(db_session, str(test_tenant.id))
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    session = await fill_sessions.upsert(
        db_session,
        SimpleNamespace(id=test_user.id, tenant_id=test_tenant.id),
        FillSessionWrite(matter_id=matter.id, template_id=uuid.uuid4()),
    )
    with pytest.raises(HTTPException) as caught:
        await fill_sessions.complete(
            db_session,
            SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4()),
            session.id,
            uuid.uuid4(),
        )
    assert caught.value.status_code == 404


async def test_upsert_waits_for_completion_lock_before_reading_saved_status(
    db_session, test_engine, test_tenant, test_user
):
    await set_tenant_context(db_session, str(test_tenant.id))
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    owner = SimpleNamespace(id=test_user.id, tenant_id=test_tenant.id)
    session = await fill_sessions.upsert(
        db_session,
        owner,
        FillSessionWrite(
            matter_id=matter.id, template_id=uuid.uuid4(), answers={"q": "original"}
        ),
    )
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    first, second = session_factory(), session_factory()
    try:
        locked = await fill_sessions._own_session(
            first, owner, session.id, for_update=True
        )
        locked.status = "saved"
        locked.members_json = [
            {"template_id": str(session.template_id), "status": "saved"}
        ]
        late_write = asyncio.create_task(
            fill_sessions.upsert(
                second,
                owner,
                FillSessionWrite(
                    id=session.id,
                    matter_id=matter.id,
                    template_id=session.template_id,
                    answers={"q": "stale"},
                ),
            )
        )
        await asyncio.sleep(0.05)
        assert not late_write.done(), "upsert must wait on the completion row lock"
        await first.commit()
        result = await asyncio.wait_for(late_write, timeout=2)
        assert result.status == "saved"
        assert fill_sessions.decrypt_answers(result.answers_ciphertext) == {
            "q": "original"
        }
    finally:
        await first.close()
        await second.close()


async def test_verified_counts_feed_the_readiness_record(
    db_session, test_tenant, test_user
):
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    template_id = uuid.uuid4()
    await set_tenant_context(db_session, str(test_tenant.id))
    user = SimpleNamespace(id=test_user.id, tenant_id=test_tenant.id)
    from app.schemas.fill_session import FillSessionWrite

    await fill_sessions.upsert(
        db_session,
        user,
        FillSessionWrite(
            matter_id=matter.id,
            template_id=template_id,
            answers={"a": "1", "b": "2"},
            verified=["a", "b"],
        ),
    )
    counts = await fill_sessions.verified_counts(
        db_session, tenant_id=test_tenant.id, matter_id=matter.id
    )
    assert counts == {str(template_id): 2}


async def test_background_save_calls_the_render_endpoint_as_the_owner_and_reports_each_member(
    client, db_session, test_tenant, test_user, monkeypatch
):
    from app.routers import document_templates
    from app.schemas.fill_session import FillSessionRenderRequest, FillSessionWrite

    await _grant_manage_documents(db_session, test_tenant, test_user)
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    await set_tenant_context(db_session, str(test_tenant.id))
    owner = await db_session.get(User, test_user.id)
    owner_id, tenant_id, matter_id = test_user.id, test_tenant.id, matter.id
    good, bad = uuid.uuid4(), uuid.uuid4()
    session = await fill_sessions.upsert(
        db_session,
        owner,
        FillSessionWrite(
            matter_id=matter.id, set_id=uuid.uuid4(), answers={"q": "v"}, verified=["q"]
        ),
    )
    preview = uuid.uuid4()
    session = await fill_sessions.enqueue_render(
        db_session,
        owner,
        session.id,
        FillSessionRenderRequest(
            members=[
                {
                    "template_id": str(good),
                    "variables": {"client_name": "Ada", "other": "x"},
                    "preview_id": str(preview),
                    "output_format": "pdf",
                    "verified_fields": ["client_name"],
                },
                {
                    "template_id": str(bad),
                    "variables": {"client_name": "Ada"},
                    "preview_id": None,
                    "output_format": "markdown",
                },
            ]
        ),
    )
    assert session.status == "saving" and session.job_id is not None
    session_id, job_id = session.id, session.job_id
    with pytest.raises(HTTPException):
        await fill_sessions.enqueue_render(
            db_session,
            owner,
            session.id,
            FillSessionRenderRequest(members=[{"template_id": str(good)}]),
        )

    calls = []

    async def fake_render(template_id, payload, current_user=None, db=None):
        calls.append((template_id, payload, current_user.id))
        if template_id == bad:
            raise HTTPException(
                status_code=409, detail="The generation preview no longer matches"
            )
        return SimpleNamespace(
            matter_document_id=str(uuid.uuid4()),
            output_filename="motion.pdf",
            output_format="pdf",
            signing_roles=["client"],
            positioned_fields=[{"field_id": "f1"}],
            signing_placement_required=True,
        )

    monkeypatch.setattr(document_templates, "render_template_endpoint", fake_render)
    from app.models.durable_job import DurableJob

    job = await db_session.get(DurableJob, job_id)
    result = await fill_sessions.run_set_render_job(db_session, job)
    assert result == {"outcome": "partial", "saved": 1, "total": 2}
    assert [call[0] for call in calls] == [good, bad]
    assert calls[0][2] == owner_id
    assert calls[0][1].preview_id == preview and calls[0][1].verified_fields == [
        "client_name"
    ]
    assert calls[0][1].matter_id == str(matter_id)

    await set_tenant_context(db_session, str(tenant_id))
    row = await db_session.get(DocumentFillSession, session_id)
    assert row.status == "open"
    statuses = {item["template_id"]: item for item in row.members_json}
    assert (
        statuses[str(good)]["status"] == "saved"
        and statuses[str(good)]["output_filename"] == "motion.pdf"
    )
    # The signing descriptor travels with the saved member so a packet saved in
    # the background can still be sent for signature after it is reopened.
    assert statuses[str(good)]["signing_roles"] == ["client"]
    assert statuses[str(good)]["positioned_fields"] == [{"field_id": "f1"}]
    assert statuses[str(good)]["signing_placement_required"] is True
    assert statuses[str(bad)] == {
        "template_id": str(bad),
        "status": "preview_expired",
        "detail": "Preview expired; review it again.",
    }
    assert "1 of 2" in row.last_error

    # Retrying after a lost queue acknowledgement carries only the member
    # that still needs work; the successful member is never rendered again.
    retry = await fill_sessions.enqueue_render(
        db_session,
        owner,
        session_id,
        FillSessionRenderRequest(
            members=[
                {
                    "template_id": str(good),
                    "variables": {"client_name": "Ada", "other": "x"},
                    "preview_id": str(preview),
                    "output_format": "pdf",
                    "verified_fields": ["client_name"],
                },
                {
                    "template_id": str(bad),
                    "variables": {"client_name": "Ada"},
                    "preview_id": None,
                    "output_format": "markdown",
                },
            ]
        ),
    )
    retry_statuses = {item["template_id"]: item for item in retry.members_json}
    assert retry_statuses[str(good)]["status"] == "saved"
    assert retry_statuses[str(bad)]["status"] == "queued"
    retry_job = await db_session.get(DurableJob, retry.job_id)
    retry_job.payload = {
        key: value for key, value in retry_job.payload.items() if key != "job_id"
    }
    await db_session.commit()
    await db_session.refresh(retry_job)
    calls.clear()
    await fill_sessions.run_set_render_job(db_session, retry_job)
    assert [call[0] for call in calls] == [bad]

    # Replaying an old job after a newer save owns the session must not mutate
    # that newer job's state or its member results.
    row = await db_session.get(DocumentFillSession, session_id)
    row.status = "saving"
    row.job_id = uuid.uuid4()
    row.last_error = "owned by a newer save"
    current_members = list(row.members_json)
    await db_session.commit()
    await db_session.refresh(retry_job)
    stale = await fill_sessions.run_set_render_job(db_session, retry_job)
    assert stale["failure_code"] == "stale_job"
    await db_session.refresh(row)
    assert row.status == "saving" and row.last_error == "owned by a newer save"
    assert row.members_json == current_members

    # The same replay after completion leaves the final saved result intact.
    row.status = "saved"
    row.last_error = "completed"
    completed_members = list(row.members_json)
    await db_session.commit()
    await db_session.refresh(retry_job)
    stale_completed = await fill_sessions.run_set_render_job(db_session, retry_job)
    assert stale_completed["failure_code"] == "stale_job"
    await db_session.refresh(row)
    assert row.status == "saved" and row.last_error == "completed"
    assert row.members_json == completed_members

    # A user who can no longer save documents blocks the job rather than saving as nobody.
    monkeypatch.setattr(
        "app.services.rbac_service.get_user_capabilities",
        lambda db, user_id: _no_caps(),
    )
    # Requeue the current job state for the actor check; the worker must still
    # reject the save when the preparer has lost the required capability.
    row.status = "saving"
    row.job_id = retry_job.id
    row.last_error = None
    await db_session.commit()
    await db_session.refresh(retry_job)
    blocked = await fill_sessions.run_set_render_job(db_session, retry_job)
    assert blocked["failure_code"] == "actor_unavailable"


async def _no_caps():
    return set()


def test_migration_198_is_tenant_isolated_and_encrypts_nothing_in_clear():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "198_document_fill_sessions.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "197_document_evidence"' in source
    assert (
        "FORCE ROW LEVEL SECURITY" in source
        and "document_fill_sessions_tenant_isolation" in source
    )
    assert "answers_ciphertext" in source and "expires_at" in source
    assert "(template_id IS NOT NULL) <> (set_id IS NOT NULL)" in source
