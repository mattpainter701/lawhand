import pytest
from httpx import AsyncClient

from app.services.commercial_pricing import (
    COMMERCIAL_PLANS,
    BillingCadence,
    SeatClass,
    quote_commercial_plan,
)
from tests.platform_auth_helpers import platform_headers


def test_core_and_ai_catalog_prices_are_explicit():
    assert list(COMMERCIAL_PLANS) == ["core", "ai"]

    core = COMMERCIAL_PLANS["core"]
    ai = COMMERCIAL_PLANS["ai"]
    assert core.price_for(SeatClass.ATTORNEY).monthly_cents == 9_900
    assert core.price_for(SeatClass.ATTORNEY).annual_monthly_equivalent_cents == 8_900
    assert ai.price_for(SeatClass.ATTORNEY).monthly_cents == 19_900
    assert ai.price_for(SeatClass.ATTORNEY).annual_monthly_equivalent_cents == 16_900
    assert core.price_for(SeatClass.STAFF) == ai.price_for(SeatClass.STAFF)
    assert ai.premium_ai is True
    assert core.premium_ai is False


@pytest.mark.parametrize(
    "plan_id,attorneys,staff,expected_monthly_cents",
    [
        ("core", 1, 0, 9_900),
        ("ai", 1, 0, 19_900),
        ("core", 1, 2, 17_700),
        ("ai", 1, 2, 27_700),
        ("core", 3, 3, 41_400),
        ("ai", 3, 3, 71_400),
        ("core", 5, 5, 69_000),
        ("ai", 5, 5, 119_000),
    ],
)
def test_monthly_quotes_match_commercial_examples(
    plan_id, attorneys, staff, expected_monthly_cents
):
    quote = quote_commercial_plan(
        plan_id,
        BillingCadence.MONTHLY,
        attorney_seats=attorneys,
        staff_seats=staff,
    )

    assert quote.monthly_equivalent_cents == expected_monthly_cents
    assert quote.billing_period_total_cents == expected_monthly_cents
    assert quote.checkout_ready is False


def test_annual_quote_returns_monthly_equivalent_and_amount_due():
    quote = quote_commercial_plan(
        "ai",
        BillingCadence.ANNUAL,
        attorney_seats=1,
        staff_seats=2,
    )

    assert quote.billing_period_months == 12
    assert quote.monthly_equivalent_cents == 23_500
    assert quote.billing_period_total_cents == 282_000
    assert [(line.seat_class, line.quantity) for line in quote.lines] == [
        (SeatClass.ATTORNEY, 1),
        (SeatClass.STAFF, 2),
    ]


@pytest.mark.parametrize(
    "plan_id,cadence,attorneys,staff,message",
    [
        ("unknown", "monthly", 1, 0, "Unknown commercial plan"),
        ("core", "quarterly", 1, 0, "Unknown billing cadence"),
        ("core", "monthly", 0, 0, "at least one attorney"),
        ("core", "monthly", 1, -1, "cannot be negative"),
    ],
)
def test_quote_rejects_unknown_or_invalid_inputs(
    plan_id, cadence, attorneys, staff, message
):
    with pytest.raises(ValueError, match=message):
        quote_commercial_plan(
            plan_id,
            cadence,
            attorney_seats=attorneys,
            staff_seats=staff,
        )


@pytest.mark.asyncio
async def test_operator_can_review_catalog(client: AsyncClient):
    response = await client.get(
        "/api/platform/commercial-plans", headers=platform_headers(["platform:read"])
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "proposed"
    assert payload["checkout_ready"] is False
    assert [plan["id"] for plan in payload["plans"]] == ["core", "ai"]


@pytest.mark.asyncio
async def test_operator_can_quote_ai_firm(client: AsyncClient):
    response = await client.get(
        "/api/platform/commercial-plans/quote",
        headers=platform_headers(["platform:read"]),
        params={
            "plan_id": "ai",
            "cadence": "monthly",
            "attorney_seats": 1,
            "staff_seats": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["monthly_equivalent_cents"] == 27_700
    assert payload["billing_period_total_cents"] == 27_700
    assert payload["checkout_ready"] is False


@pytest.mark.asyncio
async def test_commercial_catalog_requires_operator_token(client: AsyncClient):
    assert (await client.get("/api/platform/commercial-plans")).status_code == 403
    assert (
        await client.get(
            "/api/platform/commercial-plans/quote",
            params={
                "plan_id": "core",
                "cadence": "monthly",
                "attorney_seats": 1,
                "staff_seats": 0,
            },
        )
    ).status_code == 403
