# Trial access, paying, and premium AI

How a firm on a free trial is treated while the trial runs, after it ends, and
once it pays through Helcim. Public signup itself stays off
(`PUBLIC_SIGNUP_ENABLED=false`) until the whole trial-to-paid path has been
rehearsed.

## Where trial state lives

- `Tenant.expires_at` is the enforcement boundary. Signup sets it to
  `SIGNUP_TRIAL_DAYS` (30) from now. The operator trial editor
  (`PUT /api/platform/tenants/{id}` with `trial_ends_at`) moves or clears it.
- `TenantSettings.custom_config` carries the display marker: `trial`,
  `trial_started_at`, `trial_ends_at`, and after conversion
  `trial_converted_at`.
- Demo and fixture workspaces also use `expires_at`, but they are synthetic
  tenants and none of the trial rules below apply to them.

`app/services/tenant_access.py` is the one place these rules are written down.

## While the trial runs

- Full access to the firm's plan modules.
- **No premium AI**, whatever a user's `premium_ai_enabled` flag says (see
  below).
- `/api/auth/me` reports `access_state: "trial"` and `trial_ends_at`.

## When the trial ends unpaid: billing only

The firm is a hard stop except for paying. An active, non-synthetic firm whose
only problem is an elapsed `expires_at` can still:

- sign in (password, Google, Microsoft), refresh its session, and complete the
  OAuth callback exchange;
- call `GET /api/auth/me`, which reports `access_state: "trial_expired"`;
- call `GET /api/billing/status` and every `/api/billing/subscription/*` route,
  subject to the usual finance and billing permissions.

Every other route still returns `403 "Tenant access has expired"`.

**This loosens access deliberately and only this far.** Before this change the
only page that could end the lockout was itself locked, so an expired firm
could not pay. An **inactive** firm, a **missing** firm, and an **expired demo
workspace** are refused exactly as before, at sign-in and everywhere else. A
refresh for an inactive firm still revokes the whole session chain.

The allowance is an explicit path list (`EXPIRED_TRIAL_ALLOWED_PATHS` and
`EXPIRED_TRIAL_ALLOWED_PREFIXES`); anything added there must be account or
billing surface only.

## Paying ends the trial

When Helcim reports a subscription that is **live, billed at least once, and
has no failed payments**, `platform_billing.end_trial_when_paid`:

- clears `Tenant.expires_at`;
- sets the `trial` marker to false, removes `trial_started_at` and
  `trial_ends_at`, and records `trial_converted_at`;
- leaves the firm's plan unchanged.

It runs after every subscription sync: checkout completion, manual refresh,
the signed provider webhook, and the scheduled reconcile. A pending, failed,
or cancelled subscription leaves the trial exactly as it was. A paid firm that
was never on a trial is untouched.

Before this change the sync set the tier and seats but never touched the
trial, so a firm that paid on day ten was still locked out on day thirty and
still refused premium AI.

### The Helcim plan must not have its own trial

LawHand runs the trial from signup. The configured Helcim payment plan
(`HELCIM_PAYMENT_PLAN_ID`) must have `freeTrialPeriod = 0`:

- the subscription offer returns `503` for a plan with a Helcim free trial;
- checkout always sends `withFreeTrialPeriod: false`.

Otherwise subscribing on day 29 would start a second free period, and the
first charge would land around day 59.

## Premium AI

Premium AI now needs **both** the user's `premium_ai_enabled` flag **and** a
firm that is not on a trial and is not a demo or fixture workspace
(`tenant_access.user_may_use_premium_ai`). This is enforced where premium AI
actually runs, not only at the settings toggle:

| Site | Behaviour when not allowed |
|---|---|
| Chat (`_premium_for_user`) | Falls back to the standard route |
| Plugin runs (both entry points) | Runs on the standard route |
| Template AI field proposal | `403` |
| Matter document revisions (`model_tier: "premium"`) | `403 premium_model_not_enabled` |
| Email agent scan drafts and `/api/email/draft-response` | Drafts on the standard model |

**Tightening:** the email agent previously drafted with the premium model for
every user, including users whose premium flag was off and trial firms. It now
follows the same rule as chat.

`/api/auth/me` reports `premium_ai_available`, which is false on trials and
demo workspaces regardless of the per-user flag.

## Operator notes

- **Extending a trial** moves `expires_at` and keeps the firm on trial, so
  premium AI stays off.
- **Clearing `trial_ends_at`** (setting it to null) ends the trial without
  payment. Premium AI becomes available to users whose flag is on.
- **An expired firm that pays** regains full access on the next subscription
  sync. `POST /api/billing/subscription/refresh` forces one.
- **An expired firm is routed to billing** and a firm on trial sees a
  countdown; see "What the firm sees" below.

## What the firm sees

- `AppShell` renders `TrialBanner` for any firm whose `/api/auth/me` reports
  `access_state: "trial"`. It counts whole days from `trial_ends_at` and
  escalates from neutral to amber at 7 days and red at 2. A user without
  finance access is told to ask a firm administrator rather than shown a
  billing link they cannot use. Demo workspaces never see it: they report
  `access_state: "active"` and carry their own banner.
- Once `access_state` is `trial_expired`, every protected route redirects to
  `/billing?reason=trial_expired`, which explains the hard stop. This mirrors
  the allowlist above. Without it each page fails with its own `403` and the
  firm never reaches the one screen that can end the lockout.
- **Self-serve signup provisions the `full-trial` plan.** Signup previously
  fell through to `register()`, which creates a tenant with no `expires_at`,
  so turning on `PUBLIC_SIGNUP_ENABLED` as it stood would have handed out
  unlimited free accounts with no trial window at all. `full-trial` carries
  every module on the `trial` billing tier (1,000 requests/day) with premium
  AI off, and upsells to `full-platform`.
