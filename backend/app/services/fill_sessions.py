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


async def _own_session(db, user, session_id) -> DocumentFillSession:
    session = await db.scalar(
        select(DocumentFillSession).where(
            DocumentFillSession.id == session_id,
            DocumentFillSession.tenant_id == uuid.UUID(str(user.tenant_id)),
            DocumentFillSession.user_id == user.id,
        )
    )
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
        session = await _own_session(db, user, payload.id)
        if session.status == "saving":
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
    if session.status in ("saved", "failed", "abandoned"):
        session.status = "open"
        session.members_json = []
        session.last_error = None
    session.expires_at = _now() + timedelta(days=SESSION_DAYS)
    await db.commit()
    await set_tenant_context(db, str(tenant_id))
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

    session = await _own_session(db, user, session_id)
    if session.status == "saving":
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
        }
        for member in payload.members
    ]
    session.status = "saving"
    session.last_error = None
    session.members_json = [
        {"template_id": member["template_id"], "status": "queued"} for member in members
    ]
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
            "verified": list(session.verified_json or []),
            "members": members,
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
    verified = set(payload.get("verified") or [])
    saved = 0
    # Snapshotted before any rollback: a rollback expires the row, and an
    # expired attribute read on the async session is a MissingGreenlet.
    session_id, matter_id = session.id, session.matter_id
    for member in payload.get("members") or []:
        template_id = str(member.get("template_id") or "")
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
            verified_fields=sorted(name for name in variables if name in verified),
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
        # The endpoint committed its own document; re-read the session row
        # the commit may have expired before recording this member.
        session = await db.get(DocumentFillSession, session_id)
        session.members_json = outcomes + [
            {"template_id": str(rest.get("template_id")), "status": "queued"}
            for rest in (payload.get("members") or [])[len(outcomes) :]
        ]
        await db.commit()
        await set_tenant_context(db, str(tenant_id))

    session = await db.get(DocumentFillSession, session_id)
    total = len(payload.get("members") or [])
    session.members_json = outcomes
    session.status = (
        "saved" if saved == total and total else "open" if saved < total else "saved"
    )
    session.last_error = (
        None
        if saved == total
        else f"{total - saved} of {total} document(s) were not saved."
    )
    await db.commit()
    return {
        "outcome": "saved" if saved == total else "partial",
        "saved": saved,
        "total": total,
    }
