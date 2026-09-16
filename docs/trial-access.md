# Trial access, paying, and premium AI

How a firm on a free trial is treated while the trial runs, after it ends, and
once it pays through Helcim. Public signup is **off by default**
(`PUBLIC_SIGNUP_ENABLED=false`); a deployment turns it on deliberately and may
turn it back off as an incident-response kill switch. Production preflight
requires both flags to be set explicitly and to match, but accepts either value
so the switch stays reversible.

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
- **No premium AI by default.** A platform operator can deliberately sponsor
  it for a trial firm; both the firm grant and the user's flag must then be on.
- `/api/auth/me` reports `access_state: "trial"` and `trial_ends_at`.

## Registration is a request, never a session

- The only path that creates a firm is `POST /api/auth/signup/plan`. It records
  an inactive tenant and inactive founder with a `signup_status: pending`
  marker, then emails the operator. No trial clock, session, Stripe customer,
  module access, or AI spend exists until Platform approval.
- `POST /api/auth/register` is **closed** (`410`); it no longer provisions a
  tenant or mints a session.
- **Google and Microsoft OAuth are sign-in only.** Completing a provider flow
  for a domain with no workspace is refused (`not_invited`) instead of
  provisioning a tenant, so OAuth cannot bypass approval.
- `POST /api/auth/signup/plan` is rate-limited by source IP (5 per hour),
  matching the marketing lead form, because it writes a pending tenant and
  emails the operator from an unauthenticated request.

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

Premium AI needs the user's `premium_ai_enabled` flag and a non-synthetic firm.
A paid firm passes the tenant gate normally. A trial firm passes it only when a
platform operator has set `Tenant.premium_ai_trial_enabled`; the flag defaults
false and Platform applies it to every licensed human user. This is enforced
where premium AI actually runs, not only at the settings toggle:

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

`/api/auth/me` reports `premium_ai_available`, which is false on ordinary
trials and demo workspaces. It becomes true for an explicitly sponsored trial.

## Operator notes

- **A public registration is pending, not provisioned.** It creates an inactive
  tenant and inactive founder with no `expires_at`, session, Stripe customer,
  module access, or AI spend. Platform's Approve trial action atomically
  activates both, starts the selected trial window, applies the optional
  Premium AI sponsorship, and emails the founder. A generic tenant update is
  refused for pending registrations so it cannot bypass that boundary.
- **Register a customer privately** creates an active trial plus a single-use
  founding-admin invitation. Platform reports delivery and returns the backup
  acceptance URL once, so tomorrow's customer does not depend on opening the
  public registration flag.
- **Extending a trial** moves `expires_at`, keeps the firm on trial, and sends
  a branded email to its active administrators. An email failure is reported
  in Platform but does not roll back the access extension.
- **Revoking a trial** sets the expiry to the past, immediately leaving only
  sign-in and billing available. Deactivating the tenant is a stronger,
  separate control.
- **Sponsored Premium AI** is an explicit Platform toggle. It is separate from
  the trial date, updates licensed users, and remains off for every new trial.
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
- **Self-serve signup requests the `full-trial` plan.** It does not provision
  access or start the 30-day clock. The registration confirmation explicitly
  says it is awaiting approval; the founder cannot sign in until Platform
  approves the firm. This keeps an optional public form from becoming an
  anonymous inference-spend switch.
- **Platform shows and controls the access date.** An operator can set an exact
  UTC date, extend from the later of now or the current expiry by 30 days or six
  calendar months, revoke immediately, or clear the trial into active access.
