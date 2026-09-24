# Operator Console Review

Date: 2026-09-23
Scope: the platform operator console (`/platform`, `frontend/src/pages/PlatformPage.jsx`) and the platform API it drives (`backend/app/routers/platform*.py`, the operator routes in `backend/app/routers/operating_trust.py`), reviewed from a support and account-management perspective. Follow-up to the [July UX review](platform-ux-review-2026-07-23.md), which deferred "Administration and Platform: operator-focused navigation, save feedback, validation, and destructive-action hierarchy".

## Executive summary

The console was capable but built around configuration, not support. Three problems mattered most:

1. **Customer support requests had nowhere to land.** Firm administrators file S1–S4 requests from Admin → Support, each with a published acknowledgement clock (60 minutes, continuous, for S1). The platform could move a request only with a `PATCH` that needs both the tenant and request IDs up front; there was no list endpoint, no console view and no alert. A filed request was visible only from a database shell.
2. **The troubleshooting API was unreachable.** User lookup by email, error detail and resolution, request tracing, tenant diagnostics and the operator audit trail all exist behind `platform:debug`, but the console had no UI or client functions for them — and no bootstrap credential could carry `platform:debug` anyway, because the startup allow-list in `app/config.py` and the documented hashing script omitted it. The documented credential stopped the app from starting.
3. **Everyday firm management was clunky and in places risky.** Search only filtered the 50 rows on screen; approvals, expiring trials and lapsed firms had no queue; whole-firm actions (deactivate, end access, change billing, sponsor Premium AI) fired on a single click; the log pages could not page past page 1; and every 403 — including a simple missing scope — signed the operator out of a 15-minute session and lost their place.

This change fixes all three. The console opens on what needs attention, has a Support desk (queue plus one lookup box), gives each firm a sectioned panel with Health and History, and asks before acting on a whole firm.

## How the review was done

- Read the console and every platform route, then inventoried API capabilities against what the UI exposes.
- Exercised the result against a seeded local stack (Postgres, Redis, FastAPI, Vite) with the backend connected as the production-style `NOBYPASSRLS` runtime role, driving headless Chromium through the main support paths and checking layouts at 1440, 1280 and 900 px.

## Findings and disposition

| Priority | Finding | Impact | Disposition |
|---|---|---|---|
| P0 | No operator list or UI for customer support requests; no alert when one is filed. | S1 clocks could run out unseen. | Fixed: `GET /api/platform/operating-trust/support`, a Support tab queue with acknowledge / mitigate / resolve, and a best-effort email to the operator inbox on filing. |
| P0 | `platform:debug` missing from the bootstrap allow-lists (`app/config.py`, `backend/scripts/hash_platform_bootstrap.py`) although the docs tell operators to grant it. | Every troubleshooting route unreachable from a console session; the documented credential blocks startup. | Fixed, with a test that keeps all three scope lists identical. |
| P1 | User lookup, error detail/resolve, request trace, tenant diagnostics and the audit trail had no client functions or UI. | Support had to use curl or borrow a customer login. | Fixed: Support lookup box, firm Health and History sections, inline error detail with resolve notes. |
| P1 | Firm search filtered only the loaded page; no lifecycle filters; pending approvals had no queue. | Firms beyond the newest 50 could not be found by name. | Fixed: server-side search (name, domain, company, tenant ID) and views with counts — needs approval, active, trials, ending ≤14 days, expired, inactive, demo. |
| P1 | Deactivate, end trial access, convert to active, billing tier and sponsor Premium AI acted on one click. | Easy to lock out or bill a firm by accident. | Fixed: confirmations. "Revoke trial now" is renamed **End access now** so it is not confused with the new **Revoke trial and release its login**. |
| P1 | Log pagination: every Next reloaded page 1. | Errors after the first 50 were unreachable. | Fixed. |
| P1 | API traffic "4xx" summed six named codes, so any absent code made it 0; no 5xx card; summary ignored the firm filter. | Traffic health read as clean when it was not. | Fixed: status-class totals, a 5xx card, firm-scoped summary. |
| P1 | Log load failures were swallowed silently. | Empty tables looked like "no errors". | Fixed: failures are shown. |
| P1 | Any 403 signed the operator out, including a missing scope; a 15-minute session expiry discarded the operator's place; the header showed the first 8 characters of the JWT (`eyJhbGci…` for everyone). | Constant re-navigation; no idea who is signed in or when the session ends. | Fixed: scope denials are explained in place; tab, view, search, open firm and log filter live in the URL; the header shows the operator and session end, and sign-in returns to the same place with a reason. |
| P1 | A firm's detail was one inline stack of eight panels. | Long scrolls to find a control. | Fixed: Overview · Access & billing · Health · Support · AI & workspace · History · Compliance. |
| P2 | Dashboard "Top Tenants" ranked only the loaded page; model cost was labelled "Revenue". | Misleading management figures. | Fixed: `/usage` returns the true top ten; relabelled **Model cost**. |
| P2 | Seats and Research MCP entitlement were settable only by API. | Routine changes needed curl. | Fixed. |
| P2 | Trial revocation (`/tenants/{id}/revoke`) had no UI. | Abandoned trials kept their addresses. | Fixed: danger-zone form that requires typing a login address at the firm. |
| P2 | Ten ungrouped tabs overflowed the bar at common laptop widths with no scroll. | Some tabs were unreachable. | Fixed: Customers · Operations · Configuration groups; all tabs fit from 1280 px and the bar scrolls below that. |
| P2 | Infrastructure status needed a second sign-in, and its expiry check looked for 401 while the API returns 403. | Stuck "could not be refreshed" error. | Fixed: embedded in the System tab; expiry handled. |
| P2 | Duplicate "Tenant Logs" sub-tab; error-type filter state with no control. | Two views of the same data. | Fixed: one Errors view with firm and type filters. |
| P2 | Saving a firm's AI routing left the form marked unsaved. | Confusing save state. | Fixed. |
| P2 | Unknown tenants were labelled with mojibake (`â€”`). | Garbled label in traces. | Fixed. |
| P2 | "Unresolved errors" counted every client 401/404, which are logged as warnings. | Noise hides real failures. | Overview counts unresolved errors and criticals only (`unresolved_by_severity`). The source of most warnings is a follow-up below. |
| P2 | The backup invitation link opened in the operator's browser. | Risk of an operator setting up the customer's login. | Fixed: copy-to-clipboard with guidance. |

## What changed

**Overview.** Needs-attention cards (approvals, support work with overdue count, access ending within 14 days, expired-but-active, unresolved errors) link to the matching filtered view. Busiest and newest firms open the firm.

**Firms.** Server-side search and lifecycle views with counts; registration is behind a button; pasting a user's email also finds their firm (debug scope). Opening a firm from anywhere searches by its tenant ID, so it is always the visible row. The panel adds Health (the runbook's diagnostics), Support (that firm's requests) and History (operator actions on the firm, including support and error actions recorded against their own resources).

**Support.** One lookup box accepts an email, error ID or request ID (UUIDs are tried as both at once), with Open firm and resolve actions on results. The queue orders work the way the policy does — unresolved first, then severity, then the acknowledgement clock — shows the published escalation path for overdue requests, and never resets the escalation level when a request moves on.

**Logs, Audit, System.** Working pagination, correct status-class totals, visible failures, inline error detail with resolution notes; a global Audit tab that hides per-request rows by default; embedded infrastructure status and session details.

**Code layout.** New console code lives in `frontend/src/pages/platform/` (shared primitives, tenant controls, tenant panel, support, logs, audit); `PlatformPage.jsx` shrinks from ~4,400 to ~3,500 lines and re-exports what existing imports use.

## API changes

| Route | Scope | Change |
|---|---|---|
| `GET /api/platform/operating-trust/support` | `platform:read` | New. `status` (`active`, `all`, `open`, `acknowledged`, `mitigated`, `resolved`), `severity`, `tenant_id`, `limit`; returns `counts` and an `overdue` flag. Reads each tenant under its own RLS scope. |
| `GET /api/platform/tenants` | `platform:read` | Adds `q` and `status` views with `counts`; defaults unchanged. |
| `GET /api/platform/usage` | `platform:read` | Adds `top_tenants`. |
| `GET /api/platform/logs/summary` | `platform:read` | Adds `unresolved_by_severity`. |
| `GET /api/platform/audit` | `platform:debug` | Adds `tenant_id` (matches `resource_id` or `metadata.tenant_id`) and `exclude_requests`; defaults unchanged. |
| `POST /api/compliance/operating/support` | tenant admin | Unchanged response; now also emails `MARKETING_LEAD_EMAIL` (the address that already receives registration alerts). Never fails the request. |

## Follow-ups (not in this change)

- **Auth-probe noise.** The app shell probes `/api/auth/me` and `/api/auth/refresh` on every route, and each expected 401 is stored as an `api_error` warning. Queued separately.
- **Mojibake** remains in `backend/app/routers/tasks.py` and `backend/app/services/task_automation.py`. Queued separately.
- Consoles for routes that still have none: public status-page incidents (`/api/platform/operating-trust/incidents`), two-operator offboarding approval, operator API keys (`/api/platform/api-keys`), and document reindexing (`/api/platform/documents/reindex`).
- Per-user operator actions (resend an invitation, end a user's sessions) have no API yet.
- Support alerts are best-effort email. S1 may warrant a pager integration or a dedicated support address rather than the shared operator inbox.
- Support escalation can only change together with a status transition; changing it independently needs an API change.
- The tenant list reads one tenant-scoped settings row per inactive or unexpired firm to place firms in views. Fine at current scale; a registry-level lifecycle column would remove it if firm counts reach the thousands.
- `PlatformPage.jsx` still holds the AI Routing, MCP, SMS and Integrations tabs; continue splitting it along tab boundaries.
