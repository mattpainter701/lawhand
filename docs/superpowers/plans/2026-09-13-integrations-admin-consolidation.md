# Integrations Admin Consolidation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the integrations admin surface honest about credential health, set cloud storage up visibly during onboarding rather than silently at the end, and collapse the firm-admin view to status-first with operator tooling nested behind a disclosure.

**Origin:** Compiled 2026-09-13 at `7ba830f` from a code audit prompted by a live symptom: a Google card simultaneously showing "Reconnect Required", a 62-day-old `invalid_grant`, "Granted 8 / Missing 0", and a cloud-sync that had just completed 700 ok. Every finding below is cited to file and line.

**Architecture:** Three workstreams, deliberately ordered. A is correctness plus the missing safety net and is independently shippable today. B closes a customer-visible onboarding gap and does not touch A's files. C is the information-architecture change and should land last, because it moves the very components A adds tests for.

**Tech Stack:** FastAPI, SQLAlchemy (async), React (Vite), Vitest, pytest.

**Related:** `docs/superpowers/plans/2026-09-07-cloud-provider-portability-remediation.md` (Workstream C — storage migration — is **already implemented**; this plan places its UI, it does not rebuild it), `docs/PROVIDER_APP_OWNERSHIP_MIGRATION.md`, `docs/integrations-setup.md`.

**Not in scope:** Rewriting `IntegrationsPanel.jsx` or `ZoomPanel.jsx`. Decomposing those is a later plan that A's characterization tests exist to enable.

---

## Findings summary

| # | Finding | Severity | Workstream |
| --- | --- | --- | --- |
| 1 | Re-authorization never clears `health`, `last_refresh_error`, or `last_refresh_at`, so a successful re-auth still renders as a failure | **Live UX bug; drives re-auth loops** | A |
| 2 | `apply_scope_audit` refuses to lift `health == "revoked"`, which is right on refresh and wrong on fresh consent | Root cause of 1 | A |
| 3 | `IntegrationsPanel.jsx` — 897 lines owning both Google and Microsoft OAuth — has **no tests** | Blocks safe change | A |
| 4 | A revoked credential still renders "Required 8 / Granted 8 / Missing 0" from its stored scope string | Actively misleading | A |
| 5 | One card conflates the tenant-wide credential with per-user tokens, which fail independently | Operator cannot tell what is broken | A |
| 6 | Onboarding never asks where documents go; `initialize_cloud_root_folder` runs silently inside `/complete` | Customer-visible gap | B |
| 7 | Storage migration tooling is fully built but surfaced inside the firm-admin cloud panel | Wrong audience | C |
| 8 | Firm-admin and operator surfaces are interleaved in one hub; a managing partner can reach client-secret fields | Embarrassment; support load | C |
| 9 | All eight hub sections render expanded regardless of whether the provider is configured | Noise | C |

---

## Requirements this plan serves

- An administrator who has just re-authorized sees that it worked.
- A card never claims scopes are granted on a credential that cannot be used.
- Tenant-wide and per-user credentials are distinguishable, because they fail independently.
- A new firm chooses and confirms where its documents will live, during onboarding, before any matter exists.
- A firm admin sees status; an operator reaches migration and app-credential tooling deliberately, not by scrolling.

---

## Workstream A — Credential health correctness and safety net

Independently shippable. Do this first; it is also the safety net for C.

### Task A1: A successful re-authorization must clear stale failure state

**Problem:** Every credential upsert path sets `is_active = True` and stops there. `backend/app/routers/integrations.py:727` (Google admin) and `:529` (Microsoft admin) never touch `health`, `last_refresh_error`, or `last_refresh_at`. `apply_scope_audit` is then called (`:745`, `:548`) but `backend/app/services/integration_observability.py:45` guards with `if getattr(row, "health", None) != "revoked"`, so `revoked` survives.

The result is the observed screen: `is_active` true gives `connected` true and a full granted count, while `health` stays `revoked` and renders "Reconnect Required" (`frontend/src/components/IntegrationsPanel.jsx:738`) beside a 62-day-old error string (`:781-783`). It self-heals only on the next successful refresh, which does clear the fields (`backend/app/services/token_vault.py:65-72`). Until then the admin believes the re-auth failed and does it again.

The guard is correct for a refresh cycle — a revoked grant must not be papered over because scopes happen to look complete — so the fix belongs at the callback, not by weakening the guard.

**Files:**
- Modify: `backend/app/routers/integrations.py`
- Modify: `backend/app/services/integration_observability.py`
- Test: `backend/tests/test_integration_reauthorization_clears_health.py` (new)

- [ ] **Step 1: Write the failing tests** — for each of the four upsert paths (Google admin, Google user, Microsoft admin, Microsoft user): seed a credential with `health="revoked"`, `is_active=False`, a stale `last_refresh_error` and an old `last_refresh_at`; run the callback with a valid full-scope grant; assert `health` is `healthy`, `last_refresh_error` is `None`, and `last_refresh_at` has advanced.
- [ ] **Step 2:** Add an explicit helper — `clear_refresh_failure(row)` in `integration_observability.py` — that resets `health`, `last_refresh_error` and `last_refresh_at`. Do not widen `apply_scope_audit`; its `revoked` guard protects the refresh path and must stay.
- [ ] **Step 3:** Call the helper from all four callback upsert paths, before `apply_scope_audit`, so a genuine missing-scope result still wins.
- [ ] **Step 4:** Assert the negative case — a refresh that returns `invalid_grant` still sets `revoked` and `is_active=False` (`token_vault.py:83-87`). The guard must not regress.

### Task A2: Health outranks scopes in the card

**Problem:** `IntegrationsPanel.jsx:746` computes `grantedRequiredCount` from `info.connected` alone, so an unusable credential advertises a full green scope list (finding 4). Scope counts describe what was *once* consented; they say nothing about whether the credential works now.

**Files:**
- Modify: `frontend/src/components/IntegrationsPanel.jsx`
- Test: `frontend/src/components/IntegrationsPanel.test.jsx` (new — see A3)

- [ ] **Step 1: Write the failing test** — a provider with `health: "revoked"` must not render a green granted count, and must lead with the remedy.
- [ ] **Step 2:** When `health` is `revoked` or `refresh_failed`, suppress the Required/Granted/Missing block and the per-scope list; show the failure and the re-authorize action instead. Keep the detail reachable behind a disclosure for support.
- [ ] **Step 3:** Render `last_refresh_at` as an explicit "last successful refresh", since a failed attempt also stamps it (`token_vault.py:79-80`). "Token refresh 62d ago" beside a live error reads as a working connection.

### Task A3: Characterization tests before anything moves

**Problem:** `IntegrationsPanel.jsx` is 897 lines and has no test file, while `ZoomPanel.jsx` (809) has 255 lines of tests and `TeamsPanel.jsx` (283) has 321. The largest and most load-bearing panel — it owns the Google and Microsoft connect and disconnect flows during an active credential migration — is the one with no coverage.

**Files:**
- Create: `frontend/src/components/IntegrationsPanel.test.jsx`

- [ ] **Step 1:** Cover the states the panel can be in, from `/api/integrations/status`: disconnected, healthy, `missing_scopes`, `refresh_failed`, `revoked`, and connected-with-additional-scopes.
- [ ] **Step 2:** Cover the actions: connect at `intent=admin` and `intent=user`, re-authorize, disconnect, sync now — asserting the request each fires, since `IntegrationsPanel.jsx:324` navigates by `window.location.href`.
- [ ] **Step 3:** Cover tier gating: a provider reporting directory sync unavailable must render that as a tier statement, never as a failure.
- [ ] **Step 4:** These are characterization tests. Record behavior as it is, including behavior you consider wrong; A1 and A2 change it deliberately and update the expectations in the same commit.

### Task A4: Separate tenant-wide from per-user credentials in the UI

**Problem:** The card merges the tenant credential (`tenant_credentials`) with per-user tokens (`user_oauth_tokens`). They refresh independently through different code paths — `token_vault._locked_tenant_credential` versus `_locked_user_token` — and the observed incident had the tenant credential revoked for 62 days while per-user sync ran 700 items clean. One status line cannot be true for both.

**Files:**
- Modify: `frontend/src/components/IntegrationsPanel.jsx`
- Modify: `backend/app/routers/integrations.py` (status response)
- Test: `backend/tests/test_integration_status_credential_split.py` (new)

- [ ] **Step 1: Write the failing test** — `/api/integrations/status` reports tenant-credential health and per-user token health as distinct fields.
- [ ] **Step 2:** Extend `IntegrationStatus` with a per-user summary: count connected, count needing re-auth. `integration_status` already loads `UserOAuthToken` rows for the tenant (`integrations.py:1727-1731`) and currently only counts them.
- [ ] **Step 3:** Render them as two rows with distinct remedies — the admin grant is re-authorized by an admin, a user token by that user.

---

## Workstream B — Onboarding sets storage up visibly

Independent of A and C. Highest customer-visible value.

### Task B1: An explicit storage step in the wizard

**Problem:** `frontend/src/pages/OnboardingWizard.jsx:15-20` defines `Welcome → Connect → Sync Users → Review → Complete`. There is no storage step; the only mention of folders is marketing copy on the welcome screen (`:244`). Storage is created implicitly at the end — `backend/app/routers/onboarding.py:238-241` calls `initialize_cloud_root_folder` inside `/complete`. A firm never chooses a provider, never sees the destination, and never confirms it.

**Files:**
- Modify: `frontend/src/pages/OnboardingWizard.jsx`
- Modify: `backend/app/routers/onboarding.py`
- Test: `frontend/src/pages/OnboardingWizard.test.jsx`
- Test: `backend/tests/test_onboarding_storage_step.py` (new)

- [ ] **Step 1: Write the failing tests** — completing onboarding without an explicit storage confirmation is rejected; confirming records the chosen provider and the created root.
- [ ] **Step 2:** Insert a Storage step between Connect and Sync Users: choose the provider when both are connected, show the root folder that will be created, and require confirmation.
- [ ] **Step 3:** Move `initialize_cloud_root_folder` out of `/complete` and behind that confirmation, so the folder exists before the admin leaves the wizard and its identity is shown, not assumed.
- [ ] **Step 4:** Preserve the existing re-run guard. Finding 11 of the portability plan notes `/complete` overwrites `cloud_root_folder`; a second pass must not silently repoint a tenant with matters.
- [ ] **Step 5:** Keep the step honest on personal tiers — when directory sync is unavailable the step says so rather than reporting a failure.

### Task B2: Prove the workflow on a genuinely new tenant

**Problem:** The wizard cannot be exercised on an existing tenant, so this path is effectively untested. It is also the end-to-end proof of the new Google OAuth client from `docs/PROVIDER_APP_OWNERSHIP_MIGRATION.md`: one fresh tenant exercises login callback, admin consent, directory sync, storage root creation, and first matter folder in a single pass.

**Files:**
- Modify: `docs/integrations-setup.md`

- [ ] **Step 1:** Create a fresh tenant on dev1 and run the wizard start to finish against the dev OAuth client.
- [ ] **Step 2:** Verify `/api/integrations/status` reports no missing scopes, the storage root exists in the connected account, and the first matter folder lands inside it.
- [ ] **Step 3:** Return after one hour and perform one Drive or Gmail operation, proving `token_vault` refreshes against the new client. This is the check that de-risks the production credential cutover.
- [ ] **Step 4:** Record the result as the provider production-proof required by `docs/integrations-setup.md`.

---

## Workstream C — Consolidate the hub, nest the operator tools

Land last: it moves the components A covers with tests.

### Task C1: Status-first, collapsed by default

**Problem:** `frontend/src/components/IntegrationsHub.jsx:25` defines eight sections, all rendering expanded regardless of configuration. Reaching a single control means AdminPage (12 tabs) → Integrations → hub section → panel, three levels deep, across roughly 3,100 lines of integration UI.

**Files:**
- Modify: `frontend/src/components/IntegrationsHub.jsx`
- Test: `frontend/src/components/IntegrationsHub.test.jsx`

- [ ] **Step 1: Write the failing test** — an unconfigured provider renders collapsed with a one-line status and a set-up action; a configured one renders its status summary and expands on demand.
- [ ] **Step 2:** Give each section a status summary sourced from `/api/integrations/status`, so the hub answers "is this working?" without expanding anything.
- [ ] **Step 3:** Collapse by default; expand on demand. Never auto-expand a section whose provider is unconfigured.

### Task C2: Split by audience

**Problem:** Firm-admin actions sit beside operator actions. A managing partner can reach tenant-owned app credential fields — `ZoomPanel.jsx:607` renders a `client_id` input — and MCP server grants. `INTEGRATION_SECTIONS` already carries an `audience` field (`IntegrationsHub.jsx:28`), currently `'admin'` throughout, so the hook exists and is unused.

**Files:**
- Modify: `frontend/src/components/IntegrationsHub.jsx`
- Test: `frontend/src/components/IntegrationsHub.test.jsx`

- [ ] **Step 1: Write the failing test** — a firm admin does not see operator sections; an operator reaches them behind an explicit disclosure.
- [ ] **Step 2:** Classify every section as `firm` or `operator`. Connect-an-account is `firm`; app credentials, MCP servers and storage migration are `operator`.
- [ ] **Step 3:** Render operator sections under one nested "Advanced" disclosure, closed by default, not as peers of "Connect Google".
- [ ] **Step 4:** Gate on role rather than on collapse alone. A disclosure is presentation, not authorization.

### Task C3: Place the migration tooling that already exists

**Problem:** `backend/app/services/storage_migration.py` (27.5 KB), `backend/app/routers/storage_migration.py` and six test files are implemented — the portability plan is 46 of 48 tasks complete. `StorageMigrationPanel.jsx` is imported into `IntegrationsPanel.jsx:19`, which puts a destructive, rarely-used operator flow inside the panel a firm admin uses to connect Gmail. Nothing here needs building; it needs moving.

**Files:**
- Modify: `frontend/src/components/IntegrationsPanel.jsx`
- Modify: `frontend/src/components/IntegrationsHub.jsx`

- [ ] **Step 1:** Remove `StorageMigrationPanel` from `IntegrationsPanel` and mount it as an `operator` section under Advanced.
- [ ] **Step 2:** Add the re-run-onboarding entry point beside it — portability finding 11 records that migration has no entry point today.
- [ ] **Step 3:** Confirm no behavior changed. This task moves a mount point; it must not touch `storage_migration.py`.

---

## Sequencing

1. **A3** first — the safety net, before anything moves.
2. **A1, A2, A4** — correctness; ship as its own PR. A1 is a live bug and should not wait on the redesign.
3. **B** — independent; unblocks the first-customer onboarding path and proves the new OAuth client.
4. **C** — last, on top of A3's tests.

Each workstream is its own PR. Do not open a single PR spanning all three: it would touch roughly 3,100 lines of UI plus four backend callback paths and would be unreviewable. A long-lived branch is also the wrong shape here — `main` moved ten commits during the session that produced this plan.
