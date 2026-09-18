---
slug: email-intake
title: Email tasks
description: Forward client email from your phone and route it into reviewed matter work.
order: 170
read_time: 4 min
icon: mail
---

# Email tasks

Your firm can have one forwarding address saved as **LawHand Tasks** on your phone or in your mail app. You do not need a separate contact for each matter.

## Save the contact once

On [Tasks](/tasks), find **Email tasks** and select **Save LawHand Tasks contact**. Open the downloaded contact file and save it in your phone or mail app. Alternatively, copy the address and create the contact yourself. If the panel is not shown, ask your administrator to enable firm email intake.

## Forward a request

Forward the client email to LawHand Tasks. Edit the subject to start with one of these explicit tags:

```text
[TASK] Jane, review this tomorrow
[TASK] Review the attached agreement
[TASK] Jane Smith, call the client in two weeks
[REVIEW] Jane, settlement agreement tomorrow
[DEADLINE due=2026-09-30] Jane, file response
```

Remove any `Fwd:` before the tag. Names and tags are case-insensitive. A colleague's first name, full name, or registered email can go before the comma. Without a name, LawHand suggests you as the owner. If two colleagues share a name, choose the right person during review.

Dates are optional for tasks and reviews. A deadline requires a confirmed date during review. “Tomorrow” and “in N days/weeks” at the end of the subject use the firm's time zone and when LawHand receives your forward. Exact dates also work. Unrecognized phrases such as “next Friday” remain in the title without setting a date; choose the date during review. This flow does not calculate court deadlines or read instructions from attachments.

Forward from your registered LawHand staff email address. The client or court does not need a LawHand account. If delivery is rejected, ask your administrator to check your registered address and sending provider's DKIM configuration.

## Confirm the matter and create work

In **Tasks → Email tasks → Needs review**, you or a colleague:

1. Reads the email preview.
2. Confirms the suggested matter, or chooses one. Original-sender hints and case numbers help find matches; a client with multiple matters may need your help.
3. Confirms the owner, title, and optional date.
4. Selects **File + create task**, **File + create review**, or **File + create deadline**.

The task appears in the matter's Tasks list and the assigned colleague's task views. Filing retains the forwarded email and attachments in matter correspondence and gives the task a source reference. After filing succeeds, LawHand sends the normal assignment notice and projects a dated task to the assignee's connected Google or Outlook calendar. Notification or calendar-provider failure does not roll back the filed email or task.

**Every request waits for review. Forwarding alone does not create a final task.** Untagged forwards also wait in the queue and can be turned into an ordinary task by entering the details. Tags select task type and priority; they never bypass human confirmation.

Select **Reject** and confirm only when the request should be discarded; this permanently removes the quarantined copy. Already-filed requests cannot be accepted again. Identical redelivery to the same address is ignored, but an edited or separately resent forward may appear again.

## Find missing requests

Refresh **Needs review**. It shows the oldest 50 requests; more appear as those are processed. Replaced and disabled addresses stop receiving new requests, while existing queued requests remain available. Save the new contact after an address replacement.

If original-sender hints cannot be recognized, select the matter manually. Check any legal deadline separately under your firm's procedure.
