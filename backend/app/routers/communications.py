"""
Communications router — log inbound/outbound communications.

  GET  /api/communications       list with filters
  POST /api/communications       create log entry
  GET  /api/communications/{id}  detail
  PATCH /api/communications/{id} update (content of hand-logged entries only;
                                 captured records can only be re-filed)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, set_tenant_context
from app.middleware.tenant import get_current_user
from app.models.communication_log import CommunicationLog
from app.models.contact import Contact
from app.models.plugin import Matter
from app.schemas.communication_log import (
    CommunicationLogCreate,
    CommunicationLogListResponse,
    CommunicationLogResponse,
    CommunicationLogUpdate,
)
from app.services.cache import ExpertiseCacheManager
from app.services.rbac_service import get_user_capabilities
from app.services.matter_access import can_access_matter, matter_access_predicate

router = APIRouter(prefix="/api/communications", tags=["communications"])
communication_context_cache = ExpertiseCacheManager()


async def _can_access_sms(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return "manage_matters" in await get_user_capabilities(db, user_id)


def _require_sms_access(*, channel: str | None, allowed: bool) -> None:
    if channel == "sms" and not allowed:
        raise HTTPException(status_code=403, detail="SMS communication access required")


async def _can_access_sms_record(db: AsyncSession, user, matter_id) -> bool:
    return bool(
        matter_id
        and await _can_access_sms(db, user.id)
        and await can_access_matter(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            is_admin=user.role == "admin",
            matter_id=matter_id,
        )
    )


async def _record_client_contact(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    contact_id: uuid.UUID | None,
    occurred_at: datetime,
) -> None:
    """Advance recency for a contacted person and their canonical client account."""
    if contact_id is None:
        return
    contact = (
        await db.execute(
            select(Contact).where(
                Contact.id == contact_id,
                Contact.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        return
    targets = [contact]
    if contact.client_account_id:
        account = (
            await db.execute(
                select(Contact).where(
                    Contact.id == contact.client_account_id,
                    Contact.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if account is not None:
            targets.append(account)
    for target in targets:
        if target.last_contacted_at is None or occurred_at > target.last_contacted_at:
            target.last_contacted_at = occurred_at


async def _invalidate_communication_context(
    tenant_id: str, matter_id: uuid.UUID | None
) -> None:
    if matter_id is None:
        return
    try:
        if (
            communication_context_cache.cache_enabled
            and not communication_context_cache.redis_client
        ):
            await communication_context_cache.init()
        await communication_context_cache.invalidate_matter_context(
            str(matter_id), tenant_id
        )
    except Exception:
        # The communication is already durable; cache availability must not
        # turn a successful write into an API failure.
        return


# Channels whose rows are always a record of a real message, never a note.
_EVIDENCE_CHANNELS = {"sms", "portal"}
# Fields that describe what was said; re-filing fields are handled separately.
_CONTENT_FIELDS = {"subject", "body", "summary", "status"}


def _content_locked(log: CommunicationLog) -> bool:
    """Whether this row records what was actually sent or received.

    Captured mail, portal and SMS messages and system sends carry a provider
    or system reference, a stored message, or a delivery status. Editing their
    subject or body would rewrite the firm's record of what was said, so only
    hand-logged entries (status "logged", nothing stored behind them) are
    editable.
    """
    return bool(
        log.external_ref
        or log.document_id
        or log.channel in _EVIDENCE_CHANNELS
        or (log.status or "logged") != "logged"
    )


async def communication_responses(
    db: AsyncSession, tenant_id: uuid.UUID, logs
) -> list[CommunicationLogResponse]:
    """Serialize rows with the matter and contact names people recognise."""
    matter_ids = {log.matter_id for log in logs if log.matter_id}
    contact_ids = {log.contact_id for log in logs if log.contact_id}
    matters: dict = {}
    contacts: dict = {}
    if matter_ids:
        rows = await db.execute(
            select(Matter.id, Matter.matter_name, Matter.matter_number).where(
                Matter.tenant_id == tenant_id, Matter.id.in_(matter_ids)
            )
        )
        matters = {row.id: row for row in rows.all()}
    if contact_ids:
        rows = await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id, Contact.id.in_(contact_ids)
            )
        )
        contacts = {contact.id: contact for contact in rows.scalars().all()}

    responses = []
    for log in logs:
        response = CommunicationLogResponse.model_validate(log)
        matter = matters.get(log.matter_id)
        contact = contacts.get(log.contact_id)
        responses.append(
            response.model_copy(
                update={
                    "matter_name": matter.matter_name if matter else None,
                    "matter_number": matter.matter_number if matter else None,
                    "contact_name": contact.display_name if contact else None,
                    "content_locked": _content_locked(log),
                }
            )
        )
    return responses


async def _response(
    db: AsyncSession, tenant_id: uuid.UUID, log: CommunicationLog
) -> CommunicationLogResponse:
    return (await communication_responses(db, tenant_id, [log]))[0]


@router.get("", response_model=CommunicationLogListResponse)
async def list_communications(
    matter_id: Optional[uuid.UUID] = None,
    contact_id: Optional[uuid.UUID] = None,
    channel: Optional[str] = None,
    direction: Optional[str] = None,
    occurred_after: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = str(current_user.tenant_id)
    await set_tenant_context(db, tenant_id)
    can_access_sms = await _can_access_sms(db, current_user.id)
    _require_sms_access(channel=channel, allowed=can_access_sms)

    stmt = select(CommunicationLog).where(
        CommunicationLog.tenant_id == uuid.UUID(tenant_id),
        CommunicationLog.status != "deleted",
    )
    if matter_id:
        stmt = stmt.where(CommunicationLog.matter_id == matter_id)
    if contact_id:
        stmt = stmt.where(CommunicationLog.contact_id == contact_id)
    if channel:
        stmt = stmt.where(CommunicationLog.channel == channel)
    if channel == "sms" and can_access_sms:
        stmt = stmt.where(
            matter_access_predicate(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                is_admin=current_user.role == "admin",
                matter_id_column=CommunicationLog.matter_id,
            )
        )
    elif not channel and can_access_sms:
        stmt = stmt.where(
            or_(
                CommunicationLog.channel != "sms",
                and_(
                    CommunicationLog.channel == "sms",
                    matter_access_predicate(
                        tenant_id=current_user.tenant_id,
                        user_id=current_user.id,
                        is_admin=current_user.role == "admin",
                        matter_id_column=CommunicationLog.matter_id,
                    ),
                ),
            )
        )
    elif not can_access_sms:
        stmt = stmt.where(CommunicationLog.channel != "sms")
    if direction:
        stmt = stmt.where(CommunicationLog.direction == direction)
    if occurred_after:
        stmt = stmt.where(CommunicationLog.occurred_at >= occurred_after)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(CommunicationLog.occurred_at.desc())
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return CommunicationLogListResponse(
        items=await communication_responses(db, uuid.UUID(tenant_id), logs),
        total=total,
    )


@router.post("", response_model=CommunicationLogResponse, status_code=201)
async def create_communication_log(
    payload: CommunicationLogCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = str(current_user.tenant_id)
    await set_tenant_context(db, tenant_id)
    if payload.channel == "sms":
        raise HTTPException(
            status_code=422,
            detail=(
                "Provider SMS communication evidence can only be created by the "
                "signed SMS lifecycle"
            ),
        )
    _require_sms_access(
        channel=payload.channel,
        allowed=await _can_access_sms(db, current_user.id),
    )

    data = payload.model_dump(exclude_none=True)
    if "occurred_at" not in data:
        data["occurred_at"] = datetime.now(timezone.utc)

    log = CommunicationLog(
        tenant_id=uuid.UUID(tenant_id),
        created_by_user_id=current_user.id,
        **data,
    )
    db.add(log)
    await _record_client_contact(
        db, uuid.UUID(tenant_id), log.contact_id, log.occurred_at
    )
    await db.commit()
    await db.refresh(log)
    await _invalidate_communication_context(tenant_id, log.matter_id)
    return await _response(db, uuid.UUID(tenant_id), log)


@router.get("/{log_id}", response_model=CommunicationLogResponse)
async def get_communication_log(
    log_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = str(current_user.tenant_id)
    await set_tenant_context(db, tenant_id)

    result = await db.execute(
        select(CommunicationLog).where(
            CommunicationLog.id == log_id,
            CommunicationLog.tenant_id == uuid.UUID(tenant_id),
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Communication log not found")
    if log.channel == "sms" and not await _can_access_sms_record(
        db, current_user, log.matter_id
    ):
        raise HTTPException(status_code=404, detail="Communication log not found")
    return await _response(db, uuid.UUID(tenant_id), log)


@router.patch("/{log_id}", response_model=CommunicationLogResponse)
async def update_communication_log(
    log_id: uuid.UUID,
    payload: CommunicationLogUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = str(current_user.tenant_id)
    await set_tenant_context(db, tenant_id)

    result = await db.execute(
        select(CommunicationLog)
        .where(
            CommunicationLog.id == log_id,
            CommunicationLog.tenant_id == uuid.UUID(tenant_id),
        )
        .with_for_update()
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Communication log not found")
    if log.channel == "sms" and not await _can_access_sms_record(
        db, current_user, log.matter_id
    ):
        raise HTTPException(status_code=404, detail="Communication log not found")
    if log.channel == "sms":
        raise HTTPException(
            status_code=409,
            detail="Provider SMS communication evidence is immutable",
        )

    changes = payload.model_dump(exclude_none=True)
    content_changes = {
        field
        for field in _CONTENT_FIELDS & changes.keys()
        if changes[field] != getattr(log, field)
    }
    if content_changes and _content_locked(log):
        raise HTTPException(
            status_code=409,
            detail=(
                "This is a record of a message that was actually sent or "
                "received, so its content cannot be edited. It can only be "
                "moved to a different matter or contact."
            ),
        )

    tid = uuid.UUID(tenant_id)
    new_matter_id = changes.get("matter_id")
    if new_matter_id and new_matter_id != log.matter_id:
        # Re-filing puts the message in front of everyone on the target
        # matter, so the person moving it must be able to see that matter.
        if not await can_access_matter(
            db,
            tenant_id=tid,
            user_id=current_user.id,
            is_admin=current_user.role == "admin",
            matter_id=new_matter_id,
        ):
            raise HTTPException(status_code=404, detail="Matter not found")
    new_contact_id = changes.get("contact_id")
    if new_contact_id and new_contact_id != log.contact_id:
        contact_exists = await db.scalar(
            select(Contact.id).where(
                Contact.id == new_contact_id, Contact.tenant_id == tid
            )
        )
        if not contact_exists:
            raise HTTPException(status_code=404, detail="Contact not found")

    previous_matter_id = log.matter_id
    for field, value in changes.items():
        setattr(log, field, value)

    await _record_client_contact(db, tid, log.contact_id, log.occurred_at)
    await db.commit()
    await db.refresh(log)
    await _invalidate_communication_context(tenant_id, previous_matter_id)
    if log.matter_id != previous_matter_id:
        await _invalidate_communication_context(tenant_id, log.matter_id)
    return await _response(db, tid, log)


@router.delete("/{log_id}", status_code=204)
async def delete_communication_log(
    log_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = str(current_user.tenant_id)
    await set_tenant_context(db, tenant_id)

    result = await db.execute(
        select(CommunicationLog)
        .where(
            CommunicationLog.id == log_id,
            CommunicationLog.tenant_id == uuid.UUID(tenant_id),
        )
        .with_for_update()
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Communication log not found")
    if log.channel == "sms" and not await _can_access_sms_record(
        db, current_user, log.matter_id
    ):
        raise HTTPException(status_code=404, detail="Communication log not found")
    if log.channel == "sms":
        raise HTTPException(
            status_code=409,
            detail="Provider SMS communication evidence is immutable",
        )

    log.status = "deleted"
    await db.commit()
    await _invalidate_communication_context(tenant_id, log.matter_id)
