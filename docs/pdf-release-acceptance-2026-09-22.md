# PDF filling acceptance and product corrections

The production audit of build `329df4e400d6a67e8533d35954f3b90dcb1afe19`
found usable single-PDF rendering but failed draft recovery, incomplete mixed
packets, ambiguous sample questions, and a workspace unable to save to its
configured OneDrive connection. This change addresses the reproducible code
defects. A code/test pass does not establish that a tenant's cloud grant works.

## Product flow

The everyday flow is **choose a matter → finish missing answers while reviewing
the document → save or download**. Template setup belongs to authoring; ordinary preparers
should reuse the information the firm already entered.

Published single-document PDFs (including Word templates with PDF output)
preview automatically in the matter dialog and Prepare page. The first preview
waits for restored answers and matter prefill; later previews start after a
650 ms pause in editing. Only one render runs at a time, and responses for old
answers are discarded. While updating, the last PDF is explicitly marked out
of date and cannot be saved or downloaded. Page and zoom choices survive
refreshes. A failed preview offers **Retry preview** without repeatedly retrying
on its own. **Save to matter** still requires all required answers and preview
evidence for the exact current values and matter. Previewing never marks an
answer verified, publishes a template, saves a document or sends it for signing.
Draft publication tests and non-PDF previews remain explicit actions.

Sample-library **Preview** and packet **Open preview** display PDFs inside
LawHand with page navigation and zoom. Sample loading and fetch errors stay
visible in the dialog, with retry and close actions. Closing before a fetch
finishes does not reopen it. Changing packet answers invalidates the displayed
generated preview. Word packet output uses **Download Word preview** for review
in a Word-compatible application. Generating or opening a preview does not
save the document or establish that its contents have been reviewed.

Sample-fill summaries use current answers and the source's declared required
flags. **Missing** shows required blanks; **Optional** shows optional blanks;
**Filled** shows answered controls. An unchecked required checkbox is still
missing, while a numeric zero remains an answer. Source flags are not a legal
completeness determination. Follow-up questions remain visible unless authored
conditional metadata explicitly governs them. Fields without usable source
labels retain numbered/page references and ask the preparer to check the PDF.

For a cloud-search diagnostic, open **Administration → Integrations → Search →
Test Search**. Select the intended sources and enter a distinctive filename or
phrase. **Match exact filename or phrase** keeps that text together rather than
asking the planner to choose keywords; filenames enable this mode automatically.
Full-content fetching is off by default. **Search details** exposes the technical
plan when needed. Selecting a search source does not change document storage or
grant access to another account.

Google Drive exact diagnostics combine literal filename equality with phrase
matching and escape the Drive query value once, following the
[Drive query examples](https://developers.google.com/workspace/drive/api/guides/search-files).
Request-level regression cases include apostrophes, double quotes and backslashes;
live provider acceptance remains a separate check.

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
| Optional sample blanks inflate "need attention" | Derive current-answer counts and separate source-declared required blanks from optional blanks. Check manual edits, defaults, unchecked checkboxes and numeric zero. |
| All values verified but a suggestion still needs review | Checking a suggested value records that exact answer as reviewed in single and packet preparation. A resumed packet restores acknowledgement for saved verified answers even when the interview returns the same suggestion. Editing or unchecking invalidates the review; no matter fact, approval or delivery is implied. |
| Full filename lookup returns unrelated emails | Preserve literal diagnostic queries and expose source selection. Compare a distinctive QA identifier and its full filename; verify the correct file in the selected provider. |
| Folder failure points at File Shares, or pending setup implies waiting is enough | Direct recovery to this matter's Documents / Document tools and check cloud reconnection where needed. Preserve the no-file-stored message, draft answers and existing storage guards. |
| Foreground packet saves are absent from a resumed session; a lost non-PDF save response can be retried as a new file | Use one durable session save path, drain answers first, reconcile current server status, and preserve recorded successful members on retry. Test partial failure, lost queue response, blank optional forms and reopening saved results. |

The Microsoft follow-up follows the [Graph Search API limits](https://learn.microsoft.com/en-us/graph/api/resources/search-api-overview?view=graph-rest-1.0): one search request per HTTP call, supported entity combinations, and the smaller message page size. It does not replace reauthorization when Microsoft requires MFA.

## Release acceptance requirements

Use clearly labeled synthetic QA data. For each cloud provider, save one PDF
and a mixed packet, find the saved files on the matter, reopen the actual bytes,
and verify values and layout. Then exercise background packet save and retry.
Do not change a production workspace's primary provider merely to get a pass.

PDF retries reuse their consumed preview evidence. The packet worker also skips
recorded successful members. A process crash between a non-PDF document commit
and the separate member-status commit is not covered by those protections;
exercise that fault separately before claiming exactly-once non-PDF saves.

The audited workspace's Microsoft grant had an MFA-related refresh failure;
Google was disconnected. Those require account authorization and are not fixed
by a status badge. Neither provider has an end-to-end pass until tested with a
working connection.

All 80 seeded PDFs parsed and matched their recorded digests during the audit.
Duplicate/generic labels and three zero-area-widget forms remain source-review
candidates. This release does not certify every seed's edition, legal currency,
or field meaning. OCR, handwriting, client signing and full responsive coverage
need their own acceptance results; do not infer them from rendering unit tests.
