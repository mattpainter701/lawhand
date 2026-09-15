# Template Studio: consolidation and binding coverage

**Date:** 2026-09-15
**Status:** scoping only. Nothing here is implemented; this document exists to be
picked up in a separate session.
**Relationship to other docs:** `docs/template-studio-engine-review.md` judged the
*model* (bindings, logic, versions). This one is narrower and later: the bindings
it recommended have since landed, and this is about the **authoring surface** —
what a firm sees between uploading a form and having one that fills itself.

---

## The question this answers

> If we upload a sample doc, shouldn't there be visual highlightable coverage
> showing the fields we discovered? Maybe that's how Template Studio should work.

Yes — and it is already built. Twice. The problem is not a missing capability.
It is that the capability is split across two editors, the half a firm reaches
first is the half that cannot bind, and neither one ever tells a firm how much
of their form will actually fill itself.

---

## 1. What exists today

Two independent React editors, both full visual field editors over a rendered
page, both built from the same primitives (`Rnd` draggable/resizable field
rectangles, `DrawFieldLayer`, `PdfPageCanvas`, `PdfThumbnail`, zoom, undo/redo):

| Editor | Lines | Reached from | Formats | Can set a binding? |
|---|---|---|---|---|
| `PrepareFormWorkspace.jsx` | 642 | `TemplatesPage.jsx:1060` — the upload/intake flow | PDF, image | **No** |
| `TemplateStudioEditor.jsx` | 931 | `TemplateStudioWorkspace.jsx:121` — Studio | PDF, Word | **Yes** |

`WordImportWorkspace.jsx` (122 lines) is a third, thinner surface for .docx.

### 1.1 The split that matters

`PrepareFormWorkspace` contains the string `binding` **zero times**.
`TemplateStudioEditor` contains it 16 times and is the only consumer of
`TemplateBindingPicker` (`TemplateStudioEditor.jsx:806`).

So the screen where a firm first sees its own form with every discovered field
highlighted — the moment the question *"what is this field?"* is live in their
head — is the one screen that cannot answer *"and where does its value come
from?"*. Binding happens later, in a different editor, against a field list they
have already stopped looking at.

The data is not the obstacle: `TemplatesPage.jsx:553` already carries
`binding: field.binding || ''` through intake state. Only the control is absent.

### 1.2 Studio's other tabs

`TemplateStudioWorkspace.jsx:165` still renders, verbatim:

> "This route is reserved for the Template Studio {section} view. No {section}
> records or controls are available in Phase 1; the current template remains
> unchanged."

for **Versions** and **Activity**. `document_template_versions` exists (added by
the completion plan described in the engine review), so Versions is closer to
real than the copy suggests — but as shipped, Studio is a second copy of an
editor you already have, wrapped in a shell with two placeholder tabs.

---

## 2. The gap that is actually missing

Both editors report *discovery* coverage:

- `TemplateStudioEditor.jsx:535` — "N fields · N need review"
- `WordImportWorkspace.jsx:58` — "N detected or added fields · N need review"

Neither reports **binding coverage**: how many of those fields will fill
themselves from a matter, and how many are dead weight a human retypes every
time.

For a concrete case — `docs/tenant-forms/wcbls/`, a real firm's questionnaire —
the number that decides whether the template is worth having is:

> **11 of 41 fields fill from the client record.** 10 of those resolve by field
> *name* alone; 4 needed a binding declared; 5 are pinned `manual` on purpose;
> the remaining 25 are genuinely the client's to answer.

Nothing in the product surfaces any part of that, before or after saving. A firm
cannot tell a well-wired template from a badly-wired one, and cannot see what it
would cost to improve one.

This is the central promise of document automation — *generate a document from
matter data in one click* — and it is currently unmeasured in the UI.

### 2.1 The three resolution paths a coverage read-out must model

Any honest indicator has to distinguish these, because they fail differently:

1. **Declared binding** — `field.binding` is a catalogue path. Resolves through
   `alias_for_binding()`. Stable; survives renames.
2. **Name match** — no binding declared, but `_normalize_variable_name(name)` is
   in the Smart Fill vocabulary (`_smart_fill_alias_vocabulary()`,
   `document_templates.py`). Works, but silently stops working if the field is
   renamed. A firm has no way to know it is relying on this.
3. **`manual`** — declared "always typed by hand". Suppresses path 2 by design.
   Correct for an SSN or a card number; a mistake if set by accident.

Everything else is unbound: a box someone retypes on every matter.

Both the resolver and the vocabulary already exist and are already used together
by `_validate_approval_ready()`, so computing this is a read, not new logic.

---

## 3. Constraint: the premium-AI path is metered

`/templates/intake/ai-propose` already proposes a `binding` per field and the
whole chain is wired and safe:

- `AiFieldProposal.binding` → `reviewed_binding()` → `proposed_binding_entry()`
  → applied in `reconcile_ai_template_fields` (`template_ai_assist.py`).
- A path the catalogue does not describe is **discarded**, not stored — the
  comment is explicit that keeping an invented path would let a fill silently
  find nothing.
- A role *instance* is refused even though it is a valid path: which of a
  matter's defendants a blank means is a decision about that matter, not
  something document text can settle.
- Only an explicit `manual` from the model stores `manual`.
- An already-bound field is never overwritten.

But it is gated on `require_capability("use_premium_ai")` **and**
`current_user.premium_ai_enabled`, and those gates are deliberate: the API cost
is billed to the tenant.

**Design consequence.** The manual path is not a fallback for a minority. It is
the default for every tenant without premium AI, and it is exactly the path that
currently has no binding control on the screen where fields are first reviewed.
Any plan that assumes AI proposal closes this gap is wrong for the tenants that
need the help most.

---

## 4. Recommendation

Three pieces, independently shippable, in this order. Each is worth doing alone.

### Step 1 — Put the binding control where the fields are first reviewed

Add `TemplateBindingPicker` to `PrepareFormWorkspace`'s property inspector,
beside the existing Label / Type / Required controls.

The state already carries `binding`; the picker already exists; the save path
already accepts and validates it (`document_templates.py:1347-1358`, validated
against `template_cards.is_valid_path`). This is wiring, not new capability.

*Why first:* it is the smallest change with the largest effect on whether an
uploaded form arrives usable, and it does not depend on either other step.

### Step 2 — Binding coverage, on the page and as a number

Compute the four-way split from §2.1 and show it two ways:

- **As a count**, next to the existing "N fields · N need review":
  *"11 of 41 fill from the record — 4 bound, 6 by name, 1 manual, 30 unbound."*
- **On the page**, as the fill/outline colour of each highlighted field rect, so
  a firm can see at a glance which parts of their form are wired and which are
  a wall of retyping.

Surface *name-matched* distinctly from *bound*. It is the state that works today
and breaks silently on a rename, and a firm currently cannot see that it is
relying on it.

*Open question for whoever picks this up:* the vocabulary check needs the Smart
Fill alias set on the client. Either expose `_smart_fill_alias_vocabulary()`
through the existing bindings/cards endpoint, or compute the split server-side
and return it with the analysis. The second is probably right — it keeps the
name-matching rule in one place — but it has not been costed.

### Step 3 — Decide what Studio is for

Once Step 1 lands, `PrepareFormWorkspace` and `TemplateStudioEditor` do
substantially the same job. Maintaining two visual editors over the same
geometry primitives is the actual cost here, and it is already being paid: the
`required`-control fix in #513 had to be reasoned about in one of them while the
other was untouched.

Two defensible directions — **this needs a product decision, not an engineering
one**:

- **(a) Studio becomes the one editor.** Intake hands off to it after upload.
  Studio keeps Word support and the binding picker; `PrepareFormWorkspace` is
  retired. Versions/Activity become Studio's reason to exist.
- **(b) Studio is retired as a separate surface.** Intake is the editor, Versions
  and Activity move onto the template detail page, and the Phase 1 placeholders
  go away.

What should *not* happen is a third editor, or building "visual field coverage"
as though it does not exist.

Before choosing, someone should diff the two editors properly. The headline
difference is Word support and the binding picker, but 931 vs 642 lines is not
explained by those alone, and the remainder decides whether (a) is a merge or a
rewrite. **That diff has not been done and is the first task under this step.**

---

## 5. What is explicitly out of scope

- **An importable bindings sidecar.** `docs/tenant-forms/wcbls/` ships a
  `.variable_schema.json` listing its bindings, and it was tempting to make the
  upload flow accept one. It is the wrong fix: it only helps forms *we* author
  programmatically, and it would build a JSON-authoring workflow no firm wants.
  Steps 1 and 2 serve the same need on the screen a firm is already looking at.
- **Loosening the premium-AI gates.** See §3 — metered cost, deliberate.
- **Conditionals, repeats and template versions.** Covered by
  `docs/template-studio-engine-review.md` §5 steps 2 and 3. Unchanged by this.

---

## 6. Evidence index

Every claim above is checkable at these locations:

| Claim | Where |
|---|---|
| Two visual editors, same primitives | `PrepareFormWorkspace.jsx`, `TemplateStudioEditor.jsx` |
| Upload flow has no binding UI | `PrepareFormWorkspace.jsx` — zero occurrences of `binding` |
| Only Studio can bind | `TemplateStudioEditor.jsx:806`, sole use of `TemplateBindingPicker` |
| Intake state already carries binding | `TemplatesPage.jsx:553` |
| Save path accepts + validates binding | `document_templates.py:1347-1358` |
| Studio tabs still placeholders | `TemplateStudioWorkspace.jsx:165` |
| Discovery coverage exists, binding coverage does not | `TemplateStudioEditor.jsx:535`, `WordImportWorkspace.jsx:58` |
| Three resolution paths | `template_bindings.declared_bindings`, `_smart_fill_alias_vocabulary`, `_binding_is_resolvable` |
| AI proposes and validates bindings | `template_ai_assist.py` — `reviewed_binding`, `proposed_binding_entry` |
| AI path is gated | `document_templates.py:3110-3125` |
