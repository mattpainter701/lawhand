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
exists. A global item is a shared, read-only reference; it cannot be attached
directly to a matter.

## Bring a global form into the firm

Choose **Add to firm** for a global form. The application loads the catalog
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
