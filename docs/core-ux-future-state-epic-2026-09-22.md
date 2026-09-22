# LawHand future core UX and features: refinement epic

Status: draft for ongoing collaboration. Research and an initial walkthrough are complete; product implementation has not started. Keep this planning PR in draft until the user requests otherwise.
Owner: “Plan legal platform UX refinement” — future state of core UX and features, assigned by the user on 22 September 2026.
Date: 22 September 2026.

## Outcome

Help staff open the right matter, see what needs attention, record work, and return to their queue without rebuilding their context. Preserve LawHand’s current visual identity and familiar destinations. Give users a useful starting arrangement plus a few easy ways to change it.

Working audience: paralegals and legal assistants with limited comfort learning software; attorneys and intake staff are secondary validation groups. This is an assumption pending the user's preference, not a finding from user interviews. The user's report that staff feel overwhelmed is the problem statement. Competitor reviews and an expert walkthrough suggest causes; usability sessions must test those hypotheses.

The first release should make daily work clearer before asking anyone to configure anything. Personalization must stay optional. Success means fewer decisions and less searching to finish the same work, not simply fewer visible controls.

## Ownership and collaboration contract

The user assigned the future state of core UX and features to **Plan legal platform UX refinement**, and document automations to **Validate PDF engine release**. The document-automation owner confirmed this split on 22 September 2026. Ownership is agreed; the proposed UX behavior, priorities and estimates below remain open for collaboration.

| Responsibility | Owner and scope |
| --- | --- |
| Future core UX and features | This epic: My Matters, matter overview hierarchy, work/focus semantics, Tasks, Calendar, CRM directory and lead pipeline, navigation, preferences and cross-module continuity. |
| Document automations | Validate PDF engine release: document questionnaires, template selection/mapping, filling, generation, preview/review, signing/filing, persisted preparation sessions and document-intake draft recovery. |
| Shared product boundary | Core owner defines how staff discover and enter document work and see its status in the matter workspace. Document owner defines the preparation flow, its state/evidence contract and what actions are actually available. Agree the interface before editing either side. |
| Shared implementation files | One editor at a time for MatterDetailPage, shared API exports, navigation and shared backend routers. Coordinate by file and function; directory ownership is not permission to overwrite another active branch. |

The document owner's current corrective PR is [#580: fill PDFs from matters and preserve document preparation progress](https://github.com/mattpainter701/lawhand/pull/580), reported at head 7a131b7e9c46ed0aa2e0f0c7f3f2bcfab1a84abf with CI pending on 22 September 2026. Its owner retains merge, deployment and production acceptance responsibility. That PR leaves MatterDetailPage, Tasks, Calendar, CRM directory and global navigation untouched. Its precise changed-file list is authoritative; do not treat this dated status as a continuing lock after that work completes.

Agreed interface constraints from the document owner:

- Entry links retain the existing /templates/prepare route with template/set, matter, folder and return target. Persisted drafts carry a session in the URL; Resume continues through Documents in progress.
- Changing the source matter clears old-client answers, verification and previews. Manual values must not silently carry to a different client.
- Preserve tenant/matter access checks, verified-field attribution and fill-session preparer ownership. Background saving acts as the preparer and uses their preview evidence.
- PR #580 does not change focus semantics, default reviewers or signature permissions. UX-01A must agree a reviewer-responsibility contract with the document owner before changing fallback selection, while retaining reviewer eligibility and review/signature evidence rules.
- UX-02 owns overview shell ordering, collapse state, summaries and entry visibility. It does not replace SignatureRequestsPanel, ClientConversation, their delivery/signing behavior, or document persistence. Required statuses and errors stay discoverable when a panel is collapsed.
- Document-intake durable resume and Gavel-inspired automation/builder parity belong to the document owner. UX-06 owns CRM lead conversion and the handoff; it consumes document state instead of implementing another questionnaire or draft engine.

Coordination is event-driven: share proposed interface changes and conflicting file ownership before implementation; send exact PR/commit links when a dependency lands; jointly validate matter → document work → return/status using synthetic records. Each owner keeps a separate branch/worktree and owns their tests. This draft changes documentation only and does not authorize edits in the document owner's active worktree.
## Scope and boundaries

Included: My Matters, matter overview, Tasks, Calendar, Clients & CRM, the existing Intake handoff, and their shared navigation/preferences. Keep colors, typography, component vocabulary, data models, and established routes wherever possible.

Excluded from this epic: a visual rebrand; free-form dashboard/canvas builder; new AI assistant or automation engine; broad global search across documents; billing/trust redesign; replacing the lead/contact model; court-rule deadline calculation; bulk deadline changes; provider migration; PDF filling or signing-engine fixes. Those may be valuable but do not need to be prerequisites for basic workspace clarity.

Target guardrails: changing a view never changes permissions, matter status, assignment, deadlines, consent, or client visibility. The existing working flag violates that separation; UX-01A is an explicit authorization/reviewer-policy change that must establish the new contract before focus is offered as ordinary personalization. Required alerts remain visible even when a related section is collapsed. Clicking a filter never changes business data. Automated work is grouped for readability, never silently completed or hidden from the work queue.

## Evidence baseline

- Production inspected through the authenticated browser at getlawhand.com. Visible build: `329df4e400d6a67e8533d35954f3b90dcb1afe19`, built 2026-09-22 03:30:55 UTC.
- Source reviewed from freshly fetched `origin/main`: `c4d80b46522e1c2b9436fdc8fae343c9d78db8c9`. Production and main are different snapshots; recheck both at implementation kickoff.
- Walkthrough: My Matters list and Columns; a synthetic demo matter overview and Customize view; matter Add Task; Tasks board and New Task; Calendar list and New Event; CRM directory, New client and a synthetic client detail; Intake pipeline.
- Opened and cancelled creation dialogs. No task, event, client, lead, message, paperwork, consent or preference was saved. Existing demo/validation records are not representative of customer workload; overdue counts are not a measure of customer behavior.
- Screenshots and accessibility observations were reviewed in this task. This report deliberately does not reproduce private client details.
- Read-only source audit reviewed current implementations and existing tests. No application tests were run because no product code changed. Backend payload persistence and successful provider sync were not tested live.
- The document-automation task owns active PR #580 and its production acceptance. Its scope and interface constraints are recorded above; document engine, questionnaire and draft fixes are outside this epic.
- A companion [feature-parity audit](./research/core-ux-feature-parity-2026-09-22.md) (22 September 2026) reads the same source revision and records, for each capability across Matters, Tasks, Calendar, CRM/Intake and navigation, whether LawHand matches, partially supports, lacks or has not yet verified it — and whether a gap is a missing capability or an existing one users struggle to find. It also extends the [competitive research brief](./research/core-ux-competitive-research-2026-09-22.md) with Smokeball, Filevine, Rocket Matter, Actionstep, Centerbase and Lawmatics. Its gap register introduces UX-10 to UX-13 below.
- Existing UX planning/implementation PRs were inspected as background, particularly #395, #396, #425 and #431. Many old findings are already fixed. Before creating this draft, #395 was confirmed closed/unmerged and #425/#431 merged; current open PRs included #580 (document automation), #578 (ops) and #548 (Google root migration), with no duplicate core UX epic returned. This plan extends current main rather than reviving old branches. Remote branches alone do not prove active ownership.

## Current UX: what to retain and what to refine

| Area | Already working / worth retaining | Observed friction | Proposed refinement |
| --- | --- | --- | --- |
| My Matters | List/board choices; real matter links; keyword filtering; status tabs; sortable, resizable, hideable columns | At the inspected 1420px viewport, nine data columns plus Actions push deadline/status off the visible part of the table. Attorney metadata takes space before the next deadline. “5 matters need attention” is text rather than a direct queue entry. A second All Matters section adds another list model. | Everyday columns prioritize matter/client, next deadline, status, owner. Make Needs attention a view. Keep all fields available through Customize view. Give My/Firm scope one clear control where permissions allow. |
| Matter overview | Five primary tabs; client link; Quick Actions; Key Dates; task links; existing field visibility | Large description/budget header, onboarding card, empty message composer and expanded signature-creation form precede Quick Actions, Key Dates and To-Do. The existing gear cannot reorder these sections. | Compact identity; attention and work first; setup/actions opened deliberately. Let users reorder/collapse a finite set of overview sections using up/down controls. |
| Task creation | Existing API and matter context; optional date/time; assignment support | Matter modal defaults to Deadline; global form defaults to general. Due-time controls differ. Matter assignment control disappears when the team list is empty. | One shared task composer and clear assignment state; same plain labels and date/time behavior across entry points. |
| Tasks queue | My Work/Firm Work; board/list; due filters; workflow states; move menu alongside drag | Board can show many items in To Do with several empty columns. Risk counters are passive. Several filters live only in component state; no visible title search. | Everyday list with actionable Overdue/Today/Upcoming/Waiting views; board stays available. Preserve filters/scroll when returning; add bounded task search. |
| Calendar | Day/week/month/list, mobile agenda, event-type labels, task/provider deduplication, explicit drag intent | The inspected List begins with old entries and shows October entries under a September heading. No visible matter/type/source filter. “Deadline Calendar” describes only part of its content. | Calendar label, an accurate range, a useful upcoming agenda, a compact filter row, readable source/type labels. Preserve all current views and safe rescheduling behavior. |
| CRM / Intake | CRM uses the contact model; search and lifecycle filters; client-to-matter links; Intake already has five stages and Convert to Matter | “Call Intake” and “Intake” sit together without explaining their difference. CRM emphasizes four summary cards including SMS consent; new client exposes payment and lifecycle fields immediately. Filters are not URL-backed. | Clear cross-links for Clients, Contacts and Intake pipeline; existing lead handoff made explicit. Contact/next work first, optional administrative details second. |
| Navigation / preferences | Role presets, personal hide/reorder, sidebar sizing and collapse already exist | In the admin account, 18 navigation destinations are available. Personal navigation follows the user, while matter/column settings say “on this device.” Gear is near the profile, with a different customization surface on each page. | A consistent Customize view vocabulary, clear preference scope, opt-in everyday preset and easy reset. Preserve user choices and module/role authorization. |
| Cross-module search | Per-module search exists: matters (name only), clients, contacts, firm memory, matter documents and the intake dashboard | No global search or command palette; the global chat shortcut creates a conversation with no input guard, so it can fire while typing in a form | Add a scoped search entry point in a later release; make the shortcut focus-safe now (UX-07, UX-10). |
| Bulk actions | — | No multi-select bulk reassign/status/archive on matters, and no bulk complete/reassign on tasks | Add permission-checked bulk actions with a confirmation summary and no partial silent failure (UX-11). |
| Task structure | Recurring, dependency and subtask concepts are absent; checklists exist only inside matter-workflow templates | Filevine Taskflow, Actionstep and Smokeball generate dependent and repeating tasks from matter phases | Validate demand before adding recurrence/dependencies; do not assume parity requires it (validated backlog). |

The Calendar range issue is source-confirmed: list uses the start of this month through the end of the next month, while its header uses only the pivot month's label. Treat the proposed upcoming default as a design choice, and the inaccurate range label as a correctness fix.

## User feedback: what does “Working on this” mean?

The user reports that staff ask what the button does and suggests it could show which matters are being worked on in a busy office. This is a concrete comprehension failure to include in baseline testing.

**Verified behavior in current main:** the button stores a manual boolean on an existing matter assignment. It remains set until someone switches it off. It does not start a timer, record a time entry, lock the matter, change its lifecycle status, add/remove its assignment, or determine whether it appears in My Matters. It has no dedicated focus timestamp or automatic expiry. The matter overview uses it for an Active Workers count and team labels. The Team panel still says Active / Set Active and Actively working, whereas the portfolio says Work on this / Working on this. The portfolio's hover hint explains part of the intent, but staff should not need hover help to discover a primary action's meaning.

**Hidden dependencies make this more than a wording change:**

- Research workspace routes require a flagged assignment for non-admin users who are not the matter owner. Clearing the flag can produce a 403 even while the user is still assigned to the matter. Workspace membership and write-role checks also apply; setting the flag alone does not grant every workspace permission.
- Chat document-reviewer fallback selection ranks flagged assignees ahead of other assignees. This can influence suggested/default reviewers; it does not directly reassign existing tasks or override explicit reviewer eligibility.
- The old active/watching board arrays are not the rendered board. The visible board uses matter lifecycle status. Do not reintroduce flag-based lifecycle movement.

These are source findings, not live permission or reviewer mutation tests. Their exact production behavior must be verified against the deployed revision.

**Recommended product contract:** preserve a lightweight, team-visible personal focus list, while making assignment, permissions and reviewer responsibility explicit and independent. Proposed copy:

| Surface | Proposed wording and behavior |
| --- | --- |
| Matter row secondary action | Add to my focus → Remove from my focus |
| Personal queue/filter | My focus; an additive view of accessible assigned matters the user has deliberately selected, leaving the assignment-based My Matters list intact |
| Shared indicator | On Alex's focus list; multiple names where appropriate |
| Short help beside the control | Keep this matter in your focus list and share that choice with your team. It stays here until you remove it. |
| Distinct concepts | Assigned to you = responsibility/membership; Status = case lifecycle; My focus = personal work selection |

Keep Open matter as the obvious way into the record. Show the shared focus indicator only to people already permitted to see the matter. Use a text/icon treatment that does not resemble online presence. Existing true values should remain selected after migration; do not reset staff choices. Do not label it “today,” “online,” “busy,” or “currently editing” without implementing the time/session behavior those words promise.

Before presenting this contract, remove the flag's hidden permission and reviewer-ranking roles under UX-01A. Research access must follow explicit tenant, assignment, workspace membership and capability rules, preserving documented owner/admin exceptions and denying unauthorized users. Default reviewers must follow an explicit responsibility/role policy; focus changes must not silently route review work. Review those policies at implementation kickoff rather than substituting an unrestricted membership check. Ordinary users may change only their own focus. Any manager/owner/admin action on another user's focus requires an explicit authority policy and a separately labeled, audited path; do not silently preserve the current generic team toggle.

A cosmetic rename alone cannot meet this contract. If the access work cannot fit, retain truthful existing semantics and defer the focus feature's rollout. Real-time office presence, automatic expiry, time tracking and work checkout are separate possible future products, outside this refinement epic.

## Gavel concepts applied to this epic

The [research brief](./research/core-ux-competitive-research-2026-09-22.md#gavel-workflows) documents the evidence and limitations. Gavel Workflows is most relevant to guided intake; its document-automation builder is not a replacement design for LawHand's everyday matter screen.

Apply a small set of interaction rules: each form has a clear purpose and next outcome; ask only relevant questions; show known client/matter information so it can be checked; put short help at the point of confusion; preserve input when validation or saving fails. Longer existing intake/conversion flows may use named steps and a review/edit summary. Simple task creation remains a short form.

UX-06 should test interruption and return at the CRM/document handoff using the document owner's existing persistence contract. “Saved” must mean the server confirmed persistence, and “Submitted” must identify the resulting record/action. If durable draft/resume is missing, record it as a separate dependency and coordinate with the PDF/intake task; do not imply that this epic already delivers a new draft or workflow engine. Calendar filters and matter navigation do not need interview-style steps.


## Proposed experience

**My Matters:** one recognizable workspace. Start with “My matters,” “Needs attention,” and “All accessible matters” as scope/view choices, with counts whose scope is explicit. The everyday table shows Matter/client, Next deadline, Status and Responsible person. Client can be a second line under the matter name on narrower screens. Filters and Customize view are adjacent. Secondary metadata stays available. Preserve existing assignments; introduce the secondary My focus action only after UX-01A decouples its hidden access/reviewer effects. My focus is separate from My/Firm scope and lifecycle status.

**Inside a matter:** compact identity and client; essential alerts; Add task / Add note / Add date actions; Next work and Key dates; Recent activity; Client communication and paperwork summaries; optional detail/billing information. Maintain the current primary tabs. Unread messages, failed delivery, expired/declined requests and overdue work remain visible as actionable summaries. Open the full composer or signature setup only when requested. Existing matters with unknown engagement status show a concise status prompt; never automatically mark them engaged.

**Tasks:** an everyday list for users who choose the everyday preset, preserving existing users' board/list choice. Overdue, Today, Upcoming and Waiting lead to filtered queues. Completed work remains reachable. Each row answers: what, which matter, who, when and status. Show the total when work is grouped. A task's recorded due date remains visible even when it appears in a waiting group. Use server search for the accessible corpus, not just the current page.

**Calendar:** upcoming agenda plus existing grid views. Users can narrow by matter, event kind and source where the backend supports the required scope. Clearly separate Task due, Appointment, Key date and Work block. Show local display timezone; date-only tasks stay date-only. A disconnected provider banner states what is unavailable while preserving local dates. Do not describe a successful local save as successful external sync.

**CRM:** clients and prospects are easy to find, with contact details, related matters and follow-up links near the top. Label existing Intake as “Intake pipeline” and Call Intake as “Call log & intake” provisionally; validate terminology with staff before changing labels. Offer explicit existing-record selection before creating a duplicate. Keep the contact model, record IDs, conflict decisions and current conversion endpoint. No drag into a new stage should silently accept a legal engagement.

## Parity audit: what it changes

The [feature-parity audit](./research/core-ux-feature-parity-2026-09-22.md) confirms the existing P0 scope and separates two things this epic previously blurred: **capabilities that are missing** and **capabilities that exist but are hard to find**. It changes scope in four ways:

- It confirms the P0 correctness fixes implied by the walkthrough: the calendar list-range label (G-14), a local save shown as success when provider sync failed (G-16), and the global chat shortcut firing while a form is focused (G-25). The first two belong to UX-05; the shortcut fix belongs to UX-07.
- It confirms the scale gaps already assigned to UX-08: the 100-record cap on personal matters and the 200-record task fetch.
- It adds two P1 stories — UX-10 (global cross-module search) and UX-11 (bulk actions) — and two validated-backlog items (UX-12 recurring/dependent/subtask work; UX-13 saved views). The P1 stories are follow-up release candidates, not part of the two-sprint plan, unless staff sessions show search or bulk work is a blocking failure.
- It records what must **not** expand this epic: document version history and prepared-document drafts (document-automation owner), stage-entry automation and automatic deadline shifting (excluded), ethical-wall policy authoring (security owner), and CRM-side portal/e-sign actions (document/client-portal owner).

## Delivery backlog

Effort is a planning estimate in engineer-days including focused implementation tests, not a commitment. UX research, shared CI waiting and independent acceptance are additional. One implementation owner and one isolated branch/worktree per story; shared-file stories run sequentially.

| ID | Priority / effort | User story and acceptance criteria | Dependencies / likely owner |
| --- | --- | --- | --- |
| UX-00 | P0 / 1–2 | **Baseline and validate the arrangement.** Run the seven scenarios below with 5 representative staff using synthetic records. Record success, time, wrong turns and assistance. Review a simple arrangement prototype with the product owner. Confirm primary persona and label choices. No customer-data recording without consent. | First; product/UX with engineer support |
| UX-01 | P0 / 2–3 | **Everyday My Matters.** At 1366×768 and 1440×900, the new/default everyday arrangement shows matter identity, next deadline and status without horizontal scrolling. Existing customized views retain their selected columns and may intentionally scroll. Needs attention opens the corresponding records. Keep column sorting, widths, existing preferences, board and lifecycle semantics. My/Firm counts identify their scope. Fix/remove the decorative View affordance in the secondary All Matters table. Search/filter state survives open → Back. | UX-00; frontend A |
| UX-01A | P0 prerequisite / 4–6 | **Decouple authorization/reviewer policy, then clarify the work signal.** Confirm and implement explicit research-access and default-reviewer policies independent of focus, then apply Add to my focus / Remove from my focus and shared list wording consistently in portfolio, overview and Team. Preserve existing selections. My focus is an additive filter over the current user's assigned matters; it never replaces the assignment-based access/list path or changes My Matters membership, lifecycle, deadlines or task ownership. Ordinary users can change only their own focus; any privileged on-behalf action is separately authorized, labeled and audited. Switching focus must leave legitimate research access and reviewer responsibility unchanged; unauthorized access must remain denied. No timer, lock or real-time-presence implication. | UX-00; backend owner first, frontend A afterward; agree policy with research/document-automation owners |
| UX-02 | P0 / 3–4 | **Matter overview arranged around work.** On the same laptop sizes, identity, actionable alerts and entry points to tasks/dates appear before setup forms. No empty full signature/message form in the everyday overview. Scope is the overview shell and entry-point presentation; preserve panel internals, delivery/signing behavior and the document owner's state contract. Move optional sections up/down, collapse/restore, reset; visible summary signals remain. Optional sections may be hidden but required alerts/identity cannot be. Values never disappear from Edit. Cancelling arrangement restores the prior layout. Keyboard and touch work without dragging. | UX-00; frontend A, after coordination with PDF task |
| UX-03 | P0 / 2–3 | **One task composer.** Open from global Tasks, a matter, or a matter-filtered queue: current context is visibly prefilled and correct. Global entry can select a matter. Title, assignee state and due date are easy to find; More options holds type/priority/reminders/notes as appropriate. Default general Task unless the entry explicitly says Deadline. Optional due time available consistently. No team members means an explicit Unassigned state or permitted staff search. Same payload semantics, linked-contact support where relevant, validation and server error handling. Prefilled client/matter context is visible and checkable; brief field help explains unusual choices. Two context-specific shells may remain if they share the composer contract. Failed saves retain input; repeated submit cannot create duplicates. | UX-00; frontend B + API review |
| UX-04 | P0 / 3–4 | **A queue users can resume.** Make risk counters actionable filters; add title search with an explicit new backend query parameter and scoped query tests; preserve view/scope/filters/page and return position. Everyday list is opt-in for existing users. Overdue and waiting work remains visible, with counts matching filtered data. Keep board transitions, reassignment, close reasons and review rules. A task created through UX-03 appears in the correct queue. Loading, truly empty, filtered empty and failed states differ. | UX-03; frontend B + backend |
| UX-05 | P1 / 2–3 | **A calendar that explains what is shown.** A regression test first proves the label matches the actual list range; upcoming agenda begins at today with a separate past/overdue route. Filter by matter, type and source; restore filters and view. Type labels and timezone are explicit. App-only save and provider-sync failure are distinguishable. Existing task dedup and move-deadline versus block-time confirmation remain. Editing dates works without drag. No automatic deadline shifting. | UX-03/04 data semantics; frontend B |
| UX-06 | P1 / 3–4 | **Clear CRM-to-intake handoff.** Expose links among Clients, Contacts and Intake pipeline without adding a new data silo. New client starts with identity/contact information; optional admin/payment fields expand on demand, consent is never inferred. Surface existing matches with distinguishing details before new creation. Lead conversion previews selected client/matter details, retains history/owner and handles retries without duplicates. Use short named steps only where they reduce a longer flow, show applicable questions, and allow review/edit before conversion. Validate existing interruption/resume behavior and truthful save/submission state; a missing durable draft facility is a separately estimated dependency. Back restores directory filters. Unclassified clients have an explicit filter/recovery path. Load Activity when opened rather than making every related record block the profile. | UX-03/04; frontend A + backend |
| UX-07 | P1 / 2–3 | **Predictable personal views and navigation.** Reuse existing personal navigation and role presets. Offer an everyday preset with the four core destinations prominent; review and apply deliberately, preserve existing custom order. All permitted modules remain discoverable. Use route links for browser new-tab/copy-link behavior. Scope shortcuts so typing in forms cannot start a chat or lose work. Match Customize view, Save/Cancel/Reset and scope labels across pages. Matter/column settings remain explicitly device-local for this release; navigation remains account-synced. | UX-01/02; frontend A |
| UX-08 | P1 / 3–5 | **Complete, honest lists.** Add paging/load-more and scoped totals for both My Matters and All accessible matters, CRM, and bounded task/overdue paths. The personal-matters endpoint needs a pagination/total contract; the all-matters and clients APIs already support paging and should be reused. Search examines all accessible matches for its documented fields. Demonstrate >100 assigned matters, >100 accessible firm matters, >100 clients and >200 tasks with late matches, separately. Loading older results preserves filters and does not duplicate rows. An interrupted fetch cannot replace newer search results. No new cross-tenant access. | UX-01/04/06; backend + frontend integration |
| UX-09 | P0 release gate / 2–3 | **Usability acceptance and rollout.** Repeat the baseline scenarios with equivalent synthetic cases. Resolve failures; check keyboard-only use, 200% zoom, small viewport, restricted role, no data, dense data, failed request and disconnected calendar. Update short user guides. Pilot behind reversible presentation defaults, then expand after acceptance. Rollback restores prior views while preserving all business data and preferences. | All committed stories; QA/product |
| UX-10 | P1 follow-up / 3–5 | **Find anything you are allowed to see.** One search entry point over the permitted corpus (matters, clients and contacts), with tenant/role scoping and explicit result types. Matches the accessible corpus rather than the current page. Loading, empty and failed states differ. No cross-tenant or restricted-matter leakage; denied by default. Document-content search stays with the firm-memory/document owner. | Parity G-24; backend + frontend A |
| UX-11 | P1 follow-up / 2–3 | **Act on many records safely.** Multi-select bulk reassign/status/archive on My Matters and bulk complete/reassign on Tasks, each permission-checked with a confirmation summary of what will change. No partial silent failure; the queue reflects results and counts stay consistent. | Parity G-05, G-12; frontend B + backend |
| UX-12 | P2 validated backlog / 4–6 | **Repeatable task structure — only if validated.** Recurring tasks, dependent/sequential tasks and subtasks, generated deterministically from a matter type or stage and visible in the queue. Do not start until staff sessions show demand; competitor parity alone is not a reason. | Parity G-13; needs UX-00 evidence |
| UX-13 | P2 validated backlog / 3–4 | **Named saved views.** Server-persisted named views for matters, tasks and reports that survive a device change, with clear scope labels and no permission widening. Deferred unless baseline testing shows users rebuild the same view repeatedly. | Parity G-28; backend + frontend A |

Revised estimated implementation: 27–40 engineer-days plus approximately 3–5 days of UX/independent QA effort. UX-01A is provisionally 4–6 engineer-days following review of its authorization and reviewer-policy scope; uncertainty is highest in permission-policy decoupling, server search/paging and existing-record conversion. A new durable draft/resume facility is not included. The parity audit adds two P1 follow-up stories and two validated-backlog items: including the P1 stories (UX-10, UX-11) the extended range is 32–48 engineer-days, while UX-12 and UX-13 stay explicitly outside both ranges until UX-00 evidence justifies them. Scope must be trimmed if discovery exposes backend gaps; do not call untested search or conversion complete to meet a date.

### Sprint proposal

Provisional proposal: two 10-working-day sprints with two engineers, product input and QA support. The upper estimate consumes the full nominal engineering capacity and includes no schedule buffer; re-cut scope or extend the schedule after the UX-01A policy review. Add buffer if staffed by one engineer or if CI/deployment queues delay acceptance.

**Sprint 1 — Daily work becomes easier.** UX-00; UX-01; UX-01A; UX-02; UX-03; UX-04. Sequence the access/reviewer contract before shipping focus-list wording. Aim for a usable vertical slice by the midpoint: find a matter → see next work → add an owned task → return to its queue. Product review after the first slice, before extending the arrangement pattern. UX-02 waits on ownership coordination if the PDF task touches the same matter-page sections.

**Sprint 2 — Continuity and confidence.** UX-05; UX-06; UX-07; UX-08; UX-09. Integrate filtering, honest list completeness, CRM/Intake links and consistent navigation. UX-05 carries the two parity correctness fixes (list-range label and sync-failure truthfulness); UX-07 carries the focus-safe global shortcut. Reserve the final two days for novice-user retests and fixes, not new features. UX-08 moves earlier if real staff are already affected by list caps.

Parallel lanes: A handles matters → CRM/navigation; B handles task composer/queues → calendar; a single designated backend owner sequences shared API/schema work. Parallel research/review is safe; parallel edits to the same page or migration chain are not.

Release each coherent slice only after its acceptance checks; don't merge all stories into one giant PR. The parity follow-ups — global search (UX-10), bulk actions (UX-11) and saved views (UX-13) — and new automation remain a follow-up backlog rather than sprint stretch goals; recurring/dependent tasks (UX-12) require UX-00 evidence first.

## Backend reuse and exact search scope

Current APIs already provide paginated all-matter listing (`page`, `page_size`, `total`) and client listing (`q`, `limit`, `offset`, `total`). Reuse them. All-matter search currently matches matter name only; do not promise client, case-number or attorney matching without an explicit backend extension. Task title search is new work; task listing already has `limit`/`offset`, while the overdue endpoint is unbounded. The personal `/matters/my` endpoint has a separate hard limit of 100 without pagination or total. UX-04 owns the task title-query change; UX-08 owns complete paging/totals and bounded overdue queries. Test tenant/role scope and dense-data query performance. No new schema is assumed for existing matter/client paging; assess indexes for new task search before committing its estimate.

## Usability validation

Use 5 participants initially: 3 paralegals/assistants, 1 attorney, 1 intake staff member, adjusting to the user-selected primary role. Use realistic synthetic cases with duplicate names, one restricted matter, overdue tasks, no-date tasks and a disconnected calendar. Let users work without coaching; record each assistance request. Counterbalance equivalent cases between before/after sessions to reduce practice effects.

| Scenario | Completion criteria | Proposed target (not an observed result) |
| --- | --- | --- |
| Find a matter and its next deadline | Correct matter and date; identify missing/overdue state correctly | 4/5 unassisted within 30 seconds |
| Understand the work signal | Explain what selecting/removing focus does, who can see it, and whether it starts time tracking or changes assignment | 4/5 explain correctly without hover help; nobody assumes it locks the matter or reports live presence |
| Capture a callback from the matter | Correct matter, owner and due date; no duplicate | 4/5 unassisted within 60 seconds |
| Decide what to do today | Find own urgent/due work and open one item | 4/5 unassisted within 30 seconds |
| Arrange the workspace | Move Key dates above Activity, collapse an optional section, restore defaults | 4/5 unassisted within 90 seconds; no lost values |
| Schedule and distinguish a work block from deadline | Create/edit the intended item; actual deadline unchanged when blocking time | All participants preserve the correct deadline; 4/5 unassisted |
| Handle a new inquiry for an existing contact | Reuse the correct contact, set next follow-up, understand conversion into a matter; separately probe interruption/return and whether save/submission state is understood | 4/5 unassisted within 2 minutes; no accidental outreach or duplicate |

Secondary targets: at least 30% lower median completion time versus measured baseline; task ease score median ≥5/7; fewer wrong destinations/assistance requests. This small formative sample finds usability problems; it does not establish statistical prevalence. Any wrong matter, wrong deadline, unintended send, lost input or access leak blocks rollout even if average speed improves.

Collect event name, elapsed duration, role category and success state only if telemetry is added. Do not log names, task text, message bodies, searches or document contents. Manual moderated measurement is sufficient for the first sprint; analytics infrastructure is not a prerequisite.

## Engineering validation and completion

Use focused existing suites and add behavior tests where changes warrant them:

- Matters: MyMattersList, MyMattersActiveSemantics, MatterPortfolioBoard/Triage, MatterListColumns, MatterNavigation, MatterViewGear; browser open/back and responsive checks.
- Focus semantics: real API/database tests for both flag states with tenant separation, own/other assignment, owner/admin exceptions, authorized workspace member and non-member. Focus changes cannot add/remove research access, change default reviewer responsibility or create time/task records. UI copy and counts agree across portfolio/overview/Team. Preserve prior selections and deny unauthorized focus edits.
- Tasks: TasksPage and TaskBoard; both creation entry points; assignment authorization; date-only/time handling; keyboard transitions; same input retained after failure; duplicate-submit protection.
- Calendar: CalendarPage scheduled-events, timezone, task-drag, CalendarTaskDeduplication; accurate agenda range and filters; provider failure alongside local dates.
- CRM/navigation: ClientsPage, ClientDetailPage, IntakePage, navigation/NavigationEditor/Sidebar; identity reuse, restricted results, cancellation, stale responses, URL restoration and role changes.
- API search/paging/conversion: actual HTTP/database tests with synthetic tenant-separated fixtures, boundary sizes and retry assertions. Do not rely exclusively on mocked UI responses.

Before each implementation story: fetch/prune origin, inspect existing branches/worktrees/PRs, compare with current main, confirm ownership and clean state, then create one task branch/worktree from origin/main. Record starting SHA and affected shared files. Do not recover stale branches merely for their unique commits.

Before completion: semantically update from current main; review final diff; focused tests and required CI; correct customer release sequence where applicable; exactly one documentation and release-note option in the PR template plus security/privacy attestation; push/open PR; wait for all required checks and the merge gate at the final head SHA; merge only with fresh green CI; verify exact merge on origin/main; perform authorized staged/production acceptance; remove only the completed clean worktree under retention policy. Use the current deployment skill when deployment is actually requested/undertaken. No deployment is part of this planning pass.

## Decisions for collaboration

1. Confirm the first audience. Proposed: assistants/paralegals, with attorney and reception validation.
2. Confirm the first visible change. Proposed: matter overview hierarchy plus consistent task creation; My Matters columns ship in the same sprint.
3. Confirm customization scope. Proposed: finite section order/collapse and clear presets, with account sync for existing navigation and explicit device-local matter layouts in release one.
4. Confirm staffing/timing. Proposed: two 10-day sprints with two engineers, scope reviewed at the first usable slice.
5. Confirm the focus-list contract. The user supplied the first concrete confusion example: “Working on this.” Proposed: a durable team-visible personal selection, with permissions/reviewer responsibility decoupled. Test comprehension before expanding this signal into live office activity.

These are product tradeoffs for the collaboration the user requested. No extra policy approval is required to continue reversible planning. Implementation follows the agreed scope; this document is not a claim that code has shipped.

## Source map and publication state

See the [competitive research brief](./research/core-ux-competitive-research-2026-09-22.md) for vendor documentation, user-review evidence and limitations, and the [feature-parity audit](./research/core-ux-feature-parity-2026-09-22.md) for the per-capability match/partial/gap register and its source appendix.

Current source anchor examples (immutable audit snapshot):

- [Working toggle and current hint](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/MatterPortfolioPage.jsx#L69)
- [Persisted assignment flag](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/models/matter_assignment.py#L50)
- [Flag update endpoint](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/routers/matters.py#L1635)
- [Research workspace access dependency](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/routers/research_workspaces.py#L50)
- [Document-reviewer fallback ordering](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/services/chat_tools/handlers.py#L664)

- [My Matters list and loading](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/MatterPortfolioPage.jsx#L675)
- [Column configuration](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/components/matters/MatterListColumns.jsx#L132)
- [Matter overview ordering](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/MatterDetailPage.jsx#L1065)
- [Matter task composer](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/components/AddTaskModal.jsx#L19)
- [Task queue state and loading](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/TasksPage.jsx#L1175)
- [Calendar implementation](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/CalendarPage.jsx)
- [Client directory loading](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/ClientsPage.jsx#L140)
- [Navigation preferences](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/components/NavigationEditor.jsx)

This documentation draft starts from origin/main at c4d80b46522e1c2b9436fdc8fae343c9d78db8c9 on branch docs/core-ux-future-state-plan, owned by Plan legal platform UX refinement. It adds this epic, its competitive research companion and the feature-parity audit companion only. No application files, migrations, provider settings or customer release notes change. Runtime tests and production acceptance belong to later implementation PRs; the draft must remain open for collaboration without merging or enabling auto-merge.
