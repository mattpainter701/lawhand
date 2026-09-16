# Core and AI commercial pricing plan

Status: proposed catalog; not connected to checkout or tenant entitlements.

## Decision

LawHand will use two commercial tiers with role-based internal seats:

| Plan | Monthly | Annual monthly equivalent | Product boundary |
| --- | ---: | ---: | --- |
| Core attorney | $99 | $89 | Full practice management and Standard AI |
| AI attorney | $199 | $169 | Core plus matter-aware Premium AI, document analysis, advanced drafting, and automation |
| Staff, either plan | $39 | $33 | Staff workspace access within the firm's selected plan |

Annual prices are monthly equivalents billed for twelve months. Client portal
users are not billable seats. A future accountant/read-only license may be free,
but it is not part of this implementation.

Premium AI will use a firm-pooled allowance followed by administrator-enabled
overage. The included allowance, overage unit, alerts, and spending cap remain
open until reconciled provider cost data supports a margin decision. LawHand
must not promise unlimited Premium AI or silently downgrade confidential work to
Standard when an allowance is exhausted.

## Founding customer

The first customer may be contracted at $200 per month as a time-bounded
Founding Firm offer: one attorney, up to two staff users, full platform access,
Premium AI for the attorney subject to a written fair-use allowance, onboarding,
and a 24-month price lock. This is a negotiated order, not a third public tier.
Additional seats use the applicable Core/AI catalog price stated in the order.

## Why role-based seats

A uniform $200 internal-user price makes a solo attorney expensive and a
staff-heavy firm difficult to adopt. Attorney and staff prices keep the premium
value attached to attorney-facing AI and approval work while making the whole
office usable without account sharing.

License class must be stored independently from authorization roles. Changing a
user's permissions must not silently change the invoice, and changing the paid
license class must not grant legal authority. The eventual migration therefore
needs an explicit `license_class`, not an inference from `users.role`.

## Current-state gaps

The current product has access plans (`demo`, `intake-only`, `mcp-only`, and
`full-platform`) and billing states (`payg`, `flat`, and synthetic tiers). These
are not commercial Core/AI products. Helcim currently exposes one configured
payment plan and snapshots a single flat seat count at enrollment. Per-user
Premium AI is an entitlement toggle, not a separately purchased SKU.

Do not map Core or AI onto the existing `billing_tier` field by name. Product
access, payment state, commercial plan, license class, and AI entitlement are
separate concepts and should remain separately auditable.

## Code boundary in this change

`app.services.commercial_pricing` is the proposed source of truth for catalog
prices and deterministic quotes. The operator-only endpoints are:

- `GET /api/platform/commercial-plans`
- `GET /api/platform/commercial-plans/quote`

Every response says `checkout_ready: false`. The endpoints do not accept money,
change a tenant, activate Premium AI, or alter a payment-provider subscription.
This makes sales examples testable without implying that the migration is done.

## Required implementation before activation

1. Add explicit tenant commercial plan and per-user license class records with
   effective dates and an immutable change history.
2. Decide whether Helcim uses separate Core/AI payment plans plus attorney/staff
   add-ons or invoice line items. Verify taxes, proration, cancellation, renewal,
   quantity changes, and webhook reconciliation in a sandbox.
3. Make seat activation transactional with provider quantity changes. A user
   must not become billable without a durable provider update, and a provider
   failure must not leave an unbilled active seat.
4. Migrate existing `flat` firms deliberately. Never infer AI from historical
   Premium toggles or silently reprice an active customer.
5. Build the Premium allowance ledger, preflight, 50/80/100 percent alerts,
   administrator opt-in overage, monthly cap, and fail-closed exhaustion state.
6. Update the public pricing page only when checkout and entitlements implement
   the same catalog. Until then the proposed operator API remains non-public.
7. Add reconciliation reporting for purchased versus active attorney/staff
   seats and provider invoice quantities.

## Acceptance criteria for checkout readiness

- Core and AI orders produce provider totals identical to the quote engine.
- Annual checkout charges twelve times the displayed monthly equivalent.
- Staff seats cannot enable attorney-only approval or Premium AI authority by
  changing a role label.
- Adding, removing, or reclassifying a seat is idempotent and reconciled with
  the payment provider.
- Existing customers retain their contracted price until an explicit accepted
  order changes it.
- Premium usage cannot exceed the configured cap without recorded administrator
  consent.
- The marketing page, order, checkout, invoice, entitlements, and billing UI all
  identify the same commercial plan and quantities.
