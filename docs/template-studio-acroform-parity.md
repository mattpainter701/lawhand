# Template Studio — AcroForm parity findings

**Date:** 2026-09-15
**Method:** a firm-authored client questionnaire + fee agreement was converted to an
AcroForm PDF and driven through every reachable stage of the shipping template
pipeline, with the shipped sample-library `client-questionnaire.pdf` run beside it
as a control. Each finding below was reproduced against the repository's own
services, not inferred from reading them.

**Status (2026-09-15):** all seven findings are fixed. The table below records
what was wrong and how it was verified; each finding now carries the change that
resolved it. Issues #512-#518.

**Question asked:** can Template Studio take a firm's own fillable PDF from upload
to a generated, signable document without hand-holding?

**Answer:** yes for discovery, binding, activation, generation and signing — those
five stages are solid, and a correctly authored AcroForm passes all of them. No for
authoring: the repository's own PDF authoring script emits forms the renderer then
refuses to generate, and nothing in the save path can undo it. Findings 1 and 2 are
the blockers; finding 3 is a live mis-classification that fires on a label present
on nearly every American intake form.

---

## Stage-by-stage result

Run against `docs/tenant-forms/wcbls/wcbls-client-questionnaire-fee-agreement.pdf`
(41 fields: 37 text, 4 radio) and the shipped `intake/client-questionnaire.pdf`
(114 fields: 62 text, 52 checkbox).

| Stage | Entry point | Authored form | Shipped control |
|---|---|---|---|
| 1. Field discovery | `pdf_templates.discover_pdf_fields` | PASS 41 fields | PASS 114 fields |
| 1b. Required-field audit | `/Ff` bit 2 | PASS none required | **52 required** |
| 2. Schema construction | `seed_sample_templates._variable_schema` | PASS | PASS |
| 3. Binding catalogue | `template_bindings.is_valid_binding` | PASS 12 declared | PASS 11 declared |
| 4. Smart Fill resolution | `template_bindings.declared_bindings` | PASS 7 auto / 5 manual | PASS 11 auto |
| 5. Server page preview | `pdf_templates.render_pdf_page_preview` | **FAIL** widgets invisible | **FAIL** widgets invisible |
| 6. Activation gate | `validate_representative_pdf_variables` | PASS | PASS |
| 7. Generation (editable) | `fill_pdf_template(enforce_required=True)` | PASS 47,592 B | **FAIL** |
| 7. Generation (flattened) | `fill_pdf_template(enforce_required=True)` | PASS 97,148 B | **FAIL** |
| 8. Signature placement | `esign.plan.build_plan` | PASS signature + date | PASS signature + date |

Value round-trip was verified separately: all 41 written values, radio selections
included, read back identically from the generated PDF.

---

## Finding 1 — CRITICAL: every authored checkbox is required, and a required checkbox blocks generation

**Fixed** — `build_library_intake_forms.py` now passes `fieldFlags=CHECKBOX_FLAGS`
(empty) and `RADIO_FLAGS` (`"radio"`), the three seed PDFs are rebuilt with zero
required fields, and `build_form()` fails the build if any field comes back
required. `test_authored_forms_generate_with_every_checkbox_false` is the
regression.


`reportlab.pdfbase.acroform.AcroForm` defaults its button field flags to
*required*:

```
textfield  fieldFlags default = ''
checkbox   fieldFlags default = 'required'
radio      fieldFlags default = 'noToggleToOff required radio'
```

`backend/scripts/build_library_intake_forms.py` never overrides `fieldFlags` on its
`checkbox()` calls, so `/Ff` bit 2 is set on every one. All three shipped
starter-pack forms carry it:

| Form | Checkboxes | Marked required |
|---|---|---|
| `engagement_letter/general-legal-services-fee-agreement.pdf` | 39 | 39 |
| `intake/client-questionnaire.pdf` | 52 | 52 |
| `intake/prospective-client-intake-form.pdf` | 39 | 39 |

The renderer then treats a required checkbox as unsatisfied unless it is *checked*
(`backend/app/services/pdf_templates.py:1837`, AcroForm branch):

```python
for name, field_type in required_variables.items():
    value = str(variables.get(name) or "").strip()
    if not value or (field_type == "checkbox" and not _truthy(value)):
        missing_required.append(name)
```

So generating the shipped questionnaire with every checkbox answered *false* —
the only truthful answer for most of them — fails:

```
Required PDF field(s) are empty or unchecked: asset_bank_accounts, asset_business,
asset_investments, asset_other, asset_real_estate, asset_retirement, asset_vehicles,
communication_apps, communication_email, communication_in_person, communication_letters,
communication_other, communication_phone, ...
```

This is not merely inconvenient, it is **unsatisfiable**. The same form declares
`existing_case_yes`, `existing_case_no` and `existing_case_unsure` — three mutually
exclusive answers — all required. No set of answers generates the document.

`enforce_required=True` is set on the paths that matter: activation preview
(`routers/document_templates.py:4092`, `:4245`), matter-bound generation (`:5144`,
`:5162`) and the document workspace (`services/document_template_workspace.py:282`).
The three forms a firm is handed to start with therefore cannot produce a document
against a matter.

**Fix:** pass `fieldFlags=""` on `checkbox()` and `fieldFlags="radio"` on `radio()`
in the library builder, rebuild the three PDFs, and add a build-time assertion that
no authored field comes back from `discover_pdf_fields` with `required` set.
`backend/scripts/build_wcbls_client_forms.py` does all three and can be copied.

**Regression test worth adding:** assert every seeded sample library form generates
with all checkboxes false and `enforce_required=True`.

---

## Finding 2 — HIGH: a source-required field can never be made optional

**Fixed** — option (a) and (b) together. The save path and the renderer now honour
review for checkboxes specifically, while a source-required *text* field keeps its
requirement; discovery emits `source_required` so the editor can disable the
control, with an explanation, exactly where it is genuinely locked.


The save path ORs the submitted value with the discovered one
(`backend/app/routers/document_templates.py:1492`):

```python
# The source controls geometry/type/options and a source-required
# field can never be weakened, but review may promote an optional
# AcroForm field to required for downstream automation.
field["required"] = bool(authoritative.get("required") or submitted_required)
```

and the renderer re-asserts it at generation time from the live PDF, not the stored
schema (`pdf_templates.py:1795`):

```python
if not is_signing_template_field(actual_field) and (
    actual_field.get("required") or field.get("required")
):
```

Verified: saving the shipped questionnaire's schema with `required: False` on every
field and generating still fails with the same `Required PDF field(s) are empty or
unchecked` error.

Meanwhile `PrepareFormWorkspace.jsx:587` renders an editable **Required** checkbox.
Unticking it and saving appears to work and changes nothing — the field comes back
required.

The intent (a form author cannot weaken a constraint the source document asserts)
is defensible on its own. Combined with finding 1, where the "constraint" is a
library-authoring accident rather than anything the form's author chose, it means
the only repair is re-authoring the PDF. A firm that uploads a reportlab-produced
form of their own hits a dead end with no in-product route out.

**Fix (pick one):** (a) let review weaken `required` on a checkbox specifically,
since an unchecked box is a meaningful answer in a way an empty text field is not;
or (b) keep the lock but surface it — make the UI control read-only with an
explanation when the source asserts required, so the setting stops silently
reverting.

---

## Finding 3 — HIGH: "Middle Initial" turns a name field into a signing initials widget

**Fixed** — `_is_initials_field()` tests the field name and the label against
different patterns and vetoes both on name-part wording, so a name box stays text.
The WCBLS form's label is back to the firm's own "Middle Initial", and its build
guard calls the engine's classifier rather than a copy of its regexes.


`backend/app/services/esign/plan.py:80`:

```python
_ACROFORM_INITIALS = re.compile(r"(?i)\binitials?\b|_initials?(_|$)")
```

`_widget_kind()` applies it to `f"{widget.pdf_field_name} {label}"` — the field name
concatenated with its tooltip — and promotes any match to `kind="initials"`, which
`PlanField.is_signature_kind` counts as a signing field.

Reproduced on the first draft of this form. The field `client_name`, labelled
`"Last Name, First Name, Middle Initial"` exactly as the firm's Word original writes
it, was planned as:

```
kind=initials  role=client  page=1  source=acroform  rect=(48.0, 634.0, 318.0, 647.0)
```

That rectangle is the client's own name box. The portal would render an initials
control over it and ask the signer to initial inside their name.

"Middle Initial" appears on a large share of American legal intake forms, so this is
a high-frequency trigger rather than an edge case. The other signing patterns are
written narrowly — `_SIGNATURE_LABEL` requires the label to *be* a signature label
rather than merely contain the word, precisely to avoid this class of mistake — but
`_ACROFORM_INITIALS` substring-matches.

Scope: template filling is unaffected, because `is_signing_template_field()` keys off
the schema's `field_type`, which discovery emits as `text`. The damage is confined to
the signing plan — which is where it matters, because that is what the client sees.

**Fix:** anchor the pattern the way `_SIGNATURE_LABEL` is anchored — match a label
that *is* an initials blank (`"Initials"`, `"Client initials:"`) rather than any label
mentioning one. A word-boundary match on a 30-character label is not a strong enough
signal to convert a field into a signature widget.

**Workaround applied here:** the label reads `"Last Name, First Name, M.I."`.
`build_wcbls_client_forms.py` carries `check_signing_classifier()`, which fails the
build if any field label would be misread, so the workaround cannot silently regress.

---

## Finding 4 — MEDIUM (latent): server-side page preview draws no form fields

**Fixed** — `render_pdf_page_preview()` calls `document.init_forms()` before
rendering. The shipped questionnaire went from 73,982 to 638,354 ink pixels.


`pdf_templates.render_pdf_page_preview()` renders with `draw_annots=True` but never
calls `document.init_forms()`. pdfium draws widget appearance streams only when the
document has a form-fill environment, so every AcroForm field is omitted from the
image even though the widgets all carry `/AP` (verified: 46 of 46 on the authored
form, 117 of 117 on the shipped one).

Measured ink, page 1 at scale 2.0:

| Form | As shipped | With `init_forms()` |
|---|---|---|
| Authored | 63,506 px | 388,786 px |
| Shipped control | 73,982 px | 638,354 px |

The page comes back with its printed text and blank space where every input should
be. `/NeedAppearances` is not the cause — removing it changes the output not at all.

**Latent, not currently user-visible.** `POST /templates/intake/pdf-page-preview`
exists and is exported as `previewTemplateUploadPdfPage` in `frontend/src/api.js`,
but no component calls it; `PrepareFormWorkspace.jsx` renders the PDF client-side
with pdf.js, which does draw the widgets. The defect surfaces the moment anything
server-rendered shows a page — thumbnails, PDF cover generation, or the DOCX page
rendering the engine review proposes for visual authoring.

**Fix:** call `document.init_forms()` before `page.render()`. One line.

---

## Finding 5 — MEDIUM: the binding catalogue omits contact columns that already exist

**Fixed** — ten `client.*` entries added (date of birth, secondary phone,
preferred contact method and window, preferred language, referral source, and the
four emergency-contact keys), with matching Smart Fill candidates and probe
attributes so the approval vocabulary stays in sync.


`template_bindings._CATALOGUE` exposes eight client paths: `client.name`,
`client.email`, `client.phone` and five address parts. `Contact`
(`backend/app/models/contact.py`) stores considerably more, and none of it is
reachable from a template.

Eight fields on this one form map to columns LawHand already populates:

| Form field | Column that already holds it |
|---|---|
| `client_date_of_birth` | `Contact.date_of_birth` |
| `client_cell_phone` | `Contact.secondary_phone` |
| `best_contact_method` | `Contact.preferred_contact_method` |
| `best_contact_time` | `Contact.preferred_contact_window` |
| `referral_source` | `Contact.referral_source` |
| `emergency_contact_name` | `Contact.emergency_contact` (JSON) |
| `emergency_contact_phone` | `Contact.emergency_contact` (JSON) |
| `emergency_contact_street` | `Contact.emergency_contact` (JSON) |

`referral_source` is the sharpest case: the questionnaire asks "How did you find out
about our firm?", the answer is stored on the contact under that exact name, and the
template cannot reach it.

This is the cheapest high-value fix available — the data, the resolver and the
schema field all exist; only catalogue rows are missing. A firm can work around it
today by defining custom contact fields and binding `custom.contact.<uuid>`, but that
means re-declaring columns the product already ships.

---

## Finding 6 — LOW: the authoring DSL has no radio construct

**Fixed (construct)** — `RADIO(...)` and `Choice(...)` are available and covered by
`test_radio_block_builds_one_exclusive_field`. Converting the existing library
forms' yes/no groups is deliberately left out: it renames fields, so it needs its
own manifest and binding refresh.


`build_library_intake_forms.py` offers `CHECKS(...)` only, so every mutually
exclusive question in the shipped library is modelled as independent checkboxes —
`existing_case_yes` / `existing_case_no` / `existing_case_unsure` are three boxes a
client can tick all of.

The engine supports radio groups correctly end to end: `_discover_pdf_fields` reports
`field_type: "radio"` with `options` read from `/_States_`, `fill_pdf_template`
validates a submitted value against those options, and the flattened output draws
the selected button. Verified on the four radio groups in this form. The capability
is simply unused by the authoring layer.

---

## Finding 7 — LOW: importing a PDF helper pulls in the whole application

**Fixed** — `app/services/__init__.py` resolves its re-exports through PEP 562
`__getattr__`. Importing `app.services.pdf_templates` no longer loads the
embeddings stack, openai, Stripe, Redis or pgvector.


`app/services/__init__.py` eagerly imports `EmbeddingService`, so
`from app.services.pdf_templates import discover_pdf_fields` — a module whose only
real dependency is pypdf — transitively requires FastAPI, SQLAlchemy, pgvector,
Stripe, Redis, tiktoken, asyncpg and the JWT middleware. Any build or analysis script
touching PDF templates needs a full application environment.

**Fix:** make `app/services/__init__.py` lazy, or leave it empty and let callers
import the submodule they need.

---

## What the engine handles well

Worth stating plainly, because the findings above are all authoring-side or
classification-side and none of them impugn the core:

- **Discovery is exact.** Qualified field names through `/Parent` chains, radio
  `/_States_`, `/TU` tooltips as labels, per-widget geometry, colours, border styles,
  alignment and `/DA` font size. Rotated widgets and unsupported border appearances
  are rejected with actionable messages rather than rendered wrong.
- **Generation is correct.** All 41 values round-tripped, radio selections included,
  in both editable and flattened output. The flattened render places text accurately
  inside every box and draws the selected radio.
- **Signature placement needs no setup.** `build_plan()` found the printed
  "Signature" rule and its paired "Date" rule on page 2 and emitted one signature and
  one date placement for the client role, entirely from the drawn lines. No `/Sig`
  widget is needed or wanted.
- **The active-content posture is real.** `_validate_no_active_content` rejects
  JavaScript, embedded files, XFA, launch and submit actions, and external GoTo
  targets before anything else touches the file.
- **Bindings work as designed.** `declared_bindings()` tolerates pre-binding schemas,
  a `manual` declaration genuinely suppresses name matching, and an unknown path
  fails the save rather than silently falling back.

---

## Order the fixes landed in

1. **Finding 1** — rebuild the three library PDFs with correct field flags, and add
   the generate-with-all-checkboxes-false regression test. Until this lands, the
   starter pack does not work.
2. **Finding 3** — anchor `_ACROFORM_INITIALS`. Small, and it stops a visible
   client-facing mistake on a very common label.
3. **Finding 5** — add the missing `client.*` catalogue rows. Pure upside, no
   migration.
4. **Finding 2** — decide between weakening the lock for checkboxes and making the
   UI honest about it.
5. **Findings 4, 6, 7** — one-line fix, a DSL addition, and an import cleanup.
