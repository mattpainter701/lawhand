# Smart Fill engine

**Date:** 2026-09-19
**Status:** shipped on `claude/pdf-auto-filing-mechanism-e5tqb5`, including
Phase 2 (auto-initiation of document prefill); Phase 3 is logged at the end (3a and 3b shipped; see `template-prepare-route-plan-2026-09-19.md`, which also holds Phases 4 and 5).

Smart Fill is the mechanism that fills a template's fields from a matter. This
page says what it is now that it lives in one place, what the quirk campaign
found, what changed because of it, and what is still deliberately open.

## Where it lives

| Piece | Module |
|---|---|
| Sources, registry, vocabulary, resolution, `prepare_fill()` | `backend/app/services/template_fill_engine.py` |
| The four tenant-scoped reads and the `Loaders` bundle | `backend/app/services/template_fill_loaders.py` |
| Fitting a value to a choice, checkbox or date field | `backend/app/services/template_fill_formatters.py` |
| Fill-state read-out (bound / name_matched / manual / signature / unresolved / unbound) | `backend/app/services/template_fill_coverage.py` |
| The binding catalogue and the card grammar | `backend/app/services/template_bindings.py`, `template_cards.py` |
| Route shim (`build_variable_suggestions`, `smart-fill-preview`) | `backend/app/routers/document_templates.py` |
| Quirk campaign and rehearsal script | `backend/tests/fill_campaign/`, `backend/scripts/rehearse_smart_fill.py` |

## How a field gets a value

1. **Sources** are loaded. The matter and its party rows always; the retainer
   and the estate only when a declared binding or an unbound field name asks
   for one of their aliases (`FillSource.needed`). The firm profile and
   tenant custom fields are read by their own services.
2. Every source writes its **candidates** into one `CandidateIndex`, keyed by
   alias (`client_name`, `case_number`, `petitioner_name`, ...), in registry
   order: current user, estate, matter, retainer, party rows, client contact,
   inferred caption, attorney of record. **The first writer of an alias wins.**
   Later writes with a different value are kept as `Collision` records so a
   report can show them; they never change the fill.
3. Each template field is **resolved** in this precedence: a `firm.*` binding
   from the firm profile; a `custom.*` binding from a tenant custom field; any
   other declared binding through its alias; an unbound field by its folded
   name (`re.sub("[^a-z0-9]+", "_", name.lower())`), then by a **synonym**
   (`first_name` -> `client_first_name`, at confidence 0.9 and flagged for
   review); otherwise `no_deterministic_source`. A declared binding never
   falls back to the name.
4. The suggestion is **fitted** to the field: a choice or radio widget gets an
   option's export value (matched by value or label, case-insensitively; a US
   state by code or name either way), a checkbox gets `true`/`false`, a
   `date` field gets `MM/DD/YYYY`. Text fields are untouched. A value the
   field cannot hold is withdrawn with `provenance.format_warning` rather
   than pushed into a widget that would reject or misread it.
5. `PreparedFill` carries the suggestions (what the preview route returns),
   `values` (the same thing shaped for a renderer, signing fields excluded),
   the coverage split, `missing_required`, `collisions` and `sources_loaded`.

The **approval vocabulary** (`vocabulary()`) is the union of what the sources
declare plus the synonym keys. It used to be learned by running the resolver
over a fabricated matter; that probe is kept in
`backend/tests/fill_campaign/probe.py` and a test asserts the declaration and
the probe agree alias for alias.

## The quirk campaign

`python scripts/rehearse_smart_fill.py --seed-pdfs --out build/quirks` (from
`backend/`) runs six mock matters against an AcroForm PDF and a Word letter
whose fields are named in every convention a firm's own form uses, plus the
five seeded sample forms that ship bindings. Each case resolves, renders
through the production PDF or DOCX writer, reads the page back and reports one
row per field:

```
scenario | document | field | state | coverage | source | value | note
```

with `state` one of `filled`, `blank`, `choice_mismatch`, `signature`,
`dropped_by_renderer`, plus alias collisions and render errors. The same
campaign is pinned by `tests/test_fill_campaign.py` (mock documents),
`tests/test_fill_campaign_seed_pdfs.py` (seeded forms) and
`tests/test_smart_fill_route_matter.py` (persisted rows through the route).

### What it found, and what changed

| Finding | Before | Now |
|---|---|---|
| A person's first and last name, the organization name, entity type and client number were unreachable; "Dear {{first_name}}" could not fill | blank | `client.first_name` ... `client.client_number` bindings and aliases; `first_name`/`last_name` fill by synonym, for review |
| `matter_number`, `practice_area`, `opened_on` unreachable | blank | `matter.number`, `matter.practice_area`, `matter.opened_on` |
| Only plaintiff and defendant party rows produced aliases; a family-law caption stayed blank | blank | every party role has a card and a `party.<role>.name(s)` binding; `petitioner_name` fills from the row |
| A contact's `ND` never selected a court form's "North Dakota" option; a value a choice widget could not take was passed anyway | `choice_mismatch` | option matching by value, label or state code; unmatched values are withdrawn for review |
| An unbound field named `estate_decedent_name` was classed `name_matched` by coverage, passed the approval gate, and rendered blank because the estate loaded only for an `estate.` binding | coverage lied | a source loads for a matching field name too |
| A structured party silently beat `matter.counterparty` | invisible | reported as a collision |

Over the campaign, filled outcomes rose from 447 to 538 of 1,261 with no
render errors. Every bound field on the five seeded forms fills; the fee
agreement's `contingency_percentage` is the one legitimate blank for an
hourly matter.

### Still pinned as quirks, on purpose

- Two PDF widgets whose names fold to one variable (`client_name` and
  `Client Name`) are discovered as `client_name` and `client_name_2`; the
  second no longer matches by name. Bind it, or rename the widget.
- `ClientName` folds to `clientname` and matches nothing. Bind it.
- A second defendant is reachable only through `defendant.2.full_name`. Its
  alias `defendant_2_name` is producible but kept out of the approval
  vocabulary so the gate's answer did not change in this work.
- Money renders raw in a text field (`250.00`). A template author formats the
  template around it; there is no `money` field type to fit to.
- `matter.role` inference (client stands in for the represented side) still
  covers plaintiff and defendant only, at confidence 0.75.
- A `client` party row does not write `client_*`: the client contact owns
  those aliases and a row would shadow it.

## Adding a source

Subclass `FillSource`, declare `key` and `aliases`, set `always = False` if
the record costs a query, implement `collect(index, records)`, and append it
to `SOURCES` at the position its precedence deserves. Then extend the probe in
`tests/fill_campaign/probe.py` with a fully populated record so
`test_declared_vocabulary_equals_what_the_resolver_writes` still holds, and
add the catalogue path and card field so a binding can name it. A source that
writes an alias it did not declare, or declares one it never writes, fails
the vocabulary test.

## Phase 2: prepared the moment a matter has data (shipped)

`app/services/document_prefill.py` runs Smart Fill unattended. A
`document_prefill` durable job is queued, in the same transaction as the save
that triggered it, when a matter is created (`POST /api/matters`), converted
from a lead (which now also fires `matter_created` for firm workflow rules),
receives a portal questionnaire (`intake_submitted`), or has intake answers
accepted (`intake_writeback_accepted`). The job's idempotency key is the
matter id plus a digest of the engine's own candidate index, so the same facts
never run twice and changed facts queue a fresh run. A failure to queue is
logged and released inside a savepoint; it never blocks the save.

The job fills every active, published, automation-ready template (PDF:
approved) for the matter, highest-ranked first and at most 20, and records one
`document_prefill_ready` matter event. Its metadata carries counts and field
names only: fields, filled, percent, missing required, to-confirm, the
coverage split, the sources loaded, and any alias collisions. No value, no
rendered page, no matter document, no preview evidence. Generating a document
is still a person's act behind the preview-evidence gate.

`GET /api/matters/{id}/document-prefill` returns the newest record with
`stale` set when the matter's fill-relevant facts changed since. Case
Documents shows it as "N documents ready to review, X% filled from this
matter" and **Review and save** opens the existing review with that template
preselected, where the values are computed live.

Follow-ups still open: a rule action that requests a document (a Stack A
`document_propose` step bridging to `propose_document_from_template`), and the
Phase 3 guided route below.

## Phase 3 (3a and 3b shipped; 3c, 3d planned): Studio to signature in one path, with set fan-out

Planned in [`template-prepare-route-plan-2026-09-19.md`](template-prepare-route-plan-2026-09-19.md):
a `/templates/prepare` route (Select, Matter, Populate, Review, Save, Send)
reached from Studio's "Use on a matter", the library, the matter page's
readiness banner and the Probate tab; a Send step reusing the E-Signature
panel's logic with the client signer prefilled; set fan-out that fills once,
previews every member in the browser, saves all one document at a time with
per-document status, and offers Send per PDF member; and, later, a resumable
fill session and a durable save-all once that session exists.
