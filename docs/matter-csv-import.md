# Bulk create matters from a CSV template

Matter managers with `manage_matters` use **New Matter → Bulk create from CSV**
to enter a client's many existing matters at once. The sheet carries one row
per matter; the client is reused when it already exists and created otherwise.
Nothing is sent to any client, no matter-created automations fire, and no
cloud folders are provisioned: these are historical matters being catalogued,
as with the folder importer. Files and signed fee agreements are added
afterwards from each matter.

## Template

`GET /api/matter-imports/csv/template` downloads `matters-template.csv` with
the header row and one example row (formula-lead cells are neutralised).
Columns:

| Column | Meaning |
| --- | --- |
| `matter_name` | Required. |
| `description`, `practice_area`, `matter_type`, `case_number`, `court`, `judge`, `jurisdiction`, `venue`, `role`, `counterparty` | Same fields as the New Matter form. |
| `status` | `open` (default), `active` or `pending`. |
| `opened_on` | `YYYY-MM-DD`; the date the firm opened the matter (today when blank; never in the future). Retention runs seven years from it. |
| `engagement` | `existing` (default; stage Active), `review` (Transfer / Review Required) or `required` (Intake / Awaiting Documents). |
| `agreement` | For an existing engagement: `pending_copy` (default; the signed copy is uploaded from the matter later), `signed_no_copy` or `no_agreement`. |
| `agreement_signed_on`, `agreement_note` | Signing date; the note is required for `signed_no_copy` (where it was signed) and `no_agreement` (why there is none). |
| `attorney_email`, `partner_attorney_email` | Active staff members' emails; the attorney of record leads the matter. |
| `billing_method`, `hourly_rate` | `hourly` by default; a number. |
| `client_id`, `client_number`, `client_email` | Reuse an existing client, in that order of preference. A number and an email that name different contacts is a row error. |
| `client_first_name`, `client_last_name`, `client_organization`, `client_phone` | Create a client when nothing above matches. Rows in one file naming the same new client (same number, email, organization or first and last name) share one contact. Names alone never match an existing contact. |

Unknown columns are ignored and reported. Limits: 1 MiB, 500 data rows,
UTF-8 (a byte-order mark is fine).

## Preview and confirm

`POST /api/matter-imports/csv` (multipart `file`, optional `id` for replay)
parses the sheet and returns every row with its normalised values, how its
client resolves (`match` with the contact, `create`, or `create_shared` with an
earlier row), the attorneys, and a list of problems. The run is staged as an
external import (`provider = matter_csv_v1`) bound to the file's SHA-256, so
a repeated preview under the same identifier returns the same run and a
different file is refused. Runs are private to their creator and tenant.

`POST /api/matter-imports/csv/{id}/confirm` with `{"confirm": true,
"include_rows": [...]}` (row numbers as previewed; omitted means all) creates
the included rows' contacts and matters in one transaction: matter numbers,
the open date, the stage for the engagement, the engagement record, the
attorney and importer assignments, a matter event, and a provenance link per
matter and per created contact. An included row with problems, or a client or
staff member that no longer exists since the preview, refuses the whole
confirmation. A confirmation repeated after a lost response returns the stored
results without creating anything more. `GET /api/matter-imports/csv/{id}`
returns the run for resume.

## Afterwards

The results list links to each matter. To bring in files, open the matter →
Documents → Import files & emails, or use **New Matter → Import existing
matters** and choose the new matters as destinations. To file a signed fee
agreement, open the matter and choose **Add signed copy** on its paperwork
card ([Existing engagement](matter-intake.md#existing-engagement-no-paperwork-sent)).

## Validation

PostgreSQL tests cover the template, client and staff resolution, every row
rule, the size and row bounds, replay under one identifier, creator privacy,
confirmation with excluded rows, the refusal of problem rows and stale
previews, and the idempotent repeat. Frontend tests cover the mode in New
Matter, the review table, row exclusion and the results.
