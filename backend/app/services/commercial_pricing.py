"""Commercial Core/AI catalog and deterministic sales quote calculations.

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
    premium_usage_policy: str
    seat_prices: tuple[SeatPrice, ...]

    def price_for(self, seat_class: SeatClass) -> SeatPrice:
        for price in self.seat_prices:
            if price.seat_class is seat_class:
                return price
        raise ValueError(f"Plan {self.id!r} has no {seat_class.value!r} seat price")


@dataclass(frozen=True)
class QuoteLine:
    seat_class: SeatClass
    quantity: int
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
    checkout_ready: bool = False


_STAFF_PRICE = SeatPrice(
    seat_class=SeatClass.STAFF,
    monthly_cents=3_900,
    annual_monthly_equivalent_cents=3_300,
)

COMMERCIAL_PLANS: dict[str, CommercialPlan] = {
    "core": CommercialPlan(
        id="core",
        label="LawHand Core",
        description="Full practice management with Standard AI.",
        premium_ai=False,
        premium_usage_policy="not_included",
        seat_prices=(
            SeatPrice(
                seat_class=SeatClass.ATTORNEY,
                monthly_cents=9_900,
                annual_monthly_equivalent_cents=8_900,
            ),
            _STAFF_PRICE,
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
        premium_usage_policy="pooled_allowance_then_opt_in_overage",
        seat_prices=(
            SeatPrice(
                seat_class=SeatClass.ATTORNEY,
                monthly_cents=19_900,
                annual_monthly_equivalent_cents=16_900,
            ),
            _STAFF_PRICE,
        ),
    ),
}


def get_commercial_plan(plan_id: str) -> CommercialPlan:
    try:
        return COMMERCIAL_PLANS[plan_id]
    except KeyError as exc:
        raise ValueError(f"Unknown commercial plan: {plan_id}") from exc


def quote_commercial_plan(
    plan_id: str,
    cadence: BillingCadence | str,
    *,
    attorney_seats: int,
    staff_seats: int,
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
                billing_period_total_cents=(
                    monthly_equivalent_cents * period_months
                ),
            )
        )

    monthly_equivalent_cents = sum(
        line.monthly_equivalent_cents for line in lines
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
    )


def serialize_plan(plan: CommercialPlan) -> dict:
    return {
        "id": plan.id,
        "label": plan.label,
        "description": plan.description,
        "premium_ai": plan.premium_ai,
        "premium_usage_policy": plan.premium_usage_policy,
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
    }
