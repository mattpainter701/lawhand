"""Record how a matter was engaged when no intake packet did it.

A client who arrives with live matters has usually already signed a fee
agreement, sometimes years ago and sometimes with another firm, and a few
legacy or unusual arrangements have no fee agreement at all. Sending the intake
packet would be wrong for those matters: it mints a portal invitation, a native
e-signature request and a client email. This module records the engagement
instead, as an explicit status on the matter plus, when the firm has it, the
signed agreement filed as a matter document.

Nothing here contacts the client, creates a signature request or claims
signature evidence: a copy that arrived on paper is a filed document, not an
e-signed one, and the E-Signature panel keeps listing only native requests.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.matter_document import MatterDocument
from app.models.plugin import ENGAGEMENT_STATUSES, Matter, MatterEvent

ACTIVE_STAGE = "Active"

# Stages an engagement record may move to Active. A stage a firm set by hand
# is left alone, and an applied firm workflow keeps ownership of its stage
# regardless (set_intake_stage checks that).
REPLACEABLE_STAGES = frozenset(
    {"", "Intake / Awaiting Documents", "Transfer / Review Required"}
)

# Statuses that mean "engaged, but the signed copy is not on file". Any of
# them may later be upgraded by adding the copy.
WITHOUT_COPY = frozenset({"pending_copy", "signed_no_copy", "no_agreement"})

# Statuses staff choose directly. pending_copy is only stamped by importers,
# which know a signed date but cannot carry the file.
STAFF_STATUSES = ("signed_on_file", "signed_no_copy", "no_agreement")

EVENT_TITLES = {
    "signed_on_file": "Signed fee agreement recorded",
    "signed_no_copy": "Engagement recorded without agreement copy",
    "no_agreement": "Matter opened without a fee agreement",
    "pending_copy": "Engagement recorded; signed copy pending",
}

STATUS_LABELS = {
    "signed_on_file": "signed fee agreement on file",
    "signed_no_copy": "signed, no copy on hand",
    "no_agreement": "no fee agreement",
    "pending_copy": "signed copy pending",
}


def engagement_payload(matter: Matter) -> dict | None:
    """The engagement record as the matter API returns it, or None."""
    if not matter.engagement_status:
        return None
    document = matter.engagement_document
    recorder = matter.engagement_recorder
    return {
        "status": matter.engagement_status,
        "signed_on": matter.engagement_signed_on,
        "document_id": (
            str(matter.engagement_document_id) if matter.engagement_document_id else None
        ),
        "document_name": document.filename if document else None,
        "note": matter.engagement_note,
        "recorded_at": matter.engagement_recorded_at,
        "recorded_by": (
            str(matter.engagement_recorded_by) if matter.engagement_recorded_by else None
        ),
        "recorded_by_name": (
            (recorder.full_name or recorder.email) if recorder else None
        ),
    }


def validate_engagement(
    status: str, *, signed_on: date | None, note: str | None, has_document: bool
) -> None:
    """Enforce what each status needs so the record is never half-stated."""
    if status not in ENGAGEMENT_STATUSES:
        raise HTTPException(422, "Unknown engagement status")
    if signed_on is not None and signed_on > date.today():
        raise HTTPException(422, "The signing date cannot be in the future")
    if status == "signed_on_file" and not has_document:
        raise HTTPException(
            422, "Upload the signed fee agreement or choose it from the matter documents"
        )
    if status != "signed_on_file" and has_document:
        raise HTTPException(
            422, "A document only belongs with a signed fee agreement on file"
        )
    if status in ("signed_no_copy", "no_agreement") and not (note or "").strip():
        raise HTTPException(
            422,
            "Explain where the agreement was signed"
            if status == "signed_no_copy"
            else "Explain why this matter has no fee agreement",
        )
    if status == "no_agreement" and signed_on is not None:
        raise HTTPException(422, "A matter with no fee agreement has no signing date")


def transition_allowed(current: str | None, new: str, *, replace: bool) -> bool:
    """Whether the record may move from ``current`` to ``new``.

    Adding the signed copy to any record that lacks one is always fine, and a
    pending copy may be resolved as "no copy" or "no agreement". Anything that
    contradicts an existing record -- above all replacing a filed signed
    agreement -- needs an explicit ``replace``.
    """
    if current is None or replace:
        return True
    if new == "signed_on_file" and current in WITHOUT_COPY:
        return True
    if current == "pending_copy" and new in ("signed_no_copy", "no_agreement"):
        return True
    return False


def apply_engagement(
    matter: Matter,
    *,
    status: str,
    signed_on: date | None,
    note: str | None,
    document_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    at: datetime | None = None,
) -> None:
    """Stamp the engagement columns. Callers validate and event separately."""
    matter.engagement_status = status
    matter.engagement_signed_on = signed_on
    matter.engagement_document_id = document_id
    matter.engagement_note = (note or "").strip() or None
    matter.engagement_recorded_at = at or datetime.now(timezone.utc)
    matter.engagement_recorded_by = user_id


def engagement_event(
    db, matter: Matter, *, user_id: uuid.UUID | None, actor: str, extra: str = ""
) -> MatterEvent:
    """Append the system event every engagement transition writes."""
    status = matter.engagement_status
    parts = [f"Engagement: {STATUS_LABELS.get(status, status)}."]
    if matter.engagement_signed_on:
        parts.append(f"Signed {matter.engagement_signed_on.isoformat()}.")
    if matter.engagement_document_id:
        parts.append(f"Document {matter.engagement_document_id}.")
    if matter.engagement_note:
        parts.append(f"Note: {matter.engagement_note}")
    if extra:
        parts.append(extra)
    parts.append(f"Recorded by {actor}. No messages sent.")
    event = MatterEvent(
        tenant_id=matter.tenant_id,
        matter_id=matter.id,
        event_type="intake",
        title=EVENT_TITLES[status],
        content=" ".join(parts),
        note_type="system",
        created_by=user_id,
    )
    db.add(event)
    return event


async def activate_stage(db, matter: Matter, *, user_id: uuid.UUID) -> bool:
    """Move an unset or intake/transfer stage to Active; report whether it moved."""
    from app.services.durable_workflow_automations import enqueue_matter_event
    from app.services.matter_intake import set_intake_stage

    if (matter.stage or "") not in REPLACEABLE_STAGES:
        return False
    prior = matter.stage
    await set_intake_stage(db, matter, ACTIVE_STAGE)
    if matter.stage == prior:
        return False
    await enqueue_matter_event(
        db, matter=matter, trigger_event="matter_stage_changed", actor_user_id=user_id
    )
    return True


async def record_engagement(
    db,
    user,
    matter: Matter,
    body,
    filename: str = "",
    content: bytes = b"",
) -> tuple[Matter, bool]:
    """Record or update the matter's engagement. Returns (matter, created).

    ``created`` is False when the request repeats the record already on the
    matter, so a retried submission never files the agreement twice.
    """
    from app.services.matter_intake import MAX_AGREEMENT_BYTES, get_packet, store_file

    if matter.is_closed or matter.status == "closed":
        raise HTTPException(409, "Reopen the matter before recording its engagement.")
    document_id = body.document_id
    validate_engagement(
        body.status,
        signed_on=body.signed_on,
        note=body.note,
        has_document=bool(document_id or content),
    )

    document = None
    if document_id:
        document = await db.scalar(
            select(MatterDocument).where(
                MatterDocument.id == document_id,
                MatterDocument.tenant_id == user.tenant_id,
                MatterDocument.matter_id == matter.id,
            )
        )
        if document is None:
            raise HTTPException(404, "Document not found")
    elif content:
        if not content.startswith(b"%PDF-") or len(content) > MAX_AGREEMENT_BYTES:
            raise HTTPException(
                422, "Upload the signed fee agreement as a PDF up to 20 MiB."
            )

    # The same submission again is a no-op, whichever way the copy was named.
    note = (body.note or "").strip() or None
    same_document = (
        matter.engagement_document_id is not None
        and (
            matter.engagement_document_id == document_id
            or (
                content
                and matter.engagement_document is not None
                and matter.engagement_document.document_sha256
                == hashlib.sha256(content).hexdigest()
            )
        )
    )
    if (
        matter.engagement_status == body.status
        and matter.engagement_signed_on == body.signed_on
        and matter.engagement_note == note
        and (same_document if body.status == "signed_on_file" else True)
    ):
        return matter, False

    if not transition_allowed(
        matter.engagement_status, body.status, replace=bool(body.replace)
    ):
        raise HTTPException(
            409,
            "This matter already has a signed fee agreement on file. "
            "Confirm that you want to replace the record.",
        )

    # A packet that is still waiting on the fee agreement owns that question;
    # staff verify an agreement that arrived outside the portal there.
    packet = await get_packet(db, user.tenant_id, matter.id, lock=True)
    if packet is not None and packet.status != "cancelled":
        requirement = (packet.requirements or {}).get("fee_agreement")
        if requirement and not requirement.get("completed"):
            raise HTTPException(
                409,
                "Client paperwork is waiting on this fee agreement. Use "
                "Review received documents on the paperwork card instead.",
            )

    if content and document is None:
        stored = await store_file(
            user.tenant_id,
            matter,
            filename or "Signed fee agreement.pdf",
            content,
            "application/pdf",
            category="contract",
        )
        if not stored.succeeded:
            raise HTTPException(
                503, "Agreement storage is unavailable. Reconnect storage and retry."
            )
        signed = (
            f"; signed {body.signed_on.isoformat()}" if body.signed_on else ""
        )
        document = MatterDocument(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            matter_id=matter.id,
            uploaded_by_user_id=user.id,
            filename=(filename or "Signed fee agreement.pdf")[:250],
            content_type="application/pdf",
            file_size=len(content),
            document_category="contract",
            document_role="filed_copy",
            document_status="filed",
            document_sha256=hashlib.sha256(content).hexdigest(),
            description=f"Signed fee agreement on file{signed}"[:500],
            portal_visible=False,
            storage_path=stored.storage_path,
            storage_provider=stored.provider,
            storage_backend=stored.backend,
            provider_object_id=stored.provider_item_id,
            provider_drive_id=stored.drive_id,
            provider_parent_id=stored.parent_id,
        )
        db.add(document)
        await db.flush()

    previous = matter.engagement_status
    apply_engagement(
        matter,
        status=body.status,
        signed_on=body.signed_on,
        note=note,
        document_id=document.id if document else None,
        user_id=user.id,
    )
    matter.engagement_document = document
    await activate_stage(db, matter, user_id=user.id)
    engagement_event(
        db,
        matter,
        user_id=user.id,
        actor=getattr(user, "full_name", None) or getattr(user, "email", None) or str(user.id),
        extra=(
            f"Replaces the earlier record ({STATUS_LABELS.get(previous, previous)})."
            if previous and previous != body.status
            else ""
        ),
    )
    await db.commit()
    await db.refresh(matter)
    return matter, True
