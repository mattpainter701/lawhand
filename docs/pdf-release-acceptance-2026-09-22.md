# PDF filling acceptance and product corrections

The production audit of build `329df4e400d6a67e8533d35954f3b90dcb1afe19`
found usable single-PDF rendering but failed draft recovery, incomplete mixed
packets, ambiguous sample questions, and a workspace unable to save to its
configured OneDrive connection. This change addresses the reproducible code
defects. A code/test pass does not establish that a tenant's cloud grant works.

## Product flow

The everyday flow is **choose a matter → review missing answers → preview →
save or download**. Template setup belongs to authoring; ordinary preparers
should reuse the information the firm already entered.

Primary product references reviewed on September 22, 2026:

- [Gavel integrations](https://www.gavel.io/use-cases/integrations) describe
  searching client records and importing matter/contact data. LawHand's matter
  picker now searches beyond the recent page and sample filling uses the same
  tenant-scoped suggestion engine as firm templates.
- [Gavel PDF automation](https://www.gavel.io/use-cases/pdf-automation) and
  [PDF setup guidance](https://help.gavel.io/articles/automating-pdf-documents)
  keep questions connected to their document fields. The sample flow now keeps
  a source/generated PDF beside grouped questions and offers missing/all filters.
- [Clio Draft templates](https://www.clio.com/draft/templates-service/)
  emphasize reuse of matter data. The packet interview must include every
  placeholder and reuse canonical bindings across documents.

These references inform interaction choices; they do not establish a measured
time-saving comparison. No customer data was sent to these services.

## Defect disposition and acceptance

| Observed issue | Correction / required retest |
| --- | --- |
| Resume loses manual values and verified ticks | Restore before automatic suggestions; serialize draft writes; expose retry failures. Resume after navigating away and after refreshing. |
| Packet omits Markdown fields and reports complete | Discover body placeholders; include them in questions and required totals; inspect the Markdown preview. |
| Packet alias fields do not prefill; dropdown becomes text | Resolve local names in bounded batches and preserve explicit manual bindings and choices. Compare single/packet values. |
| Sample filling is manual-only | Select a matter, reuse suggestions, show missing answers and a PDF preview. Switch matters and fail a request to check isolation. |
| Ambiguous authored intake choices and fee signer names | Exclusive labeled radio groups; distinct signer labels; preserve source defaults. Visually check both regenerated sources and their outputs. |
| Literal undefined labels and unreviewed samples | Honest numbered/page fallback, original metadata retained, source-review warning. This is not source curation or legal validation. |
| Storage summary claims OK while grant cannot refresh | Derive readiness from the actual selected provider and storage permissions. Reauthorize and separately prove upload/reopen on Microsoft and Google. |
| Google retry may upload after a failed existing-file lookup | Stop before upload when lookup is throttled, unavailable or interrupted. Preserve no-match uploads and checksum-based reuse. |
| Narrow Prepare view lets controls widen the page | Use a shrinkable single-column grid below the desktop breakpoint; visually retest the form and PDF preview at 884px. |
| Studio field and paused-template counts disagree | Discover body fields consistently; exclude paused templates from draft count. |
| Printed-form reading shows a generic failure before the server's successful response | Give field-by-field reading the existing 300-second budget; show progress and retry guidance; discard stale responses after context changes. |
| Microsoft cloud search returns invalid entity combination | Separate file/mail requests and cap mail results at 25; preserve successful results when one source request fails. |
| A saved single document remains in the matter's in-progress list | Drain autosave and complete the session against its persisted document; serialize late writes and retry completion without a duplicate render. |
| Packet state code is counted filled while its dropdown shows no answer | Normalize recognized state aliases to an option; leave unmatched suggestions missing. |
| Profile crashes before personal cloud reconnection controls appear | Normalize decimal-string totals before formatting and ignore non-finite values. |
| Authored intake PDF prints literal emphasis markers around radio prompts | Remove authoring markers from the source prompts and regenerate the PDF and manifest digest without changing its controls. |

The Microsoft follow-up follows the [Graph Search API limits](https://learn.microsoft.com/en-us/graph/api/resources/search-api-overview?view=graph-rest-1.0): one search request per HTTP call, supported entity combinations, and the smaller message page size. It does not replace reauthorization when Microsoft requires MFA.

## Release acceptance requirements

Use clearly labeled synthetic QA data. For each cloud provider, save one PDF
and a mixed packet, find the saved files on the matter, reopen the actual bytes,
and verify values and layout. Then exercise background packet save and retry.
Do not change a production workspace's primary provider merely to get a pass.

The audited workspace's Microsoft grant had an MFA-related refresh failure;
Google was disconnected. Those require account authorization and are not fixed
by a status badge. Neither provider has an end-to-end pass until tested with a
working connection.

All 80 seeded PDFs parsed and matched their recorded digests during the audit.
Duplicate/generic labels and three zero-area-widget forms remain source-review
candidates. This release does not certify every seed's edition, legal currency,
or field meaning. OCR, handwriting, client signing and full responsive coverage
need their own acceptance results; do not infer them from rendering unit tests.
