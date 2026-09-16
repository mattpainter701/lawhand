# Two visual editors: what they share, what they don't, and what to do

**Date:** 2026-09-15
**Status:** the diff `docs/template-studio-consolidation-plan.md` §4 named as
"the first task under step 3", now done. Steps 1 and 2 of that plan are
implemented. **The step 3 decision has since been taken: direction (a).** The
upload wizard no longer carries a field editor, `PrepareFormWorkspace.jsx` is
retired, and `TemplateStudioEditor` is the one visual editor. This document is
kept as the measurement the decision rested on, and as the record of what was
ported across rather than lost.

---

## Why this had to be measured

The plan's step 3 offered two directions — Studio absorbs intake, or Studio is
retired — and said the choice turns on whether consolidating is a merge or a
rewrite. It also said the headline difference (Word support, the binding
picker) does not explain the line gap, and that the remainder decides.

It does not explain the gap. But the gap was the wrong thing to measure.

## The numbers

Measured after steps 1 and 2 landed, which added to both files:

| | Lines | Editor machinery | Unique to it |
|---|---|---|---|
| `PrepareFormWorkspace.jsx` | 723 | ~460 | ~260 |
| `TemplateStudioEditor.jsx` | 1023 | ~500 | ~440 |
| `WordImportWorkspace.jsx` | 138 | — | .docx intake, no canvas |

**197 lines are byte-identical** after whitespace normalisation, and another
~120 differ only in class names or a single expression.

Studio is bigger because it does more, not because it is heavier per feature.
The number that matters is the other one: **roughly two-thirds of
`PrepareFormWorkspace` is code Studio already has.** The duplication is the
cost, and it is being paid now — the six divergences below are what it bought.

## What is genuinely shared

Byte-identical or near-identical in both: `updateField`, `removeField`,
`setCoverSource`, `fitWidth`, the canvas size derivation, the page/`pageCount`
derivation, the `clamp` and `setViewport(null)` effects, `indexedFields`
selection, duplicate-name detection, the 50-deep undo/redo shape, the
`react-rnd` prop set, and `visiblePlacements`.

The parts that would normally force a rewrite are already one module:

- **Coordinate math** is `pdfFieldGeometry.js`, whose header says the two
  surfaces must agree byte-for-byte. Both call `geometryToOverlays`,
  `overlayToCanvasRect` and `canvasToOverlayRect` with the same signature.
- **Field identity** is `fieldIdentity()`; both key `Rnd` on
  `${identity}:${index}` and resolve the selected entry the same way.
- **Repeated placements per page** work identically in both, via
  `placementsFor()` and a placement index.
- **AcroForm geometry locking** is identical in both.
- **The persisted shape** is the same: `{ page, rect, pdf_overlay,
  pdf_overlays }` plus the same `erase_source` fan-out.

## What only intake has (~260 lines)

| Capability | ~Lines | Studio's need |
|---|---|---|
| Its own pdf.js loader | 51 | **None.** `useTemplatePdfDocument` is the extracted version Studio already uses. Pure duplication, kept only to fire the review callbacks from its catch block. |
| Source-review gate + external fallback | ~85 | **The gate, no** — it is a pre-creation concept and `TemplatesPage` blocks creation on it. **The fallback, yes** — Studio prints a message and leaves fully armed placement tools over an empty div. ~30 of the 85. |
| Page thumbnails | 34 | Already in Studio in 11 lines; the extra is the non-PDF placeholder. |
| Preview / "Test" mode | ~28 | **None.** Studio has a real `/test` tab against matter data; this is a typing sandbox. |
| Image (non-PDF) source | ~20 | **None after upload.** The server converts every image to PDF (`image_to_pdf`), so a saved template's source is always a PDF. Intake needs it because it previews the original file. |
| Keyboard nudge and delete | 16 | **Yes** — ported in this change. |
| `source_required` lock | 20 | **Yes** — ported in this change. |
| Re-include checkbox | 2 | **Yes** — ported in this change. |
| Review-state colouring | ~25 | Yes; Studio had one flat accent colour. |
| AI-proposal panel | 6 | Yes, cheap. |

## What only Studio has (~440 lines)

.docx support and `addDocxField` (~82), the Word preview and wording editor
(~57), the markdown-template branch (25), repeating regions (~31), cover and
whiteout regions (~37), applicability/scenario rules (~19), per-field
conditional logic (37), `value_from` linking (6), signer roles (13), the
save/dirty lifecycle (~62), click-to-place tooling (~18), the derive-draft
action (19), field search (~5), and the module-level schema API (28).

## What was done

Direction (a). The wizard's job is now getting the file in and scanned; the
editor's job is making it right. `handleUploadedTemplate` already redirected to
`/templates/{id}/studio` after create, so the handoff needed no building — only
the duplicate editor needed removing.

Three things were ported into `TemplateStudioEditor` first, so nothing was
lost with the file: the failed-preview path (offer the original, refuse to
place a field whose position cannot be measured), review-state colouring, and
the AI-proposal panel. The keyboard, `source_required` and re-include ports had
already landed with the divergence fixes.

Two things had to change to make the handoff honest, and both turned out to be
improvements rather than costs:

* **The source-review attestation moved to publish** (`pdf_source_review`). It
  had gated *creating a draft*, which a draft does not warrant — it generates
  nothing — and it asked for the check on the one screen where a field that
  looks wrong could not be corrected. It was also never enforced: the checkbox
  disabled a button in the browser and was never sent anywhere.
* **"Include at least one field" was dropped from create.** It was right while
  the wizard was the only place to place a field. Kept, it would have refused
  the draft that is now the only route to the editor where fields are placed —
  leaving a firm holding a flat PDF with nowhere to go.

One regression was caught by the wizard's own tests and fixed: the document
preview panel was suppressed for PDF because the editor carried its own, so
removing the editor left a firm looking at a list of field names with no sight
of the document they came off. Every format shows the preview now.

## Verdict as measured: a merge, with one prerequisite

Consolidating is **a merge, not a rewrite**, on the evidence above: the
coordinate math, field identity, placement handling and persisted shape are
already one implementation.

**The prerequisite is state ownership.** `PrepareFormWorkspace` is a controlled
component — `fields` is a prop, every mutation goes through `onFieldsChange`,
and the parent's handler has a side-effect contract: it rewrites `draftBody` on
a rename or exclude, and clears `reviewConfirmed` on every edit.
`TemplateStudioEditor` owns `fields` and commits mean "set state, mark dirty".

That difference dissolves if intake hands off **after** the template row
exists: the body rewrite and the review invalidation belong to the pre-creation
analysis screen, not to a geometry editor. It becomes a rewrite only if Studio
is embedded **inside** the wizard as a controlled component, which means
inverting its entire state model.

Rough movement for direction (a), as estimated before it was done:

| | Lines |
|---|---|
| Delete intake's duplicate pdf.js loader | −51 |
| Delete intake's page rail, canvas, Rnd block, undo/redo, commit, field list, binding picker | ~−440 |
| Port into Studio: external-fallback gate, review-state colouring, AI panel | ~+60 |
| Rewire `TemplatesPage` to redirect to `/templates/:id/studio` after create | ~30–60 changed |
| Retire `PrepareFormWorkspace.jsx` and fold its tests in | −723 + test migration |

The keyboard, `source_required` and re-include ports are already done, so they
are off this list.

## The six divergences, and why they are the real argument

These were found by the diff, not by a bug report. Every one is a silent
failure — the editor accepts the edit and the product does something else —
and every one exists because the same behaviour is written twice. All six are
fixed in this change; see `CHANGELOG.md` 2026.09.15.05.

1. Intake mis-scaled placements in its own external-fallback path — the one
   path it exists to protect, and the one where nobody can see the page to
   notice.
2. Studio stored "paragraph" in a shape the renderer does not read, so a
   paragraph re-typed there stopped wrapping.
3. Studio offered a Required checkbox and a Type select on AcroForm fields that
   the server silently overwrites on save.
4. Excluding a field in Studio could not be undone through the UI.
5. Studio's canvas was unusable by keyboard.
6. Two of Studio's six undo snapshots dropped cover regions, and the next save
   persisted the loss.

Fixing them is not an argument for consolidating; it is a measurement of what
one round of divergence costs. There will be another round.

## Not fixed here

- `firstPageFor` precedence is inverted between the two (intake uses
  `field.page || overlay.page`, Studio inlines the reverse). They disagree only
  for a field whose stored page and first overlay page differ.
- Studio's `FIELD_TYPES` omits `choice` and `radio`; a discovered choice field
  now keeps its own value in the select rather than falling back to the first
  option, but neither can be chosen deliberately.
- Name validation is enforced in different places — per-field inline messages
  at intake versus a save-blocking banner in Studio. Both are defensible; if
  they merge, the inline messages are the better of the two and should survive.

## What should not happen

A third editor. And "add visual field coverage" as though it does not exist —
it exists in both, and as of this change both also report where each field's
value comes from.
