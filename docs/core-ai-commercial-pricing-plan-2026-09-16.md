# Core, AI, and add-on commercial pricing plan

Status: proposed catalog; not connected to checkout or tenant entitlements.

## Decision

LawHand will keep the general practice-management base inexpensive and earn
additional revenue from Premium AI access, provider-funded AI usage, and
specialized practice modules.

| Seat | Monthly | Annual monthly equivalent | Product boundary |
| --- | ---: | ---: | --- |
| Core attorney | $49 | $39 | Practice management, ordinary templates, manual drafting, deterministic workflows, and Standard AI |
| Core staff | $19 | $15 | Core workspace without Premium AI drafting or AI automations |
| AI attorney | $299 | $249 | Core plus matter-aware Premium AI, document analysis, advanced drafting, and AI automation access |
| AI staff | $149 | $129 | Premium drafting, analysis, and AI automation access within the staff user's authority |

Annual prices are monthly equivalents billed for twelve months. Client portal
users are not billable seats. A future accountant/read-only license may be free,
but it is not part of this implementation.

Core does **not** include Premium AI document drafting, document analysis, or
AI-driven automations. The AI seat price buys access to those workflows; it is
not an unlimited inference bundle.

## Founding Attorney — $199 per month

The first attorney is offered the non-public `founding-attorney-199` contract:

- exactly $199 per month;
- one AI attorney seat and up to two Core staff seats;
- a 24-month price lock from the contract effective date;
- no practice-area add-ons included; and
- zero included Premium AI usage unless a signed order states a separate,
  fixed-dollar promotional credit and expiry.

The prepaid balance or signed promotional credit is also the founding firm's
hard AI cap. A server-side meter reserves and reconciles every request whether
or not the customer can see that meter. Its founding default is
`operator_only`: LawHand operators can monitor the cap while the tenant UI is
hidden. A backend policy may change visibility to `tenant_admin` or `ai_users`
without changing the balance, ledger, or enforcement behavior.

This is a negotiated founding contract, not a third public tier. Additional
seats use the applicable public catalog price. AI staff upgrades, modules, and
AI usage are separate line items. The price lock applies to the founding bundle,
not to provider usage rates or newly purchased products.

## AI usage funded before inference

All Premium drafting, analysis, and AI automation debits a prepaid firm wallet
before work is sent through LawHand's OpenRouter key. The initial catalog
includes $0 of Premium usage in every seat and add-on price.

At activation, the customer charge should be the greater of:

- two times reconciled provider cost; or
- a published minimum charge for the operation.

This establishes a 50% gross-margin floor before payment costs and LawHand
infrastructure. The broker must reserve against the worst-case priced request,
reconcile the reservation to the authoritative provider spend, and fail closed
when either the wallet or reliable pricing is unavailable.

When the prepaid balance reaches zero, Premium work stops and asks an
administrator to add funds. There is no automatic overage, negative balance,
unlimited plan, or silent downgrade of confidential work to a cheaper model.
Alerts should fire at 50%, 80%, and 100% consumption. A separately supported
bring-your-own-key offer may remove the provider-cost debit, but it does not
remove the AI software seat or module charge.

## Practice modules are the add-on business

Modules are tenant-level purchases billed once per firm, not once per user. A
module unlocks its specialized templates, data model, calculators, and workflow
surface. Premium AI actions inside a purchased module still require an AI seat
and prepaid wallet balance.

| Add-on band | Monthly per firm | Annual monthly equivalent | Current modules |
| --- | ---: | ---: | --- |
| Specialist pack | $99 | $79 | AI Governance, Corporate, Criminal Defense, Employment, Intellectual Property, Privacy, Product, Real Estate, Regulatory |
| Workflow workspace | $199 | $169 | Commercial, Family Law, Litigation, Trust & Estate |
| Portal workspace | $299 | $249 | Mediation |

The band follows the product already present in the repository: specialist
packs primarily supply expert skills and templates, workflow workspaces have a
dedicated operational application, and a portal workspace adds external-party
collaboration. The commercial catalog uses the canonical plugin IDs and tests
that every plugin has exactly one price. Adding a plugin without pricing it will
fail the catalog test.

## Why this structure

A cheap Core seat lets a solo or small firm adopt the system without paying an
AI tax. Expensive AI seats charge for high-value capability and operational
complexity, while the prepaid wallet prevents unpredictable OpenRouter spend
from consuming subscription revenue. Firm-level module pricing monetizes the
specialized vertical product without multiplying the same module charge across
every assistant in a small office.

License class must be stored independently from authorization roles. Changing a
user's permissions must not silently change the invoice, and changing the paid
license class must not grant legal authority. The eventual migration therefore
needs an explicit `license_class`, not an inference from `users.role`.

## Current-state gaps found in the app

The product already has most of the add-on entitlement shape but not commercial
checkout:

- access plans (`demo`, `intake-only`, `mcp-only`, and `full-platform`) and
  billing states (`payg`, `flat`, and synthetic tiers) are not Core/AI products;
- `TenantPluginEntitlement` already supports tenant-level purchased, included,
  and trial states plus seat limits and effective dates;
- skill execution checks the plugin entitlement before model spend;
- the Plugins page exposes Purchase and Trial actions, but Purchase currently
  writes a local `purchased` status without collecting money;
- strict entitlement enforcement defaults off for legacy compatibility;
- the Helcim enrollment path rejects plans containing add-on IDs; and
- plugin manifests previously had no commercial price or provider SKU.

Do not map Core or AI onto the existing `billing_tier` field by name. Product
access, payment state, commercial plan, license class, module entitlement, and
AI usage balance are separate concepts and should remain separately auditable.

## Code boundary in this change

`app.services.commercial_pricing` is the proposed typed source of truth for:

- Core and AI seat prices;
- the exact Founding Attorney contract;
- every current plugin's firm-level add-on price; and
- deterministic combined seat-and-module quotes.

The operator-only endpoints are:

- `GET /api/platform/commercial-plans`
- `GET /api/platform/commercial-plans/quote`

The quote endpoint accepts repeated `addon_ids` query parameters. Every response
says `checkout_ready: false`. These endpoints do not accept money, change a
tenant, activate AI, grant a plugin, or alter a payment-provider subscription.

## Required implementation before activation

1. Add explicit tenant commercial plan and per-user license class records with
   effective dates and immutable change history.
2. Add provider SKUs for Core seats, AI seats, each add-on band, and AI wallet
   top-ups. Verify taxes, proration, cancellation, renewal, quantity changes,
   idempotency, and webhook reconciliation in a sandbox.
3. Replace the Plugins page's local Purchase mutation with checkout. Grant a
   `purchased` entitlement only after a verified provider event, then enable
   strict entitlement enforcement for migrated tenants.
4. Make seat activation transactional with provider quantity changes. A user
   must not become billable without a durable provider update, and a provider
   failure must not leave an unbilled active seat.
5. Build the prepaid Premium usage ledger with atomic reservation and
   reconciliation, 50/80/100% alerts, administrator-funded top-ups, the 2x
   provider-cost margin floor, and fail-closed zero-balance behavior.
6. Migrate existing `flat` firms deliberately. Never infer AI or paid modules
   from historical toggles and never silently reprice an active customer.
7. Update public pricing only when checkout, invoices, usage, and entitlements
   implement this same catalog.
8. Add reconciliation reporting for purchased versus active seats, module
   entitlements, provider invoice quantities, wallet liabilities, and provider
   spend.

## Acceptance criteria for checkout readiness

- Core/AI seats and modules produce provider totals identical to the quote.
- The signed founding order is exactly $199 monthly and cannot acquire included
  usage or add-ons through defaults.
- Hiding the founding usage meter never disables server-side reservations,
  reconciliation, alerts, or the zero-balance hard stop.
- Annual checkout charges twelve times the displayed monthly equivalent.
- Staff seats cannot enable attorney-only approval authority by changing a role.
- A module purchase is billed once per tenant and granted only after verified
  payment; cancellation and expiry revoke it predictably.
- Premium usage cannot exceed prepaid balance. Every reservation reconciles to
  authoritative provider cost and honors the customer charge/margin policy.
- Existing customers retain contracted prices until an accepted order changes
  them.
- Marketing, order, checkout, invoice, entitlement, wallet, and billing UI all
  identify the same products and quantities.
