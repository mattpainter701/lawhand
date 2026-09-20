# Phase 3: Prepare route, from Studio to signature, with set fan-out

**Date:** 2026-09-19
**Status:** 3a and 3b shipped on `claude/pdf-auto-filing-mechanism-e5tqb5` (CHANGELOG 2026.09.19.03 and .04); 3c, 3d proposed. Audit status and the next-commit implementation plan for Phases 4 and 5: [`smart-fill-programme-audit-2026-09-19.md`](smart-fill-programme-audit-2026-09-19.md). Phases 4 (verification pass) and 5 (documents as evidence) added 2026-09-19 from the owner's follow-up asks; see the end of this document.
**Builds on:** [`smart-fill-engine.md`](smart-fill-engine.md) (engine, Phase 2
readiness record), the Clio-parity plan's W3 (Sets) and W7.3 (`/templates/prepare`).

## The ask

From Template Studio, selecting a template should offer: auto fill, choose the
matter, save into that matter's documents so work can continue, review, and
send for e-signature. And for a set: fill once, draft the whole packet, save
all to the matter. Today those are three surfaces (Studio, the fill dialog,
the matter's E-Signature panel) with no path between them.

## Decisions made up front

**Save-all runs from the browser, one document at a time (option A).**
Generation preview evidence is minted per user, per template contract, per
values HMAC, with a 30-minute TTL, and `/render` checks the preview was taken
by the saving user. That evidence *is* the human review gate for a PDF. A
background worker can neither review for a person nor act as them, so a
durable "save all" would make only the save durable, not the review, at the
cost of extracting a 600-line handler. Phase 3a/3c save sequentially with
per-document status and honest copy ("Saves one document at a time from this
browser. Keep this tab open until every row says Saved."). If the browser
closes mid-save, every saved member is a real matter document with its
`document_generated` event; unsaved members simply do not exist and their
previews expire. A consumed preview replays the same document idempotently,
so a retry never duplicates. The durable job comes in 3d, once a fill session
exists to drive it.

**No version-addressed render.** `/render` always uses the published version.
A set member pinned to a version that is not the current published one is
reported unavailable ("Pinned to version N; the published version is M.
Re-pin or republish to draft it."), never rendered from a different version.

**Signer roles come from the saved document, not the template.** The render
response gains `signing_roles`, `signing_placement_required`,
`positioned_fields`, `signing_placement_problems` (already computed by
`template_placement_report`, currently only stored on the row) so the Send
step needs no second fetch.

**A new page, not more TemplatesPage.** `/templates/prepare` is its own lazy
page. `RenderModal` stays exported from `TemplatesPage.jsx` as a thin dialog
around the same body, so its three consumers and 25 tests keep working.

## Phase 3a: the route, single template (shipped)

Route: `/templates/prepare?template=<id>&matter=<id>&folder=<id>&return=<path>`.
Steps: Select, Matter, Populate, Review, Save.

New, under `frontend/src/components/prepare/`:

- `usePrepareFill.js`: RenderModal's state and handlers moved verbatim
  (values, sources, review, `invalidatePreview`, `setVariable`,
  `selectMatter`, `handleSmartFill` with the once-per-template-and-matter
  auto fill, `handleRender`, `handleSave`). Signature
  `usePrepareFill({template, initialMatterId, folderId, onSaved})`.
- `prepareHelpers.js`: the page-private helpers the hook needs
  (`getTemplateVariables`, `friendlyVariableLabel`, `formatMatterLabel`,
  `getErrorMessage`, `downloadRenderedText`), re-imported by the page.
- `PrepareDocumentBody.jsx`: the two-pane JSX without the dialog wrapper,
  `layout: 'modal' | 'page'`. Every accessible name preserved: `Smart Fill`,
  `Refresh matter values`, `Refresh firm values`, `Preview draft`,
  `Generate`, `Preview`, `Render & Save to Matter`, `Document preview`.
- `MatterPicker.jsx`: moved out of the page; used by both.
- `PrepareStepper.jsx`: step states derived from the hook only. Counts come
  from `fillReview`, the single derivation (W7.5).
- `prepareRouting.js`: `buildPrepareTarget({templateId, setId, matterId,
  folderId, returnTo})`, mirroring `studioRouting.buildOpenStudioTarget`.
- `frontend/src/pages/TemplatePreparePage.jsx`: loads the template with the
  same rule as `openRender` (re-fetch `published: true` when the published
  version differs from current), loads matters with `getMattersV2`. Drafts
  open in "Preview draft" mode with Save disabled, as the dialog does. On
  save: `/matters/{id}?tab=documents&document=<id>`, or `return=` plus the
  document id.

Modified:

- `App.jsx`: the route, inside the Template Studio shell.
- `TemplatesPage.jsx`: `RenderModal` becomes the dialog wrapper; library row
  action "Prepare on a matter".
- `TemplateStudioWorkspace.jsx`: "Use on a matter" beside Generate. Enabled
  only for a published template; disabled with "Publish a tested version
  first." otherwise.
- `PreparedDocumentsBanner.jsx` / `MatterDocumentsTab.jsx`: "Review and
  save" navigates to the route with template, matter, folder and return
  preselected. `MatterTemplatePicker` stays for Case Setup and email
  attachments, which need `onSaved` in place.
- `ProbateTab.jsx`: "Generate filled packet" navigates to the route.
- `MatterDocumentsTab.jsx`: one-shot `?document=` opens that document's
  preview and is removed from the URL, the way `CaseSetupCard` treats
  `?paperwork=`.

Tests: `TemplatesPage.test.jsx`, `MatterTemplatePicker.test.jsx` and
`TemplateStudioWorkspace.test.jsx` pass unchanged. New: hook tests (matter
switch clears state, edit invalidates preview, PDF save without evidence
refused, DOCX save needs a downloaded preview), stepper states, page tests
(query preselection, published-version rule, save navigation, `return=`,
draft mode), `?document=` on the documents tab, Studio button states,
ProbateTab navigation.

Acceptance: Studio, published template, "Use on a matter", pick matter,
fields auto-filled with sources, Generate, Render & Save to Matter, land on
the matter's Documents tab with the document open.

## Phase 3b: the Send step (shipped; one PR; additive backend fields)

Shipped as planned, with two departures worth knowing. The matter panel
does not merely "delegate" to the card: its whole new-request form and the
draft section *are* `SignatureSendCard`, with the document select and the
prepared-PDF upload passed in as the card's `picker`, so there is one form,
not a copy. And the route does not show a "Word documents can't be sent"
card after saving a DOCX: the explanation sits beside the output-format
choice before the save, where it can still change the outcome, and the
stepper's Send step reads "Needs PDF output to send for signature" until
PDF is chosen. A saved document with no signing fields lands on the matter
as before; only a PDF with signing roles or fields stays for the Send step.


Backend: the four signing fields on `DocumentTemplateRenderResponse`,
populated where the `MatterDocument` row is built; assert them in
`test_generated_pdf_persists_positioned_signing_descriptor_and_lists_it`.

New, under `frontend/src/components/signatures/`:

- `signatureRequestRules.js`: the helpers now private to the matter page
  (`SIGNER_ROLE_OPTIONS`, `newSignerRow`, `signingFieldOrigin`,
  `signatureSendNotice`, ...). `signatureSendNotice` stays re-exported from
  `MatterDetailPage.jsx` for its test.
- `useSignatureRequestDraft.js`: create, open draft, send, discard, lifted
  from `SignatureRequestsPanel` with its preconditions verbatim: exactly one
  signer per role in `document.signing_roles`; `placementBlockMessage` when
  placement is required and none is supplied; the `plan_review_required`
  checkbox "I have checked where each signer will sign" before
  `sendSignatureRequest(..., {acknowledge_review: true})`.
- `SignatureSendCard.jsx`: signer rows, schedule, inline
  `GeneratedSigningPlacementReview` when required, "Create request", the
  "Where each signer will sign" list, acknowledge, "Send request".
- `signerPrefill.js`: role `client` prefilled from the matter's client name
  and email; other roles empty in `signing_roles` order.

Modified: `SignatureRequestsPanel` delegates its create/send section to the
card (no copy or behaviour change); `SendStep.jsx` in the route shows the
card only for a PDF output with signing roles, otherwise says why ("Word
documents can't be sent for e-signature; save as PDF to send"); the DOCX to
PDF toggle defaults on when the template has signing fields, with the reason
shown, and the toggle stays.

Tests: `MatterSigningPlacements.test.jsx` unchanged. New: rules, hook (role
coverage, placement block, review gate, acknowledge send, source-changed
409), card, prefill, and Send-step page cases.

Acceptance: a DOCX fee agreement with signing fields defaults to PDF, saves,
shows the Send step with the client prefilled, placement reviewed when
required, sends, and the matter Overview shows the request.

## Phase 3c: sets (two PRs: backend plus library, then the route; no migration)

Backend:

- `POST /api/template-sets/{id}/documents-variables` with
  `{matter_id?, answers}` returning `{documents: {template_id: variables},
  unanswered_required, unavailable, resolved_versions}` from the pure
  `build_interview`, `answers_for_documents`, `unanswered_required`. The
  merge rule stays server-owned; nothing is ported to JavaScript.
- `_member_snapshots` reports a pinned version that differs from the
  published one as unavailable with the reason above.
- `tests/test_template_sets_rls.py`: tenant isolation for both set tables
  under live RLS, cloned from `test_document_template_preview_rls.py`. This
  is the gap the execution status names first.

Frontend:

- `/templates/sets`, `/templates/sets/new`, `/templates/sets/:id`:
  `TemplateSetsPage.jsx`, `TemplateSetEditor.jsx` (title, module,
  jurisdiction, ordered members from published templates, per-member pin or
  follow-published), `TemplateSetList.jsx`, a nav link from Studio home,
  "Prepare on a matter" per set.
- `usePrepareSet.js`: the interview from `getTemplateSetInterview`, answers,
  and `interviewReview(questions, answers, reviewed)` added to
  `templateFillReview.js` returning the same shape as `fillReview` so the
  stepper and progress bar serve both cases. Populate groups questions by
  card through `TemplateCardRail`, shows "Appears in N documents" from
  `appears_in`, and orders shared-and-required first.
- Review, "Generate all": `splitTemplateSetAnswers`, then per available
  member a generation preview through `renderTemplateFile` with concurrency
  three; per-member status, server detail on failure, per-member Retry; an
  answer edit invalidates every member's preview. Markdown members preview
  through `renderTemplate` (no evidence needed).
- Save, "Save all to matter": sequential `renderTemplate` per ready member
  with rows "Saved", "Failed: reason", "Not saved yet"; Retry re-runs only
  failed rows; an evidence-mismatch 409 sends that member back to Review
  with "Preview again". One `document_generated` event per document naming
  `template_version_no` is what the save already writes.
- Send: one `SignatureSendCard` per PDF member with signing roles, prefilled
  signers shared across cards, one request per document. Then the matter's
  Documents tab with the first saved document open.

Tests: hook, `interviewReview`, the batch pool, the sets page, and page
cases (interview loads; one answer reaches N documents; generate-all with one
failure and retry; save-all sequential with one failure that drops nothing;
an unavailable member shown and skipped; Send lists only PDF members with
roles). Everything from 3a and 3b unchanged.

Acceptance: a five-document packet, caption asked once, all five previewed,
one failing member retried without touching the others, five documents and
five events saved, three PDFs sendable, RLS test green.

## Phase 3d: durable save-all and a resumable session (later; three PRs; migration 197, since 196 is the document evidence migration)

1. Extract `save_generated_document(...)` from the render handler into
   `services/generated_documents.py` with no behaviour change: staged
   storage, compensation, reconciliation, evidence consumption and replay,
   the output-hash gate and the matter event. Parity: the whole of
   `test_document_templates.py` plus a direct service test for PDF with
   evidence, DOCX with conversion, markdown, same-folder replay,
   other-folder 409, hash mismatch 409. `render_workspace_template` keeps
   refusing PDF.
2. `document_fill_sessions` (migration `196`, `down_revision` `195_probate_track`,
   update every head pin AGENTS.md section 1 lists): tenant, user, matter,
   template or set, captured published version numbers, answers encrypted
   at rest with the existing token-vault primitive, answers digest, status,
   saved document ids, 14-day expiry, RLS like the set tables. Encrypting is
   the decision: an HMAC-only session would discard every typed value, which
   is exactly what a resumable session exists to keep. On resume, a moved
   published version invalidates every preview and says so. The matter's
   Documents tab lists "In progress" sessions with Resume.
3. `template_set_render` durable job, payload a session id plus per-member
   preview ids; the handler verifies each preview still binds to the
   session's user, values and matter, then calls the service as that user.
   Only then does the copy change to "Saving in the background". An expired
   preview fails that member with "Preview expired; review it again" and the
   session stays open.

## Verification, per PR

```
# backend, from backend/
pytest tests/test_document_templates.py tests/test_template_set_routes.py \
  tests/test_template_sets_unit.py tests/test_template_set_interview.py -q
pytest tests/test_esign_plan_review.py tests/test_esign_placement.py \
  tests/test_esign_service.py tests/test_esign_native_signing_postgres.py -q
pytest tests/test_template_sets_rls.py tests/test_document_template_preview_rls.py -q   # 3c
pytest tests/test_migrations.py tests/test_studio_render_migration.py -q               # 3d
diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
python ../scripts/generate_release_notes.py --check
# frontend, from frontend/
npx vitest run src/pages/TemplatesPage.test.jsx src/components/templates/MatterTemplatePicker.test.jsx \
  src/pages/MatterSigningPlacements.test.jsx src/components/prepare src/components/signatures \
  src/pages/TemplatePreparePage.test.jsx
npx vitest run && npx eslint src
```

## Invariants preserved

- A PDF saved to a matter always carries generation preview evidence minted
  by the same user within 30 minutes; nothing is saved that a person did not
  look at. A field edit invalidates the preview, every member's for a set.
- `/render` and `/render-file` stay the only generation paths; sets fan out
  through them one document at a time; no new renderer, no version-addressed
  render; the published version is what renders.
- Switching matters clears values, sources, review state and evidence.
- Completion counts have one derivation shared by stepper, progress and the
  Save gate.
- One `document_generated` event per saved document naming the published
  version; a failed member is reported, never dropped; no label claims
  durability the backend does not provide.
- Signer roles are read from the saved document; role coverage, placement
  review and the plan-review acknowledgement are unchanged; DOCX output is
  never offered for signature.
- Applicability rules stay advisory; templates stay catalogue objects; sets
  stay tenant-scoped lists of template ids with optional pins.

## Phase 4: the verification pass (owner's ask, 2026-09-19; 4a and 4b shipped 2026-09-20, CHANGELOG 2026.09.20.01; 4c and 4d wait on 3d)

> "a review mechanism for confidence in these automations ... presented a
> box to 'verified' and can click, click, click, change field, click
> rapidly through docs to validate them, clicking can be optional too."

What exists: the Populate pane already tracks per-field `reviewedValues`
(a value the user confirmed or typed) and `fieldSources` (where the value
came from), and `fillReview` counts them; the Prepare route's "Smart Fill"
button is the auto fill and "Refresh matter values" re-runs it against the
matter's current data, keeping hand edits. What is missing is a *fast*
verification affordance and a record that survives the page.

- **4a: one-keystroke verification in Populate.** Each filled row gets a
  "Verified" check (space or Enter on the focused row; Tab moves on), a
  "Change" that opens the input, and a running "12 of 19 verified"
  count beside the fill count. Verification is optional: Save never waits
  on it, and an unverified field is rendered with the same value. A field
  the user edits is verified by that act. Row order puts `review_required`
  and synonym matches first so rapid clicking spends attention where the
  engine was least sure. Keyboard model: `j`/`k` or arrow keys move,
  space verifies, `e` edits, `Enter` verifies and moves on.
- **4b: verification travels with the document.** The render request
  carries `verified_fields` (names only) and the `document_generated`
  event records them with the counts, so the matter's Documents tab can
  show "19 fields, 12 verified" per generated document and a reviewer can
  tell a checked document from an unchecked one. No new table: names in
  event metadata, as 2b did for readiness.
- **4c: persisted per-session state** lands with 3d's
  `document_fill_sessions` (migration 198): verified names and reviewed
  values are saved per (template, matter, user) so leaving the page and
  coming back, or moving to the next document in a set, does not lose the
  pass. The set route then supports "click through docs": the Send/Save
  rail moves to the next member with its own verification count.
- **4d: the readiness record learns from it.** `document_prefill_ready`
  gains `verified` counts from the latest session so the Case Documents
  banner can say "3 documents ready, 2 verified".

Invariants: verification is advisory and never a gate; a verified value is
still re-derived on refresh and marked "changed since verified" if the
matter moved; the generation preview evidence stays the only gate to a
saved PDF.

## Phase 5: matter documents as evidence (owner's ask, 2026-09-19; 5a, 5b, 5c v1, 5c-2 and 5d shipped 2026-09-20; 5e planned)

> "as documents get entered into the matters > doc that's the 'repo' of
> knowledge outside of matter fields ... a mechanism to read those
> documents, cache, index such, update non cached, and use OCR / handle
> handwritten info. ... a button next to document in the matter, 'use
> premium AI to gather fields' ... say we send a template out that had
> acroforms, but the customer printed it and manually filled it out."

### What the codebase already has (surveyed 2026-09-19)

- `app/services/matter_fact_extraction.py`: reads one matter document
  (PDF, DOCX, TXT, 10 MB cap, sha-checked bytes), takes AcroForm values,
  `Label: value` lines and email/phone/ZIP patterns, proposes them against
  standard bindings and the tenant's custom fields, and `accept()` writes
  through `intake_writeback` with a `MatterEvent`. It runs as the
  `matter_fact_extraction` durable job on every upload and files a review
  `Task`; `POST /matters/{id}/documents/{doc}/facts?ai=true` adds an AI pass
  (`intake_extraction_ai.extract_with_ai`, metered, closed schema, gated by
  `TenantSettings.custom_config["intake_fact_extraction"].{enabled,ai_enabled}`
  and the platform flag). The review list is
  `components/documents/MatterDocumentFacts.jsx` inside the document
  preview panel, with an "Also read with AI for scans and prose" checkbox.
  **This is the "gather fields" button, already next to the document.**
- OCR: `app/services/template_ocr.py` (local RapidOCR over pypdfium2 renders,
  pooled, bounded to 25 pages / 80M pixels, line confidence floor 0.35,
  label-plus-handwritten-value row merging) and `template_ocr_azure.py`
  (opt-in Azure Document Intelligence read). Wired only into *template*
  upload analysis; `matter_fact_extraction` explicitly warns "a scan with
  no text layer proposes nothing until OCR text is supplied".
- No cache: nothing persists extracted text; every propose re-downloads and
  re-parses. No index over matter documents: the pgvector `documents` /
  `chunks` corpus is the RAG corpus and matter documents are not in it.
  No document-kind classifier. No per-fact "verified" flag; provenance is
  the signed proposal contract, `value_hmac` and the event.

### The design

**5a: OCR reaches matter documents (one PR).** `matter_fact_extraction`
calls `template_ocr.ocr_pdf` / `ocr_image` when the text layer is empty or
thin (reuse `template_intake._needs_pdf_ocr` and `_merge_pdf_text_and_ocr`),
accepts `.png/.jpg/.tiff` uploads, and carries each candidate's OCR line
confidence into `Candidate.confidence`. The same tenant gate applies.
Handwriting is handled the way template intake already handles it: label
and value on one row; a low-confidence line is proposed with the
confidence shown, never dropped silently.

**5b: the extraction cache (one PR; migration 198, after 3d claims
its number).** `document_text_extractions(tenant_id, document_sha256,
engine, engine_version, text, pages_json, ocr_confidence, extracted_at)`,
RLS like every tenant table. Keyed by the document's bytes, so a re-upload
of identical bytes is free and a new version invalidates by construction;
"update non-cached" is a sweep job that extracts documents whose sha has
no row for the current engine version. `get_matter_document_text` (the MCP
tool) reads the cache first. Extracted text of a document is evidence
about the document, not a matter fact: it never writes to matter fields
on its own.

**5c: template-anchored reading of a printed, hand-filled form (one PR).
This is the strong idea for the owner's scenario.** A document generated
from one of our templates records `template_id` and
`template_version_no` in its `document_generated` event, and the
published version knows the exact rectangle of every field on every page
(`discover_pdf_fields` / `pdf_overlay`). When a scan comes back (uploaded
as a new document or the signed copy of a signature request), the
extraction pairs it with the template version by the user's choice or by
the closest text match over the page text, aligns each scanned page to
the template's blank page (pypdfium2 render, feature or projection
alignment), crops each field rectangle, and reads *each crop* with OCR
first and the vision model (`extract_with_ai` given the crop) when OCR
confidence is below the floor. The result is a field-name to value list
with a confidence and a thumbnail of the handwriting per field: exactly
the shape the Populate pane and Phase 4's verification pass already
consume. No "converted twin" document is generated; the template is the
pairing key and the scan stays the evidence. Whole-page extraction (5a)
remains the path for documents that did not come from our templates.

**5d: documents as a `FillSource` (one PR).** `DocumentEvidenceSource` in
`template_fill_engine` offers aliases from *accepted* facts only (the
write-back proposals a human accepted, which are already matter or custom
fields) plus, at lower precedence and `review_required`, the cached
candidates from 5a/5c for the matter's documents, with
`provenance.source_document_id` and the crop thumbnail id. Precedence
stays firm > custom > binding > name match > synonym > document evidence,
so a document never silently overrides a matter field; it fills a blank
and asks to be verified.

**5e: the index (later).** Chunk cached text with the existing
`chunk_text`, embed with `EmbeddingService`, store in a matter-scoped
table (not the RAG corpus) keyed by `document_sha256`, invalidated by the
cache row. Consumers: "find where this fact came from" in the review list,
and the assistant's matter context. Not needed for 5a to 5d.

### UX note, and Clio

Clio Manage has no OCR-to-field extraction; its document automation fills
from matter fields only, and scanned forms are stored, not read. Clio's
"Clio Duo" reads documents to answer questions, not to write fields. So
there is no parity target to copy; the closest products (Smokeball's form
filling, Lawmatics' intake) also fill from fields. The UX here is: the
document preview panel already offers "Find details"; 5c adds "Read this
scan against the form it was printed from" with the template picked or
confirmed, then the per-field list with a thumbnail beside each value and
the Phase 4 verify keys. Nothing is written until accepted.

### Costs and gates

The AI pass is metered per tenant already (`UsageRecord`,
`check_token_budget`, `background_ai_quota`) and 5c reuses it per crop
rather than per page, so a 40-field form costs 40 small calls only for the
fields OCR could not read. The local OCR engine has no per-call cost. Both
respect the existing tenant `intake_fact_extraction` settings and the
per-user `premium_ai_enabled` flag; the button is hidden, not disabled,
when the tenant has neither.

### Departures in what shipped (2026-09-20)

- The `from-form` route carries no extra tenant gate: the existing `facts`
  route has none, and the local OCR engine has no per-call cost. The AI pass
  keeps its gate.
- The MCP document text tool reads the cache but never writes it, because
  the tool is read-only; the cache fills from the upload job and the fact
  reads. A sweep job was not added.
- Alignment in 5c is by page size only (`alignment: "scaled"` in the
  response). A skewed or cropped scan reads with low confidence and says so;
  deskew and feature alignment are 5c-3.
- A typed value counts as verified (the preparer looked at it to type it), so
  a save after hand edits carries those names without a tick.

