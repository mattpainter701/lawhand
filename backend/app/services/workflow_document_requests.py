"""Documents a workflow run asks to have prepared (Phase 2c).

A workflow template version may list documents beside its checklist. The
preview resolves each one against the firm's document templates and says
whether it can be prepared right now. Applying the run opens, per document,
a Smart Fill session pre-filled from the matter (the same ``prepare_fill``
the Prepare route uses) and a "Prepare" task for the assignee, and records
a ``document_propose`` step. Nothing is rendered, saved or filed here: the
assignee opens the session, reviews and verifies the values, and saves the
document through the same preview-evidence gate as any other.

The actor is the person who approves the run: the session is owned by the
task's assignee when it has one (so they can resume it), otherwise by the
approver; the task and the step are created by the approver like every
other step of the run.

Rollback cancels the task and abandons the session, as ``task_create`` steps
are cancelled. A document already saved from its session is a blocker: the
saved document is a matter record, not something a rollback may remove.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configurable_workflow import MatterWorkflowDocumentDefinition
from app.models.document_fill_session import DocumentFillSession
from app.models.document_template import DocumentTemplate
from app.models.plugin import Matter
from app.models.user import User

STEP_TYPE = "document_propose"
PREPARE_PATH = "/templates/prepare"


def definition_entries(items: list[MatterWorkflowDocumentDefinition]) -> list[dict]:
    """The reviewable definition of the documents, in position order."""

    return [
        {
            "item_key": item.item_key,
            "stage_key": item.stage_key,
            "template_id": str(item.document_template_id),
            "title": item.title,
            "due_offset_days": item.due_offset_days,
            "assignee_role": item.assignee_role,
        }
        for item in items
    ]


def input_entries(items) -> list[dict]:
    """The same shape from a request body, so the digest matches the store."""

    return [
        {
            "item_key": item.item_key,
            "stage_key": item.stage_key,
            "template_id": str(item.template_id),
            "title": item.title,
            "due_offset_days": item.due_offset_days,
            "assignee_role": item.assignee_role,
        }
        for item in items
    ]


async def load_definitions(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    *,
    share: bool = False,
) -> list[MatterWorkflowDocumentDefinition]:
    query = (
        select(MatterWorkflowDocumentDefinition)
        .where(
            MatterWorkflowDocumentDefinition.tenant_id == tenant_id,
            MatterWorkflowDocumentDefinition.template_version_id == version_id,
        )
        .order_by(MatterWorkflowDocumentDefinition.position)
    )
    if share:
        query = query.with_for_update(of=MatterWorkflowDocumentDefinition, read=True)
    return list((await db.execute(query)).scalars().all())


def _assignee(item: MatterWorkflowDocumentDefinition, matter: Matter) -> str | None:
    if item.assignee_role == "matter_owner":
        return str(matter.user_id)
    if item.assignee_role == "attorney_of_record":
        return (
            str(matter.attorney_of_record_id) if matter.attorney_of_record_id else None
        )
    if item.assignee_role == "template_applier":
        return "approval_actor"
    return None


async def preview_entries(
    db: AsyncSession,
    *,
    matter: Matter,
    items: list[MatterWorkflowDocumentDefinition],
    stage_labels: dict[str, str],
    as_of: date,
) -> list[dict[str, Any]]:
    """Resolve each requested document for the preview.

    A template that is missing, archived or unpublished is reported with its
    reason rather than dropped: the packet says which document it cannot
    prepare. The published version number is part of the preview, so a
    template published again between preview and apply is a changed preview.
    """

    if not items:
        return []
    ids = {item.document_template_id for item in items}
    templates = {
        template.id: template
        for template in (
            await db.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.tenant_id == matter.tenant_id,
                    DocumentTemplate.id.in_(sorted(ids, key=str)),
                )
            )
        )
        .scalars()
        .all()
    }
    entries: list[dict[str, Any]] = []
    for item in items:
        template = templates.get(item.document_template_id)
        reason = None
        if template is None:
            reason = "The document template no longer exists."
        elif not template.is_active:
            reason = "The document template is archived."
        elif not template.published_version_no:
            reason = "The document template has no published version."
        entries.append(
            {
                "item_key": item.item_key,
                "stage_key": item.stage_key,
                "stage_label": stage_labels.get(item.stage_key, item.stage_key),
                "title": item.title or (template.title if template else item.item_key),
                "template_id": str(item.document_template_id),
                "template_title": template.title if template else None,
                "template_version_no": (
                    int(template.published_version_no)
                    if template is not None and template.published_version_no
                    else None
                ),
                "available": reason is None,
                "unavailable_reason": reason,
                "due_date": (as_of + timedelta(days=item.due_offset_days)).isoformat(),
                "due_offset_days": item.due_offset_days,
                "assignee_role": item.assignee_role,
                "assigned_to_user_id": _assignee(item, matter),
            }
        )
    return entries


def prepare_path(*, template_id, matter_id, session_id) -> str:
    return (
        f"{PREPARE_PATH}?template={template_id}&matter={matter_id}"
        f"&session={session_id}"
    )


async def propose_document(
    db: AsyncSession,
    *,
    run,
    matter: Matter,
    entry: dict[str, Any],
    actor_user_id: uuid.UUID,
    assigned_to_user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Open the pre-filled session and the Prepare task for one entry.

    Returns the step evidence. A template that cannot be prepared any more
    (unpublished since the preview would already be a changed preview; this
    covers a version that fails to load) yields ``blocked`` evidence and
    creates nothing.
    """

    from app.models.task import Task
    from app.services import template_fill_engine as engine
    from app.services.document_template_versions import published_template_view
    from app.services.fill_sessions import open_prepared_session
    from app.services.task_workflow import append_task_event
    from app.services.template_fill_loaders import load_matter_context, memoized

    template_id = uuid.UUID(str(entry["template_id"]))
    template = await db.scalar(
        select(DocumentTemplate).where(
            DocumentTemplate.tenant_id == run.tenant_id,
            DocumentTemplate.id == template_id,
        )
    )
    if template is None:
        return {
            "status": "blocked",
            "reason": "The document template no longer exists.",
        }
    try:
        view = await published_template_view(db, template)
    except ValueError as exc:
        return {"status": "blocked", "reason": str(exc)[:300]}

    actor = await db.scalar(
        select(User).where(User.id == actor_user_id, User.tenant_id == run.tenant_id)
    )
    # The engine reads the matter's client and attorney relationships; load
    # them on the same identity-mapped row the run holds a lock on.
    filled_matter = await load_matter_context(
        db=db, tenant_id=run.tenant_id, matter_id=str(matter.id)
    )
    prepared = await engine.prepare_fill(
        db,
        template=view,
        tenant_id=run.tenant_id,
        matter=filled_matter or matter,
        actor=actor,
        loaders=memoized(),
    )
    fields = len(prepared.coverage.states)
    filled = len(prepared.values)
    owner_id = assigned_to_user_id or actor_user_id
    session = await open_prepared_session(
        db,
        tenant_id=run.tenant_id,
        user_id=owner_id,
        template_id=template.id,
        matter_id=matter.id,
        title=str(entry["title"])[:300],
        version_no=int(template.published_version_no),
        answers=dict(prepared.values),
    )
    path = prepare_path(
        template_id=template.id, matter_id=matter.id, session_id=session.id
    )
    missing = list(prepared.missing_required)
    description = (
        f"Smart Fill prepared {filled} of {fields} fields from this matter. "
        + (f"Still needed: {', '.join(missing[:8])}. " if missing else "")
        + f"Review, verify and save it here: {path}"
    )
    task = Task(
        tenant_id=run.tenant_id,
        title=f"Prepare {entry['title']}"[:500],
        description=description,
        task_type="general",
        status="pending",
        priority="medium",
        due_date=date.fromisoformat(entry["due_date"]),
        matter_id=run.matter_id,
        assigned_to_user_id=assigned_to_user_id,
        created_by_user_id=actor_user_id,
        source="workflow",
        external_ref=f"workflow:{run.id}:{entry['item_key']}",
    )
    db.add(task)
    await db.flush()
    append_task_event(
        db,
        task,
        event_type="workflow_task_created",
        actor_user_id=actor_user_id,
        to_status="pending",
        metadata={
            "workflow_run_id": str(run.id),
            "workflow_item_key": entry["item_key"],
            "stage_key": entry["stage_key"],
            "fill_session_id": str(session.id),
        },
    )
    return {
        "status": "succeeded",
        "task_id": task.id,
        "evidence": {
            # The task fields rollback compares, exactly as task_create records them.
            "title": task.title,
            "description": task.description,
            "task_type": task.task_type,
            "priority": task.priority,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "assigned_to_user_id": (
                str(task.assigned_to_user_id) if task.assigned_to_user_id else None
            ),
            "external_ref": task.external_ref,
            "initial_version": task.version,
            # And what was prepared: counts and names, never a value.
            "document_template_id": str(template.id),
            "template_title": template.title,
            "template_version_no": int(template.published_version_no),
            "fill_session_id": str(session.id),
            "fill_session_owner_user_id": str(owner_id),
            "fields": fields,
            "filled": filled,
            "missing_required": missing[:40],
            "sources_loaded": list(prepared.sources_loaded),
            "prepare_path": path,
        },
    }


async def session_blocker(db: AsyncSession, step) -> str | None:
    """Why a document step cannot be rolled back, or ``None``."""

    session_id = (step.evidence_json or {}).get("fill_session_id")
    if not session_id:
        return None
    session = await db.scalar(
        select(DocumentFillSession).where(
            DocumentFillSession.tenant_id == step.tenant_id,
            DocumentFillSession.id == uuid.UUID(str(session_id)),
        )
    )
    if session is not None and session.status in ("saving", "saved"):
        return f"document {step.action_key} was already saved from its session"
    return None


async def abandon_session(db: AsyncSession, step) -> bool:
    """Abandon the step's session if it is still there; True when it was."""

    from app.services.fill_sessions import _digest

    session_id = (step.evidence_json or {}).get("fill_session_id")
    if not session_id:
        return False
    session = await db.scalar(
        select(DocumentFillSession).where(
            DocumentFillSession.tenant_id == step.tenant_id,
            DocumentFillSession.id == uuid.UUID(str(session_id)),
        )
    )
    if session is None or session.status == "abandoned":
        return False
    session.status = "abandoned"
    session.answers_ciphertext = ""
    session.answers_sha256 = _digest({})
    await db.flush()
    return True
