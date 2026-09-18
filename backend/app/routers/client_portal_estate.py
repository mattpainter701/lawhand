"""The client's estate inventory inside the native My Matters portal.

After the personal representative is appointed, the client can list what the
estate owns — a bank account, the farmland, a vehicle — with a rough value
and a statement or photo. Staff verify each row before it counts toward
anything: only verified assets feed the court's Inventory and Appraisement
(Form 10) and the estate's own totals.

Fail-closed like the mediation overlay: an active Trust, Estate & Probate
entitlement, exactly one estate linked to the portal's matter, and the estate
belonging to this contact. Anything else is a 404 that never says whether an
estate exists. The core portal is untouched by a missing overlay.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.estate import EstateAsset
from app.models.matter_document import MatterDocument
from app.models.plugin import Estate, Matter
from app.routers.client_portal import ClientPortalContext, portal_matter_dep
from app.services.plugin_entitlements import (
    load_plugin_entitlement,
    plugin_entitlement_is_active,
)
from app.services.probate import PROBATE_ADDON

router = APIRouter(prefix="/api/portal/client", tags=["client-portal-estate"])

CLIENT_SOURCE = "client_portal"

#: Plain-language categories the client picks from; stored as the estate's own
#: category keys so staff see the same list they use.
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("bank_account", "Bank or credit union account"),
    ("real_property", "House, land, farmland, or minerals"),
    ("vehicle", "Vehicle, boat, or equipment"),
    ("securities", "Stocks, bonds, or investment account"),
    ("retirement", "Retirement account (IRA, 401(k), pension)"),
    ("life_insurance", "Life insurance"),
    ("business_interest", "Business or farm interest"),
    ("personal_property", "Personal belongings of value"),
    ("other", "Something else"),
)
OWNERSHIP: tuple[tuple[str, str], ...] = (
    ("sole", "In their name only"),
    ("joint", "Jointly with someone still living"),
    ("tod_pod", "Names a beneficiary (POD/TOD)"),
    ("unknown", "Not sure"),
)


class PortalAssetInput(BaseModel):
    name: str = Field(min_length=1, max_length=400)
    category: Literal[tuple(key for key, _ in CATEGORIES)] = "other"  # type: ignore[valid-type]
    ownership_type: Literal[tuple(key for key, _ in OWNERSHIP)] = "unknown"  # type: ignore[valid-type]
    approximate_value: Optional[str] = Field(None, max_length=40)
    institution: Optional[str] = Field(None, max_length=300)
    notes: Optional[str] = Field(None, max_length=2000)
    artifact_document_id: Optional[uuid.UUID] = None


class PortalAssetResponse(BaseModel):
    id: str
    name: str
    category: str
    ownership_type: Optional[str]
    approximate_value: Optional[str]
    institution: Optional[str]
    notes: Optional[str]
    artifact_document_id: Optional[str]
    verification_status: str
    editable: bool
    submitted_at: Optional[datetime]


class PortalEstateView(BaseModel):
    estate_id: str
    decedent_name: Optional[str]
    inventory_open: bool
    appointment_date: Optional[date]
    assets: list[PortalAssetResponse]
    categories: list[dict]
    ownership_options: list[dict]


async def _native_estate(db: AsyncSession, ctx: ClientPortalContext) -> Estate:
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    matter_id = uuid.UUID(str(ctx.matter_id))
    entitlement = await load_plugin_entitlement(db, tenant_id, PROBATE_ADDON)
    if not plugin_entitlement_is_active(entitlement):
        raise HTTPException(status_code=404, detail="Estate inventory not found")
    estates = list(
        (
            await db.execute(
                select(Estate).where(
                    Estate.tenant_id == tenant_id,
                    Estate.matter_id == matter_id,
                    Estate.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(estates) != 1:
        raise HTTPException(status_code=404, detail="Estate inventory not found")
    estate = estates[0]
    matter = await db.get(Matter, matter_id)
    contact_id = str(ctx.contact_id) if ctx.contact_id else None
    owner = (
        str(estate.client_contact_id)
        if estate.client_contact_id
        else (
            str(matter.client_contact_id)
            if matter and matter.client_contact_id
            else None
        )
    )
    if not contact_id or owner != contact_id:
        raise HTTPException(status_code=404, detail="Estate inventory not found")
    return estate


def _inventory_open(estate: Estate) -> bool:
    facts = estate.probate_facts or {}
    return bool(estate.appointment_date) or bool(facts.get("inventory_open"))


def _money_text(value: Decimal | None) -> str | None:
    return f"{value:,.2f}" if value is not None else None


def _parse_money(value: str | None) -> Decimal | None:
    from app.services.probate.facts import parse_money

    if value is None or not str(value).strip():
        return None
    parsed = parse_money(value)
    if parsed is None:
        raise HTTPException(422, "Enter the value as a number, for example 12,500.")
    return parsed


def _response(row: EstateAsset) -> PortalAssetResponse:
    return PortalAssetResponse(
        id=str(row.id),
        name=row.name,
        category=row.category,
        ownership_type=row.ownership_type,
        approximate_value=_money_text(row.date_of_death_value),
        institution=row.institution,
        notes=row.notes,
        artifact_document_id=str(row.artifact_document_id)
        if row.artifact_document_id
        else None,
        verification_status=row.verification_status,
        editable=row.source == CLIENT_SOURCE
        and row.verification_status == "unverified",
        submitted_at=row.submitted_at,
    )


async def _client_rows(db: AsyncSession, estate: Estate) -> list[EstateAsset]:
    return list(
        (
            await db.execute(
                select(EstateAsset)
                .where(
                    EstateAsset.estate_id == estate.id,
                    EstateAsset.tenant_id == estate.tenant_id,
                    EstateAsset.source == CLIENT_SOURCE,
                )
                .order_by(EstateAsset.created_at)
            )
        )
        .scalars()
        .all()
    )


async def _view(db: AsyncSession, estate: Estate) -> PortalEstateView:
    facts = estate.probate_facts or {}
    return PortalEstateView(
        estate_id=str(estate.id),
        decedent_name=facts.get("decedent_name") or estate.grantor,
        inventory_open=_inventory_open(estate),
        appointment_date=estate.appointment_date,
        assets=[_response(row) for row in await _client_rows(db, estate)],
        categories=[{"key": key, "label": label} for key, label in CATEGORIES],
        ownership_options=[{"key": key, "label": label} for key, label in OWNERSHIP],
    )


async def _own_document(
    db: AsyncSession, ctx: ClientPortalContext, document_id: uuid.UUID | None
) -> None:
    if document_id is None:
        return
    document = await db.scalar(
        select(MatterDocument).where(
            MatterDocument.id == document_id,
            MatterDocument.tenant_id == uuid.UUID(str(ctx.tenant_id)),
            MatterDocument.matter_id == uuid.UUID(str(ctx.matter_id)),
            MatterDocument.uploaded_by_user_id.is_(None),
            MatterDocument.document_category == "client_uploads",
        )
    )
    if document is None:
        raise HTTPException(404, "Uploaded statement not found")


@router.get("/estate", response_model=PortalEstateView)
async def portal_estate(
    resolved: tuple[ClientPortalContext, Matter] = Depends(portal_matter_dep),
    db: AsyncSession = Depends(get_db),
):
    ctx, _matter = resolved
    estate = await _native_estate(db, ctx)
    return await _view(db, estate)


@router.post("/estate/assets", response_model=PortalEstateView, status_code=201)
async def portal_add_asset(
    body: PortalAssetInput,
    resolved: tuple[ClientPortalContext, Matter] = Depends(portal_matter_dep),
    db: AsyncSession = Depends(get_db),
):
    ctx, _matter = resolved
    estate = await _native_estate(db, ctx)
    if not _inventory_open(estate):
        raise HTTPException(
            409,
            "The inventory opens once the court appoints the personal representative.",
        )
    await _own_document(db, ctx, body.artifact_document_id)
    now = datetime.now(timezone.utc)
    db.add(
        EstateAsset(
            id=uuid.uuid4(),
            tenant_id=estate.tenant_id,
            estate_id=estate.id,
            name=body.name.strip(),
            category=body.category,
            ownership_type=body.ownership_type,
            date_of_death_value=_parse_money(body.approximate_value),
            institution=(body.institution or "").strip() or None,
            notes=(body.notes or "").strip() or None,
            artifact_document_id=body.artifact_document_id,
            is_probate=body.ownership_type == "sole",
            source=CLIENT_SOURCE,
            verification_status="unverified",
            submitted_at=now,
        )
    )
    await db.commit()
    return await _view(db, estate)


@router.patch("/estate/assets/{asset_id}", response_model=PortalEstateView)
async def portal_update_asset(
    asset_id: uuid.UUID,
    body: PortalAssetInput,
    resolved: tuple[ClientPortalContext, Matter] = Depends(portal_matter_dep),
    db: AsyncSession = Depends(get_db),
):
    ctx, _matter = resolved
    estate = await _native_estate(db, ctx)
    row = await db.scalar(
        select(EstateAsset).where(
            EstateAsset.id == asset_id,
            EstateAsset.estate_id == estate.id,
            EstateAsset.tenant_id == estate.tenant_id,
        )
    )
    if row is None or row.source != CLIENT_SOURCE:
        raise HTTPException(404, "Asset not found")
    if row.verification_status != "unverified":
        raise HTTPException(
            409, "The office has already reviewed this item; contact them to change it."
        )
    await _own_document(db, ctx, body.artifact_document_id)
    row.name = body.name.strip()
    row.category = body.category
    row.ownership_type = body.ownership_type
    row.date_of_death_value = _parse_money(body.approximate_value)
    row.institution = (body.institution or "").strip() or None
    row.notes = (body.notes or "").strip() or None
    row.artifact_document_id = body.artifact_document_id
    row.is_probate = body.ownership_type == "sole"
    row.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    return await _view(db, estate)
