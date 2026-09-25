# Microsoft 365 and Google Workspace integration review

**Date:** 2026-09-24
**Scope:** How LawHand uses Microsoft 365 and Google Workspace today, what it should use, how a firm's own Copilot or Gemini could do work for LawHand, document preparation in the firm's office suite, and the UX of the integration screens.
**Status:** The findings are verified. The code fixes listed under "Fixed on this branch" ship in PR #610. Later fixes are marked **Fixed** in the defect tables with their PR; everything else is roadmap.
**Evidence:** `docs/research/m365-google-workspace-review-2026-09-24/` holds the code maps, research, 119 de-duplicated defect clusters, per-claim verification verdicts and fact-check results.

## Summary

1. **Firm connections quietly act as the one administrator who connected them.** The Microsoft 365 and Google "firm" grants are the connecting administrator's own delegated consent. They are not organization-wide grants. When a staff member has no personal connection, several features fall back to that grant:
   - AI cloud search
   - the 15-minute mail index
   - calendar pushes
   - client email sends

   As a result, staff can search the administrator's mailbox and files, and other people's deadlines land on the administrator's calendar (D02, D03, D04, D25). This is the largest privacy issue in the integrations. Fixing it changes what users without their own connection can do, so it needs a product decision (see "Decisions needed").
2. **Three security defects were confirmed and are now fixed.**
   - One platform Google service account is a member of every firm's Shared Drive, and Drive search and sync ran with its token across all drives, so a firm could see another firm's files (D01).
   - `POST /api/email/scan` scanned any colleague's mailbox by `user_id` (D10).
   - The Excel add-in's "set values" action let a formula such as `=WEBSERVICE(…)` through as a plain value, past the formula ban (D19, fixed in PR #624).
   - Firm indexes built before the Drive fix may still hold other firms' rows and need a purge.
3. **The Microsoft integration was stuck on "account type unknown" for every tenant (D05).** Directory sync never ran, Teams read as unavailable and "Granted by" never showed. This is now fixed; each tenant recovers on its next re-authorize.
4. **Using the firm's Copilot or Gemini is realistic, but in the inbound direction.** The firm's AI calls LawHand tools, so the firm's licence pays for the reasoning. LawHand already has the right building block, the review-first Workspace MCP server. One auth gap blocks both Microsoft 365 Copilot and Gemini Enterprise: the server supports public OAuth clients only (D21). Outbound calls from LawHand into the firm's Copilot or Gemini exist (Work IQ, StreamAssist) but are metered, licence-gated and should wait.
5. **Document prep should use the office suite for editing, not for generation.** Keep LawHand's template engine. Add:
   - "Open in Word/Docs" that syncs edits back
   - PDF conversion in the firm's tenant as an option
   - a firm template library bound to SharePoint or Drive
   - native file pickers

   Editing a LawHand document in Word Online used to break LawHand's access to it (D08, fixed in PR #614), and AI Word drafts lost their formatting on save (D09, fixed in PR #617).
6. **Integration UX:** the worst dead ends are fixed on this branch; see "UX and UI of the integrations" for what remains. Next steps:
   - one "Connections" information architecture
   - an admin-first consent flow
   - per-capability health and toggles
   - honest labels everywhere a single consent covers mail, files and calendar

## Fixed on this branch (PR #610)

| Area | Fix |
|---|---|
| Security | Service-account Drive search, sync and content fetch are pinned to the requesting firm's Shared Drive (`corpora=drive&driveId=…`). A token with no bound drive lists nothing. (D01) |
| Security | `/api/email/scan` returns 403 when the body names another user. (D10) |
| Microsoft | The admin connect requests `openid email profile`. The account type and grantor come from the id_token, and a credential is no longer stamped "unknown" permanently. (D05) |
| Admin UI | Never-connected providers explain what they will ask for and who signs in, instead of 15 red "Missing" rows. The suite a firm doesn't use stays compact. |
| Admin UI | Declined permissions are named, the features they power are downgraded, and Re-authorize becomes the main action. The panel says whose account a firm connection acts as. |
| Admin UI | Plain-language sync job names and provider errors; Disconnect with confirmation; the result of a connect is shown on return; document storage opens itself when a connected firm can't save. |
| Google | Personal-Gmail firms can re-authorize (`account_mode=personal`) and connect personal Gmail. (D22) |
| Teams | No reconnect loop for personal Microsoft accounts or a switched-off workspace; the hub pill separates "not confirmed" from "not available". The invisible overview heading is fixed. |
| Profile | New "Connected accounts" card: each person's Microsoft/Google status, what one consent allows, and connect/reconnect. The branch's partial-consent commit adds "Limited access". |
| Onboarding | One OAuth error helper names the provider that failed and covers cancellation and admin-approval cases. |

## How the integrations work today (verified)

- **Firm connection.** An administrator clicks Connect, and LawHand stores a delegated authorization-code grant as `TenantCredential`.
  - Microsoft scopes: `User.Read.All Mail.Read Mail.Send Files.ReadWrite.All Sites.Read.All Calendars.ReadWrite`, plus Teams scopes on opt-in.
  - Google scopes: `admin.directory.user.readonly gmail.readonly gmail.send calendar drive`.
  - Every Graph or Google call made with this grant acts as that person. `/me/drive` is their OneDrive, `/me/messages` is their mailbox.
- **Per-user connection.** Each person connects from Calendar ("Connect Calendar") or, on this branch, Profile. One consent covers reading mail, sending mail, calendar and all of that person's files.
  - Nothing checks that the connected account belongs to that LawHand user (D30).
  - There is no per-user disconnect (D75).
- **Google storage.** A per-firm org Shared Drive is created automatically, and one platform service account is added to every firm's drive as fileOrganizer. The key has no per-firm isolation; see the roadmap.
- **Sync.** Everything polls. There are no Graph change notifications, no delta queries and no Gmail or Drive push. The cloud metadata index is rebuilt every 15 minutes. Correspondence capture reads a fixed 50-message, 7-day window (D39).
- **Office add-in (Word/Excel/Outlook).** Behind a feature flag. Its session is a LawHand cookie obtained through Nested App Authentication; it has no Graph access of its own. Only four action types exist (replace selection, set values, set formulas, set Outlook subject).
- **Teams app.** A static personal tab and a configurable channel tab, but nginx forbids framing `/teams` and there is no Teams SSO, so the tabs cannot render inside Teams (D17, D18). Channel notifications and Teams voice intake work.
- **AI routes.** All inference goes through LiteLLM. A BYOK path for Azure and Gemini keys exists in the API with no UI; its Gemini fallback model has been retired (see the roadmap).
- **Workspace MCP.** An OAuth 2.1 server with DCR, read tools, and review-first "propose" tools for email, SMS, tasks, documents and workflows. It is a good fit for firm-side assistants.

## Verified defects

119 clusters were checked by skeptical reviewers who re-read the code. The high-severity clusters were also reviewed a second time for privacy and security impact.
- **Results:** 63 confirmed, 55 partly confirmed, 1 refuted (already fixed).
- **Severity after review:** 19 high, 48 medium, 51 low.

The full per-claim verdicts, with file:line evidence and fix sketches, are in `verified-defects.json` in the evidence folder.

### High severity

| ID | Issue | Status | Notes |
|---|---|---|---|
| D01 | Platform Google service account surfaces other firms' Shared Drive files | **Fixed** | Purge old index rows; assess possible exposure |
| D10 | `/api/email/scan` scans another user's mailbox | **Fixed** | |
| D05 | Microsoft tier stuck at "unknown"; directory sync blocked | **Fixed** | Tenants recover on re-authorize |
| D19 | Excel `set_selected_values` bypasses the unsafe-formula ban | **Fixed** | PR #624: values starting with `=`, `+`, `-` or `@` are refused unless they are plain numbers; the add-in checks the same |
| D08 | Editing a matter document in Word/Drive, as the UI invites, breaks LawHand access (409) | **Fixed** | PR #614: open in Word/Docs and bring the edits back |
| D09 | AI Word drafts open as plain text; saving flattens formatting and truncates | **Fixed** | PR #617: DOCX drafts are office snapshots |
| D12 | Date-only tasks sent to Google with an empty time range | **Fixed** | PR #624: all-day events end on the next day |
| D02 | Cloud search and content fetch fall back to the admin's mailbox and files for every user | Open | Decision needed |
| D03 | 15-minute sync indexes the admin's mailbox into the firm-wide index | Open | Decision needed; purge existing mail rows |
| D06 | Microsoft "Auto" storage writes firm matter files to the admin's personal OneDrive | Open | Decision needed (SharePoint default) |
| D07 | Removing a matter assignee never removes their OneDrive/SharePoint/Drive folder share | **Fixed** (PR #625) | Unassign and deactivation remove LawHand's own permission; failures are recorded and retried. SharePoint grants nothing per person |
| D15 | Directory sync re-activates users an admin deactivated; their mail keeps being captured | Open | Decision on source of truth |
| D16 | Directory sync never deprovisions, and licenses guests and resource mailboxes | Open | |
| D11 | Moved or renamed key dates leave stale calendar events | Open | |
| D13 | Per-user Microsoft tokens cannot see matter folders that live in the admin's OneDrive | Open | Follows from D06 |
| D14 | After a storage migration, every sync re-walks the whole tree and rewrites the index | Open | |
| D20 | Add-in cookie session fails in Office on the web and new Outlook | Open | Needs bearer-token path |
| D21 | Workspace MCP OAuth supports public clients only; Copilot and Gemini Enterprise cannot connect | Open | Unblocks the Copilot/Gemini plays |
| D24 | MCP/workflow template render ignores Studio conditional and repeating regions | Open | |

### Medium severity, by theme

- **More admin-token fallback:**
  - approved client email is sent from the admin's mailbox (D25)
  - Gmail sync uses the Drive-only service-account token and silently returns nothing (D26)
  - the tenant token row lock is held for the caller's whole transaction (D27)
  - the scheduler holds the tenant row lock across provider calls (D48)
- **Consent and identity:**
  - unused or over-broad scopes: `Chat.ReadWrite` and `TeamsActivity.Send` are never called (D28)
  - no identity check on per-user connect (D30)
  - a cancelled sign-in shows raw 422 JSON (D33)
  - docs omit the send and write-all-files access (D81)
  - disconnect does not revoke at Microsoft (D70, partly fixed by the UI)
- **Mail filing:**
  - CC-only parties are never captured (D38)
  - a fixed 50-message window (D39)
  - two ingestion paths block each other's dedupe (D40)
  - outbound mail is filed twice (D41)
  - staff aliases count as parties (D42)
- **Calendar:**
  - timed tasks land at the wrong hour (D43)
  - key-date dedupe misses east of UTC+9 (D44)
  - editing an event deletes it and re-invites (D45)
  - Google events send no invitations and have no Meet link (D46)
  - the UI claims calendar updates that failed (D80)
- **Storage and documents:**
  - Word Online edits are orphaned by a LawHand save (D34; fixed in PR #617)
  - AI drafts require an explicit provider (D35)
  - Shared Drive deletes omit `supportsAllDrives` and orphan files (D36; fixed in PR #627: deletes now move the file to the Drive trash with `supportsAllDrives`)
  - `#` or `%` in a filename breaks OneDrive uploads (D37; fixed in PR #627: file names are percent-encoded in Graph upload paths)
  - the container has no Office-metric fonts for signing PDFs (D82)
  - unbounded LibreOffice processes in the API worker (D83)
- **Reliability:**
  - most Graph and Google call sites have no 429/Retry-After handling (D84)
  - Google 403 rate limits are shown as "Reconnect" (D85)
  - provider failures are recorded as successful syncs (D47)
  - per-user Graph search asks for listItem without `Sites.Read.All` (D50)
- **MCP:**
  - client registrations expire after 30 days whether used or not (D62)
  - RFC 8707 `resource` is required on refresh (D63)
  - the consent screen trusts a self-asserted client name, and there is no admin allowlist (D65)
- **Office add-in:**
  - CSP omits `*.cloud.microsoft` (D55)
  - the Outlook read-mode button is a dead end (D56)
  - the 30-minute session has no refresh (D57)
  - Word apply is untracked plain text (D58)
  - the planner skips the data-class check (D60)
- **Teams:** tab framing (D17), no SSO (D18), and a channel-tab save that reports success without creating a working tab (D53).
- **User UI:**
  - SharePoint matters show as unprovisioned or "Local" (D23)
  - no per-user disconnect (D75)
  - the "Connect Calendar" label hides the mail and files access (D77; the Profile card is a partial fix)
  - any tenant credential, including Zoom, counts as "cloud connected" (D78)
  - cloud errors are shown as "no files" (D79)

## Using the firm's own Copilot or Gemini

Fact-checked against primary sources on 2026-09-24. learn.microsoft.com and developers.google.com were blocked by the proxy, so the MicrosoftDocs GitHub sources and search snippets were used; the evidence files mark which.

### What is possible

| Direction | Microsoft 365 | Google | Who pays for reasoning |
|---|---|---|---|
| **Inbound:** the firm's AI calls LawHand | Declarative agent with a remote MCP plugin (GA). Federated Copilot connector, read-only and live (GA, Copilot seat or E7 only). Copilot Cowork plugin: skills plus MCP (GA 2026-06-16, Copilot seat plus credits, off by default). | Gemini Enterprise custom MCP server data store (Public Preview, admin enters client ID and secret). Custom A2A agents (Standard/Plus). Workspace add-on with Workspace Studio custom steps (limited preview, off by default). | The firm's Copilot or Gemini seat. LawHand serves only tool calls. |
| **Outbound:** LawHand calls the firm's AI | Work IQ Chat/Context/Tools APIs (GA 2026-06-16, delegated `WorkIQAgent.Ask`, metered in Copilot Credits even for seat holders). Retrieval API (GA, seat included). Meeting AI Insights (GA, seat only). | StreamAssist on Discovery Engine v1 (needs the `cloud-platform` user scope, per-user IAM, per-seat licence). No API invokes Gemini inside Docs or Gmail. | The firm, metered; per-run cost varies. |
| **Bring your own cloud** | Azure OpenAI BYOK (exists, no UI). | Gemini on the firm's Agent Platform (Vertex) project; a Google Cloud training restriction applies. | The firm's cloud bill. |

### Corrections from the fact-check

- Declarative-agent capabilities that ground in Email, People, Teams messages and Meetings are **licence-only**. Copilot Chat users without a seat cannot use them even with metering. Ship a seat-holder variant, and a web-plus-MCP-only variant for Copilot Chat.
- Copilot DCR requires the authorization server to issue a **client secret**, and the Teams Developer Portal cannot create DCR configurations yet. Gemini Enterprise custom MCP needs an admin-entered client ID and secret. **Confidential clients are required, not optional.**
- The "Copilot agent inside the Office add-in" path is **withdrawn**. Microsoft removed those docs and they now redirect to the add-ins overview; only Excel Copilot skills remain, in preview. Park the Word add-in-as-Copilot-skill idea.
- Cowork is **GA**, not Frontier-only. It still needs the Copilot seat plus Copilot Credits, and EU/UK tenants must enable Anthropic models, which triggers a DPIA.
- Microsoft's **iManage** connector is now a *federated* (MCP) connector ("iManage Work"), not a synced one. Model the LawHand connector as federated.
- LawHand's Gemini BYOK fallback `gemini-2.0-flash` was shut down on 2026-06-01, and `gemini-2.5-flash` retires in October 2026. Pin a 3.x Flash model and validate it when the setting is saved.
- Gemini Enterprise custom MCP is **preview** under Google's Pre-GA terms. Workspace Studio add-on extensibility is still limited preview.

### Recommended plays, in order

1. **Make Workspace MCP registrable by enterprise AI (unblocks everything; M).**
   - Add admin-issued confidential OAuth clients per firm: client ID plus a secret shown once, and `client_secret_post`/`basic` authentication. Keep PKCE.
   - Keep registrations alive while they are used (D62).
   - Relax the `resource` requirement on refresh (D63).
   - Show a publisher and redirect domain on the consent screen, with an admin allowlist (D65).
   - Make tool links absolute.
2. **LawHand Matter Agent for Microsoft 365 Copilot (M).**
   - Build it as a declarative agent (manifest 1.8, plugin 2.4 `RemoteMCPServer`) pointing at Workspace MCP's read and propose tools.
   - Ship two variants: seat-holder with Email/Meetings grounding, and a Copilot Chat-safe variant.
   - Publish through Partner Center to the Agent Store, with publisher verification and Publisher Attestation.
   - The firm's seat pays for the reasoning, and every write stays a reviewable LawHand proposal.
3. **Federated Copilot connector for matter lookup (M).** A read-only subset (search matters, matter context, documents, tasks) with `readOnlyHint` titles, certified through Partner Center. It lets Copilot in Word, Outlook and Teams answer "which matter is this?" without copying privileged content into the firm's Graph.
4. **Gemini Enterprise custom MCP connector (S, after play 1).** Document the admin steps (client ID and secret) and label it preview. Pair it with a SKILL.md pack for engagement letters, chronologies and client updates.
5. **Meeting recap to matter note (M).** For Copilot-licensed firms, pull `/copilot/users/{id}/onlineMeetings/{id}/aiInsights`. This needs `OnlineMeetingAiInsight.Read.All`, which is not in today's consent. Match the meeting to a matter by attendees and file it as a reviewable note.
6. **Copilot Cowork plugin (S, once play 2 exists).** Package LawHand drafting skills with the MCP connector. Document the Anthropic-model toggle, the spending limit and the DPIA for EU/UK firms.
7. **BYO Vertex/Agent Platform route (M).** Use the firm's GCP project via Workload Identity Federation, pin the region and model, and add an admin UI. Fix the retired default model now.
8. **Defer:**
   - Work IQ Chat as "Ask the firm's Copilot": metered, and the data leaves LawHand's review boundary.
   - StreamAssist.
   - a LawHand-hosted multitenant Copilot Studio agent, which would bill LawHand.
   - synced connectors for privileged content.

## Document preparation with the firm's office suite

The position: LawHand remains the template and fill engine, the source of matter data, the review gate and the system of record. The office suite is where people edit and co-author, and optionally where PDFs are converted.

| Play | Detail | Effort |
|---|---|---|
| **Open in Word / Docs, sync back** | For drafts stored in OneDrive/SharePoint, offer three ways to open: Word for the web (`webUrl?action=edit`), Word desktop (`ms-word:ofe\|u\|…`), and view. Detect edits with a drive-root subscription plus delta filtered to matter folders, then snapshot the new version into LawHand. This fixes D08 and D34. **Shipped:** PR #614 (open in Word/Docs, bring back changes on return or focus, upload fallback; fixes D08) and PR #617 (eTag check before a LawHand save; fixes D34). Change subscriptions were not built; edits are reconciled on return instead. Note that subscriptions need `Files.Read.All`/`Sites.Read.All`, which conflicts with a move to `Sites.Selected`; decide which matters more. | M–L |
| **Stop flattening Word drafts** | Default template and agent DOCX drafts to the Word/cloud editing path, not plain text (D09). | S |
| **PDF conversion in the firm's tenant** | When the source DOCX is already in OneDrive/SharePoint, use `GET …/content?format=pdf` (a 302 to a short-lived URL), validate it with the existing pypdf checks, and fall back to LibreOffice. This improves fidelity (D82) and removes load from the worker (D83). | S |
| **Firm template library in SharePoint or Drive** | An admin binds one library (SharePoint via `Sites.Selected`, Drive via Picker). LawHand ingests and version-tracks the DOCX files into Template Studio, and can publish them back as content-type templates so "New > Engagement letter" works in SharePoint. `ms-word:nft` only suggests a save location; copy into the matter folder instead. | M |
| **Native file pickers** | File Picker v8 (delegated) and Google Picker with `drive.file` for "Attach from OneDrive/Drive" and "Choose template". This also moves Google document flows off the restricted `drive` scope. Pin `@googleworkspace/drive-picker-element`, which is pre-1.0. | M |
| **Word add-in: content controls and tracked changes** | Make LawHand fields tagged content controls (WordApi 1.4–1.8 baseline, because LTSC/Office 2024 lacks 1.9), and apply AI and template edits as tracked changes (WordApi 1.4; reviewing needs 1.6). This matches what Clio for Word and Microsoft's Legal Agent have taught users to expect (D58). | L |
| **Complement Microsoft's Legal Agent** | The Legal Agent (Frontier; GA planned for early October 2026) reads playbooks as Word documents in OneDrive/SharePoint. Export the firm's clause and playbook library there instead of competing on generic redlining. | S |
| **Google Docs merge for Google-first firms** | `files.copy` then `documents.batchUpdate` (`replaceAllText`, named ranges). Keep Word-first templates on the DOCX engine: converting DOCX to Google Docs and back loses formatting. Matter links must be plain hyperlinks, because rich-link chips only work for Google resources. | M |
| **Not recommended** | A WOPI host (the CSPP programme targets storage vendors). SharePoint Embedded only as a trial-container pilot, because billing-model choices are effectively permanent. Microsoft 365 or Google eSignature cannot be orchestrated through an API, so keep the dedicated e-signature provider. | — |

## Sync, consent and trust

- **Event-driven sync (L).**
  - Microsoft: Graph subscriptions (mail and events under 7 days; driveItem roots under 30 days) with lifecycle notifications and delta resync.
  - Google: Gmail `users.watch` plus `history.list` using the stored `historyId`; Workspace Events API Drive subscriptions (GA May 2026); Calendar `events.watch` with sync tokens.
  - The receiver acknowledges within 3 seconds and queues the work on the durable job worker.
- **Admin-first Microsoft consent (M).**
  - Since the Microsoft-managed consent policy, end users cannot consent to Files/Sites (July 2025), Mail/Calendars (October 2025) or EWS/IMAP/POP (June 2026).
  - Make `/adminconsent` or Integrated Apps deployment the entry point. Show a "Waiting for your Microsoft 365 administrator" state on `consent_required`.
  - Complete publisher verification (free) and Publisher Attestation (about an hour; required for Teams apps).
- **Google launch path (M).**
  - Pilot with the customer admin marking LawHand as "Trusted" in API controls.
  - Move document flows to `drive.file` with Picker.
  - Use restricted Gmail scopes only if background mail filing stays core, which commits LawHand to an annual CASA assessment (ADA Assurance Level 2). The add-on contextual Gmail scope is reported as non-restricted only by third parties; confirm it with Google.
- **Least privilege (M).**
  - Drop `Chat.ReadWrite` and `TeamsActivity.Send` (D28).
  - Consider `Sites.Selected` for a SharePoint Matter Hub, but check the subscription conflict above first.
  - Use per-firm Google service accounts or Workload Identity Federation instead of one platform key.
- **Throttling hygiene (S–M).** Honour 429 and Retry-After everywhere (D84, D85), cap at 4 concurrent requests per mailbox, set `User-Agent: ISV|LawHand|LawHand/<version>` on SharePoint, and use `$batch`.

## UX and UI of the integrations

The branch fixes the dead ends listed at the top. The next UX steps:

1. **One place for connections.** Today Microsoft 365 and Google state appears in onboarding, Admin > Integrations > Cloud, Cloud Search, Teams, Calendar and matter pages, each with different wording. Standardise on "Connections":
   - admins manage firm connections under Administration
   - each person manages their own under Profile > Connected accounts
   - every other page links to one of those two
2. **Per-capability health.** For mail filing, sending, calendar, storage, directory and search, show state, last success, last error, and the matters affected. Suggested states: Connected, Syncing, Degraded, Needs reconnect, Needs admin approval, Missing permissions, Paused by admin.
3. **Per-capability switches.** Let a firm turn off sending as a user, mail capture, calendar writes or directory sync without revoking the whole consent. Add incremental consent later, so each switch asks only for its own scopes.
4. **Honest labels.** Rename "Connect Calendar" to "Connect your Microsoft 365 / Google account" and show what one consent allows before redirecting (D77).
5. **Matter storage clarity.** Label SharePoint files correctly and open them with a fresh link (D23). Make "where does this matter's files live" visible without expanding "Document tools". Show "Open in Word/Docs" beside Download.
6. **Recovery in context.** Non-admins who hit a disconnected provider should see "Ask your administrator" or "Reconnect your account", never a link to an admin page they cannot open (ux-user findings). Calendar should report provider failures instead of claiming success (D80).
7. **Office add-in pane.**
   - Show which matter is in context.
   - Suggest actions.
   - Show a word-level diff for Word and a changed-cell view for Excel.
   - Provide a sign-in retry and follow the Office theme.
8. **Teams.** Either finish the tab (frame-ancestors for Teams, Teams SSO, a deep link to the linked matter) or hide the tab until it works. Say in Admin how to install the Teams app and the add-in.

The UX findings in `ux.json` and `clusters-ux.json` (102 clusters) were reported by code readers and screenshots. Only the ones fixed on this branch were re-verified in this pass.

## Roadmap

| Horizon | Items |
|---|---|
| **Now** (security and correctness) | Purge firm indexes of foreign Drive rows (D01 follow-up) and of admin-mailbox rows once D03 is decided. D28 drop unused Teams scopes. D81 correct consent copy and disclosures. Pin a current Gemini model. |
| **Next** (decisions needed) | End the admin-token fallback for mail, search and calendar (D02, D03, D04, D25). SharePoint default storage instead of the admin's OneDrive (D06, D13). Directory-sync lifecycle rules (D15, D16). Confidential MCP clients (D21). Admin-first Microsoft consent. Per-capability health. |
| **Later** (growth) | Matter Agent for Microsoft 365 Copilot. Federated connector. Gemini Enterprise connector. Meeting recap. Firm template library in SharePoint/Drive. Native pickers and `drive.file`. Word add-in content controls and tracked changes. Outlook and Gmail "file to matter" add-ins. Event-driven sync. Teams tab. |

## Decisions needed

Decisions 1–3 are settled in [the permissions and visibility model](./permissions-and-visibility-model-2026-09-25.md) (25 September 2026): an org-level firm connection replaces the admin-token fallback, firm storage is firm-owned, and a LawHand deactivation holds against directory sync.

1. **Admin-token fallback.** Should staff without a personal connection lose cloud mail and file search, and calendar pushes? The recommendation is yes:
   - search only the firm's own storage roots
   - index mail per user, filtered by owner
   - send from the approver's mailbox, or from a dedicated shared mailbox
2. **Default Microsoft storage.** Should LawHand require a SharePoint library (organization-owned) instead of defaulting to the connecting admin's OneDrive?
3. **Directory sync.** Should an admin's deactivation in LawHand override the directory? Should disabled or deleted directory accounts be deactivated, and should guests and resource mailboxes be skipped?
4. **Google scope strategy.** Should LawHand commit to annual CASA for background Gmail filing, or move to add-on and Picker flows?
5. **Copilot and Gemini priority.** Is the Microsoft Matter Agent or the Gemini Enterprise connector first after the confidential-client auth work?
6. **Possible cross-firm Drive exposure.** Was `GOOGLE_SERVICE_ACCOUNT_KEY` configured in production with org Shared Drives before this fix? If so, run the purge and follow the incident process.

## Method and caveats

- **Code mapping:** 9 parallel investigators (Microsoft Graph, Google, sync, documents and templates, AI and MCP, add-in and Teams, admin UX, user UX, plans ledger), plus screenshots of every connection state rendered with a mocked API.
- **Verification:** 35 skeptical reviews over 119 clusters, plus a second privacy and security review of the high-severity ones. Each verdict cites the file:line lines the reviewer read.
- **Research:** 5 web sweeps, fact-checked by 5 more agents. learn.microsoft.com, developers.google.com and some vendor sites were blocked by the network proxy, so some claims rest on the MicrosoftDocs GitHub sources or search snippets. Check licensing and preview status again before committing to a customer.
