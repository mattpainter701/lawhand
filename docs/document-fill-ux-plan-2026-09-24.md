# Document fill UX: document-first filling, parity, and "fill where they work"

Status: phase 1 shipped (sample Fill dialog). Phases 2–6 are proposals.
Date: 2026-09-24

## 1. Why

The Template Studio sample **Fill** dialog showed a narrow field list beside a
small, one-page-at-a-time PDF preview. Feedback:

- The side panel of inputs feels like a database form, not like filling in a
  document. People recognise a form by its pages.
- On a small screen the field panel is too narrow to type in comfortably.
- The original document should be the default view. The list is still useful,
  so people should be able to switch between the two with a control at the top.
- Filling should work the same way everywhere a document is filled.
- We already render full Office documents (headless LibreOffice), and firms
  already pay for Microsoft 365 or Google Workspace. Can we fill inside the
  firm's own office suite?

## 2. Phase 1 (this change): document-first sample Fill

`frontend/src/components/templates/FillOnDocument.jsx` is a reusable
fill-on-the-page component. `SampleFillDialog.jsx` now uses it.

| Piece | Behaviour |
| --- | --- |
| **Document view (default)** | Every page of the source PDF, drawn with the shared `PdfPageCanvas`. Pages render lazily near the viewport. Each field placement (`placementsFor` → `overlayToCanvasRect`) becomes an input on its own box: text, multiline, checkbox, select (choice/radio), and a read-only "Signed later" marker for signatures. Zoom: fit width, 75–200%. |
| **Guided bar** | Under the document: the active field at full size (reusing `FieldInput`), Previous/Next in reading order, and **Next required**. Navigation scrolls the box into view but leaves focus in the bar, so a phone keyboard stays up and tiny boxes stay usable. Fields that have no box on the page are still reached this way. |
| **Top switch** | **Document / Questions / Final PDF**. Questions is the old grouped list with filters, now full-width. Final PDF appears after **Preview filled PDF** and disappears when an answer changes. Answers, matter suggestions and counts are shared across views. |
| **Status colours** | Amber means required and unanswered. Blue tint means filled from the matter and not yet edited. A light box means open. |
| **Fallbacks** | If the source PDF will not load, or no field has geometry, the dialog opens in Questions and says why. |
| **Screen use** | The dialog fills the viewport (edge to edge on phones). Matter search is folded behind **Fill from a matter** until used. Escape closes it. |

Placement accuracy: overlay boxes come from the same AcroForm `/Rect` values
that the server fills (`pdf_templates._discover_pdf_fields`). What you type
sits where it will print, and the **Final PDF** tab remains the authoritative
check.

## 3. Parity: every fill surface today

| Surface | Where | Layout today | Types on the page? |
| --- | --- | --- | --- |
| Sample Fill | `templates/SampleFillDialog.jsx` | **Document / Questions / Final** (phase 1) | **Yes** |
| Generate dialog (`RenderModal`) and Prepare route | `prepare/PrepareDocumentBody.jsx`, `pages/TemplatePreparePage.jsx` | 380px field panel plus `TemplateFillSource` reference, then live server preview | No: clicking a highlighted box only focuses the side-panel input (`PrepareDocumentBody.jsx:421`) |
| Packets (sets) | `prepare/PrepareSetBody.jsx` | Interview on the left, member list on the right, per-member preview dialog | No |
| Client portal signing | `ClientSignatureDocument.jsx` (`FieldOverlay` :76, `SigningPage` :195) | Stacked pages with inputs on the page | **Yes** (its own copy) |
| E-sign placement | `templates/GeneratedSigningPlacementReview.jsx` | Boxes on pages (placement only, not values) | n/a |

The field inputs have been written three times: `FieldInput`, the inline block
in `PrepareDocumentBody.jsx:199-306`, and the inline block in
`PrepareSetBody.jsx:106-137`. The dialog shell has also been written three
times: `TemplatesPage` `Modal`, the sample dialog's own overlay, and
`PdfPreviewDialog`.

## 4. What the market has taught users to expect

These points come from the repository's competitive notes
(`template-studio-clio-parity-plan-2026-09-11.md`,
`competitive-template-automation-review.md`,
`research/2026-07-08-document-automation-esign-enhancements.md`,
`research/m365-google-workspace-review-2026-09-24/map/research-competitors.json`),
plus widely known product behaviour.

1. **Fill on the page for forms.** Adobe Acrobat Fill & Sign, the DocuSign and
   Dropbox Sign signer experience, and our own client portal all put the input
   on the form. A guided "Next" flag that walks the required fields is the
   standard way to get through a long form. Phase 1 adopts both.
2. **An interview for documents made from a matter.** Clio Draft runs Select →
   Populate → Review, with questionnaire cards and a "Needs review" stage.
   Docassemble and Gavel run guided interviews. This is our **Questions** view,
   with provenance and verification. It should sit one click away from the
   document, not replace it.
3. **Author and edit in the word processor.** Clio for Word (a 2026 beta that
   replaces the Clio Draft Template Builder add-in), CoCounsel for Word and
   Microsoft's Legal Agent in Word all work inside Word. Content controls carry
   the fields, and AI edits land as tracked changes. Our add-in is an assistant
   and has no template or field tools (Clio parity gap G2).
4. **PandaDoc** sets the bar for an embedded editor: pre-fill, then edit, send
   and sign in one surface.

The takeaway: forms (PDF) are filled on the page, documents (Word) are reviewed
as a document and edited where the firm edits, and the interview is always
available as a list.

## 5. Proposed phases

### Phase 2: Prepare and Generate get the same switch (M)

This is the main matter flow, and the parity gap people will notice first.

- In `PrepareDocumentBody`, replace the fixed 380px panel with the same
  **Document / Questions / Preview** switch. Questions keeps today's per-field
  verify checkbox, provenance line and "matter now suggests" prompt unchanged.
- **PDF templates:** Document uses `FillOnDocument` over the source. The guided
  bar gains the verify checkbox and provenance line (a `renderInput` slot that
  already exists), so review can happen on the page. Live server preview stays
  as the Preview tab.
- **Word templates:** keep the LibreOffice page render
  (`/templates/{id}/preview-render`) with `WordPlaceholderLayer`. Clicking a
  placeholder drives the guided bar instead of the side panel. Values cannot
  be typed into a rasterised page, so the debounced live re-render
  (`usePrepareFill.js:425-430`) shows them in place.
- Lift `FieldInput` into a shared `fill/FieldInput.jsx` covering every type
  Prepare uses (date, currency, number, textarea), and remove the two inline
  copies.

### Phase 3: packets (S–M)

`PrepareSetBody` uses the same switch. Document shows the selected member
(member tabs across the top), and Questions stays the single shared interview.

### Phase 4: one on-page field component (S)

Converge `ClientSignatureDocument`'s `FieldOverlay`/`SigningPage` onto
`FillOnDocument` (with signature adoption as an extra overlay type), so the
firm and client see identical behaviour and there is one set of tests.

### Phase 5: open the result in the firm's office suite (M)

This is what "fill where they work" means for a finished document. It builds
on what already exists for AI drafts: the cloud working copy in
`cloud_artifact_materialization.py`, **Open cloud working copy** in
`DocumentDraftWorkspace.jsx:172`, and **Refresh edits from cloud**
(`POST /tasks/{id}/pending-action/sync-cloud`).

- After **Save to matter** for Word output, offer **Open in Word** / **Open in
  Google Docs**. Word opens with `webUrl?action=edit` for the web or
  `ms-word:ofe|u|…` for the desktop app. Edits come back as a new revision
  through the existing snapshot path, and review resets.
- Fix the known blockers first. In the M365/Google review these are D08 (Word
  edits to a matter document cause a 409), D34 (a LawHand save orphans Word
  Online edits) and D09 (Word drafts are flattened to plain text).
- Convert to PDF in the firm's tenant (Graph `GET …/content?format=pdf`), with
  LibreOffice as the fallback. This is small, improves font fidelity (D82) and
  takes conversion load off the API worker (D83).

### Phase 6: fill inside Word (the thick integration) (L)

- Word templates carry LawHand fields as **tagged content controls**. This is
  already planned in `office-document-assistant-plan.md:265` and `:296`, and in
  review item :211.
- The add-in task pane becomes the guided bar: the same field order,
  required/missing state, matter suggestions and provenance, served by the same
  Smart Fill endpoints. **Next** selects the content control in the document.
  Writes stay approval-gated, as the add-in's contract already requires.
- The same content controls let Word authors insert and see fields (Clio
  parity W2), so authoring and filling share one mechanism.
- For Google-first firms, merge with `files.copy` plus `documents.batchUpdate`
  (`replaceAllText`, named ranges), then open the copy in Docs. A Docs sidebar
  add-on is a later option.
- PDF forms stay in LawHand. Neither Word nor Docs fills AcroForms well, so the
  on-page filler from phases 1–4 is the answer there.

## 6. "We can render full Office, so should we?"

What exists: **headless LibreOffice conversion only** (`docx_to_pdf.py`), used
for page-accurate previews and PDF output. There is no embedded editor, no
WOPI host, and no office-server service in any Compose file.

Options for editing in the browser inside LawHand:

| Option | Fit | Cost and risk |
| --- | --- | --- |
| Keep LibreOffice headless (today) | Previews, PDF output, and phase 2's live re-render | Already in place. Fonts differ from Word (D82). Runs in the API worker (D83). |
| **Collabora Online** (LibreOffice in the browser) | Real DOCX editing embedded in LawHand. We would implement a **WOPI host** for it. This differs from Microsoft's CSPP concern, which is about hosting Office for the web. | Separate service to run and scale. Production support needs a subscription. PDF editing is unverified (`template-studio-document-workflow.md:141`). |
| ONLYOFFICE Docs | Similar embedded editor | A commercial licence is needed to embed it in a proprietary product (`template-studio-document-workflow.md:135`). |
| **The firm's own Word or Google Docs** (phases 5–6) | Editing where lawyers already work, with their fonts, styles and tracked changes | No new server to run. Needs the D08/D34/D09 fixes and, for phase 6, the add-in content-control work. |

**Recommendation.** Don't embed a second office suite yet. Firms already pay for
and trust Word or Docs, and an embedded LibreOffice editor would be a third
editing experience with its own fidelity gaps. Use LibreOffice for what it is
good at (rendering and conversion), and spend the effort on phase 5, which is
small and largely built, and then phase 6. Revisit Collabora only if a
customer segment has no Microsoft 365 or Google Workspace, or if on-premise,
no-cloud deployments need in-browser editing.

## 7. Decisions needed

1. Phase 2 next? It gives Prepare/Generate the same Document/Questions switch
   and is the biggest parity gain.
2. Which suite comes first for phases 5 and 6: Microsoft 365 or Google
   Workspace? The existing add-in and review lean toward Microsoft 365.
3. Is an embedded editor (Collabora) needed for any customer without a cloud
   office suite? Engine selection is still waiting on the paid-versus-free
   decision.
