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
| `bindings` | no | `{field name: platform variable path}` for authored forms. |
| `origin` | no | `"authored"` marks a form written in-repo rather than imported. |
| `provenance` | no | Where the form came from — see below. |

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

Four titles repeat across the imported catalog:

| Title | Variants (slug · fields · bytes) |
| --- | --- |
| ND Divorce | `nd-divorce` 9 · 344,984 · `nd-divorce-2` 18 · 202,367 · `nd-divorce-3` 91 · 1,540,490 |
| ND Divorce Start | `nd-divorce-start` 122 · 1,401,111 · `-2` 10 · 1,204,654 · `-3` 58 · 1,209,801 |
| ND General | `nd-general` 10 · 1,215,900 · `-2` 74 · 1,468,220 |
| Ohio Divorce With Children | `ohio-divorce-with-children` 94 · 1,383,544 · `-2` 88 · 651,480 |

These are distinct files — different hashes, sizes, and field counts — so they
cannot be de-duplicated mechanically. They are not labelled either: a
distinguishing label invented after the fact would render as authoritative on
the page where a paralegal picks a form to file. The library instead shows the
objective differences it has (field count, and provenance once recorded) and
says plainly that several forms share the title. Deciding per variant — label
them as editions, or curate the catalog down — is a data decision for a human
once provenance is backfilled.
