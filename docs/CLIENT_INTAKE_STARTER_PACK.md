# Client intake starter pack

Matter initiation opens with the same three pieces of paperwork for every
client. This document says what they are, where the content lives, how a matter
type selects the right questions, and what a firm must review before anything
reaches a client.

## What the client receives

| Piece | What it is | Where it lives |
|---|---|---|
| Fee agreement | Standard terms of legal representation: scope, exclusions, fees, trust deposit, costs, billing, client responsibilities, termination, file retention. | A `document_templates` row, category `engagement_letter`, installed as a **draft**. |
| Client questionnaire | The case-specific questions. Eight shared questions plus a set chosen by the matter's practice. | Printed as a fillable AcroForm PDF per practice (see below); the firm sends its own copy through **Send client paperwork** like the other two pieces. The question list itself is no longer typed into the paperwork drawer. |
| Client intake form | The client's own data — identity, contact, entity, conflict-check, billing, referral. Answered once and reused. | A `document_templates` row, category `other`, installed as a **draft**. |

All three are defined in `backend/app/services/intake_starter_pack.py`. Nothing
in that module sends, approves, or files anything.

## Attorney review is required before use

Fee terms, client trust accounts, and contingency arrangements are regulated
differently in every jurisdiction. The two documents install with
`status = "draft"` and `approved_at = NULL`, so they cannot be selected as a fee
agreement for an intake packet until an attorney reviews them for the firm's
jurisdiction and approves them through the normal template path. Installing
again never touches a template of the same name that is already there: a firm
that edited or approved its own agreement keeps it.

The jurisdiction-neutral agreement leaves explicit places for jurisdiction-
specific language — `{{trust_account_terms}}`, `{{dispute_resolution_terms}}`,
`{{jurisdiction_required_terms}}` — rather than guessing at a rule. The North
Dakota variant answers them in its own wording and records the jurisdiction it
was drafted for on the template row, so a firm can see what law the text was
written against.

A field may carry a `default` only where a jurisdiction or a settled convention
decides it — the billing increment, the confidentiality rule, the days a
statement is due. Rates, retainers, trial fees, and venue never carry one: those
are the firm's to set, and a suggested number would be read as advice.

## How a matter type picks the questions

`resolve_practice()` reads two free-text labels the firm typed: the matter type
first, then the practice area. In the live library many matters are typed
`general` and carry the real signal in the practice area ("Family Law"), so
either label can decide. A specific alias wins over a generic one — "breach of
contract" resolves to litigation, not to the "contract" in business — and an
unrecognised matter falls back to the general pack rather than to no questions
at all.

| Practice | Recognised labels include |
|---|---|
| `family` | family law, divorce, custody, support, paternity, adoption, protective order |
| `criminal` | criminal defense, DUI, DWI, felony, misdemeanor, expungement, juvenile |
| `injury` | personal injury, car accident, premises, malpractice, wrongful death |
| `estate` | estate planning, probate, will, trust, guardianship, elder law |
| `employment` | employment, termination, discrimination, wage and hour, severance |
| `business` | business, commercial, contract, corporate, entity, M&A, NDA, SaaS |
| `real_estate` | real estate, landlord, tenant, eviction, lease, closing, title, HOA |
| `immigration` | immigration, visa, green card, naturalization, asylum, removal |
| `bankruptcy` | bankruptcy, chapter 7, chapter 13, foreclosure, garnishment |
| `litigation` | litigation, dispute, lawsuit, demand, subpoena, appeal, breach of contract |
| `mediation` | mediation, arbitration, settlement conference, collaborative |
| `general` | anything else |

Each practice also names the documents the client is asked to send back. They
are offered as a suggested list in the drawer's optional **Records to request
from the client** section and only become upload requirements when staff
switch that section on.

## Field bindings and document automation

Every placeholder in both documents is declared in the template's
`variable_schema`, and each declares where its value comes from: a path from the
server-owned binding catalogue (`client.name`, `matter.case_number`,
`matter.hourly_rate`, …) or `manual`. Terms the matter's own records already
carry fill from them — the contingency percentage (`matter.contingency_percentage`),
the retainer and its replenishment threshold (`matter.retainer_amount`,
`matter.retainer_minimum_balance`, resolved from the matter's current retainer
record), and venue (`matter.venue`). Fee amounts the firm must decide — flat
fees, deposits, rate ranges — and scope and exclusions stay `manual`: a fee
term is decided by a person, never inferred from a record.

That is what makes the intake form worth collecting: its fields carry the same
bindings the rest of the document automation fills from, so a value the client
supplied once is reused rather than retyped into every later document.

## Endpoints

| Endpoint | Capability | Purpose |
|---|---|---|
| `GET /api/intake-starter-pack?matter_type=&practice_area=` | `manage_matters` | The questions, requested uploads, and document list for a matter type. |
| `GET /api/intake-starter-pack?matter_id=` | `manage_matters` | The same, reading the labels off an existing matter the caller may access. |
| `GET /api/intake-starter-pack/practices` | `manage_matters` | Every practice and the labels it recognises. |
| `POST /api/intake-starter-pack/documents` | `manage_documents` | Install any missing starter template as a draft. |

The MCP surface does not create templates: its write-like tools only produce
reviewable proposals. Installing the starter templates goes through the endpoint
above or Template Studio.

## Fillable PDF versions

`backend/scripts/generate_intake_starter_pdfs.py` renders the same markdown
sources as fillable AcroForm PDFs — the fee agreement, the intake form, and one
questionnaire per practice:

    python backend/scripts/generate_intake_starter_pdfs.py --out build/intake-pack

Every form field is named after the template's own variable or the question's
own key, so a returned PDF maps back onto the same bindings, and Template
Studio's existing AcroForm discovery finds the fields when the PDF is uploaded
as a source-backed template. Regenerate after changing any template body or
question; `backend/tests/unit/test_intake_starter_pdfs.py` fails if the printed
form and the template stop agreeing.

Three differences from the rendered markdown are deliberate. The fee agreement's
conditional fee sections (`{{#if hourly_rate}}` and the rest) all print, since a
paper form has no renderer to choose between them — strike the arrangements that
do not apply. A placeholder with a declared `default` is pre-filled with it, so a
jurisdiction-settled term such as the North Dakota billing increment is visible
on the form rather than hidden in an empty box. And signature lines are printed
as ruled lines with a "Signature" (or "Client signature") and "Date" label,
exactly the shape the portal's signature-line detection looks for, so the
client's electronic signature lands on the printed line when the form is sent for
signature.

## A completed sample for review

A partner reviewing a template wants to read a finished agreement, not a form of
placeholders:

    python backend/scripts/render_starter_sample.py --document hourly_fee_agreement_nd

It fills the template through the product's own renderer and writes a `.docx`.
The sample values are fictional and exist to show the wording; they are not a
recommendation about any firm's rates or terms. `--values` takes a JSON file to
override them.

## Where staff see it

* **Template Studio home** — "Standard client paperwork" adds the fee agreement
  and the intake form as drafts for review.
* **Start this case** — the drawer lists the fee agreement, the client intake
  form, and the client questionnaire as the three common pieces, each a PDF the
  firm supplies with a "Client signs this form" toggle, followed by additional
  forms and an optional **Records to request from the client** section whose
  "Use the suggested list" button fills it from the matter's practice pack. It
  is a deliberate action, never automatic.

Any subset may be sent. A fee agreement is optional: when one is included,
signing it opens the portal and starts the 24-hour follow-up clock; when none is
included, the portal opens on the first message and the follow-up still runs.

## The same paperwork in the global sample library

The starter pack above installs into one firm's library. The global sample
library — the platform-owned catalog every tenant reads from, in
`backend/seed/sample_templates` — carries the same three pieces as authored,
fillable AcroForm PDFs any firm can open without installing anything:

| Slug | Category | What it is |
|---|---|---|
| `general-legal-services-fee-agreement` | `engagement_letter` | One agreement for every practice area. Fee arrangement — hourly, flat, contingency, hybrid, recurring — is chosen by checkbox, as are the practice area and the stage of representation, so a firm does not keep a template per matter type. |
| `prospective-client-intake-form` | `intake` | First contact, before the firm has agreed to anything. Identity, safe-contact preferences, the kind of help sought, other parties for a conflict check, any filed case, deadlines, prior counsel, referral source, and a firm-use disposition block. |
| `client-questionnaire` | `intake` | Case development after the matter opens: parties, narrative, chronology, existing proceedings and orders, communications, evidence, witnesses, finances, objectives, and a preservation notice. |

They are authored in `backend/scripts/build_library_intake_forms.py` — that
module is the source and the committed PDF is its artifact — rather than scraped
like the rest of the library:

    python backend/scripts/build_library_intake_forms.py

The script renders each form, strips the PDF's authoring metadata, writes it
into the seed tree, and merges its manifest entry. Entries are marked
`"origin": "authored"`, which `scripts/build_sample_template_library.py`
preserves when it rebuilds the scraped catalog around them.

### Fields are the platform's variables

Every field is named after the variable the platform already fills from
(`client_name`, `matter_name`, `hourly_rate`, `retainer_amount`, `case_number`,
`venue`), and the manifest declares the binding behind each one. The seeder
attaches those declarations to the catalog row's `variable_schema`, so Smart
Fill resolves them without a firm re-declaring anything, and an answer a client
gives on one of these forms is reused rather than retyped. A binding path the
catalogue does not recognise fails the build rather than seeding a field that
quietly fills from nothing.

Fields with nothing behind them — a witness's phone number, an event date — are
left unbound rather than declared `manual`, so ordinary name matching still has
a chance at them.

The questionnaire's narrative answers use the shared intake question keys
(`matter_summary`, `desired_outcome`, `other_parties`, `key_dates`,
`related_proceedings`, `contact_preferences`), which is what lets a returned
form be read back into the matter's intake record.

### What the forms deliberately do not decide

The same rule as the starter pack applies: a field carries a default only where
a convention settles it — the billing increment, the minimum time charge, the
days a statement is due, a notice period. Rates, retainers, flat fees,
contingency percentages, late charges, and venue never carry one, and the
regulated wording (`trust_account_terms`, `dispute_resolution_terms`,
`jurisdiction_required_terms`) is left for the firm's attorney to write for its
jurisdiction. Each form states on its face that attorney review is required, and
the intake form states that completing it creates no attorney-client
relationship.

`backend/tests/unit/test_library_intake_forms.py` fails if the committed PDFs
and the authoring module drift apart, if a binding is unknown, if a form crosses
the studio's 200-widget limit, or if a fee field acquires a suggested amount.
`backend/tests/test_sample_template_library.py` holds the catalog side.
