# Auto pre-fill programme: audit status and handoff

**Date:** 2026-09-19 (updated 2026-09-20 after the Phase 4/5 commit)
**Branch:** `claude/pdf-auto-filing-mechanism-e5tqb5` (draft PR #572, base `main`)
**Companion docs:** [`smart-fill-engine.md`](smart-fill-engine.md) (the engine and Phase 2),
[`template-prepare-route-plan-2026-09-19.md`](template-prepare-route-plan-2026-09-19.md)
(Phases 3, 4, 5).

This document exists so an auditor, or the next session, can see in one place
what the programme promised, what shipped, how each piece was verified, what
is deliberately pinned, and what remains. It is a status record, not a design
document; the designs live in the companion docs.

## 1. The ask and the finding

The owner's ask: as soon as data exists in a matter, its documents should be
pre-filled and waiting for review, with a mechanism that is "engine like"
rather than a router routine; then, from Template Studio, a guided path to
fill, save into the matter, review, and send for e-signature; then a fast
click-through verification of the automated fills; and finally, treating the
matter's documents as a knowledge source, including scans and handwriting.

What the audit of the tree found on 2026-09-19 (all verified by reading and
then by the quirk campaign):

- Nothing initiated a fill. The resolver was a private function in a
  5,927-line router, mirrored branch-for-branch by a coverage module, called
  only from three user-driven routes.
- The declared-binding vocabulary was computed by running the resolver over a
  fabricated probe matter, so every new source had to be added in two places.
- Only plaintiff and defendant parties produced values; eight party roles were
  silent. Matter number, practice area, opened date and six contact columns
  were unreachable. No formatting for choice, checkbox or date fields. First
  writer won silently when two sources supplied one alias. The estate loaded
  only for a binding, so an unbound `estate_*` field passed the approval gate
  and rendered blank.
- The lead-to-matter conversion, the most important "data now exists" moment,
  emitted no event at all.

## 2. Phase status

| Phase | What | Status | Commit(s) | Evidence |
|---|---|---|---|---|
| 0 | Quirk campaign: 6 mock matters × convention PDF/DOCX + 5 seeded forms, resolve → render → read back, markdown/JSON report | Shipped | `2318934` | `tests/test_fill_campaign.py`, `tests/test_fill_campaign_seed_pdfs.py`, `tests/test_smart_fill_route_matter.py`, `scripts/rehearse_smart_fill.py`; filled outcomes 447 → 538 of 1,261 after 1b |
| 1a | Engine extraction: `FillSource` registry, `CandidateIndex` with collisions, `vocabulary()` from declarations, `prepare_fill()` without a request | Shipped | `6ac7c1c` | `tests/test_template_fill_engine.py` proves `vocabulary()` equals the old probe; all parity suites unchanged; ~560 lines leave the router |
| 1b | Reach and fit: every party role, matter/contact columns, `NAME_SYNONYMS`, formatters (state code↔name, checkbox, MM/DD/YYYY) | Shipped | `8cf91c8`, `7d349e3` | campaign fences flipped in the same commit; `tests/test_template_fill_formatters.py` |
| 2a | Initiation: `matter_created` from conversion, `document_prefill` durable job keyed `matter_id:facts_sha256`, readiness event and `GET /matters/{id}/document-prefill` | Shipped | `bc3394f`, `18b8f82` | `tests/test_document_prefill.py` (11), counts-only metadata asserted, no document/preview rows |
| 2b | Case Documents banner "N documents ready, X% filled" → review | Shipped | `bc3394f` | vitest banner + picker preselect |
| 3a | `/templates/prepare` route (Template, Matter, Populate, Review, Save), Studio "Use on a matter", library and probate entry points | Shipped | `a7c9010`, `031d3b7`, `29d1f1e` | `TemplatePreparePage.test.jsx`, `PrepareStepper.test.jsx`, `prepareRouting.test.js`; Generate dialog's 25 tests unchanged |
| 3b | Send step: signing descriptor on the render response, shared signature request form, DOCX-with-signatures defaults to PDF | Shipped | `c2c5a54` | `MatterSigningPlacements.test.jsx` (26) unchanged; `signatureRequestRules.test.js`; Send-step page cases; backend descriptor test extended |
| 2c | Rules can request a document (Stack A `document_propose` step) | Planned | — | needs a product decision on the run's actor |
| 3c | Sets: `documents-variables` endpoint, RLS test, sets library, prepare route for sets (browser-driven sequential save-all) | Shipped | CHANGELOG 2026.09.20.03 | `test_template_set_routes.py` (fan-out), `test_template_sets_rls.py` (live RLS), vitest sets page and Prepare set case |
| 3d | Service extraction, `document_fill_sessions` (migration now 197), durable `template_set_render` | Planned, three PRs | — | |
| 4a/4b | Click-through verification in Populate; verified names on the saved document | Shipped | see CHANGELOG 2026.09.20.01 | `templateFillReview.test.js`, Prepare page verification case, Generate dialog payload; `test_document_templates.py` descriptor test (event, row, list, response, 422) |
| 4c/4d | Verification persisted per session; readiness record counts | Planned with 3d | — | |
| 5a | OCR reaches matter documents (images accepted, confidence carried) | Shipped | CHANGELOG 2026.09.20.01 | `test_matter_fact_extraction_unit.py` (OCR candidates), `_postgres.py` (PNG source, empty scan, unsupported type) |
| 5b | `document_text_extractions` cache keyed by `document_sha256` (migration 197, new head) | Shipped | CHANGELOG 2026.09.20.01 | `test_document_text_cache.py` (once per digest and tenant, OCR path, image path, engine unavailable, migration RLS text); cache hit in `_postgres.py`; migration applied up, down and up on a scratch database |
| 5c | Template-anchored reading of a printed, hand-filled form (v1: scaled alignment, OCR per field crop, thumbnails); 5c-2 vision fallback per unreadable clip, opt-in and metered, off until `INTAKE_EXTRACTION_VISION_MODEL` is set | Shipped (v1 + 5c-2) | CHANGELOG 2026.09.20.01 | `test_template_form_reading.py` (windows, crop geometry, page-size scaling, thumbnails, failures), `test_matter_document_form_reading_postgres.py` (both routes, matched and unmatched readings, 404s) |
| 5d | `DocumentEvidenceSource` in the engine, lowest precedence, `review_required`; prefill digest and memoized loaders; `document_extracted` trigger | Shipped | CHANGELOG 2026.09.20.02 | `test_template_fill_evidence_postgres.py`, `TestDocumentEvidence`, all Smart Fill parity suites (255) unchanged |
| 5e | Matter-scoped index over cached text | Planned, later | — | |

## 3. What already existed and was reused (so the concern was narrower than feared)

- `app/services/matter_fact_extraction.py`: reads one matter document,
  proposes facts (AcroForm values, `Label: value` lines, patterns, optional
  metered AI pass), runs as the `matter_fact_extraction` job on every upload,
  files a review task; `accept()` writes through `intake_writeback`. The
  review list is `components/documents/MatterDocumentFacts.jsx` in the
  document preview panel. This is the "use AI to gather fields" button.
- `app/services/template_ocr.py`: local RapidOCR over pypdfium2 renders (25
  pages, 80M pixels, line confidence floor 0.35, label + handwritten value row
  merging) and an opt-in Azure Document Intelligence provider.
- `intake_writeback` and `template_fact_review`: human acceptance before a
  proposal reaches a matter field, with a signed proposal contract.
- Tenant gates: `TenantSettings.custom_config["intake_fact_extraction"]`
  (`enabled`, `ai_enabled`), per-user `premium_ai_enabled`, token budgets.

## 4. Invariants the programme keeps (and tests that pin them)

- A PDF is saved into a matter only with generation preview evidence minted by
  the same user within 30 minutes (`test_document_templates.py`); the prefill
  job stores counts and field names only, never values or bytes
  (`test_document_prefill.py`).
- First writer wins for an alias, and every losing write is recorded as a
  `Collision` (`test_template_fill_engine.py`).
- Declared bindings are never second-guessed by synonyms; synonyms apply on the
  name-match branch only, at 0.9 and `review_required`.
- A source loads when a field name matches its aliases, not only a binding
  (the estate lazy-load fix; the coverage module and the resolver agree).
- Every pre-existing binding path resolves through the same alias
  (`TestLegacyCompatibility`).
- Extraction from documents proposes; a human accepts; nothing writes on its
  own. Verification (Phase 4) is advisory and never a gate.
- `/render` and `/render-file` stay the only generation paths.

## 5. Known quirks and limits still open

From the campaign report (`scripts/rehearse_smart_fill.py --out`):

- `matter.role` inference covers plaintiff/defendant only; a family matter
  with no parties fills no caption.
- The fee agreement's `contingency_percentage` is legitimately blank for an
  hourly matter; pinned as expected.
- A custom field deleted under a template still reads as `bound` and fills
  blank (coverage module limitation; tracked, not fixed).
- Renderer drops values for a few PDF field types it cannot set
  (`dropped_by_renderer` outcomes in the report).

From the Phase 3 and 5 work:

- Save-all for sets is browser-driven and sequential until a fill session
  exists (3d), because preview evidence is per user.
- The 5c v1 alignment is scale-only (same page geometry); skewed or cropped
  scans need the deskew follow-up. No vision pass on crops yet (5c-2).
- The MCP `get_matter_document_text` tool does not accept images.
- No sweep job pre-extracts old documents; the cache fills from the upload
  job.

## 6. Implementation plan for Phases 4a, 4b, 5a, 5b, 5c (shipped 2026-09-20 as planned; departures in the Phase 3 plan doc)

Scope confirmed with the owner on 2026-09-19: one commit; 5c included in a
first version; 5d/5e planned; vision fallback deferred. Kept here as the
record of what was built against.

### Backend

- **4b.** `DocumentTemplateRenderRequest.verified_fields: list[str]` (≤400,
  each ≤100 chars, deduplicated, must be keys of `variables`, else 422).
  `document_generated` metadata gains `verified_fields` and `verified_count`
  beside `filled_variables`. New nullable JSON column
  `matter_documents.generation_summary` = `{template_id, template_version_no,
  total, filled, verified, verified_fields}`, set beside `positioned_fields`,
  exposed on `MatterDocumentResponse` and on the render response (first save
  and idempotent replay).
- **5b.** Migration `197_document_evidence.py` (`down_revision =
  "196_mcp_usage_idempotency"`): table `document_text_extractions(id, tenant_id FK,
  document_sha256 char(64) with the matter_documents regex check, engine
  {text_layer|ocr_local|ocr_azure|mixed}, engine_version, text, lines_json,
  page_count, ocr_confidence, truncated, created_at)`, unique
  `(tenant_id, document_sha256, engine_version)`, RLS enabled and forced with
  the NULLIF `tenant_isolation` policy (pattern: `192_user_invitations.py`);
  plus the `generation_summary` column. Update head literals in
  `tests/test_migrations.py:15` and `tests/test_studio_render_migration.py:25`.
  Model `models/document_text_extraction.py` (pattern `user_invitation.py`).
  Service `services/document_text_cache.py`: `extract(filename, content_type,
  content)` (docx/txt → `extract_text`; pdf → text layer then `ocr_pdf` when
  `template_intake._needs_pdf_ocr`, merged with `_merge_pdf_text_and_ocr`;
  images via `template_ocr.image_to_pdf`; OCR failure or missing runtime →
  warning, text layer stands) and `async get_or_extract(db, *, tenant_id,
  content, filename, content_type)` keyed by `sha256(content)`, insert in a
  savepoint, re-read on `IntegrityError`. Consumers: `matter_fact_extraction`
  and `matter_workspace_capabilities._extract_bounded_document_text`.
- **5a.** `_load_source` accepts `.png/.jpg/.jpeg/.tif/.tiff`; `propose` uses
  the cache; `_label_line_candidates(text, targets, *, source_kind, confidence)`
  parametrised and a new `_ocr_line_candidates(lines, targets)` over
  `reconstruct_ocr_lines` emitting `Candidate(value, "ocr", "ocr:<page>:<n>",
  score)`; the "needs OCR" warning becomes "OCR found no readable text in this
  scan." only when OCR ran and found nothing.
- **5c.** `services/template_form_reading.py`: `FieldWindow` from the published
  version's schema (`pdf_overlay.page/rect` or `page/rect`; signing and
  `value_from` fields skipped; ≤200), `read_scan(scan_pdf, windows, *,
  template_page_sizes, ocr=ocr_image, thumbnails=60)` rendering pages with
  pypdfium2 at scale 2.0, mapping rects by page-size ratio, cropping with a 4pt
  margin, OCR per crop, ≤200px PNG thumbnails; images via `image_to_pdf`.
  Routes in `routers/matter_documents.py`: `POST
  .../documents/{id}/facts/from-form` `{template_id, version_no?}` returning
  the `propose` shape with `Candidate(text, "ocr_field", "field:<name>",
  score)` for readings matched to targets by binding or normalised name, and
  unmatched readings under `readings`; `GET .../facts/form-sources` listing
  the templates named in the matter's `document_generated` events. Same
  capability and tenant gate as `.../facts`. Never writes.

### Frontend

- **4a.** `fillReview(..., verified)` adds `verified` per row and a count;
  `usePrepareFill` gains `verifiedNames` (reset with `reviewedValues`; a typed
  value is verified; a Smart Fill refresh that changes a value clears its
  flag), `toggleVerified`, `verifyAndAdvance` (focus the next filled
  unverified row's checkbox, `nextField` pattern), filter `'unverified'`, and
  `verified_fields` on the save payload only when non-empty (keeps the exact
  payload assertions in `TemplatesPage.test.jsx:1318` and
  `TemplatePreparePage.test.jsx:82/94`). `PrepareDocumentBody`: per filled
  row a checkbox `aria-label="Verified: {label}"`, Enter on it or on a
  single-line input verifies and advances. `TemplateFillProgress`: "N of M
  verified" and an `Unverified (N)` filter. Existing unnamed
  `getByRole('checkbox')` queries (`TemplatesPage.test.jsx:1292`,
  `MatterDocumentFacts.test.jsx:78`) become named.
- **4b.** `MatterDocumentsTab` preview shows "{verified} of {total} fields
  verified when generated".
- **5a/5c.** `MatterDocumentFacts.jsx`: OCR rows show "From the scan · N% OCR
  confidence"; a "Printed form" select from form-sources and "Read against the
  printed form"; rows from that read show `<img alt="Scan of {label}">`.
  `api.js`: `getMatterDocumentFormSources`, `readMatterDocumentAgainstForm`.

### Tests

Backend: `test_document_text_cache.py` (cache once, OCR path with stubbed
`ocr_pdf`, image path, OCR unavailable → warning, RLS isolation);
`test_matter_fact_extraction_unit.py` (`_ocr_line_candidates`);
`test_matter_fact_extraction_postgres.py` (PNG source, empty scan warning,
cache hit); `test_template_form_reading.py` (AcroForm PDF from
`tests/esign_pdf_fixtures.acroform_pdf()` rendered and wrapped with
`image_to_pdf`, injected `ocr` asserting crop geometry, thumbnails bounded,
page-size scaling); `test_matter_document_form_reading_postgres.py` (both
routes, cross-tenant 404, gate off); `test_document_templates.py` descriptor
test extended with `verified_fields` and the 422. RapidOCR is not installed
in the sandbox: stub the engine boundary as `test_template_ocr_unit.py` does.
Frontend: `templateFillReview`, Populate verification flow, progress filter,
`MatterDocumentFacts` OCR and form read, `MatterDocumentsTab` summary line.

### Release and docs

Release note `2026.09.19.05` (newest first; highlight descriptions ≤180
chars, summary ≤240), regenerate `RELEASE_NOTES.md`, `CHANGELOG.md` entry,
plan doc statuses, this document's table.

### Verification commands

```
# backend, from backend/
ruff check app/
pytest tests/test_document_text_cache.py tests/test_matter_fact_extraction_unit.py \
  tests/test_matter_fact_extraction_postgres.py tests/test_template_form_reading.py \
  tests/test_matter_document_form_reading_postgres.py tests/test_document_templates.py \
  tests/test_migrations.py tests/test_studio_render_migration.py tests/test_sms_migration.py -q
alembic upgrade head && alembic downgrade 195_probate_track && alembic upgrade head
python ../scripts/generate_release_notes.py --check
# frontend, from frontend/
npx vitest run && npx eslint src
```

## 7. CI gates and how to re-run every check

- Diff coverage ≥ 80% (`diff-cover coverage.xml --compare-branch=origin/main
  --fail-under=80`); measured 97% after Phase 1.
- `ruff check backend/app/`; `python scripts/generate_release_notes.py --check`
  (`release_notes.json` newest first).
- `scripts/verify_merge_policy.py`: PR body must check exactly one
  documentation option, one release-note option, and the security attestation.
- Frontend: `npx vitest run` (1529 passed at `c2c5a54`), `npx eslint src`
  (0 errors; 3 pre-existing `no-alert` warnings in ChatPage and ProfilePage).
- Backend suites run in this branch's sessions: template suites (718), matters
  and intake and durable (256), template and e-sign (165 at `c2c5a54`).
- Migration head after the Phase 4/5 commit: `197_document_evidence` (the branch's only migration).

## 8. Open risks and recommended order

1. Merge this branch as one unit. It carries one migration, `197_document_evidence`,
   pinned to `196_mcp_usage_idempotency` after main's `#574` claimed 196 first
   (renumbered from 196 per `AGENTS.md` §1; the head on `origin/main` was
   confirmed before this change).
2. 3d takes migration 198.
3. The DOCX-to-PDF default for templates with signature fields changes a
   default; a firm that wanted Word output must choose it. The reason is shown
   beside the choice.
4. The `document_prefill` job runs on every matter create, conversion, portal
   submit and accepted write-back, capped at 20 templates per run; cost is
   compute only, no AI calls.
5. Phase 5a turns OCR on for every uploaded scan under the tenant gate; the
   local engine is free but bounded (25 pages); Azure is a platform setting.
