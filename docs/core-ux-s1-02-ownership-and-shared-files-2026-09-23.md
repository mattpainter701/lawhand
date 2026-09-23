# S1.02 — owners and shared-file turns

Status: **draft** — role names are placeholders until the owner confirms them.
Evidence for the [S1.02 task](./core-ux-execution-plan-2026-09-22.md) in the ordered
core UX execution plan. It exists to unblock the Phase A gate and stop two people
editing the same shared file in parallel.

## 1. Role assignments

One person may fill several roles; the plan does not assume three engineers.

| Role | Person | Scope |
| --- | --- | --- |
| **FE-A** | _to confirm_ | Matter list/portfolio, matter workspace, CRM surfaces (S3, S6) |
| **FE-B** | _to confirm_ | Task composer/queue, calendar, shell/navigation/preferences (S4, S5) |
| **BE** | _to confirm_ | API/access/data contracts for matters, tasks, clients/contacts (S1.07, S3.01–03, S4.01–02, S6.01–02) |
| **product/UX** | _to confirm_ | S1.04 baseline scenarios, S1.05 arrangement review, acceptance calls |
| **QA** | _to confirm_ | Cross-tenant/isolation checks, dense/restricted fixtures, release validation |

Until these are named, S1.02 stays open and Phase A is not passed.

## 2. Shared-file turn map

Files more than one sprint touches. "Owner" is who holds the edit pen; everyone
else reviews or hands over. Turns are serialized, not parallel.

| Shared file | Owner | Sprints/tasks that touch it | Rule |
| --- | --- | --- | --- |
| `frontend/src/pages/MatterDetailPage.jsx` | FE-A | S2.05–S2.06, S3.08–S3.11, S3.10 | FE-A only; FE-B requests changes via FE-A |
| `frontend/src/pages/MatterPortfolioPage.jsx` | FE-A | S3.03–S3.07 | FE-A only |
| `frontend/src/components/matters/MatterListColumns.jsx` | FE-A | S3.05, S3.11 | FE-A only |
| `frontend/src/pages/TasksPage.jsx`, `AddTaskModal`, task queue composer | FE-B | S4.03–S4.12, S5 | FE-B only |
| `frontend/src/pages/CalendarPage.jsx` | FE-B | S1.08, S1.09, S5 | FE-B only; reuse the S1 fixes, do not rebuild |
| `frontend/src/components/AppShell.jsx` | FE-B | S1.10, S5, S3.13 (return-context handoff) | FE-B only |
| `frontend/src/pages/ProfilePage.jsx`, `ConflictChecksPage.jsx` | FE-B | S3.03 consumer migration | FE-B only; stale/empty follow-ups tracked in the plan |
| `frontend/src/api.js` | **BE** | Every slice with an API call | BE owns the exported signatures. FE-A/FE-B may add or rename a wrapper only in the same PR as the backend change it calls; no drive-by edits |
| `backend/app/routers/matters.py`, `backend/app/schemas/matter.py` | BE | S1.07, S3.01–S3.03 | BE only |
| `backend/app/routers/tasks.py`, task visibility/notification services | BE | S4.01–S4.02 | BE only |
| `backend/app/routers/clients.py`, `contacts.py` (+ schemas) | BE | S6.01–S6.02 | BE only |
| `backend/alembic/versions/*` | BE | Any migration (central head protocol) | One head, assigned centrally (repo `AGENTS.md` §1) |
| `backend/app/release_notes.json`, `CHANGELOG.md`, `RELEASE_NOTES.md` | BE | Any customer-facing change | Regenerate together (repo `AGENTS.md` §2) |
| `.github/workflows/ci.yml` | BE | Infra only | Explicit coordination; validate YAML and unique job keys after any rebase (repo `AGENTS.md` §4) |

## 3. Agreed editing rights

- **MatterDetailPage.jsx** — FE-A owns; FE-B never edits it directly (S3.13 hands FE-B the visible matter/assignee/return-context contract instead).
- **API exports (`api.js`)** — BE owns the contract and the export signature; frontend owners extend it only alongside the matching backend change.
- **Research access** — FE-A with BE, coordinated with the research/workspace owner (S2.04). Access is replaced with tenant/membership/capability checks, not focus flags; deliberate denials are preserved.
- **Reviewer fallback** — BE for the authorization/reviewer policy (S2), FE-B for the chat reviewer selection surface. No focus flag may gate access (S2.04).

## 4. Document-owner dependencies (recorded, not edited)

Per S1.11, these are consumed from the document owner's branch without editing it:

- Preparation entry, resume, status and error contract, including session correlation.
- Serialized autosave/completion and preserved interview state during review.
- Failed-draft completion after a successful save.
- S1.09 consumed the already-landed calendar reconnect fix; no OAuth rewrite here.

Open owner decisions remain listed in S1.11 and must be recorded before S3.10 implementation.

## 5. Sequencing note

Sprint 3's UI slices (S3.04–S3.09) rest on S3.01–S3.03, which are still Partial. This
record unblocks S1.02's ownership/turn gate; it does not by itself pass Phase A, which
also needs S1.04 (baseline scenarios), S1.05 (arrangement review) and S1.11 (document
handoff). The next implementation slice after this should be S3.02 to acceptance, then
S3.03 load-more.
