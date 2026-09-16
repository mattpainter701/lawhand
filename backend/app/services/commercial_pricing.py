"""Commercial seat/add-on catalog and deterministic sales quote calculations.

This module deliberately does not mutate tenant entitlements or payment-provider
subscriptions.  It gives operator tooling one typed source of truth while the
Helcim quantity and allowance migration is designed and reviewed separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BillingCadence(StrEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SeatClass(StrEnum):
    ATTORNEY = "attorney"
    STAFF = "staff"


class AddonBand(StrEnum):
    SPECIALIST = "specialist"
    WORKSPACE = "workspace"
    PORTAL = "portal"


class UsageMeterVisibility(StrEnum):
    OPERATOR_ONLY = "operator_only"
    TENANT_ADMIN = "tenant_admin"
    AI_USERS = "ai_users"


@dataclass(frozen=True)
class SeatPrice:
    seat_class: SeatClass
    monthly_cents: int
    annual_monthly_equivalent_cents: int

    def unit_monthly_cents(self, cadence: BillingCadence) -> int:
        if cadence is BillingCadence.MONTHLY:
            return self.monthly_cents
        return self.annual_monthly_equivalent_cents


@dataclass(frozen=True)
class CommercialPlan:
    id: str
    label: str
    description: str
    premium_ai: bool
    ai_document_drafting: bool
    ai_automations: bool
    premium_usage_policy: str
    premium_usage_included_cents: int | None
    seat_prices: tuple[SeatPrice, ...]

    def price_for(self, seat_class: SeatClass) -> SeatPrice:
        for price in self.seat_prices:
            if price.seat_class is seat_class:
                return price
        raise ValueError(f"Plan {self.id!r} has no {seat_class.value!r} seat price")


@dataclass(frozen=True)
class CommercialAddon:
    id: str
    label: str
    band: AddonBand
    monthly_cents: int
    annual_monthly_equivalent_cents: int
    billing_scope: str = "firm"
    premium_ai_features_require_ai_seat: bool = True

    def unit_monthly_cents(self, cadence: BillingCadence) -> int:
        if cadence is BillingCadence.MONTHLY:
            return self.monthly_cents
        return self.annual_monthly_equivalent_cents


@dataclass(frozen=True)
class FoundingOffer:
    id: str
    label: str
    monthly_cents: int
    included_ai_attorney_seats: int
    included_core_staff_seats: int
    price_lock_months: int
    usage_hard_cap_source: str = "prepaid_balance_or_promotional_credit"
    usage_meter_visibility: UsageMeterVisibility = UsageMeterVisibility.OPERATOR_ONLY
    usage_meter_visibility_backend_controlled: bool = True
    addons_included: bool = False
    premium_usage_included_cents: int = 0
    public_checkout: bool = False


@dataclass(frozen=True)
class QuoteLine:
    seat_class: SeatClass
    quantity: int
    unit_monthly_cents: int
    monthly_equivalent_cents: int
    billing_period_total_cents: int


@dataclass(frozen=True)
class AddonQuoteLine:
    addon_id: str
    label: str
    band: AddonBand
    unit_monthly_cents: int
    monthly_equivalent_cents: int
    billing_period_total_cents: int


@dataclass(frozen=True)
class CommercialQuote:
    plan: CommercialPlan
    cadence: BillingCadence
    attorney_seats: int
    staff_seats: int
    billing_period_months: int
    monthly_equivalent_cents: int
    billing_period_total_cents: int
    lines: tuple[QuoteLine, ...]
    addon_lines: tuple[AddonQuoteLine, ...]
    checkout_ready: bool = False


COMMERCIAL_PLANS: dict[str, CommercialPlan] = {
    "core": CommercialPlan(
        id="core",
        label="LawHand Core",
        description="Affordable practice management with Standard AI.",
        premium_ai=False,
        ai_document_drafting=False,
        ai_automations=False,
        premium_usage_policy="not_included",
        premium_usage_included_cents=None,
        seat_prices=(
            SeatPrice(
                seat_class=SeatClass.ATTORNEY,
                monthly_cents=4_900,
                annual_monthly_equivalent_cents=3_900,
            ),
            SeatPrice(
                seat_class=SeatClass.STAFF,
                monthly_cents=1_900,
                annual_monthly_equivalent_cents=1_500,
            ),
        ),
    ),
    "ai": CommercialPlan(
        id="ai",
        label="LawHand AI",
        description=(
            "Full practice management with matter-aware Premium AI, document "
            "analysis, advanced drafting, and automation."
        ),
        premium_ai=True,
        ai_document_drafting=True,
        ai_automations=True,
        premium_usage_policy="separate_prepaid_pool_hard_cap",
        premium_usage_included_cents=0,
        seat_prices=(
            SeatPrice(
                seat_class=SeatClass.ATTORNEY,
                monthly_cents=29_900,
                annual_monthly_equivalent_cents=24_900,
            ),
            SeatPrice(
                seat_class=SeatClass.STAFF,
                monthly_cents=14_900,
                annual_monthly_equivalent_cents=12_900,
            ),
        ),
    ),
}


_ADDON_PRICES: dict[AddonBand, tuple[int, int]] = {
    AddonBand.SPECIALIST: (9_900, 7_900),
    AddonBand.WORKSPACE: (19_900, 16_900),
    AddonBand.PORTAL: (29_900, 24_900),
}


def _addon(addon_id: str, label: str, band: AddonBand) -> CommercialAddon:
    monthly_cents, annual_cents = _ADDON_PRICES[band]
    return CommercialAddon(
        id=addon_id,
        label=label,
        band=band,
        monthly_cents=monthly_cents,
        annual_monthly_equivalent_cents=annual_cents,
    )


# Add-ons are billed once per firm. Their IDs intentionally match the canonical
# plugin manifest so catalog coverage can be enforced in tests.
COMMERCIAL_ADDONS: dict[str, CommercialAddon] = {
    "ai-governance-legal": _addon(
        "ai-governance-legal", "AI Governance", AddonBand.SPECIALIST
    ),
    "commercial-legal": _addon(
        "commercial-legal", "Commercial Legal", AddonBand.WORKSPACE
    ),
    "corporate-legal": _addon(
        "corporate-legal", "Corporate Legal", AddonBand.SPECIALIST
    ),
    "criminal-defense": _addon(
        "criminal-defense", "Criminal Defense", AddonBand.SPECIALIST
    ),
    "employment-legal": _addon(
        "employment-legal", "Employment Legal", AddonBand.SPECIALIST
    ),
    "family-law": _addon("family-law", "Family Law", AddonBand.WORKSPACE),
    "ip-legal": _addon("ip-legal", "Intellectual Property", AddonBand.SPECIALIST),
    "litigation-legal": _addon(
        "litigation-legal", "Litigation Legal", AddonBand.WORKSPACE
    ),
    "mediation-legal": _addon("mediation-legal", "Mediation Legal", AddonBand.PORTAL),
    "privacy-legal": _addon("privacy-legal", "Privacy Legal", AddonBand.SPECIALIST),
    "product-legal": _addon("product-legal", "Product Legal", AddonBand.SPECIALIST),
    "real-estate": _addon("real-estate", "Real Estate", AddonBand.SPECIALIST),
    "regulatory-legal": _addon(
        "regulatory-legal", "Regulatory Legal", AddonBand.SPECIALIST
    ),
    "trust-estate-legal": _addon(
        "trust-estate-legal", "Trust & Estate", AddonBand.WORKSPACE
    ),
}


FOUNDING_ATTORNEY_OFFER = FoundingOffer(
    id="founding-attorney-199",
    label="Founding Attorney",
    monthly_cents=19_900,
    included_ai_attorney_seats=1,
    included_core_staff_seats=2,
    price_lock_months=24,
)


def get_commercial_plan(plan_id: str) -> CommercialPlan:
    try:
        return COMMERCIAL_PLANS[plan_id]
    except KeyError as exc:
        raise ValueError(f"Unknown commercial plan: {plan_id}") from exc


def get_commercial_addon(addon_id: str) -> CommercialAddon:
    try:
        return COMMERCIAL_ADDONS[addon_id]
    except KeyError as exc:
        raise ValueError(f"Unknown commercial add-on: {addon_id}") from exc


def quote_commercial_plan(
    plan_id: str,
    cadence: BillingCadence | str,
    *,
    attorney_seats: int,
    staff_seats: int,
    addon_ids: tuple[str, ...] | list[str] = (),
) -> CommercialQuote:
    """Return a quote without authorizing checkout or changing entitlements."""

    plan = get_commercial_plan(plan_id)
    try:
        resolved_cadence = BillingCadence(cadence)
    except ValueError as exc:
        raise ValueError(f"Unknown billing cadence: {cadence}") from exc
    if attorney_seats < 1:
        raise ValueError("A commercial quote requires at least one attorney seat")
    if staff_seats < 0:
        raise ValueError("Staff seat count cannot be negative")
    if len(addon_ids) != len(set(addon_ids)):
        raise ValueError("A commercial add-on cannot appear more than once")

    period_months = 1 if resolved_cadence is BillingCadence.MONTHLY else 12
    lines = []
    for seat_class, quantity in (
        (SeatClass.ATTORNEY, attorney_seats),
        (SeatClass.STAFF, staff_seats),
    ):
        if quantity == 0:
            continue
        unit_monthly_cents = plan.price_for(seat_class).unit_monthly_cents(
            resolved_cadence
        )
        monthly_equivalent_cents = unit_monthly_cents * quantity
        lines.append(
            QuoteLine(
                seat_class=seat_class,
                quantity=quantity,
                unit_monthly_cents=unit_monthly_cents,
                monthly_equivalent_cents=monthly_equivalent_cents,
                billing_period_total_cents=(monthly_equivalent_cents * period_months),
            )
        )

    addon_lines = []
    for addon_id in addon_ids:
        addon = get_commercial_addon(addon_id)
        unit_monthly_cents = addon.unit_monthly_cents(resolved_cadence)
        addon_lines.append(
            AddonQuoteLine(
                addon_id=addon.id,
                label=addon.label,
                band=addon.band,
                unit_monthly_cents=unit_monthly_cents,
                monthly_equivalent_cents=unit_monthly_cents,
                billing_period_total_cents=unit_monthly_cents * period_months,
            )
        )

    monthly_equivalent_cents = sum(
        line.monthly_equivalent_cents for line in (*lines, *addon_lines)
    )
    return CommercialQuote(
        plan=plan,
        cadence=resolved_cadence,
        attorney_seats=attorney_seats,
        staff_seats=staff_seats,
        billing_period_months=period_months,
        monthly_equivalent_cents=monthly_equivalent_cents,
        billing_period_total_cents=monthly_equivalent_cents * period_months,
        lines=tuple(lines),
        addon_lines=tuple(addon_lines),
    )


def serialize_plan(plan: CommercialPlan) -> dict:
    return {
        "id": plan.id,
        "label": plan.label,
        "description": plan.description,
        "premium_ai": plan.premium_ai,
        "ai_document_drafting": plan.ai_document_drafting,
        "ai_automations": plan.ai_automations,
        "premium_usage_policy": plan.premium_usage_policy,
        "premium_usage_included_cents": plan.premium_usage_included_cents,
        "seat_prices": [
            {
                "seat_class": price.seat_class.value,
                "monthly_cents": price.monthly_cents,
                "annual_monthly_equivalent_cents": (
                    price.annual_monthly_equivalent_cents
                ),
            }
            for price in plan.seat_prices
        ],
    }


def serialize_addon(addon: CommercialAddon) -> dict:
    return {
        "id": addon.id,
        "label": addon.label,
        "band": addon.band.value,
        "billing_scope": addon.billing_scope,
        "monthly_cents": addon.monthly_cents,
        "annual_monthly_equivalent_cents": (addon.annual_monthly_equivalent_cents),
        "premium_ai_features_require_ai_seat": (
            addon.premium_ai_features_require_ai_seat
        ),
    }


def serialize_founding_offer(offer: FoundingOffer) -> dict:
    return {
        "id": offer.id,
        "label": offer.label,
        "monthly_cents": offer.monthly_cents,
        "included_ai_attorney_seats": offer.included_ai_attorney_seats,
        "included_core_staff_seats": offer.included_core_staff_seats,
        "price_lock_months": offer.price_lock_months,
        "usage_hard_cap_source": offer.usage_hard_cap_source,
        "usage_meter_visibility": offer.usage_meter_visibility.value,
        "usage_meter_visibility_backend_controlled": (
            offer.usage_meter_visibility_backend_controlled
        ),
        "addons_included": offer.addons_included,
        "premium_usage_included_cents": offer.premium_usage_included_cents,
        "public_checkout": offer.public_checkout,
    }


def serialize_quote(quote: CommercialQuote) -> dict:
    return {
        "plan": serialize_plan(quote.plan),
        "cadence": quote.cadence.value,
        "attorney_seats": quote.attorney_seats,
        "staff_seats": quote.staff_seats,
        "billing_period_months": quote.billing_period_months,
        "monthly_equivalent_cents": quote.monthly_equivalent_cents,
        "billing_period_total_cents": quote.billing_period_total_cents,
        "checkout_ready": quote.checkout_ready,
        "lines": [
            {
                "seat_class": line.seat_class.value,
                "quantity": line.quantity,
                "unit_monthly_cents": line.unit_monthly_cents,
                "monthly_equivalent_cents": line.monthly_equivalent_cents,
                "billing_period_total_cents": line.billing_period_total_cents,
            }
            for line in quote.lines
        ],
        "addon_lines": [
            {
                "addon_id": line.addon_id,
                "label": line.label,
                "band": line.band.value,
                "unit_monthly_cents": line.unit_monthly_cents,
                "monthly_equivalent_cents": line.monthly_equivalent_cents,
                "billing_period_total_cents": line.billing_period_total_cents,
            }
            for line in quote.addon_lines
        ],
    }
