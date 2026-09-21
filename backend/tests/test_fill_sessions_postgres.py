"""Resumable fill sessions: owned, encrypted, resumable, and saved in the background."""

import uuid

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.database import set_tenant_context
from app.models.document_fill_session import DocumentFillSession
from app.models.plugin import Matter
from app.models.user import User
from app.services import fill_sessions
from tests.test_document_templates import _grant_manage_documents

pytestmark = pytest.mark.asyncio


async def _matter(db_session, tenant_id, user_id):
    matter = Matter(id=uuid.uuid4(), tenant_id=tenant_id, user_id=user_id, slug=f"fs-{uuid.uuid4().hex[:8]}", matter_name="Session matter")
    db_session.add(matter)
    await db_session.commit()
    return matter


def test_answers_round_trip_through_the_vault_and_digest_deterministically():
    answers = {"defendant.full_name": "Ada Lovelace", "manual:x:note": "typed"}
    sealed = fill_sessions.encrypt_answers(answers)
    assert sealed and "Ada" not in sealed
    assert fill_sessions.decrypt_answers(sealed) == answers
    assert fill_sessions.decrypt_answers("") == {}
    assert fill_sessions.decrypt_answers("not-a-token") == {}
    assert fill_sessions._digest(answers) == fill_sessions._digest(dict(reversed(list(answers.items()))))


async def test_a_session_is_created_resumed_listed_without_answers_and_owned(
    client, db_session, test_tenant, test_user
):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    set_id = uuid.uuid4()
    created = await client.post("/api/fill-sessions", json={
        "matter_id": str(matter.id), "set_id": str(set_id), "title": "Motion packet",
        "versions": {"a": 2}, "answers": {"defendant.full_name": "Ada"}, "verified": ["defendant.full_name"],
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "open" and body["answers"] is None and body["verified"] == ["defendant.full_name"]
    session_id = body["id"]

    read = await client.get(f"/api/fill-sessions/{session_id}")
    assert read.status_code == 200, read.text
    assert read.json()["answers"] == {"defendant.full_name": "Ada"}
    assert read.json()["versions"] == {"a": 2}

    updated = await client.post("/api/fill-sessions", json={
        "id": session_id, "matter_id": str(matter.id), "set_id": str(set_id), "title": "Motion packet",
        "answers": {"defendant.full_name": "Ada", "manual:b:hearing": "2026-10-01"}, "verified": [],
    })
    assert updated.status_code == 200 and updated.json()["id"] == session_id
    assert (await client.get(f"/api/fill-sessions/{session_id}")).json()["answers"]["manual:b:hearing"] == "2026-10-01"

    listed = await client.get(f"/api/matters/{matter.id}/fill-sessions")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [session_id]
    assert listed.json()["items"][0]["answers"] is None

    # The stored answers are ciphertext, and the row belongs to its owner only.
    await set_tenant_context(db_session, str(test_tenant.id))
    row = await db_session.scalar(select(DocumentFillSession).where(DocumentFillSession.id == uuid.UUID(session_id)))
    assert "Ada" not in row.answers_ciphertext
    other = SimpleNamespace(id=uuid.uuid4(), tenant_id=test_tenant.id)
    with pytest.raises(HTTPException) as caught:
        await fill_sessions._own_session(db_session, other, uuid.UUID(session_id))
    assert caught.value.status_code == 404

    both = await client.post("/api/fill-sessions", json={"template_id": str(uuid.uuid4()), "set_id": str(set_id)})
    assert both.status_code == 422

    gone = await client.delete(f"/api/fill-sessions/{session_id}")
    assert gone.status_code == 204
    assert (await client.get(f"/api/fill-sessions/{session_id}")).status_code == 200
    assert (await client.get(f"/api/matters/{matter.id}/fill-sessions")).json()["items"] == []


async def test_a_finished_session_is_not_reopened_by_a_later_write(client, db_session, test_tenant, test_user):
    await _grant_manage_documents(db_session, test_tenant, test_user)
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    set_id = uuid.uuid4()
    created = await client.post("/api/fill-sessions", json={
        "matter_id": str(matter.id), "set_id": str(set_id), "title": "Packet",
        "answers": {"q": "v"}, "verified": ["q"],
    })
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]

    # The background save finished; a later autosave must not reopen the
    # session or erase the per-member outcomes.
    await set_tenant_context(db_session, str(test_tenant.id))
    row = await db_session.scalar(select(DocumentFillSession).where(DocumentFillSession.id == uuid.UUID(session_id)))
    row.status = "saved"
    row.members_json = [{"template_id": "t", "status": "saved", "output_filename": "x.pdf"}]
    await db_session.commit()

    again = await client.post("/api/fill-sessions", json={
        "id": session_id, "matter_id": str(matter.id), "set_id": str(set_id), "answers": {"q": "v2"}, "verified": [],
    })
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "saved"
    assert again.json()["members"][0]["status"] == "saved"


async def test_verified_counts_feed_the_readiness_record(db_session, test_tenant, test_user):
    matter = await _matter(db_session, test_tenant.id, test_user.id)
    template_id = uuid.uuid4()
    await set_tenant_context(db_session, str(test_tenant.id))
    user = SimpleNamespace(id=test_user.id, tenant_id=test_tenant.id)
    from app.schemas.fill_session import FillSessionWrite

    await fill_sessions.upsert(db_session, user, FillSessionWrite(matter_id=matter.id, template_id=template_id, answers={"a": "1", "b": "2"}, verified=["a", "b"]))
    counts = await fill_sessions.verified_counts(db_session, tenant_id=test_tenant.id, matter_id=matter.id)
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
    session = await fill_sessions.upsert(db_session, owner, FillSessionWrite(matter_id=matter.id, set_id=uuid.uuid4(), answers={"q": "v"}, verified=["q"]))
    preview = uuid.uuid4()
    session = await fill_sessions.enqueue_render(db_session, owner, session.id, FillSessionRenderRequest(members=[
        {"template_id": str(good), "variables": {"client_name": "Ada", "other": "x"}, "preview_id": str(preview), "output_format": "pdf", "verified_fields": ["client_name"]},
        {"template_id": str(bad), "variables": {"client_name": "Ada"}, "preview_id": None, "output_format": "markdown"},
    ]))
    assert session.status == "saving" and session.job_id is not None
    session_id, job_id = session.id, session.job_id
    with pytest.raises(HTTPException):
        await fill_sessions.enqueue_render(db_session, owner, session.id, FillSessionRenderRequest(members=[{"template_id": str(good)}]))

    calls = []

    async def fake_render(template_id, payload, current_user=None, db=None):
        calls.append((template_id, payload, current_user.id))
        if template_id == bad:
            raise HTTPException(status_code=409, detail="The generation preview no longer matches")
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
    assert calls[0][1].preview_id == preview and calls[0][1].verified_fields == ["client_name"]
    assert calls[0][1].matter_id == str(matter_id)

    await set_tenant_context(db_session, str(tenant_id))
    row = await db_session.get(DocumentFillSession, session_id)
    assert row.status == "open"
    statuses = {item["template_id"]: item for item in row.members_json}
    assert statuses[str(good)]["status"] == "saved" and statuses[str(good)]["output_filename"] == "motion.pdf"
    # The signing descriptor travels with the saved member so a packet saved in
    # the background can still be sent for signature after it is reopened.
    assert statuses[str(good)]["signing_roles"] == ["client"]
    assert statuses[str(good)]["positioned_fields"] == [{"field_id": "f1"}]
    assert statuses[str(good)]["signing_placement_required"] is True
    assert statuses[str(bad)] == {"template_id": str(bad), "status": "preview_expired", "detail": "Preview expired; review it again."}
    assert "1 of 2" in row.last_error

    # A user who can no longer save documents blocks the job rather than saving as nobody.
    monkeypatch.setattr("app.services.rbac_service.get_user_capabilities", lambda db, user_id: _no_caps())
    # The job row expired with the first run's rollbacks; read it afresh.
    await db_session.refresh(job)
    blocked = await fill_sessions.run_set_render_job(db_session, job)
    assert blocked["failure_code"] == "actor_unavailable"


async def _no_caps():
    return set()


def test_migration_198_is_tenant_isolated_and_encrypts_nothing_in_clear():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "migrations" / "versions" / "198_document_fill_sessions.py").read_text(encoding="utf-8")
    assert 'down_revision = "197_document_evidence"' in source
    assert "FORCE ROW LEVEL SECURITY" in source and "document_fill_sessions_tenant_isolation" in source
    assert "answers_ciphertext" in source and "expires_at" in source
    assert "(template_id IS NOT NULL) <> (set_id IS NOT NULL)" in source
