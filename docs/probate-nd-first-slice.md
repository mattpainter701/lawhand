# North Dakota probate: intake, track determination, and pre-filled court forms

This is the first shipped slice of [`probate-estate-workflow-plan.md`](probate-estate-workflow-plan.md):
a North Dakota probate intake that decides which proceeding an estate needs and pre-fills the
State Court Administrator's informal-probate forms from the estate record. It lives inside the
**Trust, Estate & Probate** add-on (`trust-estate-legal`). Everything probate-specific is in
`backend/app/services/probate/` and `backend/app/routers/probate.py` behind one constant,
`PROBATE_ADDON`, so it can be resold as its own add-on later without moving data or screens.

## The four tracks

| Will? | Time since death | Track | Court forms |
|---|---|---|---|
| yes | ≤ 3 years | `informal_testate` — informal probate of will and appointment (30.1-14-01) | NDPC Forms 2, 3, 4, then 5, 7 (+ 6, 9, 10, 15 when needed) |
| no | ≤ 3 years | `informal_intestate` — informal appointment in intestacy (30.1-14-01) | NDPC Forms 17, 18, 19, then 5, 7 (+ 6, 9, 10, 15) |
| yes | > 3 years | `formal_testate_late` — formal testacy under the 30.1-12-08 exceptions | none published; the firm's own petition, notice, order, letters |
| no | > 3 years | `formal_intestate_late` — adjudication of intestacy / determination of heirs (never time-barred) | none published; the firm's own pleadings |

Two off-ramps: `small_estate_affidavit` (probate property ≤ $100,000, no real property, 30 days
after death; Form 1, never filed) and `not_nd_domicile` (no North Dakota domicile or property).
The rules, with their statutes, are in `app/services/probate/determination.py` and are tested
as a table in `tests/unit/test_probate_determination.py`. The determination is advisory: the
attorney changes it by correcting a fact, never by editing the result.

## Three ways to answer the same questions

The probate intake (`PROBATE_QUESTIONS` in `app/services/practice_resolution.py`, practice
`probate`) is written for an older client who may never have used a court or a website:

1. **Portal questionnaire** — typed controls (date, yes/no, money, state list), plain-language
   help under each prompt, an "I don't know — the office will help" choice on optional questions,
   and "Save and finish later" kept on the client's device (`ClientIntakeChecklist.jsx`).
2. **Paper** — the authored fillable PDF `nd-probate-intake-questionnaire` (built by
   `backend/scripts/build_library_intake_forms.py`), whose field names are the question keys so a
   mailed copy reads straight back in through `read_pdf_form_values`.
3. **Staff, by phone** — the Facts form on the estate's Probate tab is the same question set.

All three land in `estates.probate_facts` (`ProbateFacts`, `app/services/probate/facts.py`).
Client answers reach the estate only through **Pull from client questionnaire** on the Probate
tab; the questionnaire submit itself only previews the track in the reviewer's task
(`intake_writeback.plan_writeback`), so nothing bypasses review.

## Court forms: shipped whole, filled once, printed by page

The court publishes *Informal Administration of an Estate* as one 63-page fillable PDF with
340 fields. It ships in the global sample library (`backend/seed/sample_templates/court_form/nd-informal-probate-guidebook.pdf`,
`origin: "court_form"`) with four companion forms, and is copied into a firm's own templates as a
draft the first time the Probate tab is opened (`app/services/probate/install.py`,
`app/services/sample_import.py`). The firm never uploads a court form.

- The PDF widget cap was raised from 200 to 400 (`MAX_PDF_WIDGETS`) so the packet stays whole.
- `GUIDEBOOK_BINDINGS` in `app/services/probate/forms.py` maps 164 of the fields onto the new
  `estate.*` binding group; Smart Fill resolves them from the estate linked to the matter
  (`app/services/probate/bindings.py`, wired into `document_templates._collect_smart_fill_candidates`).
- Generating the template produces all 63 pages filled from the same facts; the Probate tab says
  which pages to print for each form (`page_ranges`, read from the PDF's own headers and checked
  against the registry by `tests/test_nd_probate_forms.py`).
- The template installs as a **draft**. An attorney publishes it in Templates before "Generate"
  is enabled — the same review gate as any uploaded form.

Rebuilding after the court re-issues the guidebook:

```
python backend/scripts/build_nd_probate_guidebook.py --source <guidebook.pdf> \
  --companion nd-probate-declaration-of-service-mail=<...> ... --dry-run   # prints every field and its binding
python backend/scripts/build_nd_probate_guidebook.py --source <guidebook.pdf> --companion ...
python backend/scripts/seed_sample_templates.py
```

The build strips hyperlinks, the tagged-structure tree, outlines and metadata (the template
engine refuses `/URI` actions), clears any required bit, and sets the multiline flag on the heirs
and inventory fields. It stops if the field map names a field the PDF no longer has, a binding
the catalogue does not know, or a form whose page range moved.

## The clock

`app/services/probate/deadlines.py` computes the statutory dates from the estate's anchors
(date of death, appointment, first publication of the notice to creditors, closing statement
filed) and upserts `estate_deadlines` rows by type, optionally mirrored as matter tasks. A
completed row is never moved; rows are never deleted. The rules table cites 30.1-18-05,
30.1-18-06, 30.1-19-01/-03/-06, 30.1-05, 30.1-21-03, 57-37.1-07, and 50-06.3-07.

## Client-portal estate inventory

`app/routers/client_portal_estate.py` adds an "Estate inventory" tab to the native portal once the
personal representative is appointed (or staff open it early). The client lists items in plain
words with a rough value and an optional statement or photo; rows are `source="client_portal"`,
`verification_status="unverified"` until staff verify them on the estate's Assets tab. Only verified
rows feed the Form 10 inventory totals. The overlay fails closed (404) without an active
entitlement, without exactly one estate on the matter, or for a different contact.

## Routes

All under `/api/plugins/trust-estate`, gated by `require_addon_workflow(PROBATE_ADDON)`:

| Route | Purpose |
|---|---|
| `GET /estates/{id}/probate` | facts, determination, anchors, forms state, deadline preview |
| `PUT /estates/{id}/probate/facts` | save staff-entered facts and re-run the determination |
| `POST /estates/{id}/probate/facts/from-intake` | read the linked matter's questionnaire answers (`overwrite` optional) |
| `POST /estates/{id}/probate/determine` | recompute |
| `PATCH /estates/{id}/probate/anchors` | appointment / publication / letters / closing dates |
| `POST /estates/{id}/probate/deadlines/sync` | build or move the clock (`mirror_tasks`) |
| `GET /probate/forms`, `POST /probate/forms/install` | the ND pack, installed on first sight |
| `POST /estates/{id}/assets/{asset_id}/verify` | staff review of a client-submitted asset |

Portal: `GET /api/portal/client/estate`, `POST /api/portal/client/estate/assets`,
`PATCH /api/portal/client/estate/assets/{id}`.

## Known limits

- PDF generation is human-in-the-UI; the MCP `propose_document_from_template` capability refuses
  PDF templates.
- Fields in the guidebook whose purpose could not be read from the printed form (`undefined*`,
  notary blocks, clerk signature lines) are left unbound and filled by hand.
- A re-issued guidebook needs the build script re-run and the field map re-checked.
- Estate routes in the frontend are gated by the `plugins` module only; the backend entitlement
  guard remains authoritative.
