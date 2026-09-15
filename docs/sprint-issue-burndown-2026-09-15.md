# Sprint — open-issue burndown, 15–26 Sep 2026

> **Status: the committed band is delivered.** #503, #502, #488, #492, #506 and
> #484 are implemented with tests on `claude/sprint-planning-issues-6vmf80`.
> The decision gate below was not held; each gated item shipped on its
> recommended default, noted per item. Two corrections to this plan, kept
> visible rather than edited away:
>
> - **A-2 needed a migration.** The Definition of Done said it added none.
>   The failure counter had nowhere to live, so migration `187` takes the head
>   from `186_billing_parity` and both hardcoded head expectations move with it.
> - **C-1's save-400 did not reproduce.** The error-contract work landed and
>   explains the 502 and the empty message; the 400 is documented on the issue
>   rather than guessed at. See the item for what was ruled out.
>
> **#504 (stretch) was not taken**, and its blocker is unchanged: the manifest
> still has no provenance field, so nothing in the repository says which court
> form each duplicate-titled variant is.
>
> **Update — the three remaining issues are delivered.** #487, #489 and the
> open part of #504 shipped together on `claude/quirky-noether-j65hl0`, each on
> the recommended default recorded in the decision table below, so the "next
> sprint" section is closed out:
>
> - **#487** — per-conversation columns (migration `190`), hydrate on open,
>   `PATCH` on toggle; tenant `include_public_case_law` narrows only, with the
>   restriction shown in the chat switch. Precedence is written down in
>   `docs/assistant-conversation-settings.md`.
> - **#489** — one access definition
>   (`app/services/portal_document_access.py`) drives the overview count, its
>   breakdown, the portal tab's grouping and the staff badge, with a
>   count-parity test. The open question is answered: a signing grant *does*
>   widen visibility beyond the shared set, by design; the defect was the
>   "Private" label. See `docs/client-document-visibility.md`.
> - **#504** — provenance is now a documented manifest field carried by the
>   build script and stored on the catalog (migration `191`). It is **not
>   backfilled**: the import library's `catalog.json` is not in this
>   repository, so the values arrive on the next rebuild against that source.
>   Until then the library numbers same-titled forms by field count and says
>   the source was not recorded, rather than inventing an edition. The data
>   decision — label the variants as editions, or curate the catalog down —
>   stays open for a human, which is what D-3 said it should be.

Planning artifact for the nine issues open on `mattpainter701/lawhand` as of
2026-09-14 (`main` at `667f97c`, release `2026.09.13.15`). Each item below was
checked against the tree, not taken from the issue text alone — two issues are
already part-shipped and are re-scoped here accordingly.

**Sprint goal.** Every artifact the firm relies on as evidence is accurate, every
silent failure on the filing and deadline paths becomes a visible signal, and the
platform SMS sender can be configured without reading the browser console.

**Capacity assumed.** One full-time engineer across ten working days, plus review.
Scale the cut line proportionally for more hands — the workstreams are ordered so
that cutting from the bottom never leaves a half-finished path.

**Non-goals.** No work from `TASKS.md` (see [Competing backlog](#competing-backlog)).
No catalog content changes. No rewrite of the calendar merge model beyond what
#484 needs.

---

## Verified state changes since the issues were filed

Two issues are narrower than they read. Both should be re-scoped on GitHub before
the sprint starts, so the burndown reflects real remaining work.

- **#504 — sample library.** PR #505 (`6dc179e`) shipped points 2, 3 and 4: free-text
  search combining with the Type/Jurisdiction filters, collapsible type groups with
  counts and Expand/Collapse all, and `title` tooltips on truncated titles
  (`SampleLibraryCard.jsx:176-181, 230`), with tests. **Only point 1 remains** —
  disambiguating the duplicate-titled variants — and it is a data problem, not a UI
  one (see D-3).
- **#488 — evidence certificate.** The blank-field half is **already fixed** on `main`:
  `filled_field_count` (`backend/app/services/esign/certificate.py:38-54`) excludes
  empty strings and unchecked boxes, pinned by
  `test_filled_field_count_excludes_blanks_and_unchecked_boxes`
  (`backend/tests/test_esign_service.py:129`). **Only the IP half remains** — and it
  is now well-understood (see A-1).

---

## Decision gate — day 1

Four issues are blocked on a product decision, not on engineering. Three already
carry a "Decision needed" comment that has been waiting since 13 Sep. Resolving
these in one sitting on day 1 is the single highest-leverage hour in the sprint;
**#492 is inside the sprint and stalls without it.**

| Issue | Question | Recommended default |
|---|---|---|
| **#492** | Retry-exhaustion trigger (N attempts vs elapsed time), and who owns a failed filing | After 12 consecutive failures spanning ≥1 hour, raise one assigned matter follow-up task to the signing-request creator; keep retrying; resolve the task when filing succeeds |
| **#489** | Does "shared with the client" count firm-shared documents only, or everything the client can open (incl. packet grants)? | Drive the overview from the existing `_readable_documents(ctx)` union, exclude client uploads from the "Shared by your firm" figure, add a distinct grant-derived-access marker on the staff tab |
| **#487** | Per-conversation storage vs per-user default; does tenant policy override a stored preference? | Per-conversation columns; hydrate on open; tenant `include_public_case_law` narrows only, with a visible "limited by firm policy" note |
| **#504** | Are the duplicate-titled forms distinct editions, or is the catalog curated down? | Neither yet — the manifest has no provenance to decide from (see D-3) |

Only **#492** blocks sprint work. #489 and #487 are deliberately **out of this
sprint** (see [Next sprint](#next-sprint)); their answers are wanted now so that
sprint can start cold.

---

## Workstream A — Evidence and failure signalling (P0)

**Why first.** These are the two places where LawHand is silently wrong about
something a firm would rely on in a dispute: what an evidence certificate attests,
and whether anyone learns that a signed document never reached storage.

### A-1. #488 — Evidence certificate records an internal proxy IP (1.5d)

The issue's "hard limit" — *do not change evidence attribution before the trusted
proxy configuration is confirmed* — is satisfiable, and the gap is now located:

- nginx **already** resolves the real client. `nginx/nginx.conf:238-247` sets
  `set_real_ip_from` for the Cloudflare ranges plus the Docker bridge
  (`172.16.0.0/12`, `10.0.0.0/8`), `real_ip_header X-Forwarded-For`, and
  `real_ip_recursive on`, and every proxied location forwards
  `$proxy_add_x_forwarded_for`.
- The application **discards it**. The signing path reads `request.client.host`
  (`backend/app/routers/esignature.py:997, 1129, 1171`), which is the nginx peer.
- **No uvicorn invocation anywhere passes `--proxy-headers`/`--forwarded-allow-ips`**
  — checked across `backend/Dockerfile:74`, `docker-compose.yml:183`,
  `docker-compose.dev1.yml:68`, `docker-compose.cube-m.yml:69`,
  `docker-compose.hypervisor.yml:239,363`, `docker-compose.override.yml:14`.
  So `request.client.host` is the proxy address by construction, in every
  environment. That is the whole defect.

Tasks:
- [x] Resolve the signer address through an explicit trusted-proxy allowlist,
      preferring an application-level helper over blanket `--proxy-headers` so the
      trusted set is expressed in one reviewable place and covers all six compose
      files at once.
- [x] Where the address cannot be attributed to a client, record that fact and have
      the certificate say so plainly rather than printing an infrastructure address.
- [x] Regression coverage pinning the address source: trusted proxy → client address;
      untrusted or absent header → "not attributable", never a silent proxy IP.
- [x] Do **not** rewrite certificates already issued (issue hard limit).

Out of scope: the field-count half, already fixed and tested on `main`.

### A-2. #492 — No escalation when filing retries are exhausted (2d) — *gated on the day-1 decision*

`retry_pending_completions` retries every 5 minutes with **no attempt cap**; a
failure writes `completion_error`, one passive `MatterEvent` and a staff banner.
A permanently unreachable store therefore means silent non-filing.

Tasks:
- [x] Add the attempt counter (none exists today) and the terminal exhausted state.
- [x] On exhaustion, raise one assigned follow-up task via the existing
      `ensure_followup_task` + `notify_task_created` primitives — once, not per retry.
- [x] Keep retrying after escalation; resolve the task when filing finally succeeds.
- [x] Document the retry contract (attempts, window, terminal behaviour) — the issue
      requires the specification, not just the code.
- [x] Regression test that drives a filing to exhaustion and asserts the escalation
      exists, is assigned, and is not duplicated on further retries.

---

## Workstream B — Deadlines reach the lawyer's calendar (P0)

### B-1. #484 — Outlook task push drops the due time and duplicates the task (3d)

Largest item in the sprint and the one most likely to overrun; it is sequenced after
A so a slip cuts into the stretch band, not into evidence work. The 13 Sep
verification comment confirms release `.14` fixed the *matter key-date* path, not
this one.

Tasks:
- [x] Thread `due_time` through `push_task_to_calendars`
      (`backend/app/services/task_notifications.py:138`), which today passes
      `due_date` only and returns early on a missing date.
- [x] Build a timezone-aware timed event in both providers instead of forcing all-day
      (`microsoft_calendar.py` `"isAllDay": True`; `google_calendar.py`
      `"start"/"end": {"date": ...}`). A task with no saved time keeps all-day.
- [x] Surface the existing provider identity (Microsoft `clarity_task_id`, Google
      `privateExtendedProperty`) on the calendar **read** path so
      `mergeCalendarEvents` (`frontend/src/pages/CalendarPage.jsx:223`) collapses the
      synced copy against the LawHand task instead of rendering both.
- [x] Make both entries navigate to the same task: provider entries carry `url: null`
      today and the local task links to `/tasks`, not `/tasks/{id}`.
- [x] Regression coverage: timed propagation across a non-UTC timezone, and a repeat
      sync that produces no second entry.

---

## Workstream C — Platform SMS operability (P1)

### C-1. #506 — Twilio shared sender fails with 400/502 and says nothing useful (2d)

Reading the code explains the 502 and the empty error, and leaves one unknown.

**Explained — the 502 and the useless message.** `send_platform_test_sms`
(`backend/app/services/platform_sms.py:281-298`) maps *any* non-2xx Twilio response
to a **502** `platform_sms_provider_rejected`. A Twilio rejection of the reporter's
input — the `VA…` Verify Service SID pasted where an `MG…` Messaging Service SID
belongs, and the placeholder `+15551234567` sender — is a caller-configuration
error, but we return it as a server error. Cloudflare then replaces our 502 body
with its own origin-error page, so the structured `detail` the API did produce never
reaches the UI. That is exactly the reported symptom, and it makes the fix concrete:
**4xx for provider-rejected configuration, 5xx only for genuine transport failure.**

**Unknown — the 400 on save.** Not reproduced from the tree. The two 400 paths in
`upsert_platform_sms_provider` (`:159-173`) are both "incomplete config", and the
"leave blank to keep" flow is handled correctly by the UI, which omits blank fields
rather than sending `""` (`PlatformPage.jsx:373-376`) — so the obvious wipe-the-token
hypothesis is **wrong**. The reporter's console also names `POST` on a `PUT`-only
route, so the labels may be imprecise. This needs a reproduction before a fix.

Tasks:
- [~] Reproduce the save 400 against a real operator session; fix or close out with
      the finding. **Timebox to 0.5d** — if it does not reproduce, the error-surfacing
      work below makes the next report self-diagnosing.
      **Outcome: did not reproduce.** Every 400 path in the save requires a field
      the report says was set; the console names `POST` on a `PUT`-only route; and
      the UI already rendered `detail`, so a genuine 400 would have been visible.
      Most likely those were earlier attempts before the token was entered. Left
      as a note on the issue rather than a guessed fix.
- [x] Validate SID shapes on save: `account_sid` `AC…`, `messaging_service_sid` `MG…`,
      rejecting a Verify (`VA…`) SID by name rather than letting Twilio fail later.
- [x] Reclassify Twilio 4xx rejections as caller errors carrying Twilio's own message
      and code; keep 502 for timeout/transport only.
- [x] Confirm the UI renders `detail` for every status the API can now return, and
      that no response body large enough or slow enough to be replaced by Cloudflare
      remains on this path.
- [x] Tests for each: wrong SID type, unusable from-number, Twilio auth failure,
      transport timeout.

---

## Workstream D — My Matters says what it means (P2)

Cheapest real wins in the sprint. Scheduled to run alongside the day-1 decision gate
so the sprint ships something on day 1.

### D-1. #503 — `View →` is decorative (0.5d)

`MatterPortfolioPage.jsx:377` renders a styled `<span>` with no `href`, `onClick`, or
role, inside a row (`:342`) that has no handler either. It promises an action, does
nothing, and is not keyboard-operable.

- [x] Make the affordance a real link to `/matters/{id}` (or remove it); if kept, it —
      or the whole row — must be reachable by keyboard.
- [x] Regression test asserting the row's View affordance navigates.

### D-2. #502 — "Active" means three different things (1d)

Status filter tab (`:174-180`), `StatusBadge` (`:59-73`), and a per-row toggle
(`:259-271`, `:361-375`) all read "Active". The toggle only flips
`MatterAssignment.is_active_working` for the signed-in user.

- [x] Rename the control for what it does ("Working on this" / "Stop working").
- [x] Make the filter tab, the badge, and the assignment flag visually distinct.
- [x] Regression coverage pinning the label and confirming it patches the assignment,
      not the matter status.

### D-3. #504 — duplicate-titled variants (stretch, 1d) — *blocked on provenance*

Point 1 is all that remains, and it **cannot be decided from the repository**:
`backend/seed/sample_templates/manifest.json` carries `category`, `description`,
`field_count`, `filename`, `jurisdictions`, `sha256`, `size_bytes`, `slug`, `title`
— and **no source URL or edition**. The ten affected files are genuinely distinct
(e.g. `nd-divorce` 9 fields / 344,984 bytes, `nd-divorce-2` 18 / 202,367,
`nd-divorce-3` 91 / 1,540,490), so they cannot be mechanically de-duplicated, and
nothing in the tree says which court form each one is.

The useful sprint deliverable is therefore **not** a label — it is provenance:

- [x] Add a source/edition field to the manifest schema and backfill it from the
      import source, so a human can then decide per variant. *Schema, build
      script, catalog column and API shipped; the backfill needs the import
      library, which is not in this repository, so the values land on the next
      rebuild against it.*
- [ ] Only after that: distinguishing labels, or a curated catalog. *Still a
      human's data decision. Meanwhile the library shows the differences it
      actually has and says the source was not recorded.*

Take this only if A, B and C are done. Otherwise it moves to next sprint with the
provenance question answered out-of-band.

---

## Sequencing and cut line

| Day | Work |
|---|---|
| 1 | Decision gate (30–60 min) · D-1 · start D-2 |
| 2 | D-2 · start A-1 |
| 3–4 | A-1 |
| 4–6 | A-2 |
| 6–8 | C-1 (repro timeboxed to 0.5d) |
| 8–10 | B-1 |
| stretch | D-3 |

**Committed:** #503, #502, #488, #492, #506, #484 — ≈10 days.
**Stretch:** #504 (provenance only).
**Explicitly out:** #487, #489.

**Cut order if the sprint slips**, bottom-up: D-3, then C-1's reproduction timebox
(keep the error-contract fix — it is what makes the next report diagnosable), then
B-1's navigation sub-task. **A-1 and A-2 do not get cut**; they are the evidence and
silent-data-loss items and are why the sprint is shaped this way.

## Definition of done

Beyond each issue's own "Done when":

- Diff coverage ≥ 80% per `AGENTS.md` §2 — budgeted into each estimate, not bolted on.
- Release notes regenerated and `scripts/generate_release_notes.py --check` passing.
- A-2 adds no migration; **if #487 is pulled forward, its migration takes the next
  head number centrally** per `AGENTS.md` §1 — do not let two branches claim one head.
- Re-scope #504 and #488 on GitHub to their remaining work before the sprint starts.

---

## Next sprint — *delivered, see the status note above*

Both were decision-gated when this was written; both needed a migration or a
data-model definition, and both are consistency problems rather than
incorrect-artifact problems, which is why they sat behind Workstream A. Both
shipped on their recommended defaults.

- **#489** — shared-document counts disagree across overview, documents tab and
  signing grants. A per-recipient signing grant cannot be represented by the single
  `portal_visible` bit; the staff tab labels a grant-readable document "Private".
  Needs the definition decision, then a count-parity test.
- **#487** — conversation tier and public-case-law preference reset on reopen.
  `use_premium` / `include_public` are per-message request fields with no columns and
  no migration; `ChatPage` holds them in `useState` and never reads them back. Needs
  the scope and precedence decisions, then an additive migration, a backend
  round-trip, and a fail-closed tier test.

## Competing backlog

This sprint is deliberately issue-driven and takes **nothing** from `TASKS.md`. One
item there deserves a conscious decision rather than silent deferral: the P1 entry
for `get_overdue_tasks` (`backend/app/routers/tasks.py:490`), which has no
`limit`/`offset` and is called with none from `TasksPage.jsx:1253` — returning every
overdue task in the firm, serialized in a Python loop into unvirtualized DOM. It is
described there as *"the one most likely to actually take a page down rather than
mislead"*, and its sibling `list_tasks` already has the `limit: 100, offset: 0` shape
to copy.

At roughly half a day it is the cheapest severe item in either backlog. If capacity
appears, take it ahead of the D-3 stretch.
