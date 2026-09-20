"""Phase 2c: a workflow template requests documents; applying a run prepares them.

Real routes and rows. A version with a ``documents`` list is authored and
approved through the same capability boundary as any other; the preview
resolves each document against the firm's templates; apply opens one
Smart Fill session per document, pre-filled from the matter, and a
"Prepare" task for the assignee, recorded as a ``document_propose`` step;
rollback cancels the task and abandons the session unless the document was
already saved. Nothing here renders or files a document.
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models.document_fill_session import DocumentFillSession
from app.models.plugin import Matter
from app.models.task import Task
from app.services import fill_sessions
from app.services.configurable_workflows import stored_definition_payload
from tests.test_configurable_workflow_routes import DEFINITION, _grant
from tests.test_document_prefill import _published_pdf_template

pytestmark = pytest.mark.asyncio


def _definition(template_id, *, assignee_role="matter_owner"):
    return {
        **DEFINITION,
        "documents": [
            {
                "item_key": "engagement",
                "stage_key": "initial",
                "template_id": str(template_id),
                "title": "Engagement letter",
                "due_offset_days": 3,
                "assignee_role": assignee_role,
            }
        ],
    }


async def _approved(client, db, tenant, user, definition, name="Opening with documents"):
    role = await _grant(db, tenant, user, capabilities=["manage_workflows"])
    created = await client.post(
        "/api/workflow-config/templates", json={"name": name, **definition}
    )
    assert created.status_code == 201, created.text
    template = created.json()
    role.capabilities = ["approve_legal_work"]
    await db.commit()
    approved = await client.post(
        f"/api/workflow-config/templates/{template['id']}/versions/"
        f"{template['version_id']}/approve"
    )
    assert approved.status_code == 200, approved.text
    role.capabilities = ["approve_legal_work", "manage_matters"]
    await db.commit()
    return role, template, approved.json()


async def _matter(db, tenant, user):
    matter = Matter(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"documents-{uuid.uuid4()}",
        matter_name="Lovelace v. Babbage",
        case_number="08-2026-CV-00042",
        stage="New",
    )
    db.add(matter)
    await db.commit()
    return matter


async def _preview_and_apply(client, matter_id, version_id, *, key):
    preview = await client.post(
        f"/api/matters/{matter_id}/workflow-runs/preview",
        params={"template_version_id": version_id},
        headers={"Idempotency-Key": key},
    )
    assert preview.status_code == 201, preview.text
    body = preview.json()
    applied = await client.post(
        f"/api/matters/{matter_id}/workflow-runs/{body['run_id']}/apply",
        json={"preview_sha256": body["preview_sha256"], "confirm_apply": True},
    )
    return body, applied


async def test_documents_are_authored_previewed_and_prepared_on_apply(
    client, db_session, test_tenant, test_user
):
    tenant_id, user_id = test_tenant.id, test_user.id
    document_template = await _published_pdf_template(db_session, tenant_id)
    document_template_id = document_template.id
    role, template, approved = await _approved(
        client, db_session, test_tenant, test_user, _definition(document_template_id)
    )
    assert approved["documents"] == [
        {
            "item_key": "engagement",
            "stage_key": "initial",
            "template_id": str(document_template_id),
            "title": "Engagement letter",
            "due_offset_days": 3,
            "assignee_role": "matter_owner",
        }
    ]
    matter = await _matter(db_session, test_tenant, test_user)
    matter_id = matter.id

    preview, applied = await _preview_and_apply(
        client, matter_id, template["version_id"], key="documents-preview"
    )
    (entry,) = preview["documents"]
    assert entry["available"] is True
    assert entry["title"] == "Engagement letter"
    assert entry["template_version_no"] == 1
    assert entry["assigned_to_user_id"] == str(user_id)
    assert preview["can_apply"] is True
    assert applied.status_code == 200, applied.text
    run = applied.json()
    assert run["status"] == "applied"

    steps = [s for s in run["steps"] if s["step_type"] == "document_propose"]
    assert len(steps) == 1 and steps[0]["status"] == "succeeded"
    evidence = steps[0]["evidence"]
    assert evidence["document_template_id"] == str(document_template_id)
    assert evidence["fields"] > 0 and evidence["filled"] >= 1
    assert evidence["fill_session_owner_user_id"] == str(user_id)
    # Counts and names only: no value of the matter reaches the evidence.
    assert "Lovelace" not in str(evidence) and "00042" not in str(evidence)
    applied_event = next(e for e in run["events"] if e["event_type"] == "applied")
    assert applied_event["detail"]["document_count"] == 1

    session = await db_session.get(
        DocumentFillSession, uuid.UUID(evidence["fill_session_id"])
    )
    assert session.status == "open"
    assert session.user_id == user_id
    assert session.template_id == document_template_id
    assert session.matter_id == matter_id
    assert session.versions_json == {str(document_template_id): 1}
    answers = fill_sessions.decrypt_answers(session.answers_ciphertext)
    assert answers.get("case_number") == "08-2026-CV-00042"

    task = await db_session.get(Task, uuid.UUID(steps[0]["task_id"]))
    assert task.title == "Prepare Engagement letter"
    assert task.source == "workflow"
    assert task.assigned_to_user_id == user_id
    assert evidence["prepare_path"] in task.description
    assert (
        f"/templates/prepare?template={document_template_id}&matter={matter_id}"
        f"&session={session.id}"
    ) == evidence["prepare_path"]
    # The checklist task and the Prepare task.
    assert await db_session.scalar(select(func.count(Task.id))) == 2

    # The assignee finds it under "Documents in progress" and can resume it.
    session_id = session.id
    role.capabilities = ["manage_documents"]
    await db_session.commit()
    listed = await client.get(f"/api/matters/{matter_id}/fill-sessions")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(session_id)]
    resumed = await client.get(f"/api/fill-sessions/{session_id}")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["answers"]["case_number"] == "08-2026-CV-00042"
    assert resumed.json()["verified"] == []


async def test_an_unavailable_template_is_reported_and_blocks_only_its_step(
    client, db_session, test_tenant, test_user
):
    tenant_id = test_tenant.id
    document_template = await _published_pdf_template(db_session, tenant_id)
    _role, template, _approval = await _approved(
        client, db_session, test_tenant, test_user, _definition(document_template.id)
    )
    document_template.is_active = False
    await db_session.commit()
    matter = await _matter(db_session, test_tenant, test_user)
    matter_id = matter.id

    preview, applied = await _preview_and_apply(
        client, matter_id, template["version_id"], key="documents-archived"
    )
    (entry,) = preview["documents"]
    assert entry["available"] is False
    assert entry["unavailable_reason"] == "The document template is archived."
    assert preview["can_apply"] is True
    assert applied.status_code == 200, applied.text
    (step,) = [
        s for s in applied.json()["steps"] if s["step_type"] == "document_propose"
    ]
    assert step["status"] == "blocked"
    assert step["evidence"]["reason"] == "The document template is archived."
    assert await db_session.scalar(select(func.count(DocumentFillSession.id))) == 0
    assert await db_session.scalar(select(func.count(Task.id))) == 1


async def test_rollback_cancels_the_task_and_abandons_the_session(
    client, db_session, test_tenant, test_user
):
    document_template = await _published_pdf_template(db_session, test_tenant.id)
    _role, template, _approval = await _approved(
        client, db_session, test_tenant, test_user, _definition(document_template.id)
    )
    matter = await _matter(db_session, test_tenant, test_user)
    matter_id = matter.id
    _preview, applied = await _preview_and_apply(
        client, matter_id, template["version_id"], key="documents-rollback"
    )
    run = applied.json()
    (step,) = [s for s in run["steps"] if s["step_type"] == "document_propose"]
    session_id = uuid.UUID(step["evidence"]["fill_session_id"])
    task_id = uuid.UUID(step["task_id"])

    rolled = await client.post(
        f"/api/matters/{matter_id}/workflow-runs/{run['id']}/rollback",
        json={"reason": "Wrong template"},
        headers={"Idempotency-Key": "documents-rollback-1"},
    )
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["status"] == "rolled_back"
    cancel = next(
        s
        for s in rolled.json()["steps"]
        if s["step_type"] == "task_cancel" and s["action_key"] == "engagement"
    )
    assert cancel["evidence"]["fill_session_abandoned"] is True
    assert cancel["evidence"]["fill_session_id"] == str(session_id)
    session = await db_session.get(DocumentFillSession, session_id)
    await db_session.refresh(session)
    assert session.status == "abandoned" and session.answers_ciphertext == ""
    task = await db_session.get(Task, task_id)
    await db_session.refresh(task)
    assert task.status == "cancelled"


async def test_a_saved_document_blocks_rollback(
    client, db_session, test_tenant, test_user
):
    document_template = await _published_pdf_template(db_session, test_tenant.id)
    _role, template, _approval = await _approved(
        client, db_session, test_tenant, test_user, _definition(document_template.id)
    )
    matter = await _matter(db_session, test_tenant, test_user)
    matter_id = matter.id
    _preview, applied = await _preview_and_apply(
        client, matter_id, template["version_id"], key="documents-saved"
    )
    run = applied.json()
    (step,) = [s for s in run["steps"] if s["step_type"] == "document_propose"]
    session = await db_session.get(
        DocumentFillSession, uuid.UUID(step["evidence"]["fill_session_id"])
    )
    session.status = "saved"
    await db_session.commit()

    rolled = await client.post(
        f"/api/matters/{matter_id}/workflow-runs/{run['id']}/rollback",
        json={"reason": "Too late"},
        headers={"Idempotency-Key": "documents-saved-rollback"},
    )
    assert rolled.status_code == 409, rolled.text
    detail = rolled.json()["detail"]
    assert "document engagement was already saved from its session" in str(detail)
    task = await db_session.get(Task, uuid.UUID(step["task_id"]))
    await db_session.refresh(task)
    assert task.status == "pending"


async def test_definition_validation_and_digest_stability(
    client, db_session, test_tenant, test_user
):
    await _grant(db_session, test_tenant, test_user, capabilities=["manage_workflows"])
    template_id = uuid.uuid4()
    bad_stage = await client.post(
        "/api/workflow-config/templates",
        json={
            "name": "Bad stage",
            **DEFINITION,
            "documents": [
                {"item_key": "letter", "stage_key": "nowhere", "template_id": str(template_id)}
            ],
        },
    )
    assert bad_stage.status_code == 422
    repeated_key = await client.post(
        "/api/workflow-config/templates",
        json={
            "name": "Repeated key",
            **DEFINITION,
            "documents": [
                {"item_key": "review", "stage_key": "initial", "template_id": str(template_id)}
            ],
        },
    )
    assert repeated_key.status_code == 422

    # A version without documents digests exactly as it did before documents
    # existed, so every approved definition keeps its signed hash.
    class _Version:
        initial_stage_key = "initial"

    payload = stored_definition_payload(_Version(), [], [], [], [])
    assert "documents" not in payload
    assert "documents" in stored_definition_payload(
        _Version(),
        [],
        [],
        [],
        [
            type(
                "Doc",
                (),
                {
                    "item_key": "letter",
                    "stage_key": "initial",
                    "document_template_id": template_id,
                    "title": None,
                    "due_offset_days": 0,
                    "assignee_role": "unassigned",
                },
            )()
        ],
    )


async def test_migration_forces_rls_and_keeps_recorded_steps_on_downgrade():
    source = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "199_workflow_document_requests.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "198_document_fill_sessions"' in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid" in source
    assert "'document_propose'" in source
    # Recorded steps are immutable history; the narrower check comes back NOT VALID.
    assert "NOT VALID" in source
