"""Resumable fill sessions and the background packet save.

A session is the preparer's own work in progress for one template or one
set: the answers they typed (encrypted at rest), the names they verified, and
the published versions they were shown. It lets the Prepare route be closed
and reopened, and it is what a background save runs from.

The background save does not bypass anything. Each member is saved by
calling the render endpoint as the session's user with the preview evidence
that user minted; an expired or mismatched preview fails that member with a
reason and the session stays open for the person to preview it again. Nothing
here renders, and no document bytes are stored on the session.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import set_tenant_context
from app.models.document_fill_session import DocumentFillSession
from app.models.matter_document import MatterDocument
from app.models.user import User
from app.schemas.fill_session import (
    FillSessionMemberStatus,
    FillSessionRenderRequest,
    FillSessionResponse,
    FillSessionWrite,
)
from app.services.durable_jobs import enqueue_job
from app.services.token_vault import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

JOB_KIND = "template_set_render"
SESSION_DAYS = 14
ACTIVE_STATUSES = ("open", "saving", "failed")


def _digest(answers: dict[str, str]) -> str:
    payload = json.dumps(
        answers, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def encrypt_answers(answers: dict[str, str]) -> str:
    if not answers:
        return ""
    return encrypt_token(json.dumps(answers, ensure_ascii=False, separators=(",", ":")))


def decrypt_answers(ciphertext: str) -> dict[str, str]:
    if not ciphertext:
        return {}
    try:
        value = json.loads(decrypt_token(ciphertext))
    except Exception:  # noqa: BLE001 - an unreadable record is an empty one, not a crash
        logger.warning("A fill session's answers could not be decrypted")
        return {}
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seal_members(members: list[dict[str, Any]]) -> str:
    if not members:
        return ""
    return encrypt_token(json.dumps(members, ensure_ascii=False, separators=(",", ":")))


def _open_members(ciphertext: str) -> list[dict[str, Any]]:
    if not ciphertext:
        return []
    try:
        value = json.loads(decrypt_token(ciphertext))
    except Exception:  # noqa: BLE001 - unreadable evidence is no members, not a crash
        logger.warning("A fill session's render evidence could not be decrypted")
        return []
    return value if isinstance(value, list) else []


def _merge_member_statuses(
    prior: dict[str, dict], members: list[dict], outcomes: list[dict]
) -> list[dict]:
    """Member statuses in packet order, merging prior entries with this run.

    A retry carries only the members still needed, so the entries from an
    earlier attempt (already saved) must survive alongside this run's outcomes.
    """

    merged = dict(prior)
    order = [str(rest.get("template_id") or "") for rest in members]
    for template_id in order:
        merged.setdefault(template_id, {"template_id": template_id, "status": "queued"})
    for outcome in outcomes:
        merged[str(outcome["template_id"])] = outcome
    ordered = [merged[template_id] for template_id in order if template_id in merged]
    ordered.extend(entry for tid, entry in merged.items() if tid not in set(order))
    return ordered


def _member_has_durable_save(member: dict[str, Any] | None) -> bool:
    """Whether a member has a recorded document that a retry must preserve."""

    return bool(
        member and member.get("status") == "saved" and member.get("matter_document_id")
    )


def response_for(
    session: DocumentFillSession, *, include_answers: bool
) -> FillSessionResponse:
    return FillSessionResponse(
        id=session.id,
        matter_id=session.matter_id,
        template_id=session.template_id,
        set_id=session.set_id,
        title=session.title or "",
        status=session.status,
        versions=dict(session.versions_json or {}),
        answers=decrypt_answers(session.answers_ciphertext)
        if include_answers
        else None,
        verified=list(session.verified_json or []),
        members=[
            FillSessionMemberStatus(**item) for item in (session.members_json or [])
        ],
        last_error=session.last_error,
        expires_at=session.expires_at.isoformat(),
        updated_at=session.updated_at.isoformat()
        if session.updated_at
        else _now().isoformat(),
    )


async def _own_session(
    db, user, session_id, *, for_update: bool = False
) -> DocumentFillSession:
    query = select(DocumentFillSession).where(
        DocumentFillSession.id == session_id,
        DocumentFillSession.tenant_id == uuid.UUID(str(user.tenant_id)),
        DocumentFillSession.user_id == user.id,
    )
    if for_update:
        # Serialize a claim against a concurrent read/write of the same row.
        # Refresh an already-cached identity-map instance before inspecting its
        # status; expire_on_commit is disabled in the request/test sessions.
        query = query.with_for_update().execution_options(populate_existing=True)
    session = await db.scalar(query)
    if session is None or session.expires_at <= _now():
        raise HTTPException(status_code=404, detail="Fill session not found")
    return session


async def upsert(
    db: AsyncSession, user, payload: FillSessionWrite
) -> DocumentFillSession:
    """Create the caller's session, or update the one they own.

    A session that is saving in the background is not edited: its answers
    are what the job is saving. It is reported back unchanged.
    """

    if bool(payload.template_id) == bool(payload.set_id):
        raise HTTPException(
            status_code=422, detail="A session is for one template or one set"
        )
    tenant_id = uuid.UUID(str(user.tenant_id))
    if payload.id:
        # Serialize autosave against completion so a request that starts before
        # completion cannot apply its stale payload after the row is sealed.
        session = await _own_session(db, user, payload.id, for_update=True)
        if session.status in ("saving", "saved"):
            return session
    else:
        session = DocumentFillSession(
            tenant_id=tenant_id,
            user_id=user.id,
            template_id=payload.template_id,
            set_id=payload.set_id,
            expires_at=_now() + timedelta(days=SESSION_DAYS),
            answers_sha256=_digest({}),
        )
        db.add(session)
    session.matter_id = payload.matter_id
    session.title = payload.title[:300]
    session.versions_json = dict(payload.versions)
    session.answers_ciphertext = encrypt_answers(payload.answers)
    session.answers_sha256 = _digest(payload.answers)
    session.verified_json = sorted(set(payload.verified))
    # A session that finished is not resurrected by a later autosave: reopening
    # it would erase the per-member outcomes the background save recorded. Only
    # a failed or abandoned session reopens for another attempt.
    if session.status in ("failed", "abandoned"):
        session.status = "open"
        session.members_json = []
        session.last_error = None
    session.expires_at = _now() + timedelta(days=SESSION_DAYS)
    await db.commit()
    await set_tenant_context(db, str(tenant_id))
    await db.refresh(session)
    return session


async def complete(
    db: AsyncSession, user, session_id: uuid.UUID, matter_document_id: uuid.UUID
) -> DocumentFillSession:
    """Complete a single-template session only for its own generated document.

    The document is checked against the session tenant, matter, creator, and
    template metadata before the session is sealed. Repeating completion with
    the same recorded document is idempotent; another document cannot replace
    a saved result.
    """

    session = await _own_session(db, user, session_id, for_update=True)
    recorded = {
        str(item.get("matter_document_id"))
        for item in (session.members_json or [])
        if item.get("matter_document_id")
    }
    if session.status == "saved":
        if str(matter_document_id) in recorded:
            return session
        raise HTTPException(
            status_code=409, detail="This fill session is already saved."
        )
    if session.status == "abandoned":
        raise HTTPException(status_code=409, detail="This fill session is abandoned.")
    if session.status == "saving":
        raise HTTPException(status_code=409, detail="This fill session is being saved.")
    if not session.template_id or not session.matter_id:
        raise HTTPException(
            status_code=422,
            detail="Only a single-template session can be completed this way.",
        )
    document = await db.scalar(
        select(MatterDocument).where(
            MatterDocument.id == matter_document_id,
            MatterDocument.tenant_id == session.tenant_id,
            MatterDocument.matter_id == session.matter_id,
            MatterDocument.uploaded_by_user_id == user.id,
        )
    )
    summary = document.generation_summary if document is not None else None
    if (
        document is None
        or not isinstance(summary, dict)
        or str(summary.get("template_id")) != str(session.template_id)
        or str(summary.get("fill_session_id")) != str(session.id)
    ):
        raise HTTPException(
            status_code=409,
            detail="The saved document does not belong to this fill session.",
        )
    session.members_json = [
        {
            "template_id": str(session.template_id),
            "status": "saved",
            "matter_document_id": str(document.id),
            "output_filename": document.filename,
        }
    ]
    session.status = "saved"
    session.last_error = None
    session.job_id = None
    await db.commit()
    await set_tenant_context(db, str(session.tenant_id))
    await db.refresh(session)
    return session


async def open_prepared_session(
    db: AsyncSession,
    *,
    tenant_id,
    user_id,
    template_id,
    matter_id,
    title: str,
    version_no: int,
    answers: dict[str, str],
) -> DocumentFillSession:
    """Open a session on someone's behalf with values Smart Fill prepared.

    Used by a workflow run that asks for a document: the assignee finds it
    under "Documents in progress" and resumes it. Nothing is verified yet,
    and the caller owns the transaction (no commit here).
    """

    session = DocumentFillSession(
        tenant_id=uuid.UUID(str(tenant_id)),
        user_id=user_id,
        template_id=template_id,
        matter_id=matter_id,
        title=title[:300],
        versions_json={str(template_id): int(version_no)},
        answers_ciphertext=encrypt_answers(answers),
        answers_sha256=_digest(answers),
        verified_json=[],
        members_json=[],
        status="open",
        expires_at=_now() + timedelta(days=SESSION_DAYS),
    )
    db.add(session)
    await db.flush()
    return session


async def abandon(db: AsyncSession, user, session_id) -> None:
    session = await _own_session(db, user, session_id)
    session.status = "abandoned"
    session.answers_ciphertext = ""
    session.answers_sha256 = _digest({})
    await db.commit()


async def list_for_matter(
    db: AsyncSession, *, tenant_id, matter_id, user_id=None
) -> list[DocumentFillSession]:
    """Sessions still in progress for a matter, newest first, answers withheld."""

    query = (
        select(DocumentFillSession)
        .where(
            DocumentFillSession.tenant_id == uuid.UUID(str(tenant_id)),
            DocumentFillSession.matter_id == uuid.UUID(str(matter_id)),
            DocumentFillSession.status.in_(ACTIVE_STATUSES),
            DocumentFillSession.expires_at > _now(),
        )
        .order_by(DocumentFillSession.updated_at.desc())
        .limit(50)
    )
    if user_id is not None:
        query = query.where(DocumentFillSession.user_id == user_id)
    return list((await db.execute(query)).scalars().all())


async def verified_counts(db: AsyncSession, *, tenant_id, matter_id) -> dict[str, int]:
    """Per template, how many names the latest session for this matter verified.

    Read by the readiness record so the Case Documents banner can say
    "3 documents ready, 2 verified". Names only; nothing is decrypted.
    """

    rows = await db.execute(
        select(DocumentFillSession)
        .where(
            DocumentFillSession.tenant_id == uuid.UUID(str(tenant_id)),
            DocumentFillSession.matter_id == uuid.UUID(str(matter_id)),
            DocumentFillSession.status != "abandoned",
            DocumentFillSession.expires_at > _now(),
        )
        .order_by(DocumentFillSession.updated_at.desc())
        .limit(100)
    )
    counts: dict[str, int] = {}
    for session in rows.scalars().all():
        verified = list(session.verified_json or [])
        if session.template_id:
            counts.setdefault(str(session.template_id), len(verified))
        else:
            # A set session's verified names are interview keys; each member
            # listed in the session gets the count of names that reach it.
            for member in session.members_json or []:
                counts.setdefault(str(member.get("template_id") or ""), len(verified))
    counts.pop("", None)
    return counts


async def enqueue_render(
    db: AsyncSession, user, session_id, payload: FillSessionRenderRequest
):
    """Queue the background save from the previews the browser reviewed."""

    # Claim under a row lock: two concurrent requests must not both queue a run.
    session = await _own_session(db, user, session_id, for_update=True)
    if session.status not in ("open", "failed"):
        raise HTTPException(
            status_code=409, detail="This packet is already being saved."
        )
    if not session.matter_id:
        raise HTTPException(
            status_code=422, detail="Choose the destination matter before saving."
        )
    if not payload.members:
        raise HTTPException(
            status_code=422, detail="Nothing to save: preview the packet first."
        )
    members = [
        {
            "template_id": str(member.template_id),
            "variables": dict(member.variables),
            "preview_id": str(member.preview_id) if member.preview_id else None,
            "convert_to_pdf": bool(member.convert_to_pdf),
            "output_format": member.output_format,
            # Carried per member: the interview verifies a shared question once,
            # but each document spells the value under its own field name.
            "verified_fields": list(member.verified_fields),
        }
        for member in payload.members
    ]
    # Merge onto whatever is already recorded: a retry carries only the members
    # still needed, so entries from an earlier attempt (already saved) are kept
    # rather than wiped when the packet is re-queued.
    prior = {
        str(item.get("template_id")): dict(item)
        for item in (session.members_json or [])
    }
    pending_members = [
        member
        for member in members
        if not _member_has_durable_save(prior.get(member["template_id"]))
    ]
    if not pending_members:
        # A lost queue acknowledgement can be retried after the worker has
        # already recorded every requested document. Do not create another
        # job, which would duplicate non-PDF documents at the render layer.
        if prior and all(_member_has_durable_save(entry) for entry in prior.values()):
            session.status = "saved"
            session.last_error = None
        else:
            session.status = "open"
        await db.commit()
        await set_tenant_context(db, str(session.tenant_id))
        await db.refresh(session)
        return session
    session.status = "saving"
    session.last_error = None
    pending_ids = {member["template_id"] for member in pending_members}
    session.members_json = [
        {
            **prior.get(member["template_id"], {}),
            "template_id": member["template_id"],
            "status": "queued",
        }
        for member in pending_members
    ] + [entry for tid, entry in prior.items() if tid not in pending_ids]
    job = await enqueue_job(
        db,
        tenant_id=session.tenant_id,
        kind=JOB_KIND,
        idempotency_key=f"{session.id}:{session.answers_sha256}:{uuid.uuid4()}",
        payload={
            "session_id": str(session.id),
            "user_id": str(user.id),
            "matter_id": str(session.matter_id),
            "folder_id": str(payload.folder_id) if payload.folder_id else None,
            # The members carry the filled field values. ``durable_jobs.payload``
            # is a plain JSON column that is not cleared on completion, so the
            # values are sealed the same way the session's answers are: the job
            # decrypts them when it runs. Storing them in the clear would outlive
            # the encrypted session and defeat encrypting it.
            "members_ciphertext": _seal_members(pending_members),
        },
    )
    session.job_id = job.id
    await db.commit()
    await set_tenant_context(db, str(session.tenant_id))
    await db.refresh(session)
    return session


async def run_set_render_job(db: AsyncSession, job) -> dict[str, Any]:
    """The ``template_set_render`` handler: save each member as the session's user.

    Every member goes through the render endpoint itself, so the preview
    evidence gate, the storage staging and the matter event are exactly what
    a browser save gets. A member whose evidence no longer binds (expired,
    another user, other values) fails with that reason and the session goes
    back to open so the person can preview it again.
    """

    from app.routers.document_templates import render_template_endpoint
    from app.schemas.document_template import DocumentTemplateRenderRequest
    from app.services.rbac_service import get_user_capabilities

    payload = job.payload or {}
    members = _open_members(payload.get("members_ciphertext") or "")
    if not members and payload.get("members"):
        # A job queued before the members were sealed still carries them in the
        # clear; run it rather than dropping the save.
        members = list(payload.get("members") or [])
    tenant_id = job.tenant_id
    await set_tenant_context(db, str(tenant_id))
    session = await db.scalar(
        select(DocumentFillSession).where(
            DocumentFillSession.id
            == uuid.UUID(str(payload.get("session_id") or uuid.uuid4())),
            DocumentFillSession.tenant_id == tenant_id,
        )
    )
    if session is None:
        return {"outcome": "blocked", "failure_code": "session_missing"}
    user = await db.scalar(
        select(User).where(
            User.id == uuid.UUID(str(payload.get("user_id") or uuid.uuid4())),
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
        )
    )
    if user is None or "manage_documents" not in await get_user_capabilities(
        db, user.id
    ):
        session.status = "failed"
        session.last_error = (
            "The person who prepared this packet can no longer save documents."
        )
        await db.commit()
        return {"outcome": "blocked", "failure_code": "actor_unavailable"}

    outcomes: list[dict[str, Any]] = []
    saved = 0
    if not members:
        # The job rejects an empty packet at enqueue, so an empty member list
        # here means the sealed previews could not be read (a rotated vault
        # key, say). Reporting "saved" with nothing saved would be a lie.
        session.status = "failed"
        session.last_error = (
            "This packet's saved previews could not be read. Preview and save it again."
        )
        await db.commit()
        return {"outcome": "blocked", "failure_code": "members_unreadable"}
    # Snapshotted before any rollback: a rollback expires the row, and an
    # expired attribute read on the async session is a MissingGreenlet.
    session_id, matter_id = session.id, session.matter_id
    user_id = user.id
    # This run may carry only the members still needed; keep what an earlier
    # attempt recorded so the merge below does not drop them.
    prior_members = {
        str(item.get("template_id")): dict(item)
        for item in (session.members_json or [])
    }
    skipped_saved = 0
    for member in members:
        template_id = str(member.get("template_id") or "")
        prior = prior_members.get(template_id) or {}
        if _member_has_durable_save(prior):
            # A retry of the same job must not render a member it already
            # saved: non-PDF saves are not idempotent at the render layer, so
            # re-running one would file a second copy of the document.
            skipped_saved += 1
            continue
        variables = {str(k): str(v) for k, v in (member.get("variables") or {}).items()}
        request = DocumentTemplateRenderRequest(
            variables=variables,
            matter_id=str(matter_id),
            folder_id=uuid.UUID(payload["folder_id"])
            if payload.get("folder_id")
            else None,
            preview_id=uuid.UUID(member["preview_id"])
            if member.get("preview_id")
            else None,
            convert_to_pdf=bool(member.get("convert_to_pdf")),
            verified_fields=sorted(
                str(name) for name in (member.get("verified_fields") or [])
            ),
        )
        try:
            response = await render_template_endpoint(
                uuid.UUID(template_id), request, current_user=user, db=db
            )
            outcomes.append(
                {
                    "template_id": template_id,
                    "status": "saved",
                    "matter_document_id": response.matter_document_id,
                    "output_filename": response.output_filename,
                    # The signing descriptor travels with the outcome so the
                    # packet page can still offer Send after a background save.
                    "output_format": getattr(response, "output_format", None)
                    or member.get("output_format"),
                    "signing_roles": list(
                        getattr(response, "signing_roles", None) or []
                    ),
                    "positioned_fields": list(
                        getattr(response, "positioned_fields", None) or []
                    ),
                    "signing_placement_required": bool(
                        getattr(response, "signing_placement_required", False)
                    ),
                }
            )
            saved += 1
        except HTTPException as exc:
            detail = str(exc.detail)
            expired = exc.status_code == 409 or "preview" in detail.lower()
            outcomes.append(
                {
                    "template_id": template_id,
                    "status": "preview_expired" if expired else "failed",
                    "detail": "Preview expired; review it again."
                    if expired
                    else detail[:300],
                }
            )
            await db.rollback()
            await set_tenant_context(db, str(tenant_id))
        except Exception as exc:  # noqa: BLE001 - one member's failure must not lose the rest
            logger.exception("Background save failed for template %s", template_id)
            outcomes.append(
                {
                    "template_id": template_id,
                    "status": "failed",
                    "detail": str(exc)[:300],
                }
            )
            await db.rollback()
            await set_tenant_context(db, str(tenant_id))
        # A rollback or the endpoint's commit expired ``user``; the next
        # member's render reads ``current_user`` attributes, which would raise
        # MissingGreenlet. Read it afresh.
        user = await db.get(User, user_id, populate_existing=True)
        if user is None:
            session = await db.get(DocumentFillSession, session_id)
            # Record what this run managed before it lost its actor, so a saved
            # member is not re-rendered (and duplicated) on a later retry.
            session.members_json = _merge_member_statuses(
                prior_members, members, outcomes
            )
            session.status = "failed"
            session.last_error = (
                "The person who prepared this packet can no longer save documents."
            )
            await db.commit()
            return {"outcome": "blocked", "failure_code": "actor_unavailable"}
        # The endpoint committed its own document; re-read the session row
        # the commit may have expired before recording this member.
        session = await db.get(DocumentFillSession, session_id)
        session.members_json = _merge_member_statuses(prior_members, members, outcomes)
        await db.commit()
        await set_tenant_context(db, str(tenant_id))

    session = await db.get(DocumentFillSession, session_id)
    total = len(members)
    saved += skipped_saved
    merged_statuses = _merge_member_statuses(prior_members, members, outcomes)
    session.members_json = merged_statuses
    # The whole packet is saved only when every recorded member is, including
    # ones this retry did not carry because an earlier attempt saved them.
    all_saved = bool(merged_statuses) and all(
        entry.get("status") == "saved" for entry in merged_statuses
    )
    not_saved = sum(1 for entry in merged_statuses if entry.get("status") != "saved")
    session.status = "saved" if all_saved else "open"
    session.last_error = (
        None
        if all_saved
        else f"{not_saved} of {len(merged_statuses)} document(s) were not saved."
    )
    await db.commit()
    return {
        "outcome": "saved" if all_saved else "partial",
        "saved": saved,
        "total": total,
    }
