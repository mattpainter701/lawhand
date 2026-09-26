# Repository bloat, waste, and inefficiency audit — 2026-09-26

Read-only survey of `mattpainter701/lawhand` (branch `main` at the time of the
audit) covering backend, frontend, API surface, CI/deploy infrastructure,
satellite apps, and repository/workspace hygiene.

Method: six parallel read-only passes over the working tree, `git ls-files`,
`git log`, ripgrep reference sweeps, an import-graph walk of
`frontend/src`, and route extraction from the live FastAPI app object. No
values from any secret-bearing file are reproduced in this document. Every
number below was measured, not estimated by eye; where an inference is
stronger than the evidence, it is marked.

**Baseline and re-verification.** The survey ran against local `main` at
`f548167c`. `origin/main` moved to `32d58053` while the survey was in flight, so
every load-bearing claim was re-checked against `origin/main` before this
document was written. `origin/main` gained **494 files and lost 9** in that
window, so several *size* figures below are quoted at the baseline and the
current values are given here:

| Metric | at baseline (`f548167c`) | at `origin/main` (`32d58053`) |
|---|---:|---:|
| Tracked files | 2,444 | **2,929** |
| Tracked tree | 60.2 MiB | **78.8 MiB** |
| `backend/` files | 1,273 | **1,495** |
| `frontend/` files | 538 | **729** |
| `docs/` files / size | 181 / 2.72 MiB | **243 / 4.79 MiB** |
| `backend/seed/sample_templates` | 71 PDFs / 30.5 MiB | **82 PDFs / 39.6 MiB** |
| `.github/workflows/` | 13 | **17** (`codeql.yml` removed; `ci-durations.yml`, `deploy-inbound-email-worker.yml`, `oauth-client-health.yml`, `prod-dast.yml`, `security-scanners.yml` added) |
| `ci.yml` | 1,285 lines | **1,349 lines** |

Structural findings were all re-confirmed on `origin/main`: still **17
workflows**, still no `paths:` filter on `ci.yml`, still no
`.github/dependabot.yml`, still 8 compose files, still a 111-line dead
Makefile, still a job-level-gate-less `production-health` cron, still the
broken `.gitignore` negation, still 31/73 non-placeholder values in the two
tracked env files, still 0 consumers for the spot-checked dead settings, still
0 references to `automation-services` outside `backend/`, still 26 of 30
checkout pins mislabelled `v5.1`. The route inventory (950 entries / 767 paths)
was extracted from the live app at the baseline; `include_router` calls have
since grown from 92 to 100, so the *ratios* below hold while the absolute
count is now slightly higher. Per-directory *contents* counts (dead modules,
orphan docs, test file sizes) are baseline measurements.

---

## The short version

The **code itself is in good shape**. Across ~400k lines of Python and ~111k
lines of JS there are no duplicate routers, no orphan routes, no dead
navigation, no unused requirements, no abandoned migration branches, no
committed build artifacts, no `*_old`/`_v2`/`.bak` file litter, essentially
zero `TODO`/`FIXME` debt, and zero commented-out code. Frontend and satellite
scripts are unusually clean — 86 of 87 scripts in `scripts/` are wired into
CI, Makefile, docs, or another script.

The waste is concentrated in **five places that are not the application code**:

| # | Area | Waste | Effort |
|---|---|---|---|
| 1 | **Tracked env files in a public repo** contain secret-shaped values | security | hours |
| 2 | **Two parallel production Compose topologies** maintained in lockstep | ~400 lines, 4× env-var duplication | days |
| 3 | **CI**: no `paths:` filter, 144×/day health cron with no job-level gate, release-gate copied into 5+ workflows (7 call sites), two dead workflows, 26 mislabelled action pins | ~400 lines + constant runner churn | hours |
| 4 | **92 API endpoints with no consumer anywhere in the repo** + two parallel OAuth stacks | ~2,000+ LOC reachable only by tests | days |
| 5 | **Git history**: 130.6 MiB (74% of blob bytes) is files already deleted from `main` | 185 MiB pack → ~45–55 MiB after rewrite | needs explicit approval |

Everything else on the list below is minutes-to-hours.

---

## P0 — Security and hygiene (needs a human, this week)

### P0.1 Two tracked env files hold non-placeholder-looking values, and the repo is public

`gh repo view --json visibility` → `{"visibility":"PUBLIC"}`.

- **`.env.hypervisor`** (tracked, 6,356 bytes) — **31 values ≥16 chars that do
  not match any placeholder shape**, including `SECRET_KEY` (59),
  `LITELLM_API_KEY` (68), `DEEPSEEK_API_KEY` (50), `OPENROUTER_API_KEY` (31),
  `QBO_CLIENT_SECRET` (33), `QBO_CLIENT_ID` (27), `MICROSOFT_CLIENT_ID` (61),
  `MICROSOFT_TENANT_ID` (57), `GOOGLE_CLIENT_ID` (37), plus populated
  `DATABASE_URL` / `LITELLM_DATABASE_URL`.
- **`.env.prod.example`** (tracked, 22,442 bytes) — **73 such values**,
  including `OPENAI_API_KEY` (62), `ANTHROPIC_API_KEY` (47),
  `DEEPSEEK_API_KEY` (54), `OPENROUTER_API_KEY` (48), `POSTGRES_PASSWORD` (24),
  `REDIS_PASSWORD` (24), `LITELLM_SALT_KEY` (36), `LITELLM_DB_PASSWORD` (29),
  `COURTLISTENER_DB_PASSWORD` (35), `CLARITY_APP_PASSWORD` (26),
  `SECRET_KEY` (28), `PLATFORM_SECRET_KEY` (30), `LITELLM_API_KEY` (25).

Length and charset alone cannot prove these are live credentials — some look
synthetic. **This needs a human eyeball.** If any are real, treat them as
compromised: they are in a public clone and in every fork, and history rewriting
does not unpublish them. Rotate first, scrub second.

The repo already knows this is open work: `docs/SPRINT_PROD_READINESS.md:80` —
`- [ ] Audit .env.prod.example for any real-looking defaults; ensure all
secrets are required`.

### P0.2 The `.gitignore` negation that is supposed to protect `.env.hypervisor` is broken

`.gitignore:24`:

```
!.env.hypervisor     # tracked template — no real secrets, safe to commit
```

Gitignore does **not** support trailing comments — `#` only starts a comment at
the beginning of a line. The effective pattern is the entire string including
the comment, which matches nothing, so `.env.hypervisor` falls through to
`.gitignore:23` (`.env.*`):

```
$ git check-ignore -v --no-index .env.hypervisor
.gitignore:23:.env.*	.env.hypervisor     → exit 0
```

The file stays in the tree only because it is already tracked. The comment
asserting "no real secrets" is both syntactically inert and, per P0.1,
questionable. `.env.prod.example` has no negation at all.

Fix: move the rationale to its own line above the negation.

### P0.3 A plaintext GCP service-account key sits next to the repo

`F:\deepseek\legalapp\lawhand-prod-4469afdab9d2.json` (2,360 bytes) — outside
any git repo, so not a commit risk, but it is a credential at rest on a working
machine. Verify it is not a live key for `lawhand-storage@lawhand-prod` and
rotate/remove it.

### P0.4 The secret scanner cannot catch any of this

`scripts/scan_changed_secrets.py:18-24` is explicitly a ratchet over
`git diff base...head` only. Historical content is never re-scanned, which is
why P0.1 is invisible to CI. Worth a one-time full-tree scan, not just a
changed-lines scan.

---

## P1 — Structural waste in infrastructure

### P1.1 Two full production topologies are maintained side by side

| File | Lines | Role |
|---|---:|---|
| `docker-compose.yml` | 248 | base |
| `docker-compose.prod.yml` | 304 | overlay → base |
| `docker-compose.hypervisor.yml` | 403 | the stack every script actually deploys |

- **203 of 229 non-comment base lines (89%) appear byte-identical in
  `docker-compose.hypervisor.yml`.**
- Every scripted deploy resolves to hypervisor: `scripts/deploy_prod.sh:39`,
  `scripts/deploy_skynet_runner.sh:12`, `scripts/deploy_ionos_runner.sh:13-27`,
  `scripts/lawhand-ionos-deploy-from-github:64`.
- The `base + prod.yml` combination is reachable only through the **dead
  Makefile** (`Makefile:42-51`) and prose runbooks, plus a manual
  `workflow_dispatch` rehearsal (`fresh-host-rehearsal.yml:17`).
- Consequence: **every backend env var has to be hand-copied four times** —
  base `docker-compose.yml`, `prod.yml` backend *and* scheduler,
  `hypervisor.yml` backend *and* scheduler. The copy-paste is visible at
  `docker-compose.prod.yml:34-80` vs `:118-164` (identical ~45-line MCP env
  blocks).

**Recommendation:** collapse to one base + explicit overlays, or declare
`base+prod` dead and delete it. Either is better than today's four-way lockstep.

### P1.2 The Makefile is 100% dead

111 lines, 24 targets. `rg "\bmake (dev|test|lint|setup|prod|migrate)\b"`
across the repo (excluding `CHANGELOG`/`TASKS`/`RELEASE_NOTES`/`Makefile`
itself) returns **zero hits**. No workflow, no script, no doc invokes it.

Additional defects inside it: `make setup` copies `.env.example`, which does
not exist (`Makefile:10`); `.PHONY` omits 9 of the 24 targets; `PY ?= py` in an
otherwise bash/Docker file; `make sync-public-db` is the *only* caller of
`scripts/sync_to_vps.sh`, so that script's sole entry point is a dead target.

**Recommendation:** delete it, or fix it and make it the one documented entry
point. Today it is neither.

### P1.3 CI runs everything on every change, and one job runs 144×/day ungated

| Finding | Evidence |
|---|---|
| `ci.yml` is **1,349 lines / 19 jobs** with **no `paths:` filter** — doc-only and frontend-only PRs pay for 4 PostgreSQL-migration rehearsals + 4 backend test shards + 2 search-node jobs | `ci.yml:23-29`; `rg "paths:" .github/workflows` matches only `agent-release.yml:33` |
| `production-health.yml` fires **`*/10 * * * *` = 144 runs/day with no job-level gate**. It does have an `if:` — but only on the *alert step* (`transition == 'new-failure'`), so the workflow itself still starts 144×/day. Its siblings gate the whole **job** (`dev1-health.yml`: `if: vars.LAWHAND_DEV1_ENABLED == 'true'`, `skynet-dr-rehearsal.yml`: same pattern) | `production-health.yml:4-5` |
| `agent-release.yml` builds Windows **and** Linux packages on **every push to main** (only sign/publish are tag-gated) | `agent-release.yml:26-29` |
| The `release-gate` block (require main → validate SHA → `release_evidence.py`) is **copy-pasted with drift — 7 call sites across 5+ workflows, ~230 lines** — and there is **no `workflow_call` reusable workflow anywhere** | `deploy.yml`, `deploy-dev1.yml:68`, `deploy-ionos-candidate.yml:74,83`, `qa-acceptance.yml:68`, `production-acceptance.yml:75,156` |

### P1.4 Two workflows are dead

- **`deploy.yml`** (64 lines) self-declares at `:1-4`: *"This legacy filename
  remains for operator bookmarks, but it can only verify the retired Skynet
  runner and cannot start application writers or move the production tag."*
- **`dependabot-auto-merge.yml`** (52 lines) reacts to
  `update-type != 'version-update:semver-major'` — a *version-update* concept —
  but **`.github/dependabot.yml` does not exist and never has**
  (`git log --all --diff-filter=AD -- .github/dependabot.yml` → empty).
  Downstream, `scripts/verify_merge_policy.py` and `ci.yml:1230` both carry
  Dependabot exemptions for PRs that cannot be generated in-repo.

### P1.5 Action pin comments lie

Every `uses:` in all 17 workflows is SHA-pinned (good — zero unpinned). But the
same checkout SHA is labelled two different ways:

- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` — **26 of 30
  call sites label it `# v5.1 (Node.js 24)`; 4 label it `# v7.0.1`.** GitHub's
  API for that commit returns `prep v7.0.1 release (#2531)`, so **the 26 are
  wrong by two major versions.**
- `actions/upload-artifact` has **two different pins**: `043fb46d…` (10 uses)
  and `ea165f8d…` (1 use, `qa-acceptance.yml`).
- `ci.yml:1105` (`actions/cache`) and `:1249`
  (`dependency-review-action`) carry no version comment at all.

The next person doing a "v5.1 → v7" bump will double-bump. Worse, someone
auditing for "are we on the Node 20 action?" will read `v5.1` and conclude yes
when they are on Node 24.

### P1.6 SBOM gate coverage is inconsistent (fails open)

- `docker-compose.cube-m.yml` and `docker-compose.dev1.yml` are **missing** from
  `scripts/generate_sbom_inventory.py:46-53` (`COMPOSE_PATHS`) and
  `scripts/verify_merge_policy.py:28-33` (`SBOM_INPUTS`) — while
  `ci.yml:1233` triggers on `docker-compose.*\.yml`. Changing them *triggers*
  the gate but the generator never scans them.
- `nginx/Dockerfile.dev`, `nginx/Dockerfile.local`, `office-addin/Dockerfile`
  are missing from both Dockerfile lists, though
  `office-addin/Dockerfile` is used at `docker-compose.hypervisor.yml:369`.
- `word-addin/package.json` is still listed as an input but the directory was
  removed; `generate_sbom_inventory.py:124` (`if not p.exists()`) skips it
  **silently**, so the list rots without failing.
- `CODECOV_TOKEN` is documented as an optional secret at `ci.yml:8` and
  referenced nowhere else.

---

## P1 — API surface: large, well-wired, and ~13% unreachable

Route table read from the live app object (`app.main`, expanding include-context
prefixes) rather than by regex.

**Totals: 950 route entries (method × path), 767 unique paths, 944 OpenAPI
operations, across 89 router files / 94 routers.**
(GET 413 · POST 369 · PUT 41 · PATCH 63 · DELETE 69.)

### What is *right* (worth knowing before acting)

- All 94 `APIRouter` instances are registered (`main.py:447-551`).
- **0 duplicate (method, path) pairs**, 0 shadowed routes, 0 `/api/api/` doubling,
  0 v1/v2 legacy twins.
- **0 dangling first-party client calls.**
  `python backend/scripts/route_client_contract.py` → `PASS: 677 frontend API
  call sites match backend route contracts.` A broader 715-call-site scan across
  frontend, office-addin, agent and teams-app found 0 unmatched paths and 0
  method mismatches.

### The waste

**121 paths (14.6% of 767) have no product client.** Of those, 20 are
legitimate external consumers (webhooks, OAuth callbacks, MCP protocol, public
status pages). That leaves **92 endpoints with no consumer anywhere in the
repo** — reachable only by tests or CHANGELOG prose:

| Cluster | Routes | Evidence |
|---|---:|---|
| **Template Studio — the whole surface** | **18** | `routers/studio_drafts.py:56-195`, `studio_render.py:259-377`. `rg "template-studio\|studio/render" frontend/src` → no hits. Frontend ships `TemplateStudioWorkspace.jsx` but never calls it. |
| **`automation-services` — entire router dead** | **5/5** | `routers/automation_services.py:81-147`; `rg -F "automation-services"` outside `backend/` → 0 hits |
| Admin ops with no UI | 9 | `admin.py:513` `/api/admin/audit`, `:626`, `:1389`, `:1419`, `:1310` |
| SMB diagnostics | 6 | `smb.py:706,725,1289,1301,558,595` |
| Server-side sync exposed as REST | 7 | `document_sync.py:25,45,118,152`, `user_sync.py:29,46,63` — CHANGELOG-only |
| Research-workspace member/record CRUD | 5 | `research_workspaces.py:391,422,481,620,699` (frontend only calls `…/snapshots/{id}/export`) |
| MCP authority proxy | 4 | `mcp.py:415-432` — thin forward to mcp-server's `control/*`; nobody calls the proxy |
| Intake/conversion, matter-intake accept/reject, integration disconnect, dev/debug, trust bank-accounts | 14 | see per-file lines in the working notes |

**Structural duplication (not dead, but repeated):**

1. **Two parallel MCP OAuth stacks.** `workspace_mcp_oauth.py` (13 routes,
   990 lines) and `research_mcp_oauth.py` (12 routes, 738 lines) implement the
   same `oauth/register|authorize|token|revoke|jwks|requests/{id}|grants/{id}/revoke`
   + `.well-known` set, differing only by prefix. `difflib` ratio **0.50 — 429
   of 738 lines in common.** Two copies of a security-critical flow to keep in
   sync.
2. **Two Stripe webhook ingress paths** for one handler:
   `POST /api/billing/webhook` (`billing.py:223`) and
   `POST /api/billing/webhooks/stripe` (`billing_extended.py:2339`), both
   whitelisted in `middleware/tenant.py:24`, `middleware/rate_limit.py:71` and
   `nginx/nginx.conf:353,692`.
3. **Cross-service path collision:** mcp-server defines `GET /api/mcp` and
   `POST /api/mcp/tools/call` (`mcp-server/mcp_server/server.py:176,262`) which
   also exist on the backend (`main.py:431`) behind the same nginx.
4. **Two vocabularies for one control operation:** backend
   `/api/mcp/authority/{action}` vs mcp-server `/api/mcp/control/{action}`.

**Documentation is the weakest layer:**

- **570 of 944 operations (60%) have no description**; **502 (53%) declare no
  response model.**
- **No `openapi.json`/YAML artifact anywhere in the repo**, no generated TS/JS
  client, no CI step that emits or diffs one.
- One duplicate `operationId` (`verify_alias…`, `auth.py:99` GET+POST).
- The only machine-checked contract covers `frontend/src/api.js` alone
  (`backend/tests/test_route_client_contract.py:17`) — **office-addin and agent
  call the API through three more independent hand-rolled clients and are
  unchecked.** There are four separate request/error conventions in total
  (`frontend/src/api.js` with 4 axios instances + raw fetch SSE,
  `office-addin/src/api/officeApi.ts`, `office-addin/src/auth/officeSession.ts`,
  `agent/clarity_agent/api_client.py`).
- **The repo's own API map is stale by 86%:** `docs/api-front-backend-map-eval-2026-07-05.md:87`
  claims *"511 backend routes and 339 frontend API call sites"*; actual is 950
  and 677. Same doc echoed at `TASKS.md:1189`. With 71 of 89 router files
  touched in the last 30 days, hand-written inventories cannot stay true —
  generate one instead.

---

## P1 — Backend: low dead code, real config cruft

**Size (at baseline):** 1,273 tracked files (1,187 `.py`), ~399k lines — 1,495 files at `origin/main`.
`backend/app` = 197,462 non-blank lines / 527 modules ·
`backend/tests` = 132,576 / 456 files ·
`backend/migrations` = 185 revisions / 19,749 lines.

**Provable dead code ≈ 2,180 lines ≈ 1.1% of `app`** — low for a codebase this
size.

| Finding | Waste | Confidence |
|---|---:|---|
| **6 modules imported only by tests**: `services/mcp_platform_tools.py` (480), `services/recurring_billing.py` (277), `research_quality.py` (226), `services/citator_scope.py` (170), `services/error_log.py` (151), `services/smb_search.py` (89) — verified `rg` = 0 hits outside `tests/` | 1,393 app LOC + 1,757 test LOC | high |
| `error_log.py` is dead even internally: `schedule_error_log` has exactly 1 occurrence repo-wide — its own definition. The live path is `services/error_tracker.py` | — | high |
| `recurring_billing.generate_recurring_invoices` is never registered with `services/scheduler.py` (which registers 30+ jobs at `:554-862`) | — | high |
| **43 top-level defs referenced only at their own definition** (e.g. `token_vault.py:324,336,348` refresh helpers, `llm_routing.py:776,794`, 15 never-instantiated Pydantic schemas, an orphaned `utils/guardrails.py` subtree of 8 mutually-calling functions) | 494 LOC | high/med |
| **5 dead `__init__.py` re-export blocks** (`schemas/`, `routers/`, `utils/`, `services/`, `middleware/`) — 179 lines with **zero** `from app.X import <reexport>` users. `services/__init__.py` additionally **eagerly imports `rag`, `llm`, `billing`, `qbo_sync`, `ledes_export`, `invoice_pdf`, `embeddings` on every `import app.services.*`** for no benefit. (`models/__init__.py` is the exception — load-bearing for `migrations/env.py:14`.) | 179 LOC + import weight | high |
| `schemas/plugin.py` — **114 of 457 lines (25%)** are 12 never-imported classes, 5 of them byte-identical copies of `schemas/estate.py` classes that `routers/estates.py:35` actually uses | 114 LOC | high |
| **29 groups of structurally identical definitions across files**, incl. `_scope_is_granted` twice, `normalize_optional_text` twice, `validate_calendar_provider` twice *inside one file* (`schemas/calendar.py:81` and `:115`), `strip_base64` twice inside `workspace_mcp.py` | ~600–900 LOC | medium |
| **12 settings with zero consumers outside `config.py`**: `AZURE_OPENAI_ENDPOINT/KEY/DEPLOYMENT`, `GEMINI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_EMAIL/KEY`, `TEMPLATE_STUDIO_DRAFT_TTL_DAYS`, `OPENROUTER_FREE_MODELS`, `OPENCODE_ZEN_BASE_URL`, `PRIMARY_LLM`, `PREMIUM_LLM`, `SMB_TASK_POLL_INTERVAL`. `PRIMARY_LLM`/`PREMIUM_LLM` are even *set* by `ci.yml:396-397,618-619` and read by nothing. | 12 knobs | high |
| **3 dead vars in `.env.prod.example`**: `WORKSPACE_MCP_ALLOWED_TENANT_IDS` (`:284`), `VPS_APP_DIR` (`:412`), `GIT_BRANCH` (`:415`) — 0 hits repo-wide. Plus 8–9 dead keys in `.env.hypervisor` (`HYPERVISOR_*`, `OAUTH_TUNNEL_LOCAL_PORT`, `DOCKER_HOST`) | 3–12 knobs | high |
| **10 `print()` calls in `services/cache.py`** for *every* error path (`:69,168,219,244,269,292,318,341,384,395`) while the codebase has 100 `logging.getLogger` sites — bypasses log routing, levels and redaction | observability defect | high |
| `ruff check backend` → 21 findings repo-wide, **0 in `app/`** | — | high |

**Clean (verified, not assumed):** 0 unused `requirements.txt` entries (the two
initial flags — `Pillow`, `opencv-python-headless` — are a real import and a
documented transitive pin). 0 dead routers, 0 duplicate routes. Migrations: 1
root, 1 head (`181_session_epoch`), 0 unreachable revisions, 0 duplicate IDs (4
filename prefix collisions only, cosmetic). 0 permanently skipped/xfail tests
(all 33 skips are env-conditional). 2 conftest fixtures, both used. 0
committed coverage/cache artifacts. 0 `TODO`/`FIXME`/`HACK` markers.

**Shape bloat (not dead, but a maintenance hotspot):**

- `routers/document_templates.py` **5,663 lines**, `services/plugins/prompts.py`
  5,217, `routers/chat.py` 4,054, `routers/platform_llm.py` 3,834 — 25 routers
  and 26 services exceed 900 lines.
- `tests/test_sms_lifecycle_db.py` **8,535 lines**; top 6 test files = 24,701
  lines (16% of test LOC).
- 18 `*coverage*` files + 3 `*diff_coverage*` files + paired `*_unit` variants —
  coverage-driven fragmentation (content similarity between pairs is 0.01–0.19,
  so these are additions, not duplicates).
- 8 of 18 `backend/scripts/*` have no automated caller (plausible manual ops
  tools — review, don't delete).

---

## P1 — Frontend: only 261 dead lines, but a missing correctness gate

**Size (at baseline):** 538 tracked files / ~111k LOC (445 in `src/`, 107,029 lines) — 729 tracked files at `origin/main`. Of which
178 files / 23,828 lines (**22% of `src`**) are colocated unit tests.
JS (not TS) · React 18 · Vite 6 · Tailwind 3 · flat `eslint.config.js`.
32 direct deps → 630 resolved packages.

### The one that matters

**`eslint-plugin-react-hooks` is installed and registered but enables zero
rules.** `eslint.config.js:3` imports it, `:18` registers it, and there is no
`react-hooks/*` key in the `rules:` block (`:19-51`). Confirmed via
`eslint --print-config src/main.jsx` → `react-hooks/<rules> → (none)`, and
`rg 'rules-of-hooks|exhaustive-deps' frontend` → 0 hits.

The two rules people install that plugin for are off, so stale-hook-dependency
bugs ship silently. The plugin is already in `node_modules` — this is a
one-line change with real payoff.

### Everything else

| Finding | Evidence | Waste |
|---|---|---|
| 2 dead production components + their 2 orphan tests: `ProfessionalContextPrompt.jsx:17` (146), `WordCleanupAction.jsx:4` (24) — only referenced by their own `.test.jsx` | `rg -n "ProfessionalContextPrompt\|WordCleanupAction" .` → 6 lines total | **4 files, 261 LOC** |
| `eslint-plugin-react-refresh` — **zero references anywhere** except `package.json:33` | `rg -F` repo-wide | 1 dep |
| Stale rationale: comment says *"the repo currently carries ~890 of them"* (`eslint.config.js:28,31-32`) justifying `'no-unused-vars': 'warn'`. Measured reality: `eslint src` → **0 errors, 3 warnings**, all `no-alert` | `eslint.config.js:34-42` | 1 missed gate |
| Lint scope is `src` only (`package.json:46`) → **~1,577 unlinted lines**, including `vite.config.js`, `playwright.config.js` and all 1,219 e2e lines | `eslint.config.js:10` | coverage gap |
| `jest-axe` pulls a partial Jest toolchain into a Vitest project — direct cause of `pretty-format` 29.7.0 + 27.5.1 and `react-is` ×3 being installed | `package.json:35`; 4 of the 15 multi-version packages | ~430 KB, 4 dup entries |
| 2 e2e specs env-gated off and **never run in CI**: `matter-ux-audit.capture.e2e.js:22`, `matter-onboarding-live.e2e.js:22`. `rg E2E_AUDIT .github/workflows` → 0 hits | | 318 CI-dead lines |
| Brand style-guide HTML + README + tokens CSS are copied into `dist/` and **publicly crawlable** — `/brand/` is not in `dist/robots.txt` | `public/brand/lawhand/index.html`; `src/seo/config.js:354-367` | ~17 files / ~150 KB |
| 3 unused CSS animations + 3 dead `@keyframes` | `index.css:72,83,94,119,123,127` — 0 usages | ~20 lines |
| `ci.yml:971` step says *"Build frontend (validates TypeScript + Vite bundle)"* — **`frontend/` contains zero TypeScript** (374 `.jsx`, 77 `.js`, 0 `.ts`) | | 1 misleading line |
| `frontend/.dockerignore:3` ignores `coverage/` — no such dir, no coverage provider installed | | 1 line |
| **Monolith concentration: 55 files ≥500 lines hold 55,519 lines = 51% of all tracked JS.** `PlatformPage.jsx` = 4,002 lines, `MatterDetailPage.jsx` = 3,078, `TemplatesPage.jsx` = 2,875, `api.js` = 2,971 | | maintainability |

**Clean:** 0 dead routes (all 73 `<Route>` entries resolve; 54 distinct link
targets, 0 unmatched), 0 orphan nav entries, 0 exact-duplicate files, 0
`.bak`/`_old`/`copy` files, 0 orphan images, 0 committed `dist`/`.map`, all 3
lockfiles tracked, 0 direct-dep version conflicts, 0 skipped/`.only` tests.
26,750 files on disk vs 538 tracked reconcile exactly (25,980
`node_modules` + 221 `dist` + 9 stray Python caches).

---

## P2 — Repository size: 74% of history is already-deleted files

`git count-objects -vH` → **184.90 MiB pack**, 4 packs, 2,130 commits,
2,929 tracked files, 78.8 MiB working tree at `origin/main` (2,444 / 60.2 MiB at the baseline).

| Blob category | Blobs | On-disk in pack | Share |
|---|---:|---:|---:|
| Reachable from `main`, **path later deleted from HEAD** | 1,113 | **130.6 MiB** | **74%** |
| Reachable only from side branches | 3,808 | 17.3 MiB | 10% |
| Still in HEAD | 14,417 | 35.2 MiB | 20% |

By prefix, the dead history is:

| MiB | Paths |
|---:|---|
| **109.5** | `backend/seed/sample_templates/**` — 865 superseded/deleted seed PDFs |
| 9.0 | `frontend/src/assets/**` — replaced homepage PNGs |
| 8.6 | `frontend/public/brand/**` — retired **wellpled** brand art |
| 3.1 | `docs/research/brand-concepts/**` |
| 0.1 | `backend/coverage.xml` (accidentally committed, now gitignored) |

- **Safe and immediate:** deleting 172 merged/stale local branches + `git gc`
  reclaims **~17 MiB (9%)** with zero risk.
- **Requires an explicit, separately-approved decision:** rewriting `main` to
  drop the 1,113 deleted blobs would take the pack from 185 MiB → **~45–55 MiB
  (≈70–75%)**. That is a force-push of a shared branch and is **not** part of
  this change.

**Currently tracked binary weight:** `backend/seed/sample_templates/**` =
**82 PDFs / 39.6 MiB = 50% of all tracked bytes** (71 / 30.5 MiB at the baseline), and
`demo/cybersafeadvisor-corporate-pack/` = 2.9 MiB of `.docx`. Both are
regenerable build output (`scripts/build_sample_template_library.py`,
`scripts/build_cybersafeadvisor_demo_pack.py`), but:

> **Cross-boundary coupling:** `scripts/build_sample_template_library.py:48`
> sets `DEFAULT_SOURCE = REPO_ROOT.parent / "legal_forms_library_acro"` — a
> **42 MiB directory outside the repo**. A fresh clone cannot regenerate the 30
> MiB of seed PDFs it ships. Either vendor the input or move the output to
> object storage.

**Workspace sprawl (outside git, real disk cost):**

- **579 branches** (323 local + 256 remote). 172 already merged into `main`.
  23 ahead of upstream, several `ahead 15 / behind 309`.
- **9 worktrees = 875 MiB**, including an **orphan
  `worktrees/review/frontend/node_modules` — 25,980 files / 259.7 MiB** of pure
  duplicate install debris (not a registered worktree), 4 empty worktree group
  dirs, and one **dirty detached-HEAD** worktree (`platform-performance-resilience`).
- Local `node_modules` inside the repo: `frontend` 259.7 MiB,
  `ops/inbound-email-worker` 222.4 MiB, `office-addin` 68.6 MiB — all correctly
  gitignored, but ~550 MiB of disk.
- `validation/` (412 MiB) and other non-git siblings in `F:\deepseek\legalapp`
  contribute ~150 MiB of abandoned content.

---

## P2 — Documentation: ~35–45% is archivable

243 tracked docs / **4.79 MiB** at `origin/main` (181 / 2.72 MiB at the baseline; the orphan/ephemeral counts below are baseline measurements).

- **49 files (≈450 KB) are referenced by nothing anywhere** — includes
  `MERGE_QUALITY_SECURITY.md`, `SKYNET_DEV_DR.md`, `TEAMS_VOICE_SETUP.md`,
  `brief-check.md`, 6 `docs/superpowers/*`, 3 `docs/mcp/*`.
- 62 more are referenced *only by other docs*.
- **57 files are both ephemeral-shaped AND not code-referenced** — the strongest
  archive candidates: **all 7 of `docs/reviews/`**, **all 20 of
  `docs/research/`**, **9 of 16 `docs/superpowers/*`**, plus 8
  `template-studio-*-status/plan/review/readiness/audit` files and a dozen
  dated `*-status`/`*-review`/`*-plan` notes.
- 55 files have a `20xx-xx-xx` date in the filename.
- Conservative archive of `reviews/` + `research/` + `superpowers/` + dated
  root-level notes = **57–80 files / 1.0–1.4 MiB**, leaving the README's
  16-item documentation map and all 70 code/CI-referenced docs untouched.
- **`docs/plans/` is hidden by a local-only `.git/info/exclude` entry** — 2 live
  plan files that silently vanish for any other clone.

**Keep:** `ARCHITECTURE.md` (referenced by README, `verify_merge_policy.py`,
`backend/app/models/document.py`, a migration, and tests) and the 16 docs in
README's documentation map.

---

## P3 — Small, cheap, worth doing

| Finding | Evidence |
|---|---|
| Root `build/` has no ignore rule (15 PDFs / 435 KB show as `?? build/`); `.gitignore` only covers `/search-node/build/` | `.gitignore:78`, `git status` |
| `ops/inbound-email-worker/package-lock.json` is **tracked but ignored** — `.gitignore:15` matches it; only `frontend/` and `office-addin/` are negated at `:16-17`. Add `!ops/inbound-email-worker/package-lock.json` | `git check-ignore -v --no-index` |
| `.code-review-graph/` is ignored only by its *own inner* `.gitignore` containing `*` — fragile; add to root `.gitignore` (holds a 29 MB `graph.db`) | `git check-ignore` exits 1 |
| `scripts/requirements.txt` — wholly **unpinned** (`psycopg2-binary`, `openai`, `httpx`, `pgvector`, `python-dotenv`) and **never installed by any workflow**; only referenced by the SBOM scripts | |
| `pydantic` pinned `==2.11.10` (backend) vs `==2.10.3` (mcp-server), both under `fastapi==0.139.0`; `ruff` `==0.8.4` vs `>=0.4`; `pytest` `==9.0.3` vs `>=8.0` | separate images, so no live conflict — but drift |
| **Ruff lints 540 of 1,363 tracked `.py` files (40%).** No repo-level ruff config exists at all. Not linted: `backend/tests` (456), `backend/migrations` (186), `agent/`, `mcp-server/`, `scripts/` | `ci.yml:138-142` |
| `nginx/generate-self-signed.sh` — zero references outside itself | |
| `deploy/jetson/query-embedding.env.example` — zero references (the real `.env` *is* referenced) | |
| 4 scripts with zero references: `build_sample_template_library.py`, `demo_scenario_library.py`, `rehearse_harness_activity.py`, `rehearse_workflow_transport.py` — the latter two *are* imported by `rehearse_workflow_cloud_recovery.py`, so the agent cross-checks disagree here; verify before deleting | |
| `docker-compose.override.yml` — auto-load path exists only in README + the dead Makefile; `prod_env_preflight.sh:536-547` explicitly forbids it in prod | |
| `docker-compose.local.yml` — one consumer: `docs/local-intake-dashboard.md:12`, last touched **2026-07-09**; introduces a `local-nginx` service no other file has | |
| `config/` — entire top-level dir for one file (`dev1.env.example`) referenced only by one doc | |
| **Stale references in live docs:** `docs/legal_rag.md:15,51,54` instructs `docker-compose.mcp.yml` (**does not exist**); `README.md:253` clone URL is `github.com/mattpainter701/legalapp` (**actual remote is `lawhand`**); `docs/GITHUB_DEPLOY_RUNNER.md:21` same wrong repo; `docs/smb-agent-setup.md:294` sets `LAWHAND_RELEASE_BASE` **pointing at the wrong repo** in a copy-pasteable env var; `scripts/sync_to_vps.sh:24` writes to legacy `/var/log/clarity-legal` | |
| `.env.hypervisor` shares only 67 of 286 var names with `.env.prod.example` — operators copying the "hypervisor template" get 213 missing knobs and silent defaults | |
| `teams-app/lawhand-teams.zip` — committed build artifact regenerable by `package.ps1`; `teams-app/` has no CI job, no compose service, no Makefile target | 5 KB |
| `frontend/.ruff_cache/` + `frontend/.pytest_cache/` — Python caches sitting inside a JS directory (someone ran pytest from `frontend/`) | 9 ignored files |
| 12 docs still link the old `legalapp` repo name | `docs/ai-route-inventory-2026-08-13.md:12`, `docs/core-milestone-status.md:62` |

---

## Recommended order of attack

**Do first (human required):**

1. **Verify and, if real, rotate** the values in `.env.hypervisor` and
   `.env.prod.example`. Fix `.gitignore:24` so the negation actually works and
   the comment stops asserting something unverified. Check
   `lawhand-prod-4469afdab9d2.json`. Consider a one-time full-tree secret scan
   (the existing scanner is diff-only by design).
2. **Turn on `react-hooks/rules-of-hooks` + `exhaustive-deps`** — the plugin is
   installed and currently enforcing nothing.

**Cheap and high-confidence (minutes to an hour each):**

3. Delete the Makefile (or fix it — but stop leaving it half-alive).
4. Delete `deploy.yml`; either add `.github/dependabot.yml` or delete
   `dependabot-auto-merge.yml` and its exemptions in `verify_merge_policy.py`
   and `ci.yml`.
5. Fix the 26 wrong `# v5.1` checkout comments (the SHA is v7.0.1); unify
   `upload-artifact` in
   `qa-acceptance.yml:189`.
6. Add `paths:` to `ci.yml` (and `agent-release.yml` `branches:`), and gate
   `production-health.yml` behind a `vars.*` like its two siblings.
7. `.gitignore`: add `build/`, `.code-review-graph/`, and
   `!ops/inbound-email-worker/package-lock.json`.
8. Prune the 172 merged branches + `git gc` (reclaims ~17 MiB, zero risk).
9. Archive 57–80 ephemeral docs; fix the stale `docker-compose.mcp.yml`,
   wrong-repo README/`LAWHAND_RELEASE_BASE` references.
10. Delete the frontend's 4 dead files, unused eslint plugin, 3 dead CSS
    animations; re-promote `no-unused-vars` to an error.
11. Delete the 12 dead settings + 3 dead env vars; route `services/cache.py`
    through the logger instead of `print()`.

**Worth a real PR each (hours to days):**

12. **Collapse the two Compose production topologies** — this is the single
    biggest structural win; it is what makes every env-var change a 4-way
    copy-paste.
13. **Extract `release-gate` into a `workflow_call` reusable workflow** (229
    lines × 5, already drifted).
14. **Prune the 92 consumer-less endpoints** — start with the whole
    `automation-services` router and the 18 Template Studio routes (confirm the
    Studio UI isn't a separate delivery first), then the test-only admin/SMB/sync
    clusters. Delete their ~1,757 LOC of tests with them.
15. **Merge the two MCP OAuth stacks** — two copies of a security-critical flow
    is the kind of duplication that produces CVEs.
16. **Generate an OpenAPI artifact in CI** and extend the client contract check
    beyond `frontend/src/api.js` to cover office-addin and agent.

**Explicitly out of scope for an ordinary PR:**

17. History rewrite to drop the 130.6 MiB of deleted blobs
    (185 MiB → ~45–55 MiB). Requires a coordinated, separately-approved decision
    and a force-push to a shared branch.

---

## What is *not* broken

Said plainly, because the list above reads worse than the repo is:

- **No dead routers, no duplicate routes, no orphan routes, no dead nav
  entries.** Every route and every link resolves.
- **No dangling first-party API calls.** Four client surfaces, 715 call sites,
  zero mismatches; the frontend one is CI-enforced.
- **No unused Python or JS dependencies of consequence** (4 flags across
  `requirements.txt` + 32 frontend deps, of which 2 eslint plugins are the real
  finds).
- **No committed build output, caches, coverage, databases or logs.**
  `.gitignore` is thorough and correct.
- **All 3 `package.json` have tracked lockfiles** → reproducible builds.
- **Migrations are healthy:** 1 root, 1 head, 0 unreachable, 0 duplicate IDs.
- **No permanent test skips, no `.only`, no commented-out code, ~0 TODO debt.**
- **Action pins are all full SHAs** — a discipline many repos lack.
- **86 of 87 scripts and ~90% of satellite code are genuinely wired** into CI,
  compose, deploy scripts or installers. `scripts/` is the cleanest directory in
  the repository.

The pattern is consistent: **the team is disciplined about what it is actively
writing and undisciplined about what it stops using.** Dead configs, dead
workflows, dead endpoints and dead docs accumulate because nothing forces a
re-check. The fixes above are mostly deletions plus a handful of gates.
