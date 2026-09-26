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

The waste is concentrated in **five places that are not the application code**,
ranked by criticality in the next section:

| # | Area | Waste | Effort |
|---|---|---|---|
| 1 | **Tracked env files in a public repo** contain secret-shaped values, the `.gitignore` guard is inert, and the secret scanner cannot see history | credential exposure | hours |
| 2 | **Two parallel production Compose topologies** whose `backend` env surfaces have *already drifted* (30 / 55 / 66 keys) | silent config divergence | days, or hours if the dead one is deleted |
| 3 | **CI**: no `paths:` filter, 144×/day health cron with no job-level gate, release-gate copied into 5+ workflows (7 call sites), two dead workflows, 26 mislabelled action pins | ~400 lines + constant runner churn | hours |
| 4 | **92 API endpoints with no consumer anywhere in the repo** (capability-gated, not open) + two parallel OAuth stacks sharing 429 of 738 lines | ~2,000+ LOC reachable only by tests | days |
| 5 | **Git history**: 130.6 MiB (74% of blob bytes) is files already deleted from `main` | 185 MiB pack → ~45–55 MiB after rewrite | needs explicit approval |

Everything else on the list below is minutes-to-hours.

---

## Criticality ranking

Priority sections (P0/P1/…) below are ordered by *effort and urgency*.
This table is ordered by **criticality = blast radius × likelihood**, which
sometimes disagrees with effort — a minutes-long fix can be critical, and a
days-long refactor can be merely wasteful.

**Scale:** **C1 Critical** — data or credential exposure; act regardless of
cost. **C2 High** — can silently produce wrong production behavior.
**C3 Medium** — bounded cost: waste, drift, or a gate that fails open.
**C4 Low** — pure bloat, no behavior change.

| # | Criticality | Finding | Blast radius if it bites | Likelihood | Fix effort |
|---|---|---|---|---|---|
| 1 | **C1** | `.env.hypervisor` (31) + `.env.prod.example` (73) hold non-placeholder values in a **public** repo; the `.gitignore` negation meant to protect one is inert | LLM provider keys, `SECRET_KEY` (session signing → forge sessions), QBO OAuth client secret, Postgres/Redis/LiteLLM/CourtListener passwords | **Already public — exposure is present, not probabilistic** | hours |
| 2 | **C1** | Plaintext GCP service-account key at `F:\deepseek\legalapp\lawhand-prod-4469afdab9d2.json`, beside the repo | Object storage behind the app | Present, unrotated | hours |
| 3 | **C1** | `scripts/scan_changed_secrets.py:18-24` is **diff-only by design** — historical content is never rescanned | *This is why #1 is invisible to CI.* Any future secret lands in history unflagged | Certain | hours |
| 4 | **C2** | Compose topologies declare **different env surfaces** — `backend` has 30 / 55 / 66 keys across base / prod / hypervisor; `prod.yml` sets `TOKEN_ENCRYPTION_KEY` with **no `:-` fallback** and hypervisor omits it entirely | Switching topology silently changes what the backend receives: credential encryption (`token_vault.py:36` raises) or MCP product billing flags off | Triggered by any topology switch; `fresh-host-rehearsal.yml:17` exercises **both** | days, or hours if `base+prod` is deleted outright |
| 5 | **C2** | `eslint-plugin-react-hooks` installed and registered with **zero rules enabled** — no `rules-of-hooks`, no `exhaustive-deps` | In a legal app a stale closure renders **the wrong matter's data** with no error | Already shipping such bugs undetected | **minutes to enable** + triage whatever it flags |
| 6 | **C2** | Two parallel MCP OAuth stacks: `workspace_mcp_oauth.py` vs `research_mcp_oauth.py`, **429 of 738 lines shared** | A fix applied to one and not the other = an authz inconsistency between two tenants' MCP surfaces | Certain over time; already 0.50 drift ratio | days |
| 7 | **C2** | `production-health.yml` runs **144×/day with no job-level gate** (the `if:` is on the alert *step*, not the job) | Log/alert fatigue — the run that actually detects an outage is lost among 144 routine ones | Daily, ongoing | hours |
| 8 | **C3** | `ci.yml` has **no `paths:` filter** — 19 jobs (4 migration rehearsals, 4 test shards, 2 search-node) run on doc-only PRs | Runner minutes, and slower feedback on everything | Every PR | hours |
| 9 | **C3** | `release-gate` copy-pasted into **5+ workflows / 7 call sites, already drifted** — no `workflow_call` reusable workflow exists | A release-policy change lands in some gates and not others | On the next policy change | hours |
| 10 | **C3** | SBOM input lists are incomplete and **fail open**: `cube-m`/`dev1` compose and 3 Dockerfiles missing; deleted `word-addin/package.json` still listed and skipped silently at `generate_sbom_inventory.py:124` | Supply-chain gate silently covers less than it claims | On any dependency change in a missed file | hours |
| 11 | **C3** | **26 of 30** `actions/checkout` pins are labelled `# v5.1 (Node.js 24)`; the SHA is **v7.0.1** (verified via GitHub API). Two different `upload-artifact` pins in use | Next version bump double-bumps, or an auditor concludes "on Node 20" when on Node 24 | On the next dependency bump | minutes |
| 12 | **C3** | Two dead workflows: `deploy.yml` (self-declared retired), `dependabot-auto-merge.yml` (**`.github/dependabot.yml` has never existed**), plus exemptions for it in `verify_merge_policy.py` and `ci.yml:1230` | Misleading surface; a reviewer trusts an auto-merge path that cannot fire | On review | minutes |
| 13 | **C3** | **92 endpoints with no consumer anywhere** (18 Template Studio, 5 dead `automation-services`, admin/SMB/sync clusters) + ~1,757 LOC of tests for them | *Not* open doors — spot-checked as `require_capabilities(...)`-gated. Cost is attack surface and unexercised authz logic, where a future regression hides | Slow, structural | days |
| 14 | **C3** | **12 settings + 3 `.env.prod.example` vars with zero readers**, including `PRIMARY_LLM`/`PREMIUM_LLM` which **CI itself sets** (`ci.yml:396-397,618-619`) | An operator tunes a knob and nothing changes — silent misconfiguration | On first use of the knob | minutes |
| 15 | **C3** | `services/cache.py` routes **every error path through `print()`** (10 sites) while the codebase has 100 `logging.getLogger` sites | Cache failures invisible to log shipping, levels, and redaction | Every cache failure | minutes |
| 16 | **C3** | Stale references in *live operator docs*: `docs/legal_rag.md:15,51,54` → `docker-compose.mcp.yml` **does not exist**; `docs/smb-agent-setup.md:294` sets `LAWHAND_RELEASE_BASE` **pointing at the wrong repo**; `README.md:253` clone URL wrong | An operator follows a runbook and fails on step 1 | On first use by a new operator | hours |
| 17 | **C3** | Makefile **100% dead** (24/24 targets, 0 references); `make setup` copies a nonexistent `.env.example`; its `sync-public-db` target is the only caller of `scripts/sync_to_vps.sh` | Newcomer runs `make dev`, gets an error, concludes the repo is broken | On onboarding | minutes |
| 18 | **C4** | Dead code: ~2,180 backend lines (1.1% of `app`), 43 unreferenced defs, 5 dead `__init__` re-export blocks (one with eager imports), 261 frontend lines | None today; carrying cost only | — | hours |
| 19 | **C4** | Frontend minor: unused `eslint-plugin-react-refresh`, stale "~890 unused vars" comment demoting `no-unused-vars`, 3 dead CSS animations, brand style-guide HTML shipped in `dist/` and crawlable, lint scope missing 1,577 lines | None; a crawlable internal page is the only externally visible item | Low | hours |
| 20 | **C4** | `docs/`: 49 orphans referenced by nothing, 57 ephemeral-and-unreferenced → **35–45% archivable** | Discoverability only | — | hours |
| 21 | **C4** | Repo/workspace size: **130.6 MiB (74% of blob bytes) is already-deleted files**; 579 branches; 9 worktrees = 875 MiB incl. a 260 MiB orphan `node_modules` | Clone time and disk | — | prune: minutes · rewrite: **explicit approval** |
| 22 | **C4** | Monolith concentration: 55 frontend files ≥500 lines hold **51% of all JS LOC** (`PlatformPage.jsx` 4,002); `routers/document_templates.py` 5,663; `test_sms_lifecycle_db.py` 8,535 | Review and merge-conflict cost, rises with every PR | Ongoing | per-file, over months |

### Hypothesised remediation

Sequenced by criticality, not effort. For each, the option we would actually
take first is marked **(A)**.

**C1 — this week, human required, no code changes needed to start.**

- **(A) Verify → rotate → scrub.** Read the two env files, classify each
  value as real/placeholder/synthetic. Rotate anything real *first* (LLM keys,
  `SECRET_KEY`, QBO client secret, DB passwords), then scrub the files to
  placeholders, then fix `.gitignore:24` by moving the rationale comment to
  its own line above the negation. Rotate the GCP service-account key and
  delete the file from disk.
  *Tradeoff:* if any key was real it is already in public history — scrubbing
  does not unpublish it, so rotation is mandatory and scrubbing is secondary.
- **B) Make the scanner see history.** Add a scheduled full-tree job running
  `scan_changed_secrets.py` (or gitleaks/trufflehog) over `HEAD`, separate from
  the existing changed-lines ratchet so the ratchet still does its job on PRs.
  *Tradeoff:* a full-tree scan will light up on the two env files immediately —
  land it **after** (A), or it will be red from day one and get muted.
- **C) Add a guard so this cannot regress:** a CI assertion that no tracked
  `.env*` file contains a value over N chars that is not in an allowlist.

**C2 — next, because each one is a silent-wrong-answer machine.**

- **(A) Compose: delete the dead topology rather than unify it.** Every
  scripted deploy uses `hypervisor.yml`; `base + prod.yml` is reachable only
  via the dead Makefile and prose runbooks. Delete `docker-compose.prod.yml`,
  fold its 4 backend / 8 scheduler-only keys into `hypervisor.yml`, delete the
  second legal-combo branch in `prod_env_preflight.sh:536-547`, and drop
  `base+prod` from `fresh-host-rehearsal.yml`'s matrix. Then add a ~15-line CI
  check asserting the per-service env-key set is identical across surviving
  topologies.
  *Tradeoff:* this is the *cheap* unification — it removes a whole topology
  instead of merging two live ones. It is only safe because `base+prod` is
  genuinely unreferenced by any script; if someone is using it by hand, the
  rehearsal matrix is the tell, and that has to be confirmed first.
  *Alternative (B):* keep both and extract a shared `docker-compose.backend-env.yml`
  fragment both include. *Tradeoff:* correct but slower, and keeps two
  topologies worth of drift surface alive.
- **(A) Turn the hooks rules on, then pay down what they flag.**
  `rules-of-hooks: error` and `exhaustive-deps: warn` in
  `frontend/eslint.config.js`. The plugin is already installed, so this is a
  one-line rules block.
  *Tradeoff:* expect a first run with findings; land `rules-of-hooks` as an
  error immediately (it finds real bugs) and ratchet `exhaustive-deps` from
  warn → error separately so the PR stays reviewable. This is the highest
  benefit-per-minute item in the entire document.
- **(B) Merge the two MCP OAuth stacks.** Extract the shared
  `register|authorize|token|revoke|jwks|requests|grants|well-known` flow into a
  parameterised factory keyed on prefix and storage adapter, leaving the two
  routers as thin wrappers.
  *Tradeoff:* touches a security-critical path, so it wants the existing OAuth
  tests as a safety net first — check coverage before starting. Do **not**
  attempt this in the same PR as any behavior change.
- **(A) Gate the health cron.** Add `if: vars.LAWHAND_PROD_HEALTH_ENABLED == 'true'`
  at the *job* level, matching `dev1-health.yml:18` and
  `skynet-dr-rehearsal.yml:18`. Optionally drop `*/10` to `*/30`.
  *Tradeoff:* if the cron is genuinely load-bearing for incident detection,
  gating it behind a var risks it being off in an environment that needs it —
  so set the var at the same time, and confirm no alerting depends on the
  10-minute cadence.

**C3 — batch into one "hygiene" PR series; each item is independent.**

- **(A) CI:** add `paths:` to `ci.yml` `push:`/`pull_request:` (exclude
  `docs/**`, `**.md`), then extract `release-gate` into a
  `.github/workflows/release-gate.yml` with `workflow_call` inputs for which
  workflows to require (`ci.yml`, `codeql.yml`, optional QA) — that input is
  exactly what the five copies currently diverge on.
- **(A) Delete dead workflow surface:** `deploy.yml`; either add
  `.github/dependabot.yml` (with a real `package-ecosystem` list) or delete
  `dependabot-auto-merge.yml` plus its exemptions in `verify_merge_policy.py`
  and `ci.yml:1230`.
- **(A) Fix pins mechanically:** rewrite the 26 `# v5.1 (Node.js 24)` comments
  to `# v7.0.1`, unify `upload-artifact` in `qa-acceptance.yml`, add comments
  to the two uncommented pins. Consider a CI check that a `uses:` comment
  matches the tag GitHub reports for that SHA — that converts this class of bug
  permanently.
- **(A) SBOM:** make `generate_sbom_inventory.py` **fail** (not skip) on a
  listed input that does not exist, and add the 5 missing compose/Dockerfile
  inputs. The fail-open is the actual defect; the missing entries follow from it.
- **(A) Delete the Makefile**, or fix it and make it the single documented
  entry point. Half-alive is the worst state. If deleted, re-home
  `scripts/sync_to_vps.sh` (currently reachable only through it) or delete that
  too.
- **(A) Config:** delete the 12 zero-reader settings and 3 dead env vars;
  decide whether `PRIMARY_LLM`/`PREMIUM_LLM` should be read (then read them)
  or stop setting them in CI. Route `cache.py` through `logging`.
- **(A) Docs fixes are one pass:** correct `legal_rag.md`,
  `LAWHAND_RELEASE_BASE`, README clone URL, `/var/log/clarity-legal`.
- **(B) 92 orphan endpoints — do not mass-delete.** Confirm Template Studio is
  not an in-flight delivery first (it has a full UI component and 18 routes);
  if it is, wire it. Otherwise delete `automation-services` outright (5 routes,
  0 references, clearly abandoned) and open a tracked issue per remaining
  cluster rather than a sweep, because each needs a product answer, not a
  grep answer.

**C4 — do opportunistically; nothing here blocks anything.**

- **(A)** Archive `docs/reviews/`, `docs/research/`, `docs/superpowers/` and
  dated root-level status/review notes into `docs/archive/` (57–80 files).
- **(A)** Prune the 172 merged branches + `git gc` — safe, reclaims ~17 MiB.
  Remove the 260 MiB orphan `worktrees/review/frontend/node_modules` and the
  empty worktree group dirs; resolve the dirty detached-HEAD worktree.
- **(B) History rewrite (185 MiB → ~45–55 MiB)** — **explicitly out of scope
  for an ordinary PR.** It is a force-push to a shared branch and needs its own
  decision, its own window, and coordination with every open PR and worktree.
  Note it also does not solve C1: rewritten secrets were already cloned.
- Deletions (dead modules, dead `__init__` blocks, `schemas/plugin.py` dupes,
  frontend's 4 dead files) are safe but low value — bundle them into whatever
  PR touches those files rather than making standalone noise.

**Suggested PR series, in order:**

1. **Secrets** (C1 ×3) — human, this week, no product code.
2. **Hooks rules on** (C2 #5) — minutes, highest payoff.
3. **Compose topology** (C2 #4) — the only C2 that needs a real PR.
4. **Health cron gate + CI `paths:` + release-gate extraction** (C2 #7, C3 #8, #9) — one CI PR.
5. **Dead workflow + pins + SBOM fail-closed + Makefile** (C3 #10–12, #17) — one hygiene PR.
6. **Config cruft + cache.py logging + stale doc refs** (C3 #14–16).
7. **OAuth stack merge** (C2 #6) — separate, careful, test-first.
8. **Orphan endpoints** (C3 #13) — per-cluster, product-gated.
9. **C4 cleanup** — opportunistic.

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
- Consequence: **the `environment:` block for `backend` is maintained
  independently in three files, and it has already drifted.** Measured key
  counts under `backend.environment` (and `scheduler.environment` where
  present):

  | File | `backend` env keys | `scheduler` env keys |
  |---|---:|---:|
  | `docker-compose.yml` | **30** | — |
  | `docker-compose.prod.yml` | **55** | **51** |
  | `docker-compose.hypervisor.yml` | **66** | **47** |

  The base is a clean subset of hypervisor (0 keys lost). But **`prod.yml`
  sets keys that `hypervisor.yml` does not**, and hypervisor is the file every
  scripted deploy uses:

  - on `backend`: `TOKEN_ENCRYPTION_KEY`, `TOKEN_ENCRYPTION_KEYS`,
    `MCP_PRODUCT_ENABLED`, `MCP_PRODUCT_CALL_PRICE_CENTS`
  - on `scheduler`: the above plus `MCP_SERVER_URL`, `MCP_UPSTREAM_API_KEY`,
    `MCP_OPERATOR_ASSERTION_SECRET`, `MCP_CITATOR_SCOPE_ASSERTION_SECRET`
  - hypervisor-only on `scheduler`: `APP_VERSION`, `APP_COMMIT`,
    `APP_BUILD_TIME`, `MIGRATOR_DATABASE_URL`

  `prod.yml:50,139` writes `TOKEN_ENCRYPTION_KEY: ${TOKEN_ENCRYPTION_KEY}` with
  **no `:-` fallback**. Because `environment:` takes precedence over `env_file`
  in Compose, an unset interpolation source becomes an *empty string that
  overrides* what `env_file` would have supplied — whereas `hypervisor.yml`
  omits the key entirely and inherits from `env_file` normally. `token_vault.py:36`
  then raises `"TOKEN_ENCRYPTION_KEYS or TOKEN_ENCRYPTION_KEY is required for
  credential storage"`.

  Whether this is harmless today depends entirely on the contents of the
  **untracked** `.env` — which is the finding: switching topology changes what
  the backend receives, and nothing in the repository shows you that. The
  copy-paste is also visible structurally at `docker-compose.prod.yml:34-80` vs
  `:118-164` (identical ~45-line MCP env blocks for backend and scheduler).

**Recommendation:** pick one. Either (a) collapse to a single base +
overlays and make the env block live in one place, or (b) declare
`base+prod` dead, delete it, and delete `prod_env_preflight.sh:536-547`'s
second legal-combo branch with it. Then add a CI assertion that the set of
env keys per service is identical across the surviving topologies — that is
~15 lines of Python and it converts a silent drift into a red build.

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
repo** — reachable only by tests or CHANGELOG prose.

**Important severity qualifier:** these are *not* unauthenticated holes.
Spot-checked and confirmed capability-gated — e.g. `automation_services.py:27-28`
declares `manage = require_capabilities("manage_workflows", "manage_matters")`
and `review = require_capabilities("approve_legal_work", "manage_matters")`,
so all 5 dead routes still demand elevated caps. The cost is therefore
**attack-surface and maintenance weight, not an open door**: 92 more handlers
to keep authorized, tested and reviewed, each with authz logic nobody has an
incentive to re-verify because nothing exercises it in production. That is a
slower kind of risk — it is where a future authz regression would hide
unnoticed.

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
3. **Cross-service path collision — latent, not live (corrected on
   re-inspection).** mcp-server defines `GET /api/mcp` and
   `POST /api/mcp/tools/call` (`mcp-server/mcp_server/server.py:176,262`) which
   the backend also defines (`main.py:431`). nginx resolves this today by
   *exact-match* locations `= /api/mcp`, `= /api/mcp/workspace`,
   `= /api/mcp/manifest`, `= /api/mcp/tools/call`
   (`nginx/snippets/mcp_transports.conf:4,15,29,40`), all of which
   `proxy_pass $upstream_backend` (`mcp_transport_proxy.conf:1`). The backend
   then proxies to mcp-server over the internal network via `MCP_SERVER_URL`
   (`config.py:368`). **So mcp-server's identical paths are currently shadowed
   and unreachable from outside** — this is duplicated surface, not a routing
   bug. It becomes a hazard the moment anyone adds an nginx route straight to
   the mcp-server container, because the two definitions would then disagree
   about behavior behind the same name. Flagging it as a trap to remove, not a
   defect to fix.
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

The ranked plan — criticality, blast radius, and a hypothesised fix with
tradeoffs for each item, ending in a nine-PR series — is in
**[Criticality ranking](#criticality-ranking)** near the top of this document.
That is the operative section.

The items below are the small ones that did not earn a row in the ranking
table but are still worth doing:

1. `.gitignore`: add `build/` (currently shows as untracked output),
   `.code-review-graph/` (ignored only by its own inner `.gitignore`), and
   `!ops/inbound-email-worker/package-lock.json` (tracked but ignored).
2. Delete the frontend's 4 dead files, `eslint-plugin-react-refresh`, and the
   3 unused CSS animations; re-promote `no-unused-vars` to an error now that
   the "~890" backlog it justified is gone (measured: 0 errors, 3 warnings).
3. Generate an OpenAPI artifact in CI and extend the client contract check
   beyond `frontend/src/api.js` to cover office-addin and agent — today three
   of four API clients are unchecked.
4. Prune the 172 merged branches + `git gc` (reclaims ~17 MiB, zero risk).

**Explicitly out of scope for an ordinary PR:** history rewrite to drop the
130.6 MiB of already-deleted blobs (185 MiB → ~45–55 MiB). Requires a
coordinated, separately-approved decision and a force-push to a shared branch.
It also does **not** remediate the C1 secrets finding — anything already
cloned stays cloned.

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
