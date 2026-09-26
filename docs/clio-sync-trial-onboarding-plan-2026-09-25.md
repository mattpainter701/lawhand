# Clio sync for trial onboarding — plan

Status: **proposal, no code yet**. Date: 2026-09-25.

## Why

A prospective firm runs on Clio Manage and wants to *try* LawHand before
switching. Getting them to feature parity will take a few months, so a one-shot
import is the wrong tool: the data would be stale within days and the firm
would be double-entering work in both systems for the whole trial.

What they need is a **continuous mirror** of Clio in LawHand while Clio stays the
system of record, followed by a **per-area cutover** once LawHand covers that
area for them. This plan describes that and how it builds on what we already
have.

## Recommendation in one paragraph

Build a **one-way Clio → LawHand sync** (backfill, then incremental polling) on
top of the existing provider-neutral import tables, with Clio-owned fields
read-only in LawHand and LawHand-native work (AI output, workflows, drafts,
firm memory) layered on top. Do **not** build general two-way sync. If the trial
users need their LawHand work to reach Clio, add a narrow **append-only outbox**
(new time entries, notes, documents created in LawHand are pushed to Clio as
creates; nothing Clio owns is ever updated from LawHand). End the trial with a
**cutover per entity area** that flips ownership to LawHand and stops the pull
for that area.

## What already exists (reuse, don't rebuild)

| Piece | Where | How the sync uses it |
|---|---|---|
| Provider-neutral staging: connection, run, raw rows, record links | `backend/app/models/external_import.py`, migration `062_external_imports.py` | Clio is a new `provider="clio"`. `ExternalRecordLink` is the idempotency key for every mirrored record. |
| Reconcile → approve (report hash) → promote → rollback lifecycle | `backend/app/routers/external_imports.py` | The initial Clio backfill goes through the same human-approved gate as Tabs3. |
| `accounting_mode` on the connection (`tabs3_reference`, `qbo`, `clarity_native`) | `ExternalSystemConnection` | Add `clio_reference`: financials are mirrored for reference, never billed from LawHand. |
| CSV matter importer that suppresses client sends / automations for historical matters | `backend/app/routers/matter_csv_imports.py` | Same rule for synced records — see *Automation safety*. |
| Clio CSV history → workflow synthesis | `backend/app/routers/workflow_synthesis.py` (`provider: "clio"`), `services/workflow_synthesis.py` | Once tasks are synced via API, synthesis can read them directly instead of a CSV upload. This is the "day-one configuration from the firm's real past" pitch in `docs/capability-first-automation-scaling-plan-2026-09-08.md`. |
| Per-tenant BYO OAuth app | `backend/app/models/tenant_oauth_app.py` | Trial can run on a Clio developer app registered by (or for) the firm, avoiding Clio App Directory review up front. |
| Encrypted access/refresh tokens | `backend/app/models/qbo.py` (Fernet pattern from `TenantCredential`) | Same pattern for the Clio grant. |
| Durable, retryable tenant jobs | `backend/app/models/durable_job.py`, `services/durable_job_worker.py`, `durable_job_handlers.py` | Backfill pages, incremental polls, document downloads and outbox pushes are job kinds. |
| Integration health and sync-run history | `backend/app/models/integration_sync_run.py`, `services/integration_observability.py` | Admin sees last sync, lag, failures, revoked grant — same surface as other integrations. |
| Outbound sync pattern with retry/backoff | `backend/app/services/qbo_sync.py` | Template for the optional outbox. |

The gap today: `promote_import_run` hard-codes Tabs3 table names (`CLIENT`,
`MATTER`, `CASE`) and only promotes contacts and matters. The first engineering
step is to pull that into provider adapters so Clio (and Tabs3) share one
mapping path.

## Clio API facts that shape the design

Confirmed from Clio's published docs:

- **Rate limit is per access token**, 50 requests/minute during peak hours, with
  `X-RateLimit-Limit` / `-Remaining` / `-Reset` headers and `429` on excess.
  One firm = one token, so the sync budget is ~50 rpm at peak and the scheduler
  must respect those headers, not a fixed interval.
- **Webhooks** are signed with HMAC-SHA256 of the body (`X-Hook-Signature`),
  default to a 3-day expiry and max out at **31 days**, so they need a renewal job.

To verify in the Phase 0 spike (from memory of the v4 API, not re-checked here):

- Index endpoints accept `updated_since` and cursor paging (`order=id(asc)`,
  `limit` up to 200); only requested `fields=` are returned, so every mapper
  must ask for its fields explicitly.
- Regional hosts (US / CA / EU / AU) — the connection must store the firm's region.
- The API only sees what the **authorizing Clio user** can see. The grant must
  come from a Clio admin, or matters will silently go missing.
- Deletions are visible only via webhook `deleted` events or by diffing the full
  ID list; `updated_since` won't show them.

## Architecture

```
Clio API ──(OAuth token, rate-limited client)──► ClioAdapter
                                                   │  fetch pages (fields=…, updated_since=…)
                                                   ▼
                              external_raw_rows / source snapshot (checksum per record)
                                                   │  unchanged checksum → skip
                                                   ▼
                              provider-neutral mappers  ──► Contact / Matter / Task / …
                                                   │
                                                   ▼
                              external_record_links (provenance, idempotency, ownership)
```

### 1. Connection

- `ExternalSystemConnection(provider="clio", external_key=<clio account id>,
  accounting_mode="clio_reference")`, with `source_metadata` holding region,
  authorizing Clio user, scopes and sync scope filters.
- OAuth tokens stored encrypted (QBO pattern). Refresh failures and revocation
  flow into `integration_observability` so the admin sees "Clio disconnected",
  not stale data that looks current.
- Request read-only scopes unless the outbox (Phase 4) is enabled.

### 2. Sync scope filter

Let the firm trial on a slice — one practice area, one office, or a named set of
responsible attorneys — plus a matter-status filter (open only, or open + closed
in the last N years). This limits volume, rate-limit pressure and blast radius,
and matches how firms actually trial. Contacts are pulled when referenced by an
in-scope matter, not wholesale.

### 3. Backfill (initial load)

A backfill is an `ExternalImportRun(provider="clio")`. It pages each entity into
`external_raw_rows`, then goes through the **existing** reconcile → approve →
promote gate so a person signs off on counts before anything canonical exists.
Order: users → contacts → matters (+ practice area, custom fields) →
relationships → tasks → calendar entries → notes → document metadata →
reference financials.

User mapping: Clio users map to LawHand users by email; unmapped users become an
explicit review item, never an auto-created account.

### 4. Incremental sync

- Durable job per connection on a schedule (start at 15 min; tighten if the rate
  budget allows). Per entity, keep a high-water mark of `updated_at` and query
  `updated_since = watermark − overlap` (overlap absorbs clock skew; the checksum
  makes re-reads cheap).
- Unchanged checksum → no write. Changed → re-run the mapper and update the
  linked record's **Clio-owned fields only**.
- Deletions: weekly full-ID sweep per entity (and webhook `deleted` events once
  Phase 2b lands). A missing source record marks the link `source_deleted` and
  surfaces it for review; we never hard-delete in LawHand on a sync signal.
- Incremental changes apply automatically once the backfill was approved; a
  change that breaks a mapping invariant (e.g. a matter moved to a client we
  can't resolve) goes to a review queue instead of failing the whole run.
- Each run writes an `IntegrationSyncRun` row (counts, lag, errors).

**Webhooks (2b, optional):** subscribe to matter/contact/task/calendar/activity
events to cut lag from minutes to seconds. The handler only verifies the
signature and enqueues "re-fetch record X"; it never trusts the payload as data.
A renewal job re-extends subscriptions before the 31-day expiry. Polling stays
as the safety net.

### 5. Ownership and editing rules

This is the part that makes or breaks a trial.

- Each mirrored record carries its ownership via its `ExternalRecordLink`
  (`owner = clio | lawhand`, added as metadata or a column).
- **Clio-owned fields are read-only in LawHand** with an "Edit in Clio" link. If
  we let users edit them, the next sync silently overwrites their change.
- **LawHand-native data attaches freely** to mirrored records: AI drafts,
  research, firm memory, configurable workflows, LawHand-only notes and tasks.
  That is the value the firm is trialling.
- New records created in LawHand during the trial are `owner=lawhand` and stay
  in LawHand (or go through the outbox, below).

### 6. Automation safety

Synced records must not look like new work to the automation engine:

- Records created or updated by the sync do **not** fire matter-created
  automations, client emails/SMS, portal invites, cloud-folder provisioning or
  e-sign sends — the same rule `matter_csv_imports.py` already follows.
- Configurable workflows run on a mirrored matter only when a user explicitly
  starts them there.

### 7. Financial data (reference only)

Time entries, expenses, bills and trust balances are mirrored **read-only** under
`accounting_mode="clio_reference"`, so LawHand can show them and AI can reason
over them. LawHand must not invoice or post trust against Clio-owned
financials during the trial; otherwise the firm double-bills or breaks
trust-accounting reconciliation. Trust stays in Clio until the billing cutover.

### 8. Documents

Documents are the heaviest part (bytes and requests) and the most valuable for AI.

- Backfill **metadata** for in-scope matters first.
- Pull **content** for open in-scope matters into the firm's own storage (the
  normal matter storage — we don't keep a LawHand datastore copy), as durable
  jobs with a byte budget, latest version only.
- Closed matters: metadata plus on-demand fetch when someone opens one.
- Re-pull when Clio's version/etag changes.

### 9. Optional outbox (LawHand → Clio, append-only)

Only if the trial users would otherwise double-enter. Scope:

- New time entries captured in LawHand → Clio activities (so billing stays in Clio).
- New notes and generated documents → the Clio matter.

Rules: creates only; never update or delete a Clio-owned record; every push is a
durable job with an idempotency key and a stored Clio ID written back to the
link, so a retry can't create duplicates. This is what people usually mean by
"two-way sync", without the conflict resolution problem.

### 10. Cutover

Cutover is per entity area, not a single big-bang date, e.g. tasks/calendar
first, then documents, billing and trust last.

For an area: final delta sync → reconciliation report (counts; for billing,
unbilled time, AR and trust balance per matter, matching Clio's own reports) →
signed approval → flip links to `owner=lawhand`, unlock editing, stop pulling
that area. Provenance links remain permanently. After the last area, disconnect
the Clio grant.

If the firm doesn't convert: the trial-revocation path
(`backend/tests/test_platform_trial_revocation.py`) must also cover the Clio
connection — revoke the token and purge mirrored data per the retention decision.

## Delivery phases

Each phase is its own PR. Migrations are chained on a single head per
`AGENTS.md` §1 (current head on `main`: `202`); the number is assigned when the
PR is started, not now.

| Phase | Outcome | Rough size |
|---|---|---|
| **0. Spike** | Clio dev app, OAuth connect, read-only probe that reports per-entity counts, doc bytes, users and region for the prospect's account (like `backend/scripts/inspect_legacy_sqlserver.py` for Tabs3). Confirms the "to verify" facts above. | ~1 week |
| **1. Adapter refactor + backfill** | Provider adapters extracted from `external_imports.py` (Tabs3 keeps passing its tests); Clio connection + token storage; backfill of users, contacts, matters, relationships, tasks, calendar, notes through reconcile/approve/promote; sync scope filter. | 2–3 weeks |
| **2. Incremental sync** | Scheduled polling with watermarks and checksums, ownership locks in the UI, review queue, deletion sweep, admin health on the Integrations page. 2b: webhooks + renewal. | ~2 weeks (+1 for 2b) |
| **3. Documents + reference financials** | Document metadata/content pull into firm storage; read-only time/expense/bill/trust mirror. | 2–3 weeks |
| **4. Outbox (optional)** | Append-only push of time entries, notes and documents. | ~2 weeks |
| **5. Cutover tooling** | Per-area final sync, reconciliation report, ownership flip, disconnect/purge. | 1–2 weeks |

Phases 0–2 are the minimum for a credible trial (live matters, contacts, tasks
and calendar in LawHand). Phase 3 is needed if the trial leans on AI over
documents, which it probably should.

Test budget: every phase is a sizeable backend diff under the 80% diff-coverage
gate (`AGENTS.md` §2). Clio responses are recorded as fixtures; nothing in CI
calls Clio.

## Security and privacy

- Tokens encrypted at rest; read-only scopes unless the outbox is on.
- All new tables tenant-scoped with RLS, like the existing import tables.
- Webhook endpoint verifies the HMAC before doing anything and only enqueues
  re-fetches.
- Every backfill approval, cutover and purge writes `OperatorAuditLog`.
- Data residency: store and honour the firm's Clio region; confirm our hosting
  region is acceptable to them before the backfill.
- Trial exit purges mirrored data per the agreed retention decision.

## Open questions (for us and the prospect)

1. Which Clio region is the firm on, and which Clio user will authorize? (Needs
   to see every in-scope matter.)
2. What does the trial cover — which practice area/attorneys, and which LawHand
   features do they want to use first? That decides whether Phase 3 is needed
   before go-live.
3. Do trial users need their LawHand time entries/notes to land in Clio (the
   outbox), or will a small pilot group accept working in LawHand for AI/drafting
   and in Clio for billing?
4. Volumes: matters, contacts, document count and GB. (Phase 0 answers this.)
5. Do they use Clio Grow (intake) or Clio Payments? Those are separate surfaces
   and are out of scope here unless they say otherwise.
6. Trial app: firm-registered Clio developer app (fast, via `tenant_oauth_apps`)
   or a LawHand-owned app submitted to the Clio App Directory (needed anyway for
   more Clio prospects, but slower)? Suggest the former for this prospect and
   start the latter in parallel.

## Non-goals

- General two-way sync or field-level merge between Clio and LawHand.
- Writing to Clio trust or billing records.
- Syncing other firms or other products in this effort (the adapter refactor
  keeps that possible; Tabs3, MyCase and PracticePanther can follow the same
  shape later).
