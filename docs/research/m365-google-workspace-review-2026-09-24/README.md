# Microsoft 365 / Google Workspace integration review — working cache (2026-09-24)

Status: **in progress.** This folder saves the raw findings so the review can resume
without re-running the discovery agents. Nothing here is verified yet unless it is
marked as such below.

## What is here

| Path | Contents |
|---|---|
| `map/code-*.json` | Code maps from 9 investigators (ms-graph, google, sync, docs-templates, ai-client-leverage, addin-teams, ux-admin, ux-user, plans-ledger): capabilities, API surface, defects, opportunities, UX findings with `file:line` refs. |
| `map/research-*.json` | Web research as of Sept 2026 (copilot, gemini, office-suite-docs, eventing-consent, competitors): findings with status/licensing/sources and recommended plays. Proxy blocked learn.microsoft.com and most Google developer docs; several claims rest on MicrosoftDocs GitHub mirrors or search snippets. |
| `defects.json`, `ux.json`, `opps.json` | Flattened inputs: 147 defects, 119 UX findings (4 from Playwright screenshots, ids `shot#*`), 147 opportunities. |
| `clusters-defects.json`, `clusters-ux.json` | De-duplicated clusters: 119 defect clusters (D01–D119; 24 high), 102 UX clusters (U01–U102). Unverified. |
| `verify/w1.json` … `w3.json` | Verification batches (defects 1–18; defects 19–24 + high-severity impact batches + research fact-check; UX 1–17). Stopped before completion to save usage; re-run from these. |

## Verified by hand so far (code read + screenshot)

1. Integrations overview hero heading was invisible (global `h2` colour on a dark card). **Fixed.**
2. Teams panel offered "Reconnect to enable Teams" for personal Microsoft accounts and when Teams is switched off; hub pill contradicted it. **Fixed.**
3. Google Re-authorize omitted `account_mode`, so personal-Gmail firms could never re-authorize (callback `account_mode_mismatch`). **Fixed.**
4. Admin Microsoft connect never requests `openid` (`MICROSOFT_ADMIN_SCOPES`, `backend/app/routers/integrations.py:241`), so no id_token → `account_type="unknown"` is stamped with `account_detected_at`, which then skips `backfill_unknown_credentials` forever (`backend/app/services/account_detect.py:139`). Every Microsoft tenant stays "tier unknown": directory sync blocked, Teams capability "unavailable", "Granted by" never shown. **Not fixed yet** — proposed fix: request `openid email profile` on the admin flow without adding them to the scope audit, and/or do not stamp `account_detected_at` when claims are missing.
5. `TEAMS_REQUIRED_SCOPES` requests `Chat.ReadWrite` and `TeamsActivity.Send`, which no code calls (`backend/app/services/teams.py:39-45`). Not fixed.
6. `/auth/calendar-providers` already returns per-user connection status, which made the Profile "Connected accounts" card frontend-only.

## High-severity claims still to verify (from the code maps)

- Tenant-token fallback: users without a personal connection search/read the **connecting admin's** mailbox and files via chat/cloud search (`cloud_search.py:1516-1543`, `rag.py:344-376`), and the 15-minute tenant sync indexes the admin's Gmail/Outlook into a firm-wide index (`cloud_sync.py:68-130`, `725-830`).
- Task/deadline pushes fall back to the admin's calendar (`google_calendar.py:18-38`, `microsoft_calendar.py:23-44`).
- Matter documents default to the admin's personal OneDrive (`cloud_init.py:148-166`, `matter_file_store.py:866-870`).
- Unassigning a matter user never removes their OneDrive/Drive share (`routers/matters.py:1772-1825`).
- Deactivated users are re-activated by directory sync and their mail keeps being captured (`user_sync.py:175-181`, `scheduler.py:1894-1915`).
- `/api/email/scan` accepts another user's `user_id` (`routers/email_agent.py:31-65`).
- Workspace MCP OAuth only supports public clients, but Microsoft 365 Copilot DCR requires a client secret (`routers/workspace_mcp_oauth.py:297`).
- Teams tabs cannot frame inside Teams (`nginx/nginx.conf:412-415`) and have no Teams SSO.

## Headline opportunities (research, not yet fact-checked)

- **Client's Copilot does the reasoning:** ship a LawHand declarative agent / Copilot Cowork plugin backed by Workspace MCP (GA remote-MCP plugins, Aug 2026); federated Copilot connector for read-only matter lookup; Meeting AI Insights → matter notes; Work IQ Chat/Retrieval as opt-in (metered in Copilot Credits).
- **Client's Gemini:** custom MCP connector in Gemini Enterprise (preview), Workspace add-on (HTTP runtime) with Workspace Studio steps; BYO Vertex/Agent Platform route billed to the firm's GCP project. No public API invokes Gemini inside Docs/Gmail.
- **Office-suite doc prep:** "Open in Word (web/desktop)" + sync-back for tenant-stored drafts; tenant-side PDF via Graph `?format=pdf`; firm template library bound to SharePoint/Drive; native File Picker v8 / Google Picker with least-privilege scopes (`drive.file`, `Sites.Selected`); Word add-in content controls and tracked-change output. WOPI/CSPP is not a fit.
- **Sync/consent:** Graph change notifications + delta, Gmail watch + history, Drive/Workspace Events; admin-consent-first Microsoft onboarding; Google scope diet before CASA.

## Resume

1. Re-run verification from `verify/w*.json` (script: one skeptic per batch of 5 defect clusters, an impact lens on high-severity batches, UX verifier per 6 UX clusters, one fact-checker per research topic).
2. Write the review/roadmap doc from verified clusters + fact-checked plays.
3. Fix item 4 above in the backend with tests.
