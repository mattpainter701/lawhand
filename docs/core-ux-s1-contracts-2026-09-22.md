# Core UX Sprint 1 — shared interaction and endpoint contracts (S1.06, S1.07)

Date: 22 September 2026. Draft for owner agreement; tasks S1.06 and S1.07 of the [ordered core UX sprint execution plan](https://github.com/mattpainter701/lawhand/blob/docs/core-ux-execution-plan/docs/core-ux-execution-plan-2026-09-22.md) (PR #584). These contracts are inputs to Sprints 3–6; they do not change behavior on their own.

## S1.06 — Shared interaction contract

### Vocabulary

| Concept | Reserved meaning | Must not be conflated with |
| --- | --- | --- |
| Assigned to you | Responsibility/membership on the matter | Personal focus; permissions |
| Matter status | Case lifecycle | Focus; review state |
| My focus | A personal, team-visible selection of matters | Assignment; presence; a timer |
| Review responsibility | Who must review an artifact/task | Focus selection |
| Permission | What a user may access or do | Any view/presentation choice |

- **Clients / Contacts / Intake pipeline / Call log & intake** keep distinct labels. "Intake pipeline" = structured leads; "Call log & intake" = the receptionist call desk. Terminology is validated with staff before it ships (S6.03).
- **Saving states:** `saving` → `saved` → `save failed` → `partial` are distinct and never collapsed. "Saved" only after server confirmation.
- **Calendar source:** local save is labelled local; a provider sync failure is surfaced separately. A local save never reads as a successful external sync.
- **Preparation vs approval vs delivery vs signature** remain distinct states (document owner's contract).
- **Preference scope:** navigation is account-synced; matter/column/calendar layout is device-local. Each surface states its scope.

### Behaviors

- **Context travels with the action.** Matter/client/assignee/return target are visible and preserved; changing the client/matter invalidates incompatible prefill.
- **Default Task vs Deadline.** Entering from a generic action creates a general Task unless the entry explicitly means Deadline.
- **Cancellation creates nothing.** Failure preserves user input and focus. Retry must not duplicate a committed action.
- **Back restores the prior view** (scope, filters, sort, page, position) without revealing stale unauthorized data.
- **Reset** restores defaults without altering business data or permissions.
- **Shortcuts** never fire while an editable field, an IME composition, or a dialog has focus (implemented in S1.10).

## S1.07 — Endpoint completeness contracts

Target contract per endpoint: explicit supported fields, authorization scope, deterministic ordering (stable tie-breaker), bounded page size, and total/count meaning. Reuse current APIs where adequate.

| Endpoint | Current | Required contract | Owning task |
| --- | --- | --- | --- |
| `GET /matters/my` | Hard `limit(100)`, no `total` — **retired** | Superseded by `GET /matters/my/page`: `page`, `page_size`, `total` = matching permitted records before pagination; assignment scope. No caller remained, so the capped route was removed (expand → migrate → contract). | S3.01, S3.02 |
| `GET /matters` | Paginated with `total`; search fields expanded on main | Keep pagination; state searchable fields (name, number, client name, organization); stable order; tenant/matter scope | S3.03 |
| `GET /tasks` | `limit`/`offset`, no title query | Add title query; page semantics; totals from the same predicate as the queue | S4.01, S4.02 |
| `GET /tasks/overdue`, `/upcoming` | Unbounded | Bounded with paging; totals; documented scope | S4.02 |
| `GET /clients` | `q`, `limit`, `offset`, `total` | Reuse; document searched identity fields; offset paging in UI | S6.01, S6.02 |
| `GET /contacts` | `q`, `limit`, `offset`, no sort | Add documented sort; state fields; offset paging in UI | S6.01 |

Cross-cutting: reject/ignore stale responses so an older query cannot overwrite a newer result; distinguish empty vs filtered-empty vs failed vs partial; no cross-tenant or restricted-record leakage in rows, counts or snippets.

## Open decisions

- Confirmation of the shared vocabulary with product/UX (S1.06).
- Owner agreement on the endpoint contracts before S3/S4 implementation (S1.07 → S3.01).
