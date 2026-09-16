"""Operator-only review surface for the proposed Core/AI catalog."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.routers.platform import _require_platform_key
from app.services.commercial_pricing import (
    COMMERCIAL_PLANS,
    BillingCadence,
    quote_commercial_plan,
    serialize_plan,
    serialize_quote,
)

router = APIRouter(prefix="/platform/commercial-plans", tags=["platform-pricing"])


@router.get("")
async def list_commercial_plans(request: Request):
    _require_platform_key(request)
    return {
        "plans": [serialize_plan(plan) for plan in COMMERCIAL_PLANS.values()],
        "currency": "USD",
        "checkout_ready": False,
        "status": "proposed",
    }


@router.get("/quote")
async def quote_commercial_plans(
    request: Request,
    plan_id: str = Query(pattern=r"^[a-z][a-z0-9-]{0,39}$"),
    cadence: BillingCadence = Query(),
    attorney_seats: int = Query(ge=1, le=10_000),
    staff_seats: int = Query(ge=0, le=10_000),
):
    _require_platform_key(request)
    try:
        quote = quote_commercial_plan(
            plan_id,
            cadence,
            attorney_seats=attorney_seats,
            staff_seats=staff_seats,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_quote(quote)
