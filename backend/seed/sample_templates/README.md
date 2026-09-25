# Sample form library — manifest schema

`manifest.json` is metadata only. The PDFs beside it are the artifact, and
field schemas are derived at seed time by `backend/scripts/seed_sample_templates.py`
(via `discover_pdf_fields`), so the PDF plus application code stays the single
source of truth for what is in a form.

## Per-form fields

| Field | Required | Meaning |
| --- | --- | --- |
| `slug` | yes | Stable catalog key. Import-time collisions get a `-2`/`-3` suffix. |
| `title` | yes | Human title. **Not unique** — see [Duplicate titles](#duplicate-titles). |
| `category` | yes | Document type; also the directory the PDF lives in. |
| `jurisdictions` | no | States the source claimed for this content. |
| `description` | no | Shown in the library list. |
| `filename` | yes | `<category>/<slug>.pdf`, relative to this directory. |
| `sha256` | yes | Digest of the shipped bytes; the seeder refuses a mismatch. |
| `size_bytes` | yes | Size of the shipped bytes. |
| `field_count` | yes | AcroForm fields the studio can render. |
| `bindings` | no | `{field name: platform variable path}` for authored forms and curated imports. `"manual"` marks a field a person must type, so it never fills from a same-named client value. |
| `field_labels` | no | `{field name: label}` replacing a label the PDF left meaningless ("Text3", "undefined 2") or ambiguous; the PDF's own label stays as `source_label`. |
| `title_source` | no | `"document"` when `title` (and `description`) were read from the form's own printed title rather than the scraped catalog's name; a rebuild keeps them. |
| `option_labels` | no | `{field name: {export value: label}}` for radio/choice options the PDF names only by export value ("Choice 1"). Filling still writes the export value. |
| `origin` | no | `"authored"` marks a form written in-repo rather than imported; `"court_form"` marks a court packet shipped whole by `backend/scripts/build_nd_probate_guidebook.py`. Both survive a scraped-library rebuild. |
| `page_ranges` | no | `{"<form number>": [first, last]}` for a packet that holds several court forms in one PDF. Read from the PDF's own page headers at build time and re-checked by `tests/test_nd_probate_forms.py`; the Probate tab uses it to tell staff which pages to print. |
| `provenance` | no | Where the form came from — see below. |

## Curated imports

Imported forms arrive with only their PDF field names. Many are meaningless
("Text3", "Check Box4", "undefined 2"), some PDFs' own tooltips are copy-paste
errors, and Smart Fill can only match a field whose name happens to equal a
platform variable — so generic names such as "Address", "Phone Number" and
"Email" matched the *client's* details even in a landlord's, witness's or the
filing attorney's block. Every form that is not `origin: "authored"` is
therefore curated:

- `field_labels` gives each field a specific, unique label read from the page;
- `bindings` says where a value comes from — parties, case number and judge on
  pleadings; the maker (testator, declarant, principal, taxpayer) as the client
  on estate-planning and POA forms; the attorney and firm on attorney signature
  blocks — and marks `"manual"` any field that would otherwise fill by name from
  an unrelated record. Leases, bills of sale and contracts bind no person to the
  client, because the client may be either side;
- `option_labels` names radio/choice options the PDF calls "Choice 1".

`tests/test_sample_template_library.py` enforces this catalog-wide: no
placeholder, over-long or duplicate label, no field that fills by accidental
name match, and no unreadable option. The seeder rejects curation naming a
field or option the PDF does not have.

`scripts/build_sample_template_library.py` carries the curated keys over to the
rebuilt entry with the same `sha256`, and drops them when the file changed;
`update_manifest` (used by the ND probate and intake builders) keeps them for a
byte-identical file unless the builder declares its own.

## `provenance`

```json
"provenance": {
  "source_name": "Example Courts Self-Help Center",
  "source_url": "https://example.gov/forms/divorce-packet.pdf",
  "edition": "Rev. 03/2024",
  "retrieved_at": "2026-02-11",
  "source_files": ["ND Divorce Packet.pdf"]
}
```

Every key is optional and each may also be a list when one shipped file was
built from several source rows. `source_files` carries the import source's own
file names, which is the one distinguisher that is always available.

An unrecognised key fails the seed run: provenance is what tells a user which
of several same-titled forms they are about to file, so it is validated rather
than passed through.

**Provenance is absent for the imported catalog as it stands.** It is populated
by `scripts/build_sample_template_library.py` from the import library's
`catalog.json`, which is not in this repository, so the values arrive on the
next rebuild against that source. Until then the catalog API returns
`provenance: null` and the Template Studio library says the source was not
recorded, rather than implying one.

## Duplicate titles

The scraped catalog repeated four titles ("ND Divorce" three times, "ND
Divorce Start" three times, "ND General" twice, "Ohio Divorce With Children"
twice) over distinct files, and some titles named the wrong document: the file
called "Ohio Divorce No Children" is Ohio Domestic Relations Form 31, a Request
for Service. Curation read each form's own printed title — "Summons",
"Complaint", "Settlement Agreement", "Counterclaim for Divorce With Children
(Form 9)" — and marks those entries `title_source: "document"`. No invented
label: the new title is what the page itself says. Titles are now unique, and
`tests/test_sample_template_library.py` keeps them so.
