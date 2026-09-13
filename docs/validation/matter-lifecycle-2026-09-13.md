# Matter lifecycle validation — September 13, 2026

Validation used an explicitly designated production test matter, an existing test client,
and separate staff and client sessions. This document omits client answers, email addresses,
inbox bodies, access links, and production record identifiers. Observations below are
bounded to the tested paths; a passing release gate is not a claim that all functions pass.

## Release baseline

Production acceptance passed for `569a0cd01a847f20a64ef2fba3427c2df9465d97`
([run 34780458910](https://github.com/mattpainter701/lawhand/actions/runs/34780458910)).
PRs 476 and 481 repaired signing recovery/locking; PR482 preserved registered AI aliases
and made the nginx maintenance asset readable. Both original signing requests completed:
two executed forms and two evidence certificates were durably stored and client-visible.
Cloud reads verified unchanged artifact hashes, original signing times, and every nonempty
saved text answer. Staff showed 0 awaiting, 0 partial, 2 done and a 2/2 paperwork checklist.

## Fixes in this follow-up

| Finding and reproduction | Change | Regression evidence |
| --- | --- | --- |
| A full first-and-last-name conflict query returned no contact; the surname found it. The old test also supplied an email, concealing the failure. | Match the combined name as well as existing fields; retain active-contact and tenant filters. | Saved conflict-check API test searches `Alice Smith` without an email and verifies the linked matter and review workflow. |
| Matter settings PATCH returned429, but the UI only said “Failed to save changes.” | Show the normalized API message; leave the editor and draft open. | Details and people editors reject a save and retain a visible, actionable error. |
| The hourly limit advertised a 60-second retry even though the key resets on the UTC hour. | Compute Retry-After to the next hour and describe the rounded wait. Limits and enforcement are unchanged. | At18:10:30UTC, the second request against a one-request test limit returns429 with2970seconds and50minutes. |
| A failed client document request also displayed “No shared documents yet.” | Display the empty state only after a successful empty response. | Failed load shows the error without the empty state; retry succeeds and clears the error. |
| A next-day task appeared “Due today” in a negative UTC offset; date-only calendar entries displayed an invented evening time. | Parse task dates as local dates and omit clock labels for date-only events. | Date tests run in America/Chicago, including next-day, same-day, overdue, and timed controls. |
| A no-fee-agreement packet completed, but “Paperwork sent — follow up with client” stayed open alongside scheduling. | Cancel that superseded chase at the completion transition. Preserve fee-agreement engagement follow-ups. | Completion and replay tests retain one scheduling task, retire the chase, and keep the separate engagement case open. |

These changes do not rewrite historical signed files or automatically repair already
completed packets' old tasks. Staff should review an old follow-up before closing it.

## Remaining findings

| Priority | Observation | Follow-up and limits |
| --- | --- | --- |
| High | Outlook task push ignores the saved due time and creates an all-day event; the calendar showed both a task and its synced copy. | Test timezone-aware timed task propagation, stable provider identity, deduplication, and event navigation. The date-label fix here does not repair provider sync. |
| High, source-dependent | The supplied signature-field document was confirmed bad by the user. Generic signature detection also matched unrelated “Referred by” and firm-use “reviewed by” lines. | Keep source quality distinct from detector behavior. Validate a clean prepared form with explicit roles before attributing all placement problems to the application. Never modify historical executed copies. |
| Medium | Administrative assistant wording such as “do not do legal research” or “attorney assignment” triggered the authority guard. A neutral control returned correct matter facts but omitted two of three open tasks. | Improve intent classification and complete task retrieval while preserving safeguards for actual legal conclusions; test negated and mixed legal/administrative requests. |
| Medium | Reopening an assistant conversation reset the selected tier and public-case-law preference. | Verify preference persistence and precedence between conversation settings and platform policy. |
| Medium | The evidence certificate's filled-field count included blank serialized entries; its IP was an internal proxy address. | Define nonempty field counting and verify trusted proxy configuration before changing evidence attribution. |
| Medium | Shared-document counts and labels differed between overview, documents, and signing grants. | Align counts and explain signing-based access; no unauthorized-access conclusion was established. |
| Low | A void invoice retained a staff balance display; the time-entry status remained DRAFT after restoring nonbillable time. | Reconcile void/nonbillable display semantics. The client saw no invoice and zero balance. |
| Low | Court and judge were displayed but had no inputs in the tested general matter editors. A closed control still offered sending paperwork. | Confirm intended editing paths and suppress inappropriate closed-matter actions. |
| Follow-up | No new filing-failure escalation task was visible during the original storage outage. | Define escalation ownership and retry exhaustion behavior; successful recovery does not establish operational escalation coverage. |

## Other tested paths and limits

- Secure portal messages and notifications reached the actual staff/client inboxes in both
  directions. Signing and intake-completion notifications named the correct matter; the
  scheduling task was assigned to the attorney. The raw internal role label was removed.
- Case-number email capture matched a known inbox marker, rejected a negative control,
  and avoided duplication on repeat scans. Temporary settings were restored. This proves
  mailbox association, not court docket retrieval or court-number extraction from a form.
- Party-email matching also associated older messages from other matters sharing the same
  client email. Background capture was left off; relevance rules need separate review.
- Workflow template approval, preview, application, rollback, task transitions, waiting
  requirements, review and completion passed in tested paths. After an automatic stage
  change, a stale preview correctly returned409 without applying. Test templates/rules
  were archived; no production automation was left enabled by the test.
- An empty, no-client control passed Open → Closed → Active → Closed and remains closed.
  The original matter remains open at Intake / Schedule Initial Meeting.
- A nonbillable time entry and a draft/void invoice were exercised. No invoice was sent,
  no payment or trust transaction occurred, and no real meeting or court deadline was set.
- Browser download was blocked by the testing browser. Independently inspected durable
  cloud bytes establish storage/content recovery, not a successful browser transfer.
- Fresh live signing of a clean one-page validation form remains pending send approval
  and user signing. Automated fresh-sign and outage-recovery tests passed in prior fixes.
- Non-admin staff permissions and meaningful form-to-court-field mapping were not tested.

## Review guidance

Use labeled synthetic data and preserve attorney review decisions. Do not treat any
conflict result as automatic clearance. Revalidate the fixed paths after deployment and
keep the remaining findings open until their own acceptance checks pass.
