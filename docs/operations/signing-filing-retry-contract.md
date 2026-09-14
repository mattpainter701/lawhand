# Signing: filing retries and failure ownership

What happens between "the client signed" and "the executed copy is in the
matter", and who becomes responsible when that gap does not close.

Written for issue #492, which observed that during a storage outage no
escalation was visible to anyone while filing was failing. Recovery happened on
its own that time. This document specifies what happens when it does not.

## The two halves of a signature

Signing and filing are deliberately separated. A storage outage must never fail
the client's signing action, so:

1. **The signature is recorded immediately** and is durable from that moment
   (`record_portal_signature`). It does not depend on storage being reachable.
2. **Filing happens afterwards** — render the executed copy, build the evidence
   certificate, store both, write the timeline event, mark the request completed
   (`complete_request_if_done` → `_finalize`).

When step 2 fails, the signature stays recorded and `_record_completion_failure`
notes the failure on the request. The request sits in `partially_signed` with
`completion_error` set, and the scheduler retries.

## Retry contract

| | Value | Where |
|---|---|---|
| Retry interval | 5 minutes | `COMPLETION_RETRY_INTERVAL` |
| Attempt cap | **None — retries continue indefinitely** | `retry_pending_completions` |
| Escalation threshold | 12 consecutive failures **and** ≥ 1 hour since the first | `COMPLETION_ESCALATION_ATTEMPTS`, `COMPLETION_ESCALATION_WINDOW` |
| Escalations per request | Exactly one | `completion_escalated_at` |

**Retrying never stops.** Giving up on a signed document would guarantee the
loss that the retry exists to prevent. Exhaustion does not end the retry loop —
it changes who is responsible for the outcome, from the scheduler to a person.

**Both thresholds must be crossed.** The attempt count rules out a single blip;
the elapsed window rules out a fast flap that a few more minutes of retrying
would have cleared. At one attempt per five minutes, twelve consecutive failures
is already an hour, so the window is what binds if the retry interval is ever
lengthened — deliberately, so that slowing retries down cannot silently delay
the escalation.

## What an escalation is

On the first pass where both thresholds are crossed,
`escalate_completion_failure`:

- Raises **one assigned matter follow-up task**, "Signed copy could not be
  filed: `<document>`", at `high` priority, keyed to
  `(request_id, "signature_filing_failed")` so no retry can mint a second.
- **Owner:** the user who created the signature request, falling back to the
  matter's assignable owner through `ensure_followup_task`.
- **Destination:** the matter the signature belongs to — the same place the firm
  already looks for work on that file.
- Notifies the assignee through `notify_task_created`. A failed notification is
  logged and does **not** undo the escalation: the task is the escalation, the
  email is a courtesy.
- Writes a matter timeline event naming the failure count, the window, and the
  last error.

## Recovery

When a retry finally succeeds, `_finalize` clears `completion_failure_count` and
`completion_first_failed_at`, and `after_completion` closes the escalation task
with "Signed copy filed". Clearing the run matters: without it, an unrelated
outage months later would inherit the old count and escalate on its first
failure.

`completion_escalated_at` is deliberately **not** cleared. It is the record that
this request was once escalated.

## Operator checks

- **Is anything stuck right now?** Signature requests in `partially_signed` with
  `completion_error` set and `completion_failure_count` above zero.
- **Has anyone been told?** `completion_escalated_at IS NOT NULL` means a task
  exists on the matter. If failures are climbing and this is still NULL, either
  the thresholds have not been crossed yet or the scheduler is not running —
  check the scheduler before assuming the former.
- **Why is it failing?** `completion_error` holds the last error verbatim.
