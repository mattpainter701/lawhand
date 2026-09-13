"""LawHand subscriptions; deliberately independent of matter billing and QBO."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, set_tenant_context
from app.models.platform_subscription import PlatformSubscription
from app.models.tenant import Tenant
from app.services import platform_billing as service
from app.services.access_control import can_manage_finance, require_finance_admin

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    fingerprint: str = Field(default="", max_length=64)
    update_method: bool = False


class CheckoutResult(BaseModel):
    checkout_token: str = Field(min_length=1, max_length=200)
    data: dict
    signature: str = Field(min_length=64, max_length=64)


def require_provider():
    if service.settings.PLATFORM_BILLING_PROVIDER != "helcim":
        raise HTTPException(409, "Helcim subscription billing is not enabled")


async def require_subscription_manager(request, db):
    from app.services.rbac_service import get_user_capabilities

    user = await require_finance_admin(request, db)
    if not can_manage_finance(
        user.role
    ) and "manage_billing" not in await get_user_capabilities(db, user.id):
        raise HTTPException(403, "Manage billing permission required")
    return user


@router.get("/subscription/offer")
async def offer(request: Request, db: AsyncSession = Depends(get_db)):
    require_provider()
    user = await require_finance_admin(request, db)
    tenant = await db.get(Tenant, user.tenant_id)
    return await service.subscription_offer(tenant)


@router.post("/subscription/checkout")
async def checkout(
    body: CheckoutRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    require_provider()
    user = await require_subscription_manager(request, db)
    return await service.begin_checkout(
        db, user.tenant_id, user, body.fingerprint, update_method=body.update_method
    )


@router.post("/subscription/complete")
async def complete(
    body: CheckoutResult, request: Request, db: AsyncSession = Depends(get_db)
):
    require_provider()
    user = await require_subscription_manager(request, db)
    return await service.finish_checkout(
        db, user.tenant_id, body.checkout_token, body.data, body.signature
    )


@router.post("/subscription/refresh")
async def refresh(request: Request, db: AsyncSession = Depends(get_db)):
    require_provider()
    user = await require_subscription_manager(request, db)
    return await service.refresh_subscription(db, user.tenant_id)


@router.post("/subscription/cancel")
async def cancel(request: Request, db: AsyncSession = Depends(get_db)):
    require_provider()
    user = await require_subscription_manager(request, db)
    return await service.cancel_subscription(db, user.tenant_id)


@router.post("/provider-events")
async def provider_event(request: Request, db: AsyncSession = Depends(get_db)):
    require_provider()
    body = await request.body()
    if len(body) > 65536 or not service.verify_event(body, request.headers):
        raise HTTPException(400, "Invalid billing event signature")
    try:
        event = await request.json()
        if event.get("type") != "cardTransaction":
            return {"status": "ignored"}
        transaction_id = str(event["id"])
        if not transaction_id.isdecimal() or len(transaction_id) > 30:
            raise ValueError()
    except (ValueError, KeyError, AttributeError):
        raise HTTPException(400, "Invalid billing event")
    transaction = service.single(
        await service.request_helcim("GET", f"card-transactions/{transaction_id}")
    )
    code = transaction.get("customerCode", "")
    try:
        if not isinstance(code, str) or not code.startswith("LH") or len(code) != 34:
            return {"status": "ignored"}
        tenant_id = uuid.UUID(hex=code[2:])
    except ValueError:
        return {"status": "ignored"}
    await set_tenant_context(db, str(tenant_id))
    row = await db.scalar(
        select(PlatformSubscription).where(PlatformSubscription.tenant_id == tenant_id)
    )
    if not row or row.customer_code != code:
        return {"status": "ignored"}
    # Repeated and out-of-order events only refresh canonical provider state.
    await service.refresh_subscription(db, tenant_id)
    return {"status": "ok"}
