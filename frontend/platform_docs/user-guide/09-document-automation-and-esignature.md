---
slug: document-automation-and-esignature
title: Template Studio & e-signature
description: Turn trusted documents into tested templates, prepare reviewed drafts into a matter, and send documents for signature from the matter.
order: 90
read_time: 16 min
icon: sparkles
---

# Template Studio & e-signature

[Template Studio](/templates) turns the Word and PDF documents your firm already trusts into reusable templates. A template is built from a sample, tested with real matter data, and published; after that, anyone can prepare a reviewed copy straight into a matter and send it for signature.

Every step keeps a person in control: detected fields are suggestions, Smart Fill values are reviewed before saving, and nothing is sent for signature until you confirm it.

## Studio home

Open [Template Studio](/templates).

![Template Studio home with the Upload Sample button, the library summary, the standard client paperwork and sample form library cards, and the Continue setup, Needs attention, Awaiting publish, and Published queues above the library tabs](/guide-assets/template-studio-home.webp "Template Studio home")

1. **Upload Sample** starts a template from a Word or PDF sample. **New Template** starts one by hand.
2. **Continue setup** lists drafts still being set up or tested. **Needs attention** lists templates whose source file is missing.
3. **Published** lists templates your team can use. **Awaiting publish** lists tested drafts waiting to be published.
4. The tabs switch between the **Templates** library, the shared **Field Library**, and **Generate / Smart Fill**.

The cards across the top count the whole library: **Library** (every template), **Ready** (available to generate), **Drafts** (to test and publish), and **Attention** (missing source files). The queue counts also cover the whole library, even when a queue shows only its first few templates.

In the **Templates** tab, search by title or description, filter by status or category, and page through results. Select **Open in Studio** on a template to open its workspace at `/templates/{template-id}/studio`. **Template sets** opens the sets described [below](#template-sets).

### What a template's status means

| Status | Meaning |
| --- | --- |
| **Draft** | Being set up; not available to your team. |
| **Test failed** | The latest test found a problem. Fix it and test again. |
| **Tested · awaiting publish** | The current version passed its test and is ready to publish. |
| **Published v3** (for example) | Version 3 is available to your team. |
| **Paused** | Taken out of use by the firm. |
| **Needs source** | The original sample file is no longer available; recreate the template from the original document. |

## Build a template from a sample

### Upload the sample

1. Select **Upload Sample** (or go to `/templates/new`).
2. Drop the file on **Sample document**, or browse for it. You can upload one PDF, DOCX, TXT, PNG, JPEG, TIFF, BMP, or WebP file of up to 50 MB.
3. Wait while LawHand renders the document and detects fields.

For reliable detection, use PDFs with real form fields where you can. For scans, use upright, high-contrast pages and include a filled sample when possible.

> [!WARNING]
> Password-protected files, dynamic XFA forms, PDF scripts or actions, and embedded attachments are rejected. Export the file as a standard static PDF or DOCX first. LawHand is a controlled template and field-placement tool, not a general PDF editor.

To write a template from scratch instead, select **New Template** (`/templates/new?mode=manual`). Closing an unfinished template returns you to Studio home.

### Review the fields

Under **Review your document and fields**, LawHand highlights what it detected. Detection is a starting point: a high field count does not prove that the sample's own names and amounts are gone.

1. Work through **Next field to review**. Each field shows whether it still **Needs review**, was **Reviewed against source**, or is **Excluded**. An **AI proposal · verify** label marks a suggestion to check with extra care.
2. To add a field, highlight the exact words on the document and select **Make selection a field**. Every matching occurrence of that exact text uses the same value.
3. For each field, give it a label your team understands, such as "Client name" or "Monthly payment", and choose what it **Fills from**.
4. Use **When to use this template** to describe the scenario, such as "divorce with children".
5. Check every page for blanks you have not mapped and for names or amounts that belong only to the sample.

**Help with setup** in the workspace repeats these steps.

### Mark fields in a Word document

You can prepare a Word file before uploading it. The **Field Library** tab lists shared fields and what each fills from.

- Use a meaningful placeholder, such as `{{client_name}}` or `{{retainer_amount}}`, then choose its **Fills from** source in Studio.
- Repeat the exact same placeholder for the same fact, and give different facts different names, such as `{{retainer_amount}}` and `{{hourly_rate}}`.
- Uppercase brackets such as `[CLIENT NAME]` also work. Repeated generic brackets such as `[AMOUNT]` are reviewed one by one. Bold text, underlining, and blank lines are hints only.
- Keep each placeholder in one paragraph with consistent formatting.

Keep a field's meaning stable: `client_name` should not be an individual in one template and a company's billing contact in another. Custom client and matter fields appear in the library when they are active; fields your firm marks sensitive are not available in Studio.

### Test the draft

1. Open the **Test** view of the template's workspace.
2. Select **Open test values and preview**, choose a matter for Smart Fill, and review any missing details and their source evidence.
3. Inspect every page of the output: names, dates, amounts, conditional sections, tables, page breaks, headers, footers, and signature blocks.

The **Test** view shows the result: **Version 4 passed** (for example), **Latest test failed**, or **Not tested since the latest edit**. A passing test belongs to one exact version; any later field, wording, or logic edit needs a new test.

### Publish

When the tested version is right, select **Publish tested version**. Your team can then use it with **Use on a matter**. If you edit a published template later, the published version stays available to your team until you test and publish the new one.

**Versions** lists every saved draft and published state, newest first, and can restore an earlier one without retyping it. **Activity** shows what changed and when. Record why you changed a template, and never replace a source file in a way that makes earlier documents impossible to explain.

### Plaintiff and defendant fields

Caption fields come from contacts given the exact **Plaintiff** or **Defendant** role in the matter's **Parties** panel:

| Variable | Meaning |
| --- | --- |
| `{{plaintiff_name}}` / `{{defendant_name}}` | The primary contact for that role, or the first listed contact when no primary is marked |
| `{{plaintiff_names}}` / `{{defendant_names}}` | Every contact for that role, primary first, separated by semicolons |
| `{{plaintiff_email}}`, `{{plaintiff_phone}}` and address fields | Details for the single plaintiff chosen above |
| `{{defendant_email}}`, `{{defendant_phone}}` and address fields | Details for the single defendant chosen above |

The address suffixes are `street`, `city`, `state`, `zip`, and `country`, as in `{{defendant_city}}`. The shorter `{{plaintiff}}` and `{{defendant}}` still work, but new templates should use the `_name` forms.

`client_name` always means the matter's client, not the plaintiff, and `counterparty` is the matter's general counterparty summary, not the defendant. For an older matter without caption parties, Smart Fill may infer a plaintiff and defendant only when **Represented Side / Our Role** names one side; those values are marked for review and should be replaced by adding the parties. See [Define caption parties](/guide/matters-and-documents#define-caption-parties).

## Standard client paperwork

**Add the standard client paperwork** on Studio home adds a standard fee agreement and client intake form to the firm library as drafts. Fee, trust-account, and contingency terms differ by jurisdiction, so an attorney must review, complete, and approve them before they are sent. A template of the same name that your firm already has is left untouched. See [Send the client paperwork](/guide/intake-and-call-reception#send-the-client-paperwork).

## Prepare a document into a matter

1. Open a published template and select **Use on a matter**, or start from the matter or from [Prepare](/templates/prepare).
2. Choose the matter. LawHand fills the fields it can find from the matter.
3. Review each value, fill in anything missing, and mark values as verified. The page opens on the **Document** view:
   - For a PDF form, type into each box on the page.
   - For a Word or text template, select a highlighted placeholder.

   The bar under the document shows the selected field at full size, with its source, **Confirm**, **Verify**, and **Next**, **Previous**, and **Next required**. Press Enter in a field to verify it and move to the next one to check. Box colours show what needs you: amber for a required answer that is missing, violet for a suggestion to check, and green for a verified value.
4. Prefer a list? Choose **Questions** at the top for the field list beside the document. LawHand remembers your choice on this browser.
5. Choose **Preview** to inspect the exact generated document. For a PDF, the preview updates as you type.
6. Save. The document is saved to the matter's documents, in the folder named in the link when there is one.

After saving, the same page can create an e-signature request for the new document. See [Send a document for signature](#send-a-document-for-signature).

Before saving any generated document:

1. compare names, pronouns, entities, dates, amounts, and addresses with the source records;
2. check that conditional sections appeared correctly;
3. inspect page breaks, tables, signatures, headers, and footers;
4. remove placeholders and drafting notes; and
5. confirm the destination matter and file name.

Smart Fill and AI analysis speed up assembly; they do not approve legal content. The **Generate / Smart Fill** tab in Studio offers the same review for a template and matter you choose there.

### Documents in progress

What you type on the Prepare page is kept for fourteen days, encrypted, with the fields you marked verified. Only the person who started it can open it.

- Wait for **Answers saved** before closing the browser. If saving or restoring fails, keep the page open and use **Retry**. Refreshing the page restores the same answers.
- The matter's **Documents** section lists **Documents in progress** with **Resume** and **Discard**.
- Saving a document closes its draft. If the file saves but the draft cannot close, keep the page open and choose **Retry closing this draft**; it finishes closing without creating another copy.

## Documents from a workflow

A workflow template can list documents to prepare alongside its checklist. When someone approves a workflow run on a matter, each listed document is pre-filled from the matter and given to its assignee as a **Prepare** task that opens the draft under **Documents in progress**. The workflow itself generates, saves, and sends nothing: the assignee reviews, verifies, and saves the document as usual. Rolling the run back cancels the task and discards an unsaved draft.

## Template sets

A [template set](/templates/sets) groups the templates one matter's packet needs, such as a fee agreement, an engagement letter, and an intake form, so one interview fills them all. Preparing a set runs the same fill, review, preview, and save steps for each member; each member is saved to the matter separately and can be sent for signature from the set.

A suggested dropdown answer must match one of the options. Recognized state names and abbreviations are matched automatically; an unmatched suggestion stays missing until you choose an answer.

## Fill a sample form

The **Sample form library** on Studio home holds reference forms, such as powers of attorney, leases, and court forms. They are reference material, not legal advice.

1. Filter by **Type** or **Jurisdiction**, or search by form title. **Preview** shows the source form.
2. Choose **Fill**. The form opens on the **Document** view: every page of the original form, with each answer box ready to type in. Required boxes that are still empty are amber, and answers taken from a matter are tinted blue until you change them.
3. To pre-fill answers, choose **Fill from a matter** and search by client name, matter name, or number. Changing to another matter clears the previous matter's answers.
4. Type directly on the page, or use the bar under the document. It shows the current answer at full size, with **Next**, **Previous**, and **Next required** to move through the form in reading order. This works well on a small screen, or when a box on the form is too small to read. Answers the form keeps off the page are also reached with **Next**.
5. Prefer a list? Switch to **Questions** at the top. It shows the same answers, grouped by page. Use **Missing** to focus on required answers that are still empty, **Optional** or **Filled** to narrow the list, or **All** to review everything. You can switch between **Document** and **Questions** at any time without losing answers.
6. Choose **Preview filled PDF** to open the **Final PDF** view, review every page, then **Download filled PDF**. Changing an answer removes the final PDF, so the download always matches what you reviewed.

A sample download does not create a firm template or save anything to the matter. A numbered field label identifies a location on the form, not a verified legal meaning: check the form's issuing authority, edition, and suitability before using it. When you pick a template from a matter, **Add to firm** turns a sample into a firm template that you then set up and test.

## Read details from a completed form

1. On the matter's **Documents** section, open **Read details from a document** and choose the saved file.
2. Select **Find details**. If the document came from a known template, choose its **Printed form** and select **Read against the printed form** to compare the answers with the original field positions.
3. Review each proposed value against the document before accepting it.

Reading a scan can take several minutes; keep the page open, and retry if a timeout or connection error appears. Reading alone never changes the matter's details.

## Send a document for signature

Clients sign in their client portal, inside the document. Requests are managed from the **E-Signature** panel on the matter's **Overview**.

1. Under **Document to sign**, choose a final document from **Select document…**, or **Upload a prepared PDF**.
2. Select **Review and send**.
3. Select **Add signer** for each person: enter the **Signer email** and choose the role (**Client**, **Co-client**, **Attorney countersigner**, **Witness**, or **Signer**).
4. Tick **Require signers to complete in listed order** if the order matters.
5. Under **Review PDF signing positions**, check **Where each signer will sign**. Fields in the PDF and printed signature lines are detected automatically; place a signature, initials, or date block for a signer only when the form has neither.
6. Tick **I have checked where each signer will sign**.
7. Set when the request **Expires**, the **Reminders** (days before expiry, such as `7,1`), and optionally **Due from client**, which creates a follow-up task.
8. Select **Send for signature**.

Verify every signer's email address and authority before sending. The software records the signing; the responsible professional still confirms execution requirements, identity, attachments, and any notarization or witness rules.

### Track requests

The **Signature queue** shows each request as **Awaiting**, **Partial**, or **Done**, and flags overdue requests.

- **Resend** sends the invitation again to the signers who can act now.
- **Void** cancels a request.
- When a client uploads a signed paper copy instead, it appears as **Signed copy uploaded — review**. Open the copy, then **Accept** it to file it to the matter, or **Reject** it with a reason that tells the client what to redo.

### Correct a request

If a document changes after you send it, never ask anyone to sign the superseded version. **Void** the request, keep its history, prepare the corrected document, and send a new request with a clear explanation. Keep signed documents and signing evidence under the matter's retention and filing policy.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| **Use on a matter** is disabled | The template has no published version, its source is missing, or you have unsaved changes | Save, test, and select **Publish tested version**. |
| **Publish tested version** is missing | The current version has not passed a test, or it is already published | Open **Test** and run **Open test values and preview**. |
| A template shows **Needs source** | The original sample file is no longer retained | Recreate the template from the original document. |
| An upload is rejected | The file is protected, dynamic, scripted, has attachments, or is over 50 MB | Export a standard static PDF or DOCX and upload that. |
| A Smart Fill value is wrong | The matter record is incomplete or the field fills from the wrong source | Correct the matter record, or change the field's **Fills from**, then test again. |
| A plaintiff or defendant field is blank | No contact has that exact role on the matter | Add the party in **Matter settings** > **People**. |
| A signer never received the request | The email is wrong, or the invitation was filtered | Check the address, then **Resend**. |

## Related chapters

- [Matters & documents](/guide/matters-and-documents)
- [Intake & call reception](/guide/intake-and-call-reception)
- [Teams & client portals](/guide/teams-and-client-portals)
