# Core UX Sprint 1 — audit reconciliation (S1.01)

Date: 22 September 2026. Task: S1.01 of the [ordered core UX sprint execution plan](https://github.com/mattpainter701/lawhand/blob/docs/core-ux-execution-plan/docs/core-ux-execution-plan-2026-09-22.md) (PR #584). Purpose: reconcile the [feature-parity audit](https://github.com/mattpainter701/lawhand/blob/docs/core-ux-future-state-plan/docs/research/core-ux-feature-parity-2026-09-22.md) against current `main`, so already-landed work leaves the implementation tickets.

## Snapshot

| Item | Value |
| --- | --- |
| Audit snapshot | `c4d80b46` (audit base) |
| Main reviewed | `ead233f0` (current at kickoff; includes #579, #580, #582, #583) |
| Method | Read-only diff `c4d80b46..ead233f0` plus targeted source checks. No runtime or provider test. |

## Scope of change since the audit

The `c4d80b46..ead233f0` range is dominated by document automation (templates, fill sessions, sample library), cloud search, and OAuth reconnect routing. Only these changes touch a core-UX source path:

- `backend/app/routers/matters.py` — expanded all-matters search.
- `frontend/src/pages/CalendarPage.jsx` — personal-cloud OAuth return path.
- `backend/app/services/calendar_sync.py` — reconnect guidance copy.
- `backend/app/services/cloud_search.py`, `backend/app/routers/integrations.py` — search/cloud reconnect (owner scope, outside this epic).

## Reconciliation of affected audit items

| Gap | Audit claim | Status on `ead233f0` | Evidence | Disposition |
| --- | --- | --- | --- | --- |
| G-04 | `/matters` search matches `matter_name` only | **Fixed** | `matters.py` search now matches `matter_name`, `matter_number`, client trimmed first+last name and `organization_name`, tenant-scoped | Remove from implementation scope. UX-08/10 reuse it and state the fields searched; do not rebuild |
| G-03 | `/matters/my` hard-caps at 100 with no `total` | **Reproducible** | `matters.py:1048` still `.limit(100)`; `/my` endpoint at `:1021` unchanged | Keep in UX-08 (S3.01–S3.02) |
| G-14 | Calendar list heading under-reports its range | **Reproducible** | `CalendarPage.jsx` list branch of `rangeLabel` returns `monthLabel(pivot)` while `viewRange('list')` spans pivot month → end of next month | Fixed in this branch (S1.08) with a regression test |
| G-16 | Local save shown as success when provider sync fails | **Reproducible** | `CalendarPage.jsx:751` still sets `Event created.` unconditionally; no `sync_status`/`sync_error` read | Create-event feedback fixed in the combined S1.09 slice; Zoom/calendar outcomes validated separately. Other mutation paths remain follow-up scope. |
| G-25 | Global chat shortcut fires while typing in a form | **Reproducible** | `AppShell.jsx:261` handler had no focus/composition guard | Fixed in this branch (S1.10) with tests |
| Doc follow-up | Personal cloud recovery routes users back to the wrong place | **Landed (#583)** | `calendar_sync.py` now says "Open Calendar and choose Connect Calendar"; `CalendarPage.oauth.test.jsx` added | Consume; do not duplicate the routing fix (S1.09 reconnect piece) |

Other rows retain the historical source-audit baseline. Unchanged paths are not runtime reproduction evidence; their live status remains unknown until a relevant current-revision check is recorded.

## Human-gated tasks in Sprint 1 (not engineering)

These are recorded as blocked pending people, not skipped:

- **S1.02** — assign FE-A/FE-B/BE/product/QA owners and lock shared-file turns.
- **S1.04** — run the seven baseline scenarios with real participants.
- **S1.05** — review the everyday arrangement prototype with the product owner.
- **S1.11** — obtain the document owner's preparation entry/resume/status contract and recheck release/acceptance status.

## Notes

- No migration or schema change is introduced by this reconciliation.
- The audit's source anchors still point at `c4d80b46` for untouched rows; treat them as the audit baseline, not as current line numbers.

## Execution update and validation

The user authorized the Phase A correctness merge and subsequent B1 backend slice. S1.03 synthetic fixtures will be built with B1 paging/query tests before accepting that slice; they are not marked complete here. Focus access/reviewer policy, participant sessions and the larger arrangement review remain separate gates.

The document owner reports production ead233f0 / 2026.09.22.03 accepted and its main hold released. Session owner/tenant/matter/template correlation, serialized autosave/completion and distinct preview/save/approval/delivery states remain the shared interface. This task did not independently repeat production acceptance.

The repair adds confirmation-dialog keyboard tests and Zoom-only, mixed Zoom/calendar and missing-calendar-confirmation cases. Six added cases failed against the inherited PR code and pass after correction. The focused AppShell/calendar run passes 45 tests in nine files; changed-file lint and production frontend build also pass. Provider responses are mocked in these UI tests; no live external writes were performed.
