# Matter template catalog lifecycle

The matter's **Attach template** picker brings together firm templates and the
shared global library. Search applies to both sources. Firm-template search is
performed by the firm catalog; global results also match their category,
jurisdictions, and recorded source or edition. Source filters let you focus on
firm templates or global references. Global results show their jurisdiction
and provenance, and their PDF can be previewed in the picker.

## Readiness and use

Published firm templates show the published version that is available for a
matter. Draft and paused templates are labeled and offer **Review in Studio**.
Opening a published template uses its published snapshot when a newer draft
exists. A global item is a shared, read-only reference: it can be filled and
saved to the matter as a document, but it is never changed and is not copied
into the firm's templates by doing so.

## Fill a global form on the matter

Choose **Use on this matter** for a global form that carries a field schema.
The fill dialog opens on the form with the matter already chosen and fills
what it can from the matter (Smart Fill). Every suggested value is shown for
review; type on the document or switch to the Questions view to change it.

**Review final PDF** renders the flattened PDF from the current answers.
**Save to matter** then files that PDF in the matter's documents (in the folder
the picker was opened from) through
`POST /api/templates/library/{sample_id}/save-to-matter`. The server renders the
form again from the submitted answers, requires an explicit answer (blank is an
answer) for every field and a value for every required field, and stores the
document with category `generated`. The document's `generation_summary` and its
`document_generated` matter event record the library form, its source and
edition, the source digest and the output digest. Changing any answer discards
the reviewed PDF, so what is saved is what was last reviewed.

After saving, **Share with client** makes the document visible in the client
portal (the same switch as the Documents list), and **Download** saves a copy.
Saving requires the `manage_documents` capability; the matter and folder must
belong to the caller's firm.

A global form without a field schema offers only **Add to firm library**.

## Bring a global form into the firm

Choose **Add to firm library** for a global form when the firm wants to
customize and reuse it. The application loads the catalog
details and source PDF together and checks the PDF's SHA-256 digest against the
catalog metadata. If the digest does not match, the source is not handed to the
upload flow; retry loads the current details and bytes together.

After verification, the PDF enters the ordinary source analysis and field
review form as a file. Analysis of that file remains authoritative for field
geometry, types, options, and page information. Catalog labels and matter
bindings may be carried over only when stable PDF field identities match
uniquely; uncertain or unmatched fields remain for human review. This metadata
is a suggestion, not a confirmation that the field is correct.

Explicitly creating the form saves an inactive firm draft and opens it in
Template Studio. When the import began in a matter, the matter and selected
document-folder context are carried into Studio and its **Back to matter**
path. **Use on this matter** remains unavailable while the template is a draft.
Review and test the draft, then publish a tested version before using it on the
matter. Previewing a global PDF or importing it does not publish the template
or save a document to a matter.
