"""Resumable fill sessions: keep a preparer's work, and save a packet in the background."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, set_tenant_context
from app.schemas.fill_session import (
    FillSessionListResponse,
    FillSessionCompleteRequest,
    FillSessionRenderRequest,
    FillSessionResponse,
    FillSessionWrite,
)
from app.services import fill_sessions
from app.services.access_control import require_capability

router = APIRouter(tags=["fill-sessions"])


@router.post("/fill-sessions", response_model=FillSessionResponse)
async def write_fill_session(
    payload: FillSessionWrite,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    """Create the caller's session or update the one they own."""
    await set_tenant_context(db, str(current_user.tenant_id))
    session = await fill_sessions.upsert(db, current_user, payload)
    return fill_sessions.response_for(session, include_answers=False)


@router.get("/fill-sessions/{session_id}", response_model=FillSessionResponse)
async def read_fill_session(
    session_id: uuid.UUID,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    """The caller's own session, answers included."""
    await set_tenant_context(db, str(current_user.tenant_id))
    session = await fill_sessions._own_session(db, current_user, session_id)
    return fill_sessions.response_for(session, include_answers=True)


@router.delete("/fill-sessions/{session_id}", status_code=204)
async def abandon_fill_session(
    session_id: uuid.UUID,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    await set_tenant_context(db, str(current_user.tenant_id))
    await fill_sessions.abandon(db, current_user, session_id)


@router.post("/fill-sessions/{session_id}/render", response_model=FillSessionResponse)
async def render_fill_session(
    session_id: uuid.UUID,
    payload: FillSessionRenderRequest,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    """Save every previewed member in the background, as the caller."""
    await set_tenant_context(db, str(current_user.tenant_id))
    session = await fill_sessions.enqueue_render(db, current_user, session_id, payload)
    return fill_sessions.response_for(session, include_answers=False)


@router.post(
    "/fill-sessions/{session_id}/complete", response_model=FillSessionResponse
)
async def complete_fill_session(
    session_id: uuid.UUID,
    payload: FillSessionCompleteRequest,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single-document session saved after verifying its output."""
    await set_tenant_context(db, str(current_user.tenant_id))
    session = await fill_sessions.complete(
        db, current_user, session_id, payload.matter_document_id
    )
    return fill_sessions.response_for(session, include_answers=False)


@router.get(
    "/matters/{matter_id}/fill-sessions", response_model=FillSessionListResponse
)
async def list_matter_fill_sessions(
    matter_id: uuid.UUID,
    current_user=Depends(require_capability("manage_documents")),
    db: AsyncSession = Depends(get_db),
):
    """Packets still in progress for a matter, the caller's own, answers withheld."""
    await set_tenant_context(db, str(current_user.tenant_id))
    sessions = await fill_sessions.list_for_matter(
        db,
        tenant_id=current_user.tenant_id,
        matter_id=matter_id,
        user_id=current_user.id,
    )
    return FillSessionListResponse(
        items=[
            fill_sessions.response_for(item, include_answers=False) for item in sessions
        ]
    )
