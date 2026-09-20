# Firm Memory: build, performance and UX sprint

A two-week sprint to get the Firm Memory module and its Windows agent from
"merged but unshippable" to "a signed build a firm can install, that converges
on a real share, and that answers a query in under a second."

**The thesis in one sentence:** the code has been ready for three weeks and the
*release* is what is broken — so the sprint starts at the build pipeline, not
at the profiler.

> **Verified at `origin/main`, 2026-09-18.** Every file:line, constant and
> version in this document was read from commit `4d7b58b5`. Claims marked ✅ were re-verified by hand
> against the source after first being surfaced by analysis. Where a finding is
> inferred rather than observed, it says so.

---

## 0. Three decisions to make before any code is written

These are forks. Making them in week two means redoing week one.

### Decision 1 — `crawl_control.py`: wire it, or delete it

`agent/clarity_agent/crawl_control.py` is 2,063 lines implementing exactly the
things the live indexing path lacks: ACL refresh as its own job kind
(`crawl_control.py:80,970-979`), per-source worker/handle/byte budgets
(`:1595-1635`), queue backpressure (`:906-924`), and resumable reconciliation
checkpoints (`:739,983`).

✅ **It is imported by zero production modules.** Only `agent/tests/test_crawl_control.py`
(1,246 lines) references it, and it is absent from the PyInstaller hidden-import
list (`agent/packaging/lawhand-agent.spec:17-22`). Since nothing imports it, it
is very likely excluded from the frozen binary by import-graph analysis — but
that is an inference, not a measurement; confirm against a built artifact before
claiming a binary-size win. `CrawlPipeline.enabled` defaults `False` with
`_require_enabled()` raising (`:1651,2061`).

Performance items 1, 4, 5 and 8 in §4 are all problems this control plane
already solves correctly. The choice:

- **(a) Wire it in.** Larger up-front cost, but stops the piecemeal rebuild of a
  scheduler inside `local_index.py`.
- **(b) Delete it.** Removes 3,300 lines of module + test from the repo and CI,
  and commits to fixing `local_index.py` directly.

Doing neither — patching `local_index.py` while a better scheduler sits unused —
is the expensive option, and it is the current trajectory.

**Decision: (b) delete, fix forward.** The unused module and its isolated test
suite were removed in the week-one implementation. The live path needs four targeted
fixes (§4 items 1, 2, 3, 6) that are each smaller than the integration risk of
swapping the scheduler underneath a default-off pilot. Revisit (a) only if the
first real customer share proves the live path structurally unfixable.

### Decision 2 — Who configures Azure Trusted Signing, and when

This blocks the entire build track and **cannot be done by an agent.** See §1.2.
Nothing ships until this exists. If it cannot be scheduled in week one, the
sprint's release goal must be restated as "unsigned validation build only."

### Decision 3 — What a share with more than 250,000 files should do

✅ `SMB_MAX_FILE_INDEX_PER_SHARE: int = 250_000` (`backend/app/config.py:606`) is
a *configurable* ceiling, not a hard cap — its own comment records that it was
raised from 500 because "ordinary legal shares [went] silently partial."

Today, past the ceiling, every excess file appends a per-path error object
(`backend/app/services/smb.py:946-951`) and ✅ the response returns the whole
batch's error list (`:1035`, no aggregation). The request schema caps a sync at
500 files and the agent sends 100-file batches, so memory is bounded; however, a
750k-file share still produces 500k redundant per-path rejection records across
5,000 requests on each attempted full backfill.

Pick one: raise the ceiling with a documented memory cost; aggregate the
overflow into a single typed coverage error; or refuse to bind an oversized
share at all with an explicit operator message. Silently partial is the one
option already rejected once.

---

## 1. Where the build actually stands

### 1.1 Three unreleased versions

| | Version | Date | State |
|---|---|---|---|
| Working tree | **0.17.0** | — | `agent/clarity_agent/__init__.py`, `pyproject.toml` agree |
| Last tag | `agent-v0.15.2` | 2026-08-29 | ✅ on `origin`, **no GitHub release, no workflow run** |
| Last **published** release | **0.15.1** | 2026-08-26 | The only thing a customer can install |

Two version bumps — 0.16.0 (`325c0c00`, the file opener) and 0.17.0
(`019e2476`, firm-wide search) — were never tagged. Everything in the
OpenSearch/native-authorization wave (~16,700 lines added since the last
release) is unshipped.

The `agent-v0.15.2` tag is on `origin` and the tag *would* have passed the
publish job's version gate (✅ `__version__` and `pyproject.toml` both read
`0.15.2` at that tag). No `agent-release` run exists for it in the 2026-08-25 →
09-05 window. Cause not established; the tag is pushed but no run fired. A
fresh `agent-v0.17.0` tag is the next valid end-to-end test; do not move or
re-push the existing `agent-v0.15.2` tag.

### 1.2 Signing is unconfigured — this is the hard blocker

The release job's first signing step hard-fails if any of seven variables is
blank (`.github/workflows/agent-release.yml`, "Require Azure release signing
configuration"):

```
WINDOWS_SIGNING_AZURE_CLIENT_ID      WINDOWS_SIGNING_ENDPOINT
WINDOWS_SIGNING_AZURE_TENANT_ID      WINDOWS_SIGNING_ACCOUNT_NAME
WINDOWS_SIGNING_AZURE_SUBSCRIPTION_ID WINDOWS_SIGNING_CERTIFICATE_PROFILE_NAME
WINDOWS_SIGNING_EXPECTED_SUBJECT
```

✅ The `agent-release` environment has **zero variables and zero secrets**, and
no repository variable matches `WINDOWS_SIGNING_*`. The environment's branch
policy *does* admit `agent-v*` tags, so that is not the obstacle — the
credentials simply do not exist.

Needed: an Azure Trusted Signing account + certificate profile, a federated
credential whose subject is exactly
`repo:mattpainter701/lawhand:environment:agent-release`, and the seven variables
set at repo or environment scope. **This requires the account owner.**

### 1.3 What the pipeline does once signing exists

Build → sign exe → rebuild MSI around the *signed* exe (`build.ps1 -SkipExe`) →
sign MSI → over-top upgrade smoke test → publish. The publish job generates
`agent-update.json` (with SHA-256s) and `SHA256SUMS.txt`, creates the release as
a draft, uploads, verifies the four required assets are present, then flips it
to `--latest` and curls the public stable URLs. CI is currently green on `main`
(Windows validation ~4 min, Linux ~1 min).

**Note:** the release assets do **not** include a `lawhand-search-node` wheel.
See §5.1.

---

## 2. Shipping 0.17.0 is functionally required, not cosmetic

✅ `MULTI_MATTER_SEARCH_MIN_AGENT_VERSION = (0, 17, 0)`
(`backend/app/services/smb.py:83`).

`_agent_binds_matter_set()` (`:88-101`) returns `False` for any version below
that — and also for a missing or unparseable version. An agent that fails the
check is **reported as not covered rather than searched**, surfacing the
coverage error `agent_version_lacks_matter_set_binding` (`:2211`).

The rationale is sound: an older agent does not bind `matter_ids` into the
identity ticket, so a firm-wide relay to it would lose a tamper check, and the
system fails closed rather than relaxing the binding.

**The consequence is the sprint's business case.** The newest *installable*
agent is 0.15.1. Every agent a firm can deploy today is below the floor, so
firm-wide Firm Memory search reports every one of them as uncovered. The
feature cannot work in the field until 0.17.0 is published — regardless of how
good the code is.

---

## 3. The repo rename bricked self-update in the field

The repo was renamed `legalapp` → `lawhand`. Commit `703430b6` applied that
consistently across `updater.py`, `smbAgentInstall.js`, the workflow, the Linux
updater unit and their tests — `origin/main` is internally correct.

**Already-installed agents are not.** ✅ At `agent-v0.15.1` and `agent-v0.15.2`:

- `RELEASE_MANIFEST_URL` and `RELEASE_ASSET_BASE` point at the **old** path
  (`updater.py:24-26`).
- `GITHUB_RELEASE_PATH` is pinned to `^/mattpainter701/legalapp/releases/…`
  (`:46-50`).
- `_official_redirect_url()` enforces that regex for any `github.com` redirect:
  `hostname != "github.com" or (not query and GITHUB_RELEASE_PATH.fullmatch(path))`.

✅ The live URL now returns `301 → https://github.com/mattpainter701/lawhand/releases/latest/download/agent-update.json`
— same host, new path. The shipped allowlist rejects it, and the updater raises
`UpdateError("Refusing unsafe update redirect")` **on the first hop**. The
portal's update button drives this same code path.

✅ The Linux path is identical: `agent/packaging/linux/lawhand-agent-update` at
0.15.1 bakes the old regex into `/etc` (`:70`) with the same github.com path
enforcement (`:112`).

**CI cannot catch this class of bug.** ✅ `test_updater.py` asserts against
`updater.RELEASE_MANIFEST_URL` — the module's own constant — so renaming the
constant keeps every test green while the field breaks.

**Blast radius, stated honestly:** `docs/firm-memory-launch-readiness.md:76`
records that no production activation or customer indexing has happened, and
Firm Memory is a default-off pilot. So this is a **pre-launch defect, not a live
outage.** It is severe because it is silent, self-inflicted, and removes the
automatic rollout channel exactly when the first real build needs to go out.

**Recovery path:** a direct over-top `msiexec /i` install, which is supported
and preserves enrollment, `config.toml`, key material and the SQLite ledger
(`agent/packaging/windows/UPGRADE.md`). Portal-driven update is additionally
limited to LocalSystem services and agents ≥ 0.15.0
(`PORTAL_UPDATE_MIN_VERSION = [0, 15, 0]`, `SmbAdminPage.jsx:44`).

**Fix forward:** collapse the repo identity to one constant per surface, and add
a test that asserts the *literal* expected owner/repo string — so the next
rename fails CI loudly instead of silently in the field.

---

## 4. Performance: ranked defects

Verified in the source; ✅ marks items I re-read end-to-end myself.

| # | Defect | Evidence | Impact | Effort |
|---|---|---|---|---|
| 1 | ✅ **Hourly full-corpus re-read, re-parse and re-publish to refresh DACLs.** No ACL-only job kind exists. | `local_index.py:665-673`; `config.py:249`; worker body `local_index.py:785-800` | **High** | M |
| 2 | ✅ **Per-result live SMB DACL read at query time** — serial N+1, connection cache torn down per call. | `search_serving.py:221-243,328`; `__main__.py:524-541` | **High** | M |
| 3 | ✅ **One document per bulk request, each forcing `refresh=true`.** The 500-doc/8 MiB budget is never exercised. | `search_serving.py:148`; `opensearch_engine.py:34-35,681-682` | **High** | M |
| 4 | **A fresh OS process per document** (plus a JVM per legacy-format file), with no warm pool. ✅ The single-worker default is *deliberate* — "conservative for an HDD-backed SMB source," operator-tunable to 4 — so the defect is per-document spawn cost, not the worker count. | `config.py:229-231`; `local_index.py:574,582`; `extraction.py:128-144`; `parser.py:346-371` | High | L |
| 5 | Serial scan: a 512 KB read + full parse per file to produce a 500-char snippet; no SMB connection reuse; directory-granularity invalidation redoes it for untouched files. | `smb_scanner.py:394-401,59-71`; `__main__.py:501-541` | High | M |
| 6 | Deletion outbox drains one document per HTTP call, unconditionally every scan, holding a write transaction. | `search_serving.py:186-212` | Med | S |
| 7 | Per-query fixed overhead: 4 uncached OpenSearch preflight round trips, `track_total_hits: true`, and a `stats()` call doing an unindexed `json_extract` full scan. | `opensearch_engine.py:861,937-941`; `search_serving.py:249-252,347` | Med | S |
| 8 | ✅ Unbounded scan memory, plus the 250k-per-share ceiling and its unbounded error list (Decision 3). | `smb_scanner.py:127,313`; `backend/app/config.py:606`; `smb.py:946-951,1035` | Med-High | M |

### 4.1 Item 1 in detail — why it is the headline

The staleness sweep resets every `ready` row to `pending` when its
`acl_captured_at` is older than `acl_refresh_seconds` (`local_index.py:665`).
✅ That value is wired straight from config —
`acl_refresh_seconds=getattr(config, "acl_max_age_seconds", 3600)`
(`__main__.py:402,422`), clamped by `max(60, …)` (`local_index.py:473`), with
`acl_max_age_seconds: int = 3600` (`config.py:249`). So the default sweep
interval is **one hour**. The in-code comment says it queues "a bounded refresh
without deleting its old text."

✅ **The comment describes the row, not the work.** The worker loop has no
ACL-only branch. A re-queued row runs the identical body
(`local_index.py:785-800`): `_acl_loader(job)` → `self._fetcher(job)` — a full
file fetch over SMB — → `_extract_text(job, content)` — a full re-parse —
→ `DELETE FROM index_fts` → `_publish_text(...)`, which re-publishes the whole
document with a new mutation generation.

So the entire corpus is re-fetched, re-parsed and re-indexed **once an hour**,
purely to refresh DACLs. If a full pass takes longer than an hour — certain on
a multi-terabyte share with one extraction worker — the agent never reaches
steady state and never converges.

**Fix:** add an ACL-refresh job kind that updates `acl_json` /
`acl_captured_at` and the OpenSearch allow/deny metadata without fetching or
re-extracting file content. OpenSearch uses those tokens as a candidate filter,
so updating SQLite alone would preserve fail-closed authorization but leave new
grants falsely unsearchable. `crawl_control.py:80,970-979` already models the
separate job kind (Decision 1), but the live sink still needs the metadata-only
engine mutation.

### 4.2 Item 2 in detail — what dominates p95

✅ `OpenSearchServingIndex.authorize_path` (`search_serving.py:221`) comments
"then re-read the actual DACL" and calls `self._acl_loader(dict(row))`
unconditionally once the inherited fencing check passes. `acl_max_age_seconds`
is only used to validate the freshly-loaded record's staleness — it is **not** a
cache window.

✅ In the daemon that loader is `acl_for_index` (`__main__.py:524-541`), which
per call does a share lookup, `asyncio.to_thread(capture_smb_acl, …)` — a live
security-descriptor read against the file server — and then
`reset_connection_cache` in a `finally`. **No connection is reused.**

Overfetch is `limit*2` capped at 100 (`search_serving.py:300`), so a query can
perform up to 100 serial SMB session setup/teardowns — inside a ✅ 12-second
SaaS deadline (`LOCAL_SEARCH_TIMEOUT_SECONDS = 12.0`, `smb.py:78`). Exceeding it
yields `agent_search_timeout` and a partial-coverage response.

**Fix:** reuse one authenticated connection for the whole query, gather with
bounded concurrency, and authorize lazily for hits actually returned. Do not
cache positive authorization decisions: even a short-TTL allow can survive a
new live DENY and would weaken the current fail-closed property. A negative-only
cache is safe if profiling shows it is useful, because a stale denial affects
availability rather than disclosing content.

### 4.3 Prerequisite: none of this is measurable today

- One timer in the entire agent, around search only (`task_worker.py:236,326`).
- OpenSearch returns `took_ms` and `OpenSearchServingIndex.search` **discards
  it** (`search_serving.py:361-366`) — so the split between engine time and ACL
  re-read time is unrecoverable from any log.
- No ingest timing at all: no per-file extraction duration, SMB read duration,
  bytes/sec, files/hour or queue depth. `index_files` has no `started_at`.
- No counter separating new work from the hourly ACL re-queue, so an operator
  cannot distinguish "indexing" from "re-indexing the corpus for the third time
  today."
- `agent/benchmarks/search_node/run_benchmark.py` is a **correctness** harness
  over ~10 synthetic fixture docs (`documents.jsonl` is 1.9 KB) that never
  prints a timing. `poc_benchmark.py` computes percentiles over latencies
  supplied in its input file — it measures nothing itself.
- The heartbeat carries `active_scans`, and nothing ever sets it.

**Instrumentation lands before or alongside items 1–5, or the sprint cannot
prove it worked.**

---

## 5. Installer and onboarding

### 5.1 The MSI does not finish the job

`docs/firm-memory-launch-readiness.md:15-18` states it plainly: the agent
executable is not a Python interpreter, and "the MSI does not itself provision
that external environment." An operator must separately provide a reviewed
Python 3.11+ environment, install a *matching* `lawhand-search-node` wheel into
it, and set an absolute `SEARCH_NODE_PYTHON_EXECUTABLE`.

**And that wheel is not published.** The release assets are the MSI, the exe,
the Linux tarball, `agent-update.json` and `SHA256SUMS.txt` — no search-node
distribution. So the documented install path depends on an artifact the release
does not produce. Either publish the wheel as a release asset, or bundle the
extraction runtime, or the pilot install is a manual build step on the
customer's file server.

### 5.2 Other cliffs

- The MSI deliberately carries no pairing custom action; enrollment is a
  separate elevated `lawhand-agent register --code …` step after install.
- `lawhand-agent search-preflight` must be run, and `SEARCH_NODE_SANDBOX_VERIFIED`
  set by hand, before activation.
- Five environment flags must agree across SaaS and agent, and all default off.

---

## 6. UX defects

The truth-telling *architecture* here is genuinely strong — coverage states, the
complete/incomplete split on zero results, escaped highlight rendering. Almost
every defect is in the last inch: a reason computed correctly on the server and
then parked in a `title=` attribute, a count that means something other than
what it says, and an admin flow that ends one step before the feature works.

| # | Defect | Evidence | Impact | Effort |
|---|---|---|---|---|
| 1 | ✅ **"Open on this computer" is dead on every on-prem result.** The backend emits `open_on_device` unconditionally with `available=False` and no href, so `localOpenHref` is always falsy and the live `<a>` branch is unreachable. It renders as a `disabled` button — unfocusable, so the explanation in `title=` is unreachable by keyboard and silent to AT — and the reason reads as an instruction, "Open from the lawhand result page". | `firm_memory.py:927-931`; `UnifiedFirmMemoryPage.jsx:190,236-238`; `documentSearchApi.js:63-67,99-100` | **High** | S |
| 2 | **The search-node runtime is invisible in-product.** `SEARCH_NODE_PYTHON_EXECUTABLE` appears nowhere in `frontend/`, and there is no search-node health or preflight readout. An admin completes the whole flow and silently ships a metadata-only Firm Memory — surfaced to *end users* as "the on-premises search node could not be reached" and to the admin as nothing at all. | absent from `SmbAdminPage.jsx:317-391`; `launch-readiness.md:16-18`; user-facing copy at `UnifiedFirmMemoryPage.jsx:68` | **High** | M |
| 3 | ✅ **Matter binding — required for search to return anything — is absent from the admin flow.** `grep -c matter` over the 1,566-line admin page returns **1**, and that hit is prose in the page blurb. Binding lives in an unlinked per-matter surface. The admin's flow ends at "share added, 12,000 files" looking finished, while search returns zero and tells the user to go ask an administrator. | `SmbAdminPage.jsx:1535` only; `MatterSmbSharesTab.jsx:694-699`; `firm_memory.py:287-290` | **High** | M |
| 4 | ✅ **"25 results" is the page size, not the match count.** `limit: 25` is hardcoded at the call site and the contract has no `offset`, `cursor` or `total` anywhere. A query matching 4,000 documents renders "25 results" with no next page — on the one page whose entire thesis is that a reader must distinguish absence from non-coverage. | `UnifiedFirmMemoryPage.jsx:365,500`; `schemas/firm_memory.py:62` (only `limit`) | **High** | M |
| 5 | **Scope tabs and chip removal mutate filters without re-running or invalidating results.** Click "Cloud" and you are still reading "Everything" results, with no staleness cue. | `UnifiedFirmMemoryPage.jsx:431,454,458` vs `:346` | High | S |
| 6 | ✅ **A permanent gap is described as a temporary delay.** The agent folds `error`, `unsupported` and `ocr_pending` into one `incomplete` boolean → `index_state: "partial"`; the backend maps that to `agent_index_partial`; the UI renders "still building its index… do not cover its whole corpus yet." `grep -c -i ocr` over the backend service returns **0** — the token dies at the agent boundary, contradicting the readiness promise that OCR files are "not silently described as fully indexed." | `search_serving.py:353-366`; `firm_memory.py:274-276`; `UnifiedFirmMemoryPage.jsx:69`; promise at `launch-readiness.md:69-71` | **High** | M |
| 7 | ✅ **The portal offers an update it cannot deliver.** The update payload carries versions/status/error and **no service-account capability field**, so the button renders for custom-account hosts, the dialog promises a brief restart, a toast says "queued" — then the agent refuses minutes later with a raw string and no next step. A confidently-promised failure is worse than a correctly-disabled button. | `routers/smb.py:869-880`; `updater.py:478-483`; `SmbAdminPage.jsx:515,521,614-616,621` | Med-High | M |
| 8 | **First scan shows no progress and turns red after 60 s.** The Files column reads 0 until completion, the status badge prints the raw `in_progress` token, and `pollTask` gives up after ~60 s writing "may be offline" — rendered in rose. A healthy multi-hour first scan is reported as possibly-broken. The backend has no progress channel to poll even if the UI wanted one. | `SmbAdminPage.jsx:938,947-960,1140,1150,1157-1159`; `routers/smb.py:1182-1186`; `services/smb.py:2400,2603` | Med-High | M |
| 9 | **`update_error` is rendered raw, unredacted and untruncated** (agent-supplied, capped only at 2,000 chars) while the *identical* string is redacted and truncated in the Activity tab. The page already imports the sanitizer and applies it to shares. | `SmbAdminPage.jsx:621` vs `smbActivity.js:11-17,35`; `services/smb.py:748-749` | Med | S |
| 10 | **A failed share-unbind is swallowed by design.** The binding disappears from the UI, survives on the server, and the user is never told — so a matter keeps exposing a share the user believes they unbound. | `MatterSmbSharesTab.jsx:651-661` | Med | S |

### 6.1 Cluster worth fixing together (cheap, and mostly one pass)

- Validation (`"Enter at least two characters"`) is styled in the same red
  `role="alert"` box as a backend outage; on failure the error and the
  *pre-search invitation* render stacked.
- Loading is a button label only — no spinner, skeleton, `aria-busy` or
  `role="status"`. The first search blanks the page; a re-search leaves stale
  results fully opaque and unmarked.
- `aria-live="polite"` sits on a conditionally-mounted node, so results and
  coverage announce nothing; focus is never moved after a search.
- The most decision-critical text on the page — `coverage_message` and its next
  step — is the smallest (`text-xs`, source pills `text-[11px]`).
- Only one coverage next-step ever renders (`.find(Boolean)`), and several
  reasons have no mapping at all, surviving only as a raw token in a `title=`.
- The Linux install command interpolates the literal `<pairing code>`
  placeholder, so a copied command fails.
- The "Download MSI" link sits beside the copy-block and produces an installed,
  *unregistered* service — the word "register" appears nowhere on the page.
- The file-opener limitation paragraph is printed on all 25 result cards.

### 6.2 Worth preserving — do not "fix" these

The complete/incomplete zero-result split, the `<mark>` escaping strategy,
refinement chips as visible state, `formatSmbDiagnostic`'s 422/offline/credential
next steps, and `operationalDiagnostic`'s redaction — which should simply be
applied in the two places it currently isn't (defect 9).

Also still true, and a standing cost: two search pages are maintained in
parallel and selected at runtime from capabilities (`App.jsx` `FirmMemoryRoute`),
so every change is dual-path.

---

## 7. Dead weight

| Item | Size | Status |
|---|---|---|
| `crawl_control.py` + its test | 2,063 + 1,246 lines | ✅ Imported by nothing; not in the frozen binary. Decision 1. |
| `local_index.py` SQLite FTS5 path | 1,136 lines | Still wired into the daemon and `search_serving` though `CLARITY_LOCAL_INDEX_ENABLED=false` by default. |
| Legacy `FirmMemoryPage.jsx` | 243 lines | Still the runtime fallback. |

---

## 8. The sprint — two weeks, 2026-09-22 → 2026-10-03

Sequenced so that each track unblocks the next. Nothing in week two depends on
a week-one *finding*; it depends on week-one *decisions*.

### Week 1 — make it shippable and measurable

| # | Task | Gate |
|---|---|---|
| 1.1 | **Configure Azure Trusted Signing** (owner: account holder — see Decision 2) | Seven vars present on `agent-release`; a tag reaches the sign step |
| 1.2 | Collapse repo identity to one constant per surface; add tests asserting the **literal** `mattpainter701/lawhand` string in updater, Linux unit, install snippet and backend | Tests fail if the owner/repo string changes |
| 1.3 | Decide + execute Decision 1 (`crawl_control`) | Repo reflects the decision; CI time drops if deleted |
| 1.4 | **Ingest + query instrumentation** (§4.3): per-file extract/fetch timings, queue depth, ACL-refresh vs new-work counters, stop discarding `took_ms` | A single log line attributes query time to engine vs ACL |
| 1.5 | Tag `agent-v0.17.0`, publish, verify the four assets and the public stable URLs | A signed MSI is downloadable from `latest` |

### Week 2 — make it converge and answer fast

| # | Task | Gate |
|---|---|---|
| 2.1 | **ACL-only refresh job** (§4.1) — update manifest and engine ACL metadata without text re-fetch or re-extraction | A corpus at steady state does zero re-extractions in an hour; changed grants and denies affect candidate filtering |
| 2.2 | **Query-path authorization** (§4.2) — connection reuse, bounded concurrency, lazy per-returned-hit, and no positive-decision cache | p95 under 1s on a 10k-doc corpus; a newly-added live DENY still denies immediately |
| 2.3 | **Batch the OpenSearch write path** (§4 item 3) + outbox drain in one call with an empty-path early return (item 6) | Segment count per 1k docs drops by an order of magnitude |
| 2.4 | Per-query overhead: cache index/mapping/lease state, bound `track_total_hits`, stop the per-query `stats()` full scan (item 7) | Preflight round trips per query: 4 → 0 warm |
| 2.5 | **UX honesty tier** — §6 defects 1, 4, 6: explain the dead action (or stop rendering it), stop calling a page size a result count, and carry `ocr_pending` / permanent-failure through to distinct copy | A user can tell "no matches" from "we could not search these files", and from "this will never be searchable without OCR" |
| 2.6 | **Onboarding cliff tier** — §6 defects 2, 3, 8: search-node health readout, matter-binding step (or a cross-link) in the admin flow, first-scan progress that does not go red at 60 s | An admin who finishes the in-product flow has a *working* Firm Memory, or is told exactly what remains |
| 2.7 | **Cheap-fix tier** — §6 defects 5, 7, 9, 10 and the §6.1 cluster | Filters invalidate results; the portal never promises an update it cannot deliver; no raw agent string reaches a table cell |
| 2.8 | Decision 3 + the unbounded sync error list | A >250k share produces one typed error, not 500k |
| 2.9 | Build a ≥10k-document corpus and record first-index time, files/hour, p50/p95, disk growth | The launch-readiness "acceptance still required" list has real numbers |

### Explicitly out of scope

Production activation, customer indexing, OCR throughput work, semantic/vector
retrieval on the file-share path, and a mobile document viewer.

---

## 9. Exit criteria

1. A **signed** `agent-v0.17.0` MSI is published and installs clean and over-top.
2. The repo identity is pinned by a test that fails on rename.
3. An installed agent's self-update works, or the sprint states plainly that
   field agents require a manual over-top MSI and why.
4. Firm-wide search no longer reports agents as uncovered (§2).
5. A steady-state corpus performs **zero** full re-extractions per hour.
6. p95 query latency on a 10k-document corpus is under one second, with live
   DENY still enforced per returned result.
7. First-index time, files/hour, p95 and disk growth are **recorded numbers**,
   not estimates.
8. A reader can distinguish three different things — "no matches", "we could
   not search some of your files", and "these files will never be searchable
   until OCR is configured" — and no result renders a control that cannot work
   without saying why.
9. An admin who completes the in-product onboarding flow has a working Firm
   Memory, or is told exactly what remains (matter binding, search-node
   runtime).

---

## 10. Checklist

- [x] Decision 1 made and executed (`crawl_control` deleted)
- [ ] Decision 2 — Azure Trusted Signing configured
- [ ] Decision 3 — >250k-file share behaviour chosen
- [x] Repo-identity constants collapsed + literal-string test
- [x] Ingest/query instrumentation landed
- [ ] `agent-v0.17.0` tagged, signed, published, assets verified
- [ ] ACL-only refresh job
- [ ] Query-path connection reuse + bounded concurrency without positive-decision caching
- [ ] OpenSearch batched writes + outbox drain fix
- [ ] Per-query preflight caching
- [ ] UX honesty tier (§6 defects 1, 4, 6)
- [ ] Onboarding cliff tier (§6 defects 2, 3, 8)
- [ ] UX cheap-fix tier (§6 defects 5, 7, 9, 10 + §6.1)
- [ ] Unbounded sync error list capped
- [ ] ≥10k-doc corpus measured and recorded
- [ ] `docs/firm-memory-launch-readiness.md` updated with real acceptance numbers

---

## Appendix — house rules that apply to this work

- **Migration head protocol:** confirm the current head before adding one; the
  fm wave already had `149` claimed by four PRs at once (`AGENTS.md §1`).
- **Merge policy:** the PR body must check exactly one documentation-impact
  option, one customer release-note option, and an MCP option where relevant
  (`scripts/verify_merge_policy.py`); customer-facing changes need all three of
  `CHANGELOG.md`, `RELEASE_NOTES.md` and `backend/app/release_notes.json`.
- **Worktrees:** `gwt new <branch>` under `worktrees\`; tear down on merged-PR
  state, never `git branch --merged`.
- **Branch from a fresh `origin/main`**, never from a local checkout whose state
  or ownership has not been verified, and stage explicitly.
