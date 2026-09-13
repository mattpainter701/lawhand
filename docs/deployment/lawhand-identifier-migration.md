# LawHand identifier migration (retire Clarity and WellPled)

The product has carried three names: **Clarity Legal** → **WellPled** →
**LawHand**. The customer-facing rebrand is done (`index.html`, PWA metadata,
Office/Teams display names, frontend copy all say LawHand). What remains are
**legacy identifiers** — names baked into environment variables, database
roles, storage keys, protocol headers, model aliases, and documents. They are
not affordances; they are compatibility anchors and must be migrated
deliberately.

This is the dedicated migration the WellPled cutover deferred. The
[WellPled rebrand doc](wellpled-rebrand-cutover.md) explicitly left
`clarity_app`, `clarity-*` aliases, `claritylegal-records`, the token issuer,
protocol identifiers, storage keys, manifest IDs, and `X-Clarity-*` headers
unchanged and said to "rename them only through dedicated migrations." This is
that migration, extended to remove the WellPled name as well.

## End state

| Space | Target |
| --- | --- |
| Env vars | `LAWHAND_*` |
| DB roles | `lawhand_app` (runtime), `lawhand_safety`, `lawhand_e2e` |
| Python package | `lawhand_agent` (console script `lawhand-agent`) |
| LiteLLM aliases | `lawhand-standard`, `lawhand-premium`, `lawhand-background`, `lawhand-<route>-r<rev>` |
| JWT | `iss=lawhand-legal`, `aud=lawhand-platform-api` |
| HTTP headers | `X-LawHand-Preview-ID`, `X-LawHand-Preview-Purpose`, `X-LawHand-Internal-Key` |
| Calendar extended property | `lawhand_task_id` |
| Cloud folder | `lawhand-records` |
| localStorage | `lawhand.*` |
| Accounting mode | `lawhand_native` |
| Import bundle format | `lawhand-tabs3-bundle` |
| PDF | font `LawHandTemplateUnicode`, preview salt `lawhand-pdf-preview-values-v1` |
| E-sign consent | keep `clarity-esign-consent-v1` records; new text is `lawhand-esign-consent-v2` |

Nothing in the codebase, config, or data should still read `Clarity`,
`clarity`, `WellPled`, or `wellpled` when this is complete (except the `v1`
consent string and historical records noted below).

## Principles

1. **Display vs. identifier.** Display text is already migrated. Identifiers
   move by **expand → migrate → contract**, except where the beta status below
   lets us rename directly.
2. **Beta posture.** There are no production customers yet. Where the only
   holder of an old name is this repository or a self-hosted test host, rename
   directly. Keep a compatibility path only where a value lives outside our
   control: **deployed agents**, **customer cloud data already written**
   (calendar events, cloud folders), and **legal evidence** (consent records).
3. **Never edit applied migrations.** Add new migrations; do not touch
   `backend/migrations/versions/*` already on `main`.
4. **Single source of truth.** Introduce `backend/app/branding.py`,
   `frontend/src/utils/brand.js`, and `agent/lawhand_agent/branding.py` so no
   future brand change scatters literals again.
5. **Instrumented contract.** An old name may be deleted only when a
   compatibility counter has read zero across a full release window.

## Do not rename

- `clarity-esign-consent-v1` and any stored consent records that reference it —
  rewriting the version string invalidates signed evidence. Add `v2` for new
  consents.
- The existing Teams `entityId` (`clarity-legal-personal`) and Office add-in
  IDs (`ClarityLegal.*`) unless the app is re-published; changing an app
  identity resets installs. Plan a new manifest + re-publish instead.
- Historical documents: `docs/research/**`, `dashboard/…/brand-*`,
  `CHANGELOG.md`, `TASKS.md`, and the WellPled cutover doc itself. They record
  the decision; leave them.

## Inventory and strategy

### A. LiteLLM model aliases — **the visible admin "Clarity"**

Current: `clarity-standard`, `clarity-premium`, `clarity-background`, and the
versioned `clarity-<route>-r<rev>` generated at runtime.

Blast radius: `litellm_config.yaml`, `backend/app/config.py`,
`backend/app/services/ai_price_card.py`, `backend/app/services/llm_routing.py`,
`backend/app/services/template_ai_profile.py`,
`backend/app/routers/platform_llm.py`, stored tenant `*_model` values, the
admin Platform/Admin pages, and their tests.

Plan (direct rename, beta):
1. Rename the aliases in `litellm_config.yaml` and the backend defaults; update
   the routing/price-card prefix checks.
2. Add a migration that rewrites stored `standard_model` / `premium_model` /
   `background_model` values from `clarity-` to `lawhand-`.
3. Regenerate the LiteLLM config and reload the gateway in the same deploy.
4. Update frontend defaults, placeholders, and tests.

### B. Agent environment variables

Current: 20 `CLARITY_*` variables (`CLARITY_SAAS_URL`, `CLARITY_API_KEY`,
`CLARITY_CONFIG_DIR`, `CLARITY_SMB_*`, `CLARITY_LOCAL_INDEX_*`,
`CLARITY_NATIVE_AUTHZ_ENABLED`, `CLARITY_SEARCH_IDENTITY_PUBLIC_KEY`, …) plus
`CLARITY_APP_PASSWORD` in deploy config.

Blast radius: `agent/lawhand_agent/config.py`, `agent/…/api_client.py`,
`agent/…/__main__.py`, `agent/…/service.py`, `agent/packaging/linux/*`,
`config/dev1.env.example`, `docker-compose.hyperion/prod.yml`,
`scripts/{deploy_dev1,prod_env_preflight,rehearse_fresh_host,test_dev1_topology}.sh`,
`scripts/init_clarity_app_role.sh`, CI, docs.

Plan:
1. Read `LAWHAND_*` first, fall back to `CLARITY_*` for one release
   (deployed agents are outside our control).
2. Write both in deploy scripts and `.env` examples; document `LAWHAND_*`.
3. Delete the fallback after telemetry shows no old-name reads.

### C. Database roles

Current: `clarity_app` (runtime, `NOBYPASSRLS`), and CI/test roles
`clarity_safety`, `clarity_e2e`.

Blast radius: `backend/scripts/provision_app_role.sql`, `backend/migrations/env.py`,
`backend/migrations/versions/057_rls_hardening.py` (reference only — do not
edit), `.github/workflows/ci.yml`, `docker-compose.*.yml`,
`config/dev1.env.example`, `README.md`, `docs/ARCHITECTURE.md`,
`docs/PROD_HARDENING.md`, `frontend/src/components/IntegrationsPanel.jsx`
(`clarity_native` is a separate class — see H).

Plan: `ALTER ROLE clarity_app RENAME TO lawhand_app` (Postgres preserves grants
and ownership), add a new migration to create/rename the role in fresh
environments, update connection strings and CI role provisioning, then remove
`scripts/init_clarity_app_role.sh` in favour of `init_lawhand_app_role.sh`.

### D. Python package and console script

Current: `agent/clarity_agent/` package; console entry `clarity-agent` still
documented alongside `lawhand-agent`.

Plan: rename the package to `lawhand_agent`, update entry points, packaging,
benchmarks, and `agent-release.yml`. Keep a thin `clarity_agent` package that
re-exports `lawhand_agent` for one release, then delete it.

### E. JWT issuer and audience

Current: `iss=clarity-legal`, `aud=clarity-platform-api`
(`backend/app/services/platform_auth.py`), plus `clarity-legal` references in
MCP and scripts.

Plan: sign with `lawhand-*`, **verify both** for the token max-age window, then
stop accepting the old values.

### F. HTTP headers

Current: `X-Clarity-Preview-ID`, `X-Clarity-Preview-Purpose`,
`X-Clarity-Internal-Key` (backend `main.py`, `document_templates.py`,
`routers/mcp.py`, `services/rag.py`, `frontend/src/api.js`, MCP server,
`scripts/ionos_stage_check.sh`).

Plan: emit new and old, read both, delete the old after telemetry shows no
legacy header. These are internal-API headers, so the contract window is one
release.

### G. External data already written

- **Calendar extended properties**: `clarity_task_id` and the Graph property
  GUID in `services/{google,microsoft}_calendar.py`. Dual-read old and new,
  write new, backfill, then retire.
- **Cloud folder**: **done in code, migration not yet run.** `ROOT_FOLDER_NAME`
  in `services/cloud_init.py` is now `lawhand-records`, with
  `LEGACY_ROOT_FOLDER_NAME` kept so the old name can still be recognised;
  `routers/integrations.py`, `services/storage_migration.py` and the platform
  docs follow it. New tenants get `lawhand-records`. Existing folders are
  renamed in the provider — bound by folder ID, so matter folders and document
  bindings are untouched — by
  `backend/scripts/rename_legacy_root_folders.py`, which reports affected
  tenants without `--apply`. `_match_matter`'s canonical-path fallback accepts
  either name so an un-migrated tenant still reconciles. This is
  customer-visible: the `--apply` run renames a folder inside the firm's own
  Drive/OneDrive/SharePoint, so it needs its own customer communication and is
  an operator decision rather than a deploy step.
- **localStorage**: `clarity.workspace.*`, `clarity.chat.*`. Migrate on load,
  then remove.
- **Accounting mode**: `clarity_native` across backend, frontend, and stored
  tenant config. Accept both, migrate rows, then drop.
- **Import bundle format**: `clarity-tabs3-bundle`. Accept both, then drop.

### H. Cosmetic and internal

- PDF font `ClarityTemplateUnicode` → `LawHandTemplateUnicode`.
- Preview salt `clarity-pdf-preview-values-v1` → `lawhand-…` (cache key; safe).
- Log dir `clarity-legal-logs` / `.gitignore /var/log/clarity-legal/`.
- WellPled residue: `mcp-server` FastAPI titles and `__init__` docstring,
  `nginx/nginx.conf` header, `nginx/generate-self-signed.sh` cert `O=`,
  `scripts/test_nginx_webhook_ingress.sh` expected titles, and the stale
  `docs/deployment/wellpled-rebrand-cutover.md` (superseded by this doc).

## Phases and PR breakdown

1. **PR 1 — model aliases (A).** Fixes the visible admin "Clarity"; self-contained.
2. **PR 2 — agent env + package (B, D).** Start the longest clock first.
3. **PR 3 — database roles (C).**
4. **PR 4 — protocol boundaries (E, F).** JWT, headers.
5. **PR 5 — persisted/external data (G).** Calendar, cloud folder, localStorage,
   accounting mode, bundle format.
6. **PR 6 — cosmetics + WellPled purge (H, plus doc sweep).**
7. **PR 7 — contract.** Remove every fallback, shim, old role, old alias, and
   legacy header; delete the WellPled doc; add the CI guard.

## Cross-cutting

- **Branding modules** (principle 4) land in PR 1 so later PRs consume them.
- **Telemetry**: each compat layer increments a counter when an old name is
  read. Contract (PR 7) is gated on those counters reading zero.
- **CI guard**: a test fails if `Clarity`/`clarity`/`WellPled`/`wellpled`
  appears outside an allowlist (`docs/research/**`, `dashboard/**`,
  `CHANGELOG.md`, `TASKS.md`, the `v1` consent string, and the compat shims
  during their window).
- **Tenant isolation is unaffected.** This is naming only; the RLS and tenant
  boundary tests must stay green throughout.

## Verification

- Staging (dev1) rehearsal for the agent env fallback, the role rename, and the
  cloud-folder dual-read.
- Round-trip tests: legacy env → new agent; new token verified by a verifier
  that still accepts the old issuer; legacy header accepted; old alias still
  routed during the window.
- Post-deploy: admin platform page shows `lawhand-*` and no `clarity`; generated
  PDFs, invoices, and e-sign certificates say LawHand; Office/Teams add-ins load;
  no legacy-name log lines.

## Rollback

Each phase is independently revertible: aliases are config, the role rename is
reversible with `ALTER ROLE … RENAME TO`, env fallbacks mean the agent never
depends solely on the new name, and the compat counters reveal any missed
reader before the contract PR removes the fallback.
