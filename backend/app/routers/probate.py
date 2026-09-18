"""Probate workbench routes for the Trust, Estate & Probate add-on.

Mounted beside the estate router under the same prefix and entitlement. The
determination endpoints never write a court form; they keep the facts, run
the rules, and record what changed on the estate's activity log.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, set_tenant_context
from app.middleware.addon_guard import require_addon_workflow
from app.middleware.tenant import get_current_user
from app.models.plugin import Estate, EstateEvent
from app.routers.estates import _get_estate_or_404
from app.schemas.estate import (
    ProbateAnchorsInput,
    ProbateDeadlineSyncInput,
    ProbateFactsInput,
    ProbateFromIntakeInput,
    ProbateStateResponse,
)
from app.services.access_control import require_capability
from app.services.probate import (
    PROBATE_ADDON,
    deadlines,
    determination,
    facts as facts_module,
    intake,
)
from app.services.probate.facts import ProbateFacts

router = APIRouter(
    prefix="/api/plugins/trust-estate",
    tags=["trust-estate-probate"],
    dependencies=[Depends(require_addon_workflow(PROBATE_ADDON))],
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _facts(estate: Estate) -> ProbateFacts:
    """Facts stored on the estate, with the estate's own columns as fallback."""

    stored = facts_module.from_json(estate.probate_facts or {})
    fallback = facts_module.from_json(
        {
            "decedent_name": estate.grantor,
            "date_of_death": estate.date_of_death,
            "domicile_state": estate.domicile_state,
            "domicile_county": estate.domicile_county,
            "will_execution_date": estate.will_execution_date,
        }
    )
    return facts_module.merge(stored, fallback)


def _apply_to_columns(estate: Estate, facts: ProbateFacts) -> None:
    """Mirror the opening facts onto the estate columns other screens read."""

    if facts.decedent_name and not estate.grantor:
        estate.grantor = facts.decedent_name
    if facts.date_of_death:
        estate.date_of_death = facts.date_of_death
    if facts.domicile_state:
        estate.domicile_state = facts.domicile_state
    if facts.domicile_county:
        estate.domicile_county = facts.domicile_county
    if facts.will_execution_date:
        estate.will_execution_date = facts.will_execution_date
    if facts.probate_property_value is not None and estate.gross_estate_value is None:
        estate.gross_estate_value = facts.probate_property_value


def _determine(
    estate: Estate, facts: ProbateFacts
) -> determination.ProbateDetermination:
    result = determination.determine(facts)
    estate.probate_facts = facts_module.to_json(facts)
    estate.probate_determination = result.to_json()
    estate.probate_track = result.track
    estate.probate_determined_at = datetime.now(timezone.utc)
    estate.updated_at = datetime.now(timezone.utc)
    _apply_to_columns(estate, facts)
    return result


def _event(
    db: AsyncSession, estate: Estate, title: str, content: str | None = None
) -> None:
    db.add(
        EstateEvent(
            id=uuid.uuid4(),
            estate_id=estate.id,
            event_type="probate",
            title=title,
            content=content,
        )
    )


def _anchors(estate: Estate) -> dict:
    return {
        "date_of_death": estate.date_of_death.isoformat()
        if estate.date_of_death
        else None,
        "appointment_date": estate.appointment_date.isoformat()
        if estate.appointment_date
        else None,
        "first_publication_date": estate.first_publication_date.isoformat()
        if estate.first_publication_date
        else None,
        "letters_issued_date": estate.letters_issued_date.isoformat()
        if estate.letters_issued_date
        else None,
        "closing_statement_filed_date": estate.closing_statement_filed_date.isoformat()
        if estate.closing_statement_filed_date
        else None,
    }


async def _state(
    db: AsyncSession, estate: Estate, *, intake_preview: dict | None = None
) -> ProbateStateResponse:
    from app.services.probate import forms as forms_module

    facts = _facts(estate)
    result = estate.probate_determination
    track = estate.probate_track
    forms_state = await forms_module.forms_state(db, estate.tenant_id, track=track)
    return ProbateStateResponse(
        estate_id=str(estate.id),
        matter_id=str(estate.matter_id) if estate.matter_id else None,
        facts=facts_module.to_json(facts),
        determination=result,
        determined_at=estate.probate_determined_at,
        anchors=_anchors(estate),
        forms=forms_state,
        deadlines_preview=deadlines.plan_for_estate(estate, track).to_json(),
        sources=(estate.probate_facts or {}).get("extra", {}).get("sources", []),
        intake=intake_preview,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/estates/{estate_id}/probate", response_model=ProbateStateResponse)
async def read_probate(
    estate_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    estate = await _get_estate_or_404(db, estate_id, user.tenant_id)
    return await _state(db, estate)


@router.put("/estates/{estate_id}/probate/facts", response_model=ProbateStateResponse)
async def save_facts(
    estate_id: str,
    body: ProbateFactsInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Replace the facts with what staff entered and re-run the determination."""

    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    estate = await _get_estate_or_404(db, estate_id, user.tenant_id)
    current = _facts(estate)
    payload = body.model_dump(exclude_unset=True)
    if "heirs" in payload and payload["heirs"] is not None:
        payload["heirs"] = [row for row in payload["heirs"]]
    incoming = facts_module.from_json(payload)
    # Fields the request named are replaced, including being cleared; fields
    # it did not name keep their current value.
    merged = facts_module.merge(current, incoming, overwrite=True)
    cleared = {
        key: None
        for key, value in payload.items()
        if value in (None, "", [])
        and key in facts_module.to_json(ProbateFacts())
        and key not in ("inventory_open", "extra")
    }
    if cleared:
        merged = facts_module.from_json({**facts_module.to_json(merged), **cleared})
    merged = facts_module.ProbateFacts(**{**merged.__dict__, "extra": current.extra})
    previous = estate.probate_track
    result = _determine(estate, merged)
    _event(
        db,
        estate,
        "Probate facts updated",
        f"Track: {result.label}"
        + (f" (was {previous})" if previous and previous != result.track else ""),
    )
    await db.commit()
    await db.refresh(estate)
    return await _state(db, estate)


@router.post(
    "/estates/{estate_id}/probate/facts/from-intake",
    response_model=ProbateStateResponse,
)
async def pull_from_intake(
    estate_id: str,
    body: ProbateFromIntakeInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Read the linked matter's questionnaire answers into the facts.

    Gaps are filled by default; ``overwrite`` replaces what the client's
    answers cover and keeps everything else staff already entered.
    """

    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    estate = await _get_estate_or_404(db, estate_id, user.tenant_id)
    if not estate.matter_id:
        raise HTTPException(
            409, "Link this estate to a matter before pulling intake answers."
        )
    harvested, sources = await intake.harvest(db, user, estate)
    if not sources:
        raise HTTPException(
            404, "No probate questionnaire has been returned for the linked matter yet."
        )
    current = _facts(estate)
    merged = facts_module.merge(current, harvested, overwrite=body.overwrite)
    extra = dict(merged.extra)
    extra["sources"] = sources
    merged = facts_module.ProbateFacts(**{**merged.__dict__, "extra": extra})
    result = _determine(estate, merged)
    _event(
        db,
        estate,
        "Probate facts pulled from intake",
        f"{len(sources)} source(s); track: {result.label}",
    )
    await db.commit()
    await db.refresh(estate)
    return await _state(db, estate)


@router.post(
    "/estates/{estate_id}/probate/determine", response_model=ProbateStateResponse
)
async def recompute(
    estate_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    estate = await _get_estate_or_404(db, estate_id, user.tenant_id)
    previous = estate.probate_track
    result = _determine(estate, _facts(estate))
    if previous != result.track:
        _event(
            db,
            estate,
            "Probate track changed",
            f"{previous or 'none'} → {result.track}",
        )
    await db.commit()
    await db.refresh(estate)
    return await _state(db, estate)


@router.patch(
    "/estates/{estate_id}/probate/anchors", response_model=ProbateStateResponse
)
async def save_anchors(
    estate_id: str,
    body: ProbateAnchorsInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    estate = await _get_estate_or_404(db, estate_id, user.tenant_id)
    changed = []
    for key, value in body.model_dump(exclude_unset=True).items():
        if getattr(estate, key) != value:
            setattr(estate, key, value)
            changed.append(f"{key}={value.isoformat() if value else 'cleared'}")
    if changed:
        estate.updated_at = datetime.now(timezone.utc)
        if body.date_of_death is not None or "date_of_death" in body.model_fields_set:
            _determine(estate, _facts(estate))
        _event(db, estate, "Probate dates updated", "; ".join(changed))
        await db.commit()
        await db.refresh(estate)
    return await _state(db, estate)


@router.post("/estates/{estate_id}/probate/deadlines/sync")
async def sync_deadlines(
    estate_id: str,
    body: ProbateDeadlineSyncInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create or move the statutory deadlines from the estate's anchor dates."""

    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    estate = await _get_estate_or_404(db, estate_id, user.tenant_id)
    if estate.date_of_death is None:
        raise HTTPException(409, "Enter the date of death before building deadlines.")
    result = await deadlines.sync(
        db, estate, mirror_tasks=body.mirror_tasks, actor_id=user.id
    )
    if result["created"] or result["updated"]:
        _event(
            db,
            estate,
            "Probate deadlines built",
            f"{len(result['created'])} created, {len(result['updated'])} moved",
        )
    await db.commit()
    return result


# ── Forms pack ────────────────────────────────────────────────────────────────


@router.get("/probate/forms")
async def list_forms(request: Request, db: AsyncSession = Depends(get_db)):
    """The ND form registry joined with this firm's installed templates.

    Installs the pack on first sight so the Probate tab is never empty for a
    firm that has never opened Template Studio.
    """

    from app.services.probate import forms as forms_module, install as install_module

    user = await get_current_user(request, db)
    await set_tenant_context(db, str(user.tenant_id))
    state = await forms_module.forms_state(db, user.tenant_id)
    if not any(item.get("template_id") for item in state):
        await install_module.install_forms_pack(db, user.tenant_id, user.id)
        state = await forms_module.forms_state(db, user.tenant_id)
    return {"forms": state}


@router.post("/probate/forms/install")
async def install_forms(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_capability("manage_documents")),
):
    from app.services.probate import install as install_module

    await set_tenant_context(db, str(current_user.tenant_id))
    return await install_module.install_forms_pack(
        db, current_user.tenant_id, current_user.id
    )
