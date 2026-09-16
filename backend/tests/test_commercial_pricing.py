import pytest
from httpx import AsyncClient

from app.services.commercial_pricing import (
    COMMERCIAL_ADDONS,
    COMMERCIAL_PLANS,
    FOUNDING_ATTORNEY_OFFER,
    AddonBand,
    BillingCadence,
    SeatClass,
    UsageMeterVisibility,
    quote_commercial_plan,
)
from app.services.plugins.manifest import valid_plugin_names
from tests.platform_auth_helpers import platform_headers


def test_core_and_ai_catalog_prices_are_explicit():
    assert list(COMMERCIAL_PLANS) == ["core", "ai"]

    core = COMMERCIAL_PLANS["core"]
    ai = COMMERCIAL_PLANS["ai"]
    assert core.price_for(SeatClass.ATTORNEY).monthly_cents == 4_900
    assert core.price_for(SeatClass.ATTORNEY).annual_monthly_equivalent_cents == 3_900
    assert ai.price_for(SeatClass.ATTORNEY).monthly_cents == 29_900
    assert ai.price_for(SeatClass.ATTORNEY).annual_monthly_equivalent_cents == 24_900
    assert core.price_for(SeatClass.STAFF).monthly_cents == 1_900
    assert core.price_for(SeatClass.STAFF).annual_monthly_equivalent_cents == 1_500
    assert ai.price_for(SeatClass.STAFF).monthly_cents == 14_900
    assert ai.price_for(SeatClass.STAFF).annual_monthly_equivalent_cents == 12_900
    assert ai.premium_ai is True
    assert core.premium_ai is False
    assert ai.ai_document_drafting is True
    assert ai.ai_automations is True
    assert core.ai_document_drafting is False
    assert core.ai_automations is False
    assert ai.premium_usage_policy == "separate_prepaid_pool_hard_cap"
    assert ai.premium_usage_included_cents == 0
    assert core.premium_usage_included_cents is None


def test_every_plugin_has_a_firm_level_commercial_addon():
    assert set(COMMERCIAL_ADDONS) == valid_plugin_names()
    assert all(addon.billing_scope == "firm" for addon in COMMERCIAL_ADDONS.values())
    assert all(
        addon.premium_ai_features_require_ai_seat
        for addon in COMMERCIAL_ADDONS.values()
    )


def test_founding_attorney_offer_is_exact_and_cost_bounded():
    offer = FOUNDING_ATTORNEY_OFFER
    assert offer.id == "founding-attorney-199"
    assert offer.monthly_cents == 19_900
    assert offer.included_ai_attorney_seats == 1
    assert offer.included_core_staff_seats == 2
    assert offer.price_lock_months == 24
    assert offer.usage_hard_cap_source == "prepaid_balance_or_promotional_credit"
    assert offer.usage_meter_visibility is UsageMeterVisibility.OPERATOR_ONLY
    assert offer.usage_meter_visibility_backend_controlled is True
    assert offer.premium_usage_included_cents == 0
    assert offer.addons_included is False
    assert offer.public_checkout is False


@pytest.mark.parametrize(
    "addon_id,band,monthly_cents,annual_cents",
    [
        ("privacy-legal", AddonBand.SPECIALIST, 9_900, 7_900),
        ("family-law", AddonBand.WORKSPACE, 19_900, 16_900),
        ("mediation-legal", AddonBand.PORTAL, 29_900, 24_900),
    ],
)
def test_addon_price_bands_are_explicit(addon_id, band, monthly_cents, annual_cents):
    addon = COMMERCIAL_ADDONS[addon_id]
    assert addon.band is band
    assert addon.monthly_cents == monthly_cents
    assert addon.annual_monthly_equivalent_cents == annual_cents


@pytest.mark.parametrize(
    "plan_id,attorneys,staff,expected_monthly_cents",
    [
        ("core", 1, 0, 4_900),
        ("ai", 1, 0, 29_900),
        ("core", 1, 2, 8_700),
        ("ai", 1, 2, 59_700),
        ("core", 3, 3, 20_400),
        ("ai", 3, 3, 134_400),
        ("core", 5, 5, 34_000),
        ("ai", 5, 5, 224_000),
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
    assert quote.monthly_equivalent_cents == 50_700
    assert quote.billing_period_total_cents == 608_400
    assert [(line.seat_class, line.quantity) for line in quote.lines] == [
        (SeatClass.ATTORNEY, 1),
        (SeatClass.STAFF, 2),
    ]


def test_quote_adds_each_module_once_at_the_firm_price():
    quote = quote_commercial_plan(
        "core",
        BillingCadence.MONTHLY,
        attorney_seats=1,
        staff_seats=2,
        addon_ids=("family-law", "mediation-legal"),
    )

    assert quote.monthly_equivalent_cents == 58_500
    assert [line.addon_id for line in quote.addon_lines] == [
        "family-law",
        "mediation-legal",
    ]
    assert [line.monthly_equivalent_cents for line in quote.addon_lines] == [
        19_900,
        29_900,
    ]


@pytest.mark.parametrize(
    "addon_ids,message",
    [
        (("does-not-exist",), "Unknown commercial add-on"),
        (("family-law", "family-law"), "cannot appear more than once"),
    ],
)
def test_quote_rejects_unknown_or_duplicate_addons(addon_ids, message):
    with pytest.raises(ValueError, match=message):
        quote_commercial_plan(
            "core",
            "monthly",
            attorney_seats=1,
            staff_seats=0,
            addon_ids=addon_ids,
        )


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
    assert {addon["id"] for addon in payload["addons"]} == valid_plugin_names()
    assert all(addon["billing_scope"] == "firm" for addon in payload["addons"])
    assert payload["founding_offer"] == {
        "id": "founding-attorney-199",
        "label": "Founding Attorney",
        "monthly_cents": 19_900,
        "included_ai_attorney_seats": 1,
        "included_core_staff_seats": 2,
        "price_lock_months": 24,
        "usage_hard_cap_source": "prepaid_balance_or_promotional_credit",
        "usage_meter_visibility": "operator_only",
        "usage_meter_visibility_backend_controlled": True,
        "addons_included": False,
        "premium_usage_included_cents": 0,
        "public_checkout": False,
    }


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
            "addon_ids": ["family-law", "mediation-legal"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["monthly_equivalent_cents"] == 109_500
    assert payload["billing_period_total_cents"] == 109_500
    assert payload["plan"]["ai_document_drafting"] is True
    assert payload["plan"]["ai_automations"] is True
    assert payload["plan"]["premium_usage_included_cents"] == 0
    assert payload["plan"]["premium_usage_policy"] == ("separate_prepaid_pool_hard_cap")
    assert [line["addon_id"] for line in payload["addon_lines"]] == [
        "family-law",
        "mediation-legal",
    ]
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
