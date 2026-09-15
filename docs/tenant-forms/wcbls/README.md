# W.C. Black Legal Services PLLP — client questionnaire and fee agreement

A fillable AcroForm conversion of the firm's own Word form
(`WCBLS_Client_Questionnaire_8.26.26.docx`), for import into that firm's tenant.

**Tenant-scoped. Not part of the global sample library.** The manifest in
`backend/seed/sample_templates/` seeds every tenant; this is one firm's paperwork
and its fee terms are theirs, so it is deliberately not registered there.

| File | What it is |
|---|---|
| `wcbls-client-questionnaire-fee-agreement.pdf` | The template to upload. One page, 41 fields. |
| `wcbls-client-questionnaire-fee-agreement.variable_schema.json` | The field schema with bindings already declared, as reference while reviewing the import. |

Rebuild with:

```
python backend/scripts/build_wcbls_client_forms.py
```

The script fails the build rather than emitting a broken template if a binding path
is unknown, a binding names a field that is not in the PDF, any field comes back
marked required, or a field label would be misread as a signing widget.

## What was carried over, and what changed

Every question and every sentence is the firm's own wording. The fee-agreement
terms are reproduced verbatim from the Word source, including the bold emphasis and
the printed `$400.00` hourly rate — those are regulated terms and nothing here
rewords them.

Three things changed, all of them form mechanics rather than content:

1. **`City, State, Zip` was split into three fields.** The Word original packs them
   into one table cell. Split, each one carries its own binding and fills from the
   client record.
2. **`___ Yes ___ No` became radio groups.** The original writes these as blanks,
   which is one answer, not two boxes. A radio group makes the reader enforce the
   exclusivity. Same for `___ VISA ___ MasterCard ___ Discover`.
3. Nothing else. An earlier revision abbreviated "Middle Initial" to "M.I." to
   dodge the signing planner, which read any label containing "initial" as a
   block to be signed and so turned the client's own name box into a signing
   widget. That was fixed in the engine (finding 3 in
   `docs/template-studio-acroform-parity.md`), so the firm's own wording stands,
   and the builder now calls the engine's own classifier as a guard rather than
   a copy of its patterns.

## One page, like the Word original

The Word source sets 0.45in top/bottom and 0.55in side margins — a
532.8 x 727.2pt text block — and fits the whole form in it. The AcroForm
matches that footprint, and the builder is budgeted against it: the content
measures roughly 670pt, leaving the signature block room at the foot.

The move that made it fit is the row layout. The Word table puts a label and
its writing space in the *same* cell, on rows of 389-418 twips (19.5-20.9pt).
An earlier revision of this form stacked the caption above its box, which cost
~29pt a row and pushed the agreement onto a second page. `Sheet.row()` now
places the caption beside its box on a single 18.2pt line, which is what the
original does. Body text is 7.6pt and the fee terms are 7.6pt bold, against
the source's 7.5pt and 7pt.

If a question is ever added, the budget is the thing to check: the builder
does not force a page break anywhere, so extra content simply spills to a
second page.

## Signature

**Do not add a signature field.** The form draws a printed "Signature" rule and a
paired "Date" rule, and `app/services/esign/plan.py` finds them on upload:

```
kind=signature  role=client  page=1  source=detected  rect=(39.6, 67.8, 289.6, 95.8)
kind=date       role=client  page=1  source=detected  rect=(319.6, 67.8, 449.6, 91.8)
```

This is the same shape the shipped library forms use, and it means a hand-signed
copy and an e-signed copy land on the same line.

## Fields and bindings

7 fields fill themselves from the matter and client record. 5 are pinned `manual` so
a coincidental name match can never auto-fill sensitive data. The rest are answered
by whoever fills the form.

| Field | Label | Type | Binding |
|---|---|---|---|
| `client_name` | Last Name, First Name, Middle Initial | text | `client.name` |
| `client_date_of_birth` | Date of Birth | text | manual |
| `client_ssn` | Social Security Number | text | manual |
| `client_street` | Street Address | text | `client.address.street` |
| `client_city` | City | text | `client.address.city` |
| `client_state` | State | text | `client.address.state` |
| `client_zip` | Zip | text | `client.address.zip` |
| `mailing_street` | Mailing Address (if different from street address) | text | — |
| `mailing_city` | City | text | — |
| `mailing_state` | State | text | — |
| `mailing_zip` | Zip | text | — |
| `client_phone` | Phone Number | text | `client.phone` |
| `client_cell_phone` | Cell Phone Number | text | — |
| `client_fax` | Fax Number | text | — |
| `client_email` | E-mail Address | text | `client.email` |
| `spouse_name` | Spouse's Full Name | text | — |
| `best_contact_method` | Best method to reach you | text | — |
| `best_contact_time` | Best time to reach you | text | — |
| `employer_name` | Employer's Name | text | — |
| `employer_street` | Employer's Address | text | — |
| `employer_city` | City | text | — |
| `employer_state` | State | text | — |
| `employer_zip` | Zip | text | — |
| `work_phone` | Work Phone Number | text | — |
| `work_fax` | Work Fax | text | — |
| `work_cell` | Work Cell | text | — |
| `emergency_contact_name` | Emergency Contact Name | text | — |
| `emergency_contact_street` | Contact's Address | text | — |
| `emergency_contact_city` | City | text | — |
| `emergency_contact_state` | State | text | — |
| `emergency_contact_zip` | Zip | text | — |
| `emergency_contact_phone` | Contact's Phone Number | text | — |
| `emergency_contact_messages` | May we leave confidential messages…? | radio `yes` / `no` | — |
| `prior_representation` | 1. Has our firm assisted you before? | radio `yes` / `no` | — |
| `prior_attorney` | If yes, please specify attorney | text | — |
| `referral_source` | How did you find out about our firm? | text | — |
| `card_on_file` | May we bill all payments due to your credit card? | radio `yes` / `no` | — |
| `card_brand` | Credit Card | radio `visa` / `mastercard` / `discover` | — |
| `credit_card_number` | Credit Card Number | text | manual |
| `credit_card_expiration` | Expiration Date | text | manual |
| `credit_card_security_code` | Three Digit Security Code | text | manual |

Eight of the unbound fields hold facts LawHand already stores on the contact
record. Those catalogue rows now exist (finding 5 in
`docs/template-studio-acroform-parity.md`), so date of birth, secondary phone,
preferred contact method and window, referral source and the emergency-contact
block can each be bound in the editor at import time. They are left undeclared
here rather than pre-bound: on a questionnaire the client fills in, an answer
the firm already holds is usually the one worth confirming rather than
pre-filling. Bind them if this copy is being prepared for the attorney instead.

## Before the firm collects card data

The form carries a Social Security number, a full credit card number, an expiration
date and a CVV, exactly as the Word original does. That is the firm's choice to
make, but two points are worth raising with them before the first client fills it
in:

- **CVV must not be stored after authorization.** PCI DSS prohibits retaining the
  card verification value once a payment is authorized. A completed copy of this
  form in a document store is a retained CVV.
- **A filled copy is a card-data record.** Storing full PAN alongside an SSN brings
  the storage location into PCI scope and raises the stakes on a breach.

The usual remedy is to collect card details through a payment processor's own form
and keep the questionnaire to an authorization checkbox. If the firm prefers to keep
the fields, the builder can mark them excluded from generated copies so the data is
captured on the signed original but not carried into anything generated afterwards.
