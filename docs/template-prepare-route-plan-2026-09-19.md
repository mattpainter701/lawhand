# Phase 3: Prepare route, from Studio to signature, with set fan-out

**Date:** 2026-09-19
**Status:** 3a shipped on `claude/pdf-auto-filing-mechanism-e5tqb5` (see CHANGELOG 2026.09.19.03); 3b, 3c, 3d proposed.
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

## Phase 3b: the Send step (one PR; additive backend fields)

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

## Phase 3d: durable save-all and a resumable session (later; three PRs; migration 196)

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
