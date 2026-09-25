# Document fill UX: document-first filling, parity, and "fill where they work"

Status: phases 1 and 2 shipped (sample Fill dialog; Prepare and Generate). Option A (open in the firm's Word or Google Docs, sync back) is in progress; section 10 tracks it. Phases 3–6 are proposals. Section 9 records why LawHand does not host its own editor for now.
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

## 2. Phase 1 (shipped): document-first sample Fill

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
| Generate dialog (`RenderModal`) and Prepare route | `prepare/PrepareDocumentBody.jsx`, `pages/TemplatePreparePage.jsx` | **Document / Questions / Preview** (phase 2) | **Yes** for PDF templates; Word and text templates use the page reference with the guided bar |
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

### Phase 2 (shipped): Prepare and Generate get the same switch

`PrepareDocumentBody` now opens on **Document**, with **Questions** and
**Preview** at the top. The Document/Questions choice is remembered per browser
(`fillViewPreference.js`) and shared with the sample dialog.

- **PDF templates:** the page is typed on directly (`FillOnDocument`). Box
  colours follow review state: required and missing, suggested and needing a
  check, verified, or open. Signature and signing-date boxes show "Signed
  later" / "Dated at signing"; computed fields show "Uses …". The guided bar
  renders the same per-field editor as the list, so Confirm, Verify, source
  lines and "Matter now suggests" all work on the page.
- **Word and text templates:** the existing page reference
  (`TemplateFillSource`: the LibreOffice page render with placeholder boxes,
  or the text with inline tokens) sits above the guided bar. Clicking a
  placeholder selects that field in the bar.
- **Keyboard review is unchanged:** Enter verifies and advances, and "Next
  field needing attention" works. In Document view both move the bar and
  scroll the page.
- **Preview:** choosing Preview or Test in Document view opens the Preview
  tab. The live PDF preview keeps updating in the background, and the tab
  shows "updating…" while it does.
- **Questions** is the previous layout, unchanged: the field list beside the
  document reference or preview.
- If the source PDF cannot be loaded, the Document view falls back to the page
  reference with the bar and says why.

Still to do from the original plan: lift `FieldInput` into a shared
`fill/FieldInput.jsx` and remove the inline copies (`PrepareDocumentBody`'s
editor is now one function, `renderFieldEditor`, so only `PrepareSetBody`
still has its own copy).

### Phase 3: packets (M)

A packet asks each question once and fans the answer out to every document
that uses it. The interview already records where each answer lands:
`InterviewQuestion.appears_in` holds the `template_id` and `field_name` for
every document (`backend/app/services/template_sets.py:60`). That is enough to
put packet answers on each document's page.

- **Same switch: Document / Questions / Packet.**
  - Document is the default, with one tab per member document along the top.
    Each tab shows its own status: missing count, previewed, saved.
  - Questions is today's single interview, grouped by card.
  - Packet is today's member list with Generate all, Save all and Send.
- **Document view per member:**
  - PDF members use `FillOnDocument` over that member's source, with fields
    renamed from `field_name` to the question `key` through `appears_in`.
  - Word and text members use the page reference with the guided bar, as
    Prepare does.
  - Typing on any document writes the shared answer, so every document that
    uses it updates at once.
- **Make sharing visible.** The guided bar says "Also fills: Engagement
  letter, Conflict waiver" for a shared answer. Boxes for shared answers get a
  small link marker, so nobody is surprised that editing one document changed
  another.
- **Walk the packet in one pass.** "Next required" goes across documents: at
  the end of one member it opens the next member's tab at its first missing
  box. Each required answer is asked once, even when it appears in several
  documents.
- **Preview per member in place.** Replace the preview dialog with a Preview
  sub-tab inside each member tab, using the same live-updating PDF preview as
  Prepare.
- **Code:** the member templates are already loaded by `usePrepareSet`. The
  work is the key mapping, the member tabs, and moving `PrepareSetBody`'s
  inline input copy onto `renderFieldEditor`, which should become a shared
  component at this point.

### Phase 4: one on-page field component (S)

Converge `ClientSignatureDocument`'s `FieldOverlay`/`SigningPage` onto
`FillOnDocument` (with signature adoption as an extra overlay type), so the
firm and client see identical behaviour and there is one set of tests.

### Phase 5: open the result in the firm's office suite (M)

Section 8, Option A, now covers this for both suites.

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

Section 8, Options B–D, compares this with the Google equivalent.

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

**Decision (2026-09-25, final).** Option A only: people edit in the firm's
own Word or Google Docs, and LawHand does not host an editor for now. A
download/upload fallback covers a missing or broken connection. LawHand's own
editor (Collabora) stays a revisit option (section 9). This replaces the two
earlier entries of 2026-09-24 and 2026-09-25.

## 7. Decisions

1. ~~Phase 2 next?~~ Yes. Shipped.
2. Which suite first for "fill where they work"? The options are in section 8.
3. Embedded editor? **Not now** (2026-09-25). Option A only, with a
   download/upload fallback. Revisit on the triggers in section 9.

## 8. Options: filling and editing in the firm's own suite

Every customer runs one of the two suites. The goal is therefore "fill and
edit where they work" for **both**. The open question is how to sequence it
and how deep to go in each suite. Constraints that apply to every option:

- **PDF forms stay in LawHand.** Word and Docs do not fill AcroForms well, and
  phases 1–2 already give on-page filling there.
- **LawHand stays the engine and the record.** Templates, matter data, Smart
  Fill, review state and the saved document stay in LawHand. The suite is
  where people type and co-author. This matches the position in the M365 and
  Google review.
- **Fix the known blockers first:** D08 (editing a matter document in Word
  breaks LawHand's access), D34 (a LawHand save orphans Word Online edits) and
  D09 (Word drafts saved as plain text). Every option below depends on
  documents surviving a round trip.

### Option A: Open and sync back, both suites (S–M), recommended first

Generate the DOCX in LawHand as today, save it to the matter's cloud folder,
and offer **Open in Word** or **Open in Google Docs** beside Download.

- **Microsoft:** Word for the web (`webUrl?action=edit`) or the desktop app
  (`ms-word:ofe|u|…`).
- **Google:** Docs opens a `.docx` in Office-compatibility editing and keeps it
  a DOCX, so the file is not converted and formatting survives. The review
  doc warns against converting to a native Google Doc.
- **Edits come back** through the snapshot path that AI drafts already use
  (**Refresh edits from cloud**, `cloud_docx_snapshot.py`). Each snapshot is a
  new revision and resets review. Change notifications (Graph subscriptions,
  Drive Workspace Events) can replace the manual refresh later.
- **Reach:** 100% of customers, with one code path parameterised by provider.
- **What it doesn't do:** fill fields inside the editor. It is "fill in
  LawHand, finish in Word or Docs."

### Option B: Microsoft-first deep integration, filling inside Word (L)

The Word add-in task pane becomes the guided bar. It shows the same field
order, required and missing state, matter suggestions and provenance, served
by the Smart Fill endpoints. LawHand fields become **tagged content controls**
in the template. **Next** selects the control, and an answer is written into
it after the approval step the add-in already requires.

- **For:** Word is the lingua franca of legal drafting, and our templates are
  DOCX already. An add-in already exists with Nested App Authentication, and
  content controls are planned (`office-document-assistant-plan.md:265`,
  `:296`). Clio for Word and Microsoft's Legal Agent have set this
  expectation. The same controls also give Word-side authoring (Clio parity
  W2).
- **Against:**
  - The add-in's cookie session fails in Word for the web and new Outlook
    (D20).
  - Word for the web supports NAA only for files opened from OneDrive or
    SharePoint.
  - WordApi version floors apply (1.4–1.8 baseline, because LTSC/Office 2024
    lacks 1.9).
  - Tenant admins must deploy the add-in (Integrated Apps).
- **Reach:** Microsoft 365 firms only.

### Option C: Google-first deep integration (M–L)

Merge with `files.copy` plus `documents.batchUpdate`: `replaceAllText`, or
**named ranges** as the field anchors (`replaceNamedRangeContent`). Open the
result in Docs, and add a **Docs sidebar** (a Workspace add-on) that shows the
guided bar and writes into named ranges.

- **For:**
  - The API merge is simpler than Office.js.
  - Co-editing is native.
  - The `drive.file` scope and the Picker avoid a restricted scope.
- **Against:**
  - This path needs native Google Docs templates. Converting DOCX to a Google
    Doc and back loses formatting, so firms would keep a second template
    format or author in Docs.
  - Workspace add-ons built outside Apps Script use card-based UI, not a free
    HTML page, so the sidebar would be simpler than the LawHand bar.
  - Publishing to the Marketplace needs Google review.
- **Reach:** Google Workspace firms only. In legal, most of them still exchange
  DOCX with other parties.

### Option D: One panel, two hosts (L, after A)

Define a suite-neutral **field anchor contract**: a LawHand field key mapped to
a Word content-control tag or a Google Docs named range. Build the guided panel
once as a LawHand web page, embedded as the Word task pane and the Docs sidebar
(or, where the host needs cards, a thin card front-end over the same API).
Each host adapter only knows how to find, select and write an anchor.

- **For:** one fill UX everywhere: LawHand, the Word pane and the Docs sidebar
  all share the guided bar, review state and Smart Fill. No second
  interpretation of fields.
- **Against:** it is the largest total effort. Most of it is Option B's work
  plus a smaller Google adapter.

### Comparison

| | A. Open & sync back | B. Word fill (Microsoft first) | C. Docs fill (Google first) | D. One panel, two hosts |
| --- | --- | --- | --- | --- |
| Customers served | All | Microsoft 365 | Google Workspace | All |
| Effort | S–M | L | M–L | L (after A) |
| Fields filled inside the editor | No | Yes | Yes | Yes |
| Keeps DOCX formatting | Yes | Yes | Only with native Docs templates | Yes (Word); native Docs templates for Google |
| Builds on existing code | Cloud working copy, snapshot, matter folders | Office add-in, NAA | Drive integration | A + B |
| Main risks | D08/D34 round trip | D20, add-in deployment, API floors | Template format split, Marketplace review | Scope |

### Recommendation

1. **Ship Option A for both suites first.** It is the fastest way to "open in
   the customer's cloud office" for everyone. It forces the round-trip fixes
   (D08, D34, D09) that every later option needs, and it measures how often
   people actually edit after generating.
2. **Then build Option D with the Microsoft adapter first, unless tenant data
   says otherwise.** Before committing, count connected providers per tenant.
   The integrations already record which suite each firm connected. If Google
   firms are the majority of active tenants, build the Google adapter first:
   the panel and anchor contract are the same either way.
3. **Treat Option C as the Google adapter of D,** not as a separate product.
   Offer native-Docs templates only to firms that want to author in Docs.

## 9. LawHand's own editor: deferred

**Decision.** Build Option A only. Editing happens in the firm's Word or Google
Docs, which every customer already has. LawHand keeps filling, preview,
review, the record and signing.

**Why.**

- There is no editor service to run and no licence to buy.
- Word and Docs give the firm's real fonts, styles, tracked changes, comments
  and co-authoring.
- Most document-prep edits are field answers, and those already happen in
  LawHand on the page (phases 1–2).

**What we accept.**

- Editing happens in another tab.
- It needs a working connection, which Microsoft 365 now requires an
  administrator to approve.
- Getting edits back depends on the round-trip fixes (D08, D34, D09).
- Google Docs editing a DOCX directly has some formatting limits.

**Mitigations.**

- A **Download / Upload revised version** fallback that saves a new version.
- A "being edited in Word since …" marker on the document.
- Changes are brought back when the person returns, and the hash check never
  overwrites an edit silently.
- LibreOffice stays the renderer for previews and PDFs.

**Revisit triggers.** Measure these once Option A ships:

- how often a document is opened in Word or Docs for something other than
  answering fields;
- how often a missing or broken connection blocks editing;
- whether firms ask to edit without leaving LawHand.

If any is significant, pilot Collabora on the same checkout and revision model.
Option A builds that model, so nothing needs redoing.

**If revisited: engine options.**

| Engine | Fidelity | Cost and risk | Fit |
| --- | --- | --- | --- |
| **Collabora Online** (LibreOffice in the browser, WOPI client) | High for DOCX. It is the same engine we already use for previews and PDF output, so what you edit matches what we render. | We implement a **WOPI host** (check file info, get/put file, lock and unlock); this is a normal, documented integration. Running it needs a separate service. A subscription is needed for production support and for large deployments. | **Recommended.** WOPI's Lock/Unlock/RefreshLock calls map directly onto the checkout model above. |
| ONLYOFFICE Docs | High for DOCX | Commercial licence required to embed it in our product. Its own document server. | Viable if its licence cost is acceptable. |
| Rich-text editor (e.g. ProseMirror-based) over a DOCX subset | Loses layout, tables, headers and section formatting on round trip | Cheapest, fully ours | Fine for letters and emails, not for court or agreement documents. |

If revisited, the pilot would run behind a feature flag. We would implement
the WOPI host against the same revision store as Option A, and offer **Edit in
LawHand** beside **Open in Word/Docs**.
