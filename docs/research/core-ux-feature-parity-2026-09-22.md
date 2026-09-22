# Core UX feature-parity audit (draft)

Prepared 22 September 2026 for LawHand's core-workspace refinement epic. Companion to the [competitive research brief](./core-ux-competitive-research-2026-09-22.md) and the [epic plan](../core-ux-future-state-epic-2026-09-22.md).

## Purpose

The competitive brief explains *what good looks like* at other firms. This audit answers the follow-up question the epic previously left open: for each capability across Matters, Tasks, Calendar and CRM/Intake, does LawHand **match, partially support, lack or not-yet-verify** it — and is the gap a **missing capability** or **existing capability users struggle to find**? It is a status register, not a claim of parity.

The prior draft stated plainly that competitive research was complete but a full parity audit was not. This document closes that specific gap. It does not test competitor accounts, does not measure LawHand usability, and does not change any product behaviour.

## Method and confidence

- **LawHand side:** read-only source audit of the branch head `31cdfb07` (base `c4d80b46`), React `frontend/` and FastAPI `backend/`, with `path:line` evidence in the [appendix](#appendix-lawhand-source-evidence). No customer records or provider accounts were used and nothing was saved.
- **Competitor side:** vendor documentation and dated public reviews summarised in the [competitive brief](./core-ux-competitive-research-2026-09-22.md), including the [extended vendor set](./core-ux-competitive-research-2026-09-22.md#extended-vendor-coverage-added-in-the-parity-pass) added for this audit. G2, Capterra, TrustRadius and SoftwareAdvice were 403-blocked to automated fetching; where only search snippets or tiny self-selected samples were available, the cell says so.
- **"Competitor baseline"** means *at least one* product documents the capability. It is not a market-share, quality or pricing ranking. Subscription/integration constraints are noted where the vendor documentation states them.
- No runtime or provider test was run for this document. Backend persistence and live sync were **not** exercised.

### Legend

| Field | Values |
| --- | --- |
| LawHand status | **Supported** (exists and reachable) · **Partial** (exists with a material limitation) · **Absent** (no implementation found) · **Unverified** (code exists, behaviour or scope unconfirmed) · **Correctness** (implemented but does something other than what it claims) |
| Gap type | **Missing capability** · **Discoverability** (exists, users struggle to find/understand) · **Correctness** · **Completeness/scale** · **Policy contract** · **Out of scope / other owner** |
| Priority | **P0** first release · **P1** follow-up release · **P2** validated backlog · **OOS** other owner or explicitly excluded |

A capability can be *Supported* and still carry a *Discoverability* gap: the code working does not prove staff find it. That distinction is the point of this audit.

## 1. Matters

| Capability | LawHand status | Competitor baseline | Gap type | Priority |
| --- | --- | --- | --- | --- |
| Matter home aggregates related work | **Partial** — Overview tab has tasks, signatures, setup and cloud files; contacts and notes live in separate tabs and calendar is only a link (`MatterDetailPage.jsx:818-835`, `:1616`) | Clio, Smokeball, Actionstep: matter is the home for docs/contacts/tasks/calendar | Discoverability | P0 |
| Show/hide and reorder matter sections | **Partial** — show/hide is device-local; no reorder; one collapsible panel not persisted (`MatterViewGear.jsx:6-10`, `MatterDetailPage.jsx:1303-1310`) | Clio customizable matter sections; Smokeball dashboards | Discoverability + Missing capability | P0 |
| Custom fields | **Supported** — full server feature (`configurable_workflows.py:396-440`) | Filevine, Centerbase: custom fields/layouts | — | — |
| Configurable matter types / practice areas | **Partial** — free-text attributes, no `MatterType`/`PracticeArea` entity (`matters.py:770-785`, `:311-313`) | Case Master Pro case types; Filevine custom fields | Missing capability | P2 |
| Column configuration and sort | **Supported** — device-local columns/widths + URL sort (`MatterListColumns.jsx:142-143`, `MatterPortfolioPage.jsx:696-716`) | Smokeball, PracticePanther: save views | — | — |
| Named/saved views (server-persisted) | **Absent** — searched `saved view`; only localStorage columns | Smokeball, PracticePanther saved views | Missing capability | P2 |
| Bulk actions (reassign/status/archive) | **Absent** — searched `bulk`, `selectedIds`, `reassign`; only CSV bulk-create (`MatterCsvImport.test.jsx:35`) | Rocket Matter bulk batching; Lawmatics fewer manual steps | Missing capability | P1 |
| Matter access restrictions / ethical walls | **Partial** — assignment/owner access enforced (`matter_access.py:14,61,98`); explicit wall policy model is read-only, no writer/UI (`firm_memory.py:207-234`) | Filevine, Smokeball role/access controls | Policy contract | OOS |
| Conflict checks | **Supported** — saved, reviewable, matter-linkable, PDF report (`conflict_checks.py:140,202,278`) | Clio, Smokeball conflict checks | — | — |
| Document management | **Partial** — upload, folders, tags, sharing; no general version history (`matter_documents.py:380-750`; `matter_document.py:131,155`) | Clio, NetDocuments versioning | Out of scope / other owner | OOS |
| Client portal visibility of documents | **Supported** — per-document `portal_visible` plus packet grants (`client_portal.py:1933-1938`) | Clio, MyCase portals | — | — |
| E-signature and time tracking from a matter | **Supported** (`esignature.py:490,671`; `matters.py:2365`) | Clio, MyCase e-sign | — | — |
| Activity feed / notes / history | **Supported** — unified timeline (`matters.py:1985-2050`) | Clio central activity | — | — |
| Matter list completeness at scale | **Partial/Correctness** — `/matters/my` hard-caps at 100 with no `total`; portfolio loads `page_size:100` then filters client-side, so >100 matters are silently unreachable (`matters.py:999-1027`; `MatterPortfolioPage.jsx:735,820-838`) | Smokeball, Filevine paging | Completeness/scale | P0 |
| All-matter search fields | **Partial** — `/matters` search matches `matter_name` only (`matters.py:583-584`) | Clio keyword lookup across entities | Completeness/scale | P1 |

## 2. Tasks

| Capability | LawHand status | Competitor baseline | Gap type | Priority |
| --- | --- | --- | --- | --- |
| Create task from a matter with context prefilled | **Partial** — matter prefilled from route; contact never auto-prefilled; matter modal defaults `deadline`, global defaults `general` (`TasksPage.jsx:1451-1457,213`; `AddTaskModal.jsx:22`) | PracticePanther, Smokeball, Filevine, Actionstep prefill matter/contact | Discoverability | P0 |
| One recognizable task composer | **Partial** — two distinct shells (`TasksPage.jsx` inline modal and `components/AddTaskModal.jsx`) | PracticePanther: one predictable form | Discoverability | P0 |
| Due time | **Partial** — backend + matter modal support it; global create omits it and edit clears it (`schemas/task.py:39`; `TasksPage.jsx:282-286,338`) | Smokeball, MyCase scheduling | Missing capability (parity) | P1 |
| Linked contact on task | **Partial** — field exists, picker only in global modal (`TasksPage.jsx:288-294`) | PracticePanther matter/contact link | Missing capability (parity) | P1 |
| Reminders | **Partial** — single `reminder_sent_at` + manual remind; no per-task schedule (`models/task.py:188`; `tasks.py:2589`) | PracticePanther reusable reminders | Missing capability | P2 |
| Listing / queues (My/Firm, board/list, due buckets) | **Supported** (`TasksPage.jsx:1466-1509,1584-1644`) | All listed vendors | — | — |
| Workflow states, transitions, review policy | **Supported** (`task_workflow.py:325-445`; `models/task.py:51-134`) | Filevine, Smokeball | — | — |
| Drag/move and close-with-reason | **Supported** (`TaskBoard.jsx:223,373`; `TasksPage.jsx:877-886`) | Rocket Matter Kanban; Filevine | — | — |
| Task title/text search | **Absent** — no `search/q/title` param or UI; searched (`tasks.py:563-577`) | Smokeball global task view search | Missing capability | P0 |
| Bounded overdue/upcoming queries | **Partial** — `/overdue` and `/upcoming` are unbounded, called unbounded (`tasks.py:490-560`; `TasksPage.jsx:1254`) | — | Completeness/scale | P0 |
| Actionable risk/overdue counters | **Partial** — server counts exist; counters are passive (`TaskBoard.jsx:203-220`) | — | Discoverability | P0 |
| Filter/scroll preservation on return | **Partial** — only view mode persisted; status/priority/type ephemeral (`TasksPage.jsx:1175-1188`) | "Remember where the user was" | Discoverability | P1 |
| Workflow-triggered task generation | **Supported** — approved workflow runs + stage-change automations (`configurable_workflows.py:644-692`; `workflow_automations.py:104`) | Filevine Taskflow; Actionstep; Smokeball | — | — |
| Recurring tasks | **Absent** — no `recurr` in model/router | Filevine repeating tasks; Smokeball workflows | Missing capability | P2 |
| Task dependencies / sequences | **Absent** — no `dependenc`/`predecessor` | Filevine Taskflow dependent auto-tasks | Missing capability | P2 |
| Subtasks / task checklists | **Absent** — checklist exists only as matter-workflow template items (`configurable_workflows.py:550,705`) | Filevine, Smokeball sub-tasks | Missing capability | P2 |
| Bulk complete/reassign | **Absent** — no `bulk` endpoints or multi-select | Rocket Matter batching | Missing capability | P1 |

## 3. Calendar

| Capability | LawHand status | Competitor baseline | Gap type | Priority |
| --- | --- | --- | --- | --- |
| Day / week / month / list + mobile agenda | **Supported** (`CalendarPage.jsx:813,347,388,422,848`) | All listed vendors | — | — |
| List range matches its header label | **Correctness** — list loads start-of-month → end-of-next-month but labels only the pivot month (`CalendarPage.jsx:81-104`) | — | Correctness | P0 |
| Event-type distinction | **Supported** — six types; work block derived from `scheduled_event` + `task_id` (`CalendarPage.jsx:205-262`) | MyCase, Lawmatics event kinds | — | — |
| Task / provider event dedup | **Supported** (`CalendarPage.jsx:285-303`; `calendar_sync.py:41-51,369-371`) | — | — | — |
| Drag-to-reschedule with intent confirmation | **Supported** — "move deadline" vs "block time" modal (`CalendarPage.jsx:557-587,929-1117`) | Outlook-like scheduling (PracticeMaster) | — | — |
| Filter by matter / type / source | **Absent** — no filter UI or URL state; only view persisted (`CalendarPage.jsx:435,528`) | Centerbase calendar filters; Lawmatics | Missing capability | P1 |
| Upcoming agenda default + separate past route | **Partial** — mobile agenda only, flat; no filters (`CalendarPage.jsx:422,838`) | Smokeball Daily Digest | Discoverability | P1 |
| Timezone and date-only handling | **Supported** (`api.js:2286-2292`; `schema/calendar.py:10-15`; tests `CalendarPage.timezone.test.jsx`) | — | — | — |
| Provider sync + reconnect status | **Supported** (`scheduled_events.py:114-121`; `auth.py:2731-2781`; `CalendarPage.jsx:467-477`) | PracticeMaster/Smokeball Outlook integration | — | — |
| Local save vs provider-sync failure surfaced | **Correctness/Partial** — DB records `sync_status`/`sync_error`; UI unconditionally shows "Event created" and never reads them (`CalendarPage.jsx:696`) | — | Correctness | P1 |
| Deadline/docket calculation | **Supported** — aggregated read + alert-only watcher (`calendar.py:119-307`; `scheduler.py:1179-1265`) | Court-rules engines exist elsewhere | — | — |
| Automatic deadline shifting (business days/holidays) | **Absent** — explicitly not claimed (`operating_contract.py:63`) | Some docketing suites | Out of scope | OOS |
| Keyboard edit / reschedule | **Partial** — buttons open on Enter/Space; no keyboard reschedule (`CalendarPage.jsx:316,367,413`) | Accessibility expectation | Discoverability | P1 |
| Bounded calendar read | **Partial** — key dates fetch ≤500 open matters then filter in Python (`calendar.py:179-212`) | — | Completeness/scale | P2 |

## 4. CRM / Intake

| Capability | LawHand status | Competitor baseline | Gap type | Priority |
| --- | --- | --- | --- | --- |
| Clients directory (search, filters, paging) | **Supported API** — `q` across name/org/email/phone/number with `total` (`clients.py:181-240`) | Clio, Lawmatics | — | — |
| Clients/contacts UI paging | **Partial** — UI hardcodes `limit:100`, never sends `offset` (`ClientsPage.jsx:161`; `ContactsPage.jsx:177`) | — | Completeness/scale | P0 |
| Contacts directory | **Partial** — narrower `q` (name/org/email only), no sort (`contacts.py:51-81`) | — | Completeness/scale | P1 |
| Client detail with related matters/activity | **Supported** — but blocking `Promise.all` loads every related contact's comms/tasks before first render (`ClientDetailPage.jsx:65,187,189`) | Clio central client info | Discoverability | P1 |
| Duplicate / existing-record match before create | **Absent at create** — client unique-checks only `client_number`; contact has none; CSV import and conflict-check do match (`clients.py:129-144`; `contacts.py:100-117`) | Gavel existing-contact match; Lawmatics | Missing capability | P1 |
| Intake pipeline stages | **Supported** — 5 visible + `matter_opened`/`declined` (`IntakePage.jsx:15-21`; `intake.py:43-51`) | Clio Grow, Lawmatics pipelines | — | — |
| Pipeline drag-and-drop | **Absent** — click-to-advance button only; searched `onDrag/onDrop` (`IntakePage.jsx:247-260`) | Lawmatics drag-reorder stages | Discoverability | P1 |
| Stage entry/exit automations | **Absent** — `update_lead` only mutates fields; only conversion fires automation (`intake.py:324-325,400-412`) | Lawmatics, Filevine stage triggers | Out of scope / other owner | OOS |
| "Call Intake" vs "Intake" clarity | **Partial** — both exist and work; labels overlap (`App.jsx:427,430`; `IntakeDashboardPage.jsx:975`) | — | Discoverability | P0 |
| Lead conversion to matter | **Supported** — prefilled preview; carries contact/type/role/jurisdiction/etc. (`intake.py:332-412`) | Smokeball, Actionstep, Lawmatics | — | — |
| Conversion retry / duplicate prevention | **Partial** — 409 if already `matter_opened`; no idempotency key (`intake.py:355-359`) | — | Completeness/scale | P1 |
| Pipeline metrics | **Supported** — per-stage counts, funnel, conversion rate (`IntakePage.jsx:293-307`; `reports.py:147-173`) | Lawmatics per-stage value | — | — |
| Per-stage monetary value | **Partial/Absent** — lead `estimated_value` shown; no per-stage value math (`IntakePage.jsx:336`) | Lawmatics Total/Expected Value | Missing capability | P2 |
| Conflict check at intake | **Partial** — status gate + standalone checks exist; no action inside Intake UI (`intake.py:349`; `ConflictChecksPage.jsx`) | Clio, Smokeball conflict checks | Discoverability | P1 |
| Contact vs lead model | **Supported** — separate `Lead` FK to `Contact`; identity unified, no duplicate silo (`models/contact.py:28,211,230`) | — | — | — |
| Communication tracking + durable consent | **Supported** — `CommunicationLog`, `LeadChannelConsent` (`communications.py:115-298`; `conversion_loop.py:235-260`) | — | — | — |
| URL-backed CRM/intake filters | **Absent** — `useState` only; lost on back/reload (`ClientsPage.jsx:150-153`) | "Remember where the user was" | Discoverability | P1 |
| CRM-side portal invite / e-sign | **Absent** — portal/e-sign are matter-scoped only (`client_portal.py:2653`; `esignature.py:108`) | Clio, MyCase send from client | Out of scope / other owner | OOS |

## 5. Navigation, search, reporting

| Capability | LawHand status | Competitor baseline | Gap type | Priority |
| --- | --- | --- | --- | --- |
| Personal navigation reorder/hide | **Supported** — account-synced (`NavigationEditor.jsx:10-16`; `Sidebar.jsx:153-157`) | — | — | — |
| Role presets | **Supported admin-defined**; no user-facing preset picker (`navigation.js:56-61`; `services/navigation.py:26-38`) | — | Discoverability | P1 |
| Sidebar sizing/collapse | **Supported** — device-local (`AppShell.jsx:99,107,305-325`) | — | — | — |
| Consistent "Customize view" vocabulary | **Partial** — four vocabularies, mixed auto-save vs Save/Cancel (`NavigationEditor.jsx:24-41`; `MatterViewGear.jsx:16-20`; `MatterListColumns.jsx:273-312`; `TenantPanelSettings.jsx:16-20`) | — | Discoverability | P0 |
| Global cross-module search | **Absent** — no `/search` route, no header search, no command palette; per-module searches only (`App.jsx:281-509`; `AppShell.jsx:328-375`) | Clio keyword lookup; Lawmatics global search bar | Missing capability | P1 |
| Search/chat shortcut focus safety | **Correctness risk** — global Ctrl/Cmd+N creates a chat with no input guard, so it can fire while typing (`AppShell.jsx:258-268`) | — | Correctness | P0 |
| Preference scope messaging | **Partial** — nav/columns labelled; calendar view and sidebar width unlabelled (`NavigationEditor.jsx:25`; `MatterListColumns.jsx:281`; `CalendarPage.jsx:435`) | — | Discoverability | P1 |
| Mobile/responsive casework | **Supported partial** — mobile agenda, 44px targets, bottom tabs, e2e at 360/390 (`CalendarPage.jsx:422`; `MatterDetailPage.jsx:1002-1026`; `AppShell.jsx:391-417`) | — | — | — |
| Reporting/dashboards | **Supported** — overview/realization/WIP/A-R aging + CSV (`ReportsPage.jsx:344-600`) | — | — | — |
| Saved report views / scheduled delivery | **Absent** — active tab ephemeral; searched `saved_report` (`ReportsPage.jsx:356`) | PracticePanther scheduled reports | Missing capability | P2 |
| Record deep-link / open-in-new-tab | **Partial** — matters/chat/portal routes support it; explicit copy-link only for invite and firm-memory result | — | Discoverability | P2 |

## Gap register

Priorities here feed the epic's sprint scope; they are not a commitment. "Story" maps to the epic's delivery backlog. New stories UX-10–UX-13 are introduced by this audit.

| ID | Gap | Domain | Type | Priority | Acceptance criteria (proposed) | Story |
| --- | --- | --- | --- | --- | --- | --- |
| G-01 | Everyday matter list buries deadline/status; "Needs attention" is text, not a queue | Matters | Discoverability | P0 | At 1366×768 and 1440×900 the default view shows matter/client, next deadline, status and owner without horizontal scroll; Needs attention opens the filtered records; scope counts name their scope | UX-01 |
| G-02 | Matter overview shows setup/forms before work | Matters | Discoverability | P0 | Identity, alerts and task/date entry appear before setup forms; no empty signature/message form in the everyday view; required alerts stay visible when sections collapse | UX-02 |
| G-03 | My Matters silently unreachable beyond 100 | Matters | Completeness/scale | P0 | `/matters/my` supports paging and returns `total`; >100 assigned matters are all reachable; search/filter state survives Back | UX-08 |
| G-04 | `/matters` search matches name only | Matters | Completeness/scale | P1 | Search covers client, case-number and attorney for the documented corpus, or the UI states the exact fields searched | UX-08 |
| G-05 | No bulk actions on matters | Matters | Missing capability | P1 | Multi-select supports reassign/status/archive with a confirmation summary; permission-checked; no partial silent failure | UX-11 |
| G-06 | No configurable matter types/practice areas | Matters | Missing capability | P2 | Matter type is a firm-configurable list, not free text; existing values migrate without loss | Backlog |
| G-07 | Ethical-wall configuration has no writer/UI | Matters | Policy contract | OOS | Explicit authorization policy and audited path; security owner | OOS |
| G-08 | No document version history | Matters | Out of scope | OOS | Belongs to document-automation owner | OOS |
| G-09 | Two task forms; inconsistent defaults and missing contact/due-time | Tasks | Discoverability | P0 | One composer contract from global Tasks, a matter, or a matter-filtered queue; context visibly prefilled; general Task by default unless the entry says Deadline; due time consistent; input retained on failure; no duplicate on resubmit | UX-03 |
| G-10 | No task title search; overdue endpoint unbounded | Tasks | Missing capability + scale | P0 | Server-side title search for the accessible corpus; overdue/upcoming bounded with paging; counts match filtered data; no cross-tenant access | UX-04 |
| G-11 | Risk counters passive; filters not preserved | Tasks | Discoverability | P0/P1 | Counters open the filtered queue; view/scope/filters/page and return position preserved on Back | UX-04 |
| G-12 | No bulk complete/reassign | Tasks | Missing capability | P1 | Multi-select complete/reassign with confirmation and authorization; no duplicate transitions | UX-11 |
| G-13 | No recurring tasks, dependencies or subtasks | Tasks | Missing capability | P2 | Opt-in after staff testing; recurring and dependent tasks generate deterministically and are visible in the queue | Backlog |
| G-14 | Calendar list header under-reports its range | Calendar | Correctness | P0 | Regression test proves the label matches the actual loaded list range before any redesign | UX-05 |
| G-15 | Calendar has no matter/type/source filters | Calendar | Missing capability | P1 | Compact filter row by matter, event kind and source where the backend supports scope; filters restore on Back | UX-05 |
| G-16 | Local save shown as success when provider sync failed | Calendar | Correctness | P1 | A local-only save is labelled as local; `sync_status="error"` surfaces an actionable banner; no "created" claim implies external sync | UX-05 |
| G-17 | No keyboard reschedule path | Calendar | Discoverability | P1 | Editing/rescheduling works without drag via keyboard; focus returns sensibly | UX-05 |
| G-18 | CRM/Intake labels and cross-links unclear | CRM/Intake | Discoverability | P0 | Clients, Contacts and Intake are cross-linked; "Intake pipeline" vs "Call log & intake" terminology validated with staff; no new data silo | UX-06 |
| G-19 | No duplicate/existing-record match before create | CRM/Intake | Missing capability | P1 | Creating a client/contact surfaces matching existing records with distinguishing details before commit; import matching reused | UX-06 |
| G-20 | Intake has no drag-and-drop or in-UI conflict check | CRM/Intake | Discoverability | P1 | Stage advance via drag or button; conflict-check action available where the gate applies; no drag silently implies engagement | UX-06 |
| G-21 | CRM/intake filters lost on Back | CRM/Intake | Discoverability | P1 | Directory and pipeline filters are URL-backed and restore on Back/reload | UX-06 |
| G-22 | Client detail blocks first render on all activity | CRM/Intake | Discoverability | P1 | Activity loads when opened; unrelated records do not block the profile | UX-06 |
| G-23 | Contacts UI paging hardcoded; contacts search narrow | CRM/Intake | Completeness/scale | P1 | Paging sends `offset`; contacts search matches documented fields; >100 records reachable | UX-08 |
| G-24 | No global cross-module search | Navigation | Missing capability | P1 | One search entry point over the permitted corpus (matters, clients, contacts) with tenant/role scoping and tests; document-content search stays with the firm-memory/document owner | UX-10 |
| G-25 | Chat shortcut can fire mid-form | Navigation | Correctness | P0 | Global shortcut does not trigger while focus is in a form field; no work is lost | UX-07 |
| G-26 | Four "Customize" vocabularies; unlabelled scopes | Navigation | Discoverability | P0/P1 | One vocabulary and Save/Cancel/Reset pattern; each surface states account-synced vs device-local | UX-07 |
| G-27 | No user-facing everyday preset | Navigation | Discoverability | P1 | Opt-in preset surfaced for review before apply; existing custom order and all permitted modules preserved; easy reset | UX-07 |
| G-28 | No saved views or saved report views | Navigation | Missing capability | P2 | Server-persisted named views for matters/tasks/reports; survives device change | UX-13 |
| G-29 | Consent/monetary intake metrics partial | CRM/Intake | Missing capability | P2 | Per-stage expected/total value from historical conversion, or the metric is removed from the UI | Backlog |

## Scope implications for the epic

This audit **confirms** the epic's existing P0 stories (UX-01 to UX-04, UX-09) and adds evidence for the correctness fixes already implied (G-14, G-16, G-25). It also **adds two P1 stories** and **two P2 backlog items**:

- **UX-10 — Global cross-module search (P1, 3–5 days).** Currently absent; competitor baseline (Clio keyword lookup, Lawmatics global search bar) suggests high discoverability value. This is a follow-up release, not part of the two-sprint plan, unless staff sessions show search is a blocking failure.
- **UX-11 — Bulk actions for matters and tasks (P1, 2–3 days).** Currently absent; competitor baseline (Rocket Matter batching) and the discovery that Rocket Matter's documented friction was per-row latency.
- **UX-12 — Recurring tasks, dependencies and subtasks (P2, 4–6 days).** Absent; strong competitor baseline (Filevine Taskflow, Actionstep, Smokeball). Validate demand before scheduling; do not assume parity requires it.
- **UX-13 — Saved views and saved report views (P2, 3–4 days).** Absent; Smokeball/PracticePanther baseline. Validated backlog, not a sprint goal.

The audit also records what should **not** expand this epic: document version history and prepared-document drafts (document-automation owner), stage-entry automation and deadline auto-shifting (excluded automation/docket scope), ethical-wall policy authoring (security owner), and CRM-side portal/e-sign actions (document/client-portal owner).

## Out of scope and other owners

| Item | Owner / disposition |
| --- | --- |
| Document questionnaires, preparation, drafts, generation, versioning | "Validate PDF engine release" (PR #580) |
| Stage-entry/exit automation engine | Excluded; separate future product |
| Automatic court-rule / holiday deadline shifting | Excluded; explicitly not claimed today |
| Ethical-wall / restricted-matter policy authoring | Security/authorization owner; policy change, not a UI story |
| CRM-side client-portal invite and send-for-signature | Document/client-portal owner |

## Appendix: LawHand source evidence

Read-only audit of `31cdfb07` (base `c4d80b46`). Representative anchors, not exhaustive:

- [Matter overview sections](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/MatterDetailPage.jsx#L818)
- [Matter view gear / show-hide](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/components/MatterViewGear.jsx#L6)
- [Matter list columns](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/components/matters/MatterListColumns.jsx#L142)
- [Personal matters endpoint (limit 100)](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/routers/matters.py#L999)
- [All-matters search, name only](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/routers/matters.py#L583)
- [Task list query params (no search)](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/routers/tasks.py#L563)
- [Unbounded overdue endpoint](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/routers/tasks.py#L490)
- [Calendar list range vs label](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/CalendarPage.jsx#L81)
- [Calendar sync status not surfaced](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/CalendarPage.jsx#L696)
- [Clients endpoint with total](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/backend/app/routers/clients.py#L181)
- [Intake pipeline stages](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/pages/IntakePage.jsx#L15)
- [Global chat shortcut with no focus guard](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/components/AppShell.jsx#L258)
- [Navigation editor](https://github.com/mattpainter701/lawhand/blob/c4d80b46522e1c2b9436fdc8fae343c9d78db8c9/frontend/src/components/NavigationEditor.jsx#L10)

Evidence status: source read, no application tests run. Every "Absent" claim reflects a named search recorded in the audit method; it is not proof of impossibility, only that no implementation was found at this revision.
