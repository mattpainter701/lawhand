# Integrations Admin Consolidation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the integrations admin surface honest about credential health, set cloud storage up visibly during onboarding rather than silently at the end, and collapse the firm-admin view to status-first with operator tooling nested behind a disclosure.

**Origin:** Compiled 2026-09-13 at `7ba830f` from a code audit prompted by a live symptom: a Google card simultaneously showing "Reconnect Required", a 62-day-old `invalid_grant`, "Granted 8 / Missing 0", and a cloud-sync that had just completed 700 ok. Every finding below is cited to file and line.

**Status (2026-09-13, branch `claude/optimistic-wozniak-omr3qu`):** Workstreams A, B and C are implemented and tested on this branch, plus Workstream D (portal-wide consolidation and admin guide) which the original plan did not cover. Task B2 (prove the wizard on a genuinely new dev1 tenant) is the only open item; it needs a live environment. Deviations from the original plan are marked **Deviation** inline.

**Architecture:** Three workstreams, deliberately ordered. A is correctness plus the missing safety net and is independently shippable today. B closes a customer-visible onboarding gap and does not touch A's files. C is the information-architecture change and should land last, because it moves the very components A adds tests for.

**Tech Stack:** FastAPI, SQLAlchemy (async), React (Vite), Vitest, pytest.

**Related:** `docs/superpowers/plans/2026-09-07-cloud-provider-portability-remediation.md` (Workstream C — storage migration — is **already implemented**; this plan places its UI, it does not rebuild it), `docs/PROVIDER_APP_OWNERSHIP_MIGRATION.md`, `docs/integrations-setup.md`.

**Not in scope:** Rewriting `ZoomPanel.jsx`. Decomposing it is a later plan. `IntegrationsPanel.jsx` was restructured (not rewritten) under C; its logic is unchanged and now covered by `IntegrationsPanel.test.jsx`.

---

## Findings summary

| # | Finding | Severity | Workstream | Status |
| --- | --- | --- | --- | --- |
| 1 | Re-authorization never clears `health`, `last_refresh_error`, or `last_refresh_at`, so a successful re-auth still renders as a failure | **Live UX bug; drives re-auth loops** | A | Fixed |
| 2 | `apply_scope_audit` refuses to lift `health == "revoked"`, which is right on refresh and wrong on fresh consent | Root cause of 1 | A | Fixed at the callback; guard kept |
| 3 | `IntegrationsPanel.jsx` — 897 lines owning both Google and Microsoft OAuth — has **no tests** | Blocks safe change | A | 18 tests added |
| 4 | A revoked credential still renders "Required 8 / Granted 8 / Missing 0" from its stored scope string | Actively misleading | A | Fixed |
| 5 | One card conflates the tenant-wide credential with per-user tokens, which fail independently | Operator cannot tell what is broken | A | Fixed |
| 6 | Onboarding never asks where documents go; `initialize_cloud_root_folder` runs silently inside `/complete` | Customer-visible gap | B | Fixed |
| 7 | Storage migration tooling is fully built but surfaced inside the firm-admin cloud panel | Wrong audience | C | Moved |
| 8 | Firm-admin and operator surfaces are interleaved in one hub; a managing partner can reach client-secret fields | Embarrassment; support load | C | Gated (Zoom app credentials remain inside `ZoomPanel`, see D4) |
| 9 | All eight hub sections render expanded regardless of whether the provider is configured | Noise | C | Fixed |
| 10 | Changing the primary cloud provider saved on `<select>` change with no confirmation, repointing every new document write | Dangerous control one mis-click away | C | Fixed (inline confirm) |
| 11 | After re-authorizing from the cloud card, `_post_connect_redirect` landed the admin on Cloud Search, not the card whose health they were fixing | Confusing; hides the outcome of finding 1 | B | Fixed |
| 12 | The panel consumed `/api/admin/permissions` (`admin.py:1619`), not `/api/integrations/status` as the plan assumed; the per-user split had to land on the endpoint the card actually reads | Plan accuracy | A | Both endpoints extended |
| 13 | `AdminPage` presented 12 flat tabs; the LiteLLM alias override and the Prompts editor (system-prompt overrides for every user) sat beside everyday settings | Operator controls exposed to firm admins | D | Grouped; gated |
| 14 | The Admin Guide had no chapter on onboarding, storage confirmation, or what each credential health state means | Support cannot point at a reference | D | Added |

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

- [x] **Step 1: Write the failing tests** — for each of the four upsert paths (Google admin, Google user, Microsoft admin, Microsoft user): seed a credential with `health="revoked"`, `is_active=False`, a stale `last_refresh_error` and an old `last_refresh_at`; run the callback with a valid full-scope grant; assert `health` is `healthy`, `last_refresh_error` is `None`, and `last_refresh_at` has advanced. **Deviation:** the four paths now share one helper, `_record_fresh_grant`, so the tests exercise that helper with each path's scope set (database-free) rather than driving the HTTP callbacks.
- [x] **Step 2:** Add an explicit helper — `clear_refresh_failure(row)` in `integration_observability.py` — that resets `health`, `last_refresh_error` and `last_refresh_at`. Do not widen `apply_scope_audit`; its `revoked` guard protects the refresh path and must stay.
- [x] **Step 3:** Call the helper from all four callback upsert paths, before `apply_scope_audit`, so a genuine missing-scope result still wins.
- [x] **Step 4:** Assert the negative case — a refresh that returns `invalid_grant` still sets `revoked` and `is_active=False` (`token_vault.py:83-87`). The guard must not regress.

### Task A2: Health outranks scopes in the card

**Problem:** `IntegrationsPanel.jsx:746` computes `grantedRequiredCount` from `info.connected` alone, so an unusable credential advertises a full green scope list (finding 4). Scope counts describe what was *once* consented; they say nothing about whether the credential works now.

**Files:**
- Modify: `frontend/src/components/IntegrationsPanel.jsx`
- Test: `frontend/src/components/IntegrationsPanel.test.jsx` (new — see A3)

- [x] **Step 1: Write the failing test** — a provider with `health: "revoked"` must not render a green granted count, and must lead with the remedy.
- [x] **Step 2:** When `health` is `revoked` or `refresh_failed`, suppress the Required/Granted/Missing block and the per-scope list; show the failure and the re-authorize action instead. Keep the detail reachable behind a disclosure for support.
- [x] **Step 3:** Render `last_refresh_at` honestly. **Deviation:** because a failed attempt also stamps it (`token_vault.py:79-80`), it cannot be labelled "last successful refresh" unconditionally. It reads "Last token refresh attempt … failed" when `last_refresh_error` is present and "Last successful token refresh …" otherwise.

### Task A3: Characterization tests before anything moves

**Problem:** `IntegrationsPanel.jsx` is 897 lines and has no test file, while `ZoomPanel.jsx` (809) has 255 lines of tests and `TeamsPanel.jsx` (283) has 321. The largest and most load-bearing panel — it owns the Google and Microsoft connect and disconnect flows during an active credential migration — is the one with no coverage.

**Files:**
- Create: `frontend/src/components/IntegrationsPanel.test.jsx`

- [x] **Step 1:** Cover the states the panel can be in, from `/api/admin/permissions`: disconnected, healthy, `missing_scopes`, `refresh_failed`, `revoked`, and connected-with-additional-scopes.
- [x] **Step 2:** Cover the actions: connect at `intent=admin`, re-authorize, disconnect, sync now — asserting the request each fires, since `IntegrationsPanel.jsx:324` navigates by `window.location.href`. **Note:** `intent=user` connect is not offered by this panel (users connect from their profile); disconnect is not offered by this panel either. Both are recorded as facts, not gaps.
- [x] **Step 3:** Cover tier gating: a provider reporting directory sync unavailable must render that as a tier statement, never as a failure.
- [x] **Step 4:** These are characterization tests. Record behavior as it is, including behavior you consider wrong; A1 and A2 change it deliberately and update the expectations in the same commit.

### Task A4: Separate tenant-wide from per-user credentials in the UI

**Problem:** The card merges the tenant credential (`tenant_credentials`) with per-user tokens (`user_oauth_tokens`). They refresh independently through different code paths — `token_vault._locked_tenant_credential` versus `_locked_user_token` — and the observed incident had the tenant credential revoked for 62 days while per-user sync ran 700 items clean. One status line cannot be true for both.

**Files:**
- Modify: `frontend/src/components/IntegrationsPanel.jsx`
- Modify: `backend/app/routers/integrations.py` (status response) and `backend/app/routers/admin.py` (`/permissions`, which the card reads — finding 12)
- Test: `backend/tests/test_integration_reauthorization_clears_health.py` (per-user summary)

- [x] **Step 1: Write the failing test** — per-user token health is summarized as distinct fields (`summarize_user_tokens`).
- [x] **Step 2:** Extend both `IntegrationStatus` and the `/admin/permissions` payload with `user_tokens: {total, healthy, needs_reauth}`.
- [x] **Step 3:** Render them as two rows with distinct remedies — the admin grant is re-authorized by an admin, a user token by that user.

---

## Workstream B — Onboarding sets storage up visibly

Independent of A and C. Highest customer-visible value.

### Task B1: An explicit storage step in the wizard

**Problem:** `frontend/src/pages/OnboardingWizard.jsx:15-20` defines `Welcome → Connect → Sync Users → Review → Complete`. There is no storage step; the only mention of folders is marketing copy on the welcome screen (`:244`). Storage is created implicitly at the end — `backend/app/routers/onboarding.py:238-241` calls `initialize_cloud_root_folder` inside `/complete`. A firm never chooses a provider, never sees the destination, and never confirms it.

**Files:**
- Modify: `frontend/src/pages/OnboardingWizard.jsx`, `frontend/src/api.js`
- Modify: `backend/app/routers/onboarding.py`, `backend/app/schemas/onboarding.py`, `backend/app/routers/integrations.py`, `backend/app/routers/user_sync.py`, `backend/app/routers/demo.py`
- Test: `frontend/src/pages/OnboardingWizard.test.jsx`
- Test: `backend/tests/test_onboarding_storage_step.py` (new)

- [x] **Step 1: Write the failing tests** — completing onboarding without a storage root is rejected (400); confirming records the chosen provider and the created root.
- [x] **Step 2:** Insert a Storage step between Connect and Sync Users: choose the provider from those connected, show the root folder that was created (name and link), and require confirmation. Steps are now `0 Welcome, 1 Connect, 2 Storage, 3 Sync, 4 Review, 5 Complete`; the post-connect hooks advance `1→2` and `3→4` only, so directory sync finishing can never skip Storage.
- [x] **Step 3:** Move `initialize_cloud_root_folder` out of `/complete` and behind `POST /api/admin/onboarding/storage`, so the folder exists before the admin leaves the wizard and its identity is shown, not assumed. The endpoint also records `primary_cloud_provider` through `assert_provider_change_allowed`.
- [x] **Step 4:** Preserve the existing re-run guard. An existing root binding is kept and shown as "Folder exists"; a malformed binding returns `repair_needed` and is never rebound; `/complete` audits `onboarding_rerun` versus `onboarding_complete`.
- [x] **Step 5:** Keep the step honest on personal tiers — SharePoint is deferred to Admin with a hint rather than failing; the Sync Users step says personal accounts have no directory to import.
- [x] **Step 6 (added):** Legacy tenants that finished at old step `4` are normalized to the new Complete step on the client (`normalizeStep`) so a revisit shows the completed screen.

### Task B2: Prove the workflow on a genuinely new tenant

**Problem:** The wizard cannot be exercised on an existing tenant, so this path is effectively untested. It is also the end-to-end proof of the new Google OAuth client from `docs/PROVIDER_APP_OWNERSHIP_MIGRATION.md`: one fresh tenant exercises login callback, admin consent, directory sync, storage root creation, and first matter folder in a single pass.

**Files:**
- Modify: `docs/integrations-setup.md`

- [ ] **Step 1:** Create a fresh tenant on dev1 and run the wizard start to finish against the dev OAuth client. **Open — needs a live environment.** Watch for: the Storage step listing only connected providers, "Folder created" with a working link, and Complete refusing until then.
- [ ] **Step 2:** Verify `/api/integrations/status` reports no missing scopes, the storage root exists in the connected account, and the first matter folder lands inside it.
- [ ] **Step 3:** Return after one hour and perform one Drive or Gmail operation, proving `token_vault` refreshes against the new client. This is the check that de-risks the production credential cutover.
- [ ] **Step 4:** Record the result as the provider production-proof required by `docs/integrations-setup.md`.

---

## Workstream C — Consolidate the hub, nest the operator tools

Land last: it moves the components A covers with tests.

### Task C1: Status-first, collapsed by default

**Problem:** `frontend/src/components/IntegrationsHub.jsx:25` defines eight sections, all rendering expanded regardless of configuration. Reaching a single control means AdminPage (12 tabs) → Integrations → hub section → panel, three levels deep, across roughly 3,100 lines of integration UI.

**Files:**
- Modify: `frontend/src/components/IntegrationsHub.jsx`, `frontend/src/components/IntegrationsPanel.jsx`, `frontend/src/components/ui.jsx` (`Disclosure`)
- Test: `frontend/src/components/IntegrationsHub.test.jsx`

- [x] **Step 1: Write the failing test** — an unconfigured provider renders with a "Set up" action and an off-tone status; a configured one renders its status summary.
- [x] **Step 2:** Give each section a status summary sourced from `/api/admin/permissions` (cloud, search, Teams), `/api/integrations/zoom/status` and `/api/integrations/qbo/status`, so the hub answers "is this working?" without expanding anything. Sections without a cheap status source (email intake, file shares, MCP) show none rather than a guess.
- [x] **Step 3:** Collapse by default; expand on demand. The cloud panel's storage controls sit in a closed "Document storage" disclosure beneath the provider cards, and operator sections sit in a closed "Advanced" disclosure.

### Task C2: Split by audience

**Problem:** Firm-admin actions sit beside operator actions. A managing partner can reach tenant-owned app credential fields — `ZoomPanel.jsx:607` renders a `client_id` input — and MCP server grants. `INTEGRATION_SECTIONS` already carries an `audience` field (`IntegrationsHub.jsx:28`), currently `'admin'` throughout, so the hook exists and is unused.

- [x] **Step 1: Write the failing test** — a firm admin without the capability does not see operator sections; an operator reaches them behind an explicit disclosure.
- [x] **Step 2:** Classify every section as `firm` or `operator`. Connect-an-account is `firm`; MCP servers, storage migration, data import and provider readiness are `operator`.
- [x] **Step 3:** Render operator sections under one nested "Advanced" disclosure, closed by default, not as peers of "Connect Google".
- [x] **Step 4:** Gate on role rather than on collapse alone. `canOperateIntegrations(user)` requires `role === 'admin'`, not intake-only, and — when the session carries capabilities — `manage_integrations`. **Note:** the seeded Administrator system role holds every capability, so today every tenant admin passes; a firm creates a custom role without `manage_integrations` to withhold these tools. Backend routes for migration and app credentials remain admin-gated as before; a capability check server-side is a follow-up (see D5).

### Task C3: Place the migration tooling that already exists

- [x] **Step 1:** Remove `StorageMigrationPanel` from `IntegrationsPanel` and mount it as an `operator` section under Advanced (`StorageMigrationSection` loads its own permissions, settings and SharePoint binding).
- [x] **Step 2:** Add the re-run-onboarding entry point beside it — the section banner points at the Onboarding wizard's Restart, and the wizard preserves the root on re-entry.
- [x] **Step 3:** Confirm no behavior changed. `storage_migration.py` and `StorageMigrationPanel.jsx` are untouched.

---

## Workstream D — Portal-wide consolidation and reference docs (added 2026-09-13)

Requested during execution: onboarding should feel modern, settings must be consolidated but still serve an admin or support person, and there should be deep admin guide docs to reference — eventually over MCP.

### Task D1: Group the Administration tabs

- [x] `ADMIN_TAB_GROUPS` in `frontend/src/pages/AdminPage.jsx`: People (Users, Roles), Firm (Integrations, Firm Profile, Settings), Billing (Subscription, Licensing, Usage), Support (Admin Guide, Support, Tenant, Prompts). Tab ids are unchanged, so every `?tab=` deep link still works; the collapsed selector uses `<optgroup>`s.
- [x] Prompts is flagged `advanced` and gated by `canUseAdvancedSettings(user)` (`admin_settings` capability when capabilities are present).

### Task D2: Settings tab — everyday first, operator controls behind Advanced

- [x] Order: Case law, Alerts & budgets, Feature flags, then an Advanced disclosure holding the LiteLLM gateway alias override, then Release info.

### Task D3: Onboarding polish

- [x] Progress header ("Step n of 6 · name", percentage, progress bar), animated step transitions, one primary action per step, honest copy on the Sync step for personal tiers.

### Task D4: Admin Guide

- [x] New chapter `21-onboarding-and-storage-setup.md` (steps, why storage is a step, "Folder exists", failures, re-run, skip, endpoints).
- [x] `04-integrations.md`: hub organization and audiences, a health-state table with remedies, firm-wide versus per-user connections, the Document storage disclosure.
- [x] `07-storage-imports-and-readiness.md` and `01-admin-overview.md`: updated for where controls now live.

### Task D5: Follow-ups (not started)

- [ ] Expose the Admin Guide chapters over the Workspace MCP as read-only resources so support and assistants can reference them. The chapters are already front-mattered markdown in `frontend/platform_docs/administrative-guide/`; an MCP resource per slug is the natural shape.
- [ ] Enforce `manage_integrations` server-side on `/api/admin/storage-migrations/*`, `/api/integrations/zoom-phone/app-credentials` and `/api/admin/mcp` (today they require the admin role).
- [ ] Move Zoom app credential fields (`ZoomPanel.jsx:607`) behind the same operator gate; that is a ZoomPanel change and stays out of scope here.
- [ ] Add a unit test for `adminTabsFor` / `canUseAdvancedSettings` once `AdminPage` has a test harness; it currently imports the full page tree.

---

## Sequencing

1. **A3** first — the safety net, before anything moves.
2. **A1, A2, A4** — correctness; ship as its own PR. A1 is a live bug and should not wait on the redesign.
3. **B** — independent; unblocks the first-customer onboarding path and proves the new OAuth client.
4. **C** — last, on top of A3's tests.

**Deviation:** this branch carries A, B, C and D as separate commits on one branch rather than three PRs, because the work was executed under a single designated branch. Review it commit by commit; each commit is self-contained and its tests pass on its own.
