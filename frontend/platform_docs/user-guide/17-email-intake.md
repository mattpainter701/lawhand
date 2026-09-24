---
slug: email-intake
title: Email tasks
description: Forward client email from your phone or mail app and turn it into reviewed matter work.
order: 170
read_time: 6 min
icon: mail
---

# Email tasks

Your firm can give everyone one forwarding address, saved on your phone or in your mail app as **LawHand Tasks**. Forward a client email there with a short tag in the subject, and it waits in a review queue until you or a colleague confirms the matter, the owner, and the date. You do not need a separate address for each matter.

> [!NOTE]
> Email tasks appear on [Tasks](/tasks) only when your administrator has turned on firm email intake. If you do not see the **Email tasks** panel at the top of Tasks, ask your administrator.

## Save the contact once

1. Open [Tasks](/tasks). The **Email tasks** panel is at the top of the page.
2. Select **Save LawHand Tasks contact**. A contact file named `LawHand Tasks.vcf` downloads.
3. Open the file on your phone or in your mail app and save the contact.

Prefer to type it? Select **Copy address** and create a contact named "LawHand Tasks" yourself. Once you have saved it, select **Dismiss tip** to hide the instructions; **Show forwarding tip** brings them back.

## Forward a request

Forward the client email to LawHand Tasks and edit the subject so it starts with one of these tags:

```text
[TASK] Jane, review this tomorrow
[TASK] Review the attached agreement
[TASK] Jane Smith, call the client in two weeks
[REVIEW] Jane, settlement agreement tomorrow
[DEADLINE due=2026-09-30] Jane, file response
```

- **Remove `Fwd:`** before the tag; the tag must come first.
- **Tags and names are not case-sensitive.** Put a colleague's first name, full name, or registered email before the comma to suggest them as the owner. Without a name, LawHand suggests you.
- **Dates are optional** for tasks and reviews. "Tomorrow" and "in N days" or "in N weeks" at the end of the subject use your firm's time zone and the time LawHand received your forward. Exact dates also work.
- **Deadlines need a date.** A deadline cannot be filed until someone confirms its date during review.
- Phrases LawHand does not recognize, such as "next Friday", stay in the title without setting a date; choose the date during review.

This flow does not calculate court deadlines and never reads instructions from attachments.

> [!IMPORTANT]
> Forward from your registered LawHand email address. The client or court does not need a LawHand account, but your own sending account must sign its mail (DKIM). If LawHand rejects your forward, ask your administrator to check your registered address and your email provider's DKIM setup.

## Review and file the request

Every forwarded request waits for review. Forwarding alone never creates a task.

![The Email tasks panel with the forwarding address and the Needs review queue showing one ready task and one deadline that still needs a matter and a date](/guide-assets/email-tasks-review.webp "Needs review: one request ready to file, one that needs help")

1. On [Tasks](/tasks), select **Needs review** in the **Email tasks** panel. The number shows how many requests are waiting.
2. For each request, read the subject and **Forwarded by** line, and open **Read email preview** to see the message.
3. Check the detected type (**Task**, **Review**, or **Deadline**) and the title.
4. Choose the **Matter**. LawHand suggests one when the original sender or a case number points to a single matter; when it cannot, it says **We need your help choosing the matter**.
5. Confirm **Assign to**. If two colleagues share a name, LawHand asks you to confirm who the name refers to.
6. Set the **Due date**, which is required for a deadline.
7. Select **File + create task**, **File + create review**, or **File + create deadline**.

After filing, a confirmation offers **Open task**. The task appears in the matter's tasks and in the assignee's task views. Filing keeps the forwarded email and its attachments in the matter's correspondence and links the task to it. LawHand then sends the normal assignment notice and adds a dated task to the assignee's connected Google or Outlook calendar. A notification or calendar failure does not undo the filed email or task.

Untagged forwards also wait in the queue; enter the details to turn one into an ordinary task.

### Reject a request

Select **Reject**, then **Confirm rejection**, only when the request should be discarded. This permanently removes the queued email and cannot be undone. Select **Keep email** if you change your mind.

An identical copy sent again to the same address is ignored, but an edited or separately resent forward can appear again as a new request.

## Find missing requests

- Select **Needs review** again to refresh the queue.
- The queue shows the oldest 50 requests; more appear as those are processed.
- If your firm replaced its address, save the new contact. Replaced and disabled addresses stop receiving new requests, although requests already in the queue remain available.
- If LawHand cannot recognize the original sender, choose the matter yourself.

Check any legal deadline separately under your firm's procedure.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| The **Email tasks** panel is not on Tasks | Firm email intake is not enabled | Ask your administrator to enable it. |
| Your forward never reaches the queue | It was sent from an unregistered address, your provider did not sign it (DKIM), or it went to a replaced address | Forward from your registered address to the current LawHand Tasks contact, and ask your administrator to check DKIM. |
| The filing button stays disabled | A matter, owner, title, or deadline date is missing | Fill in every field the card asks for. |
| The date is not what you expected | Relative dates count from when LawHand received the email, in the firm's time zone | Correct the date on the card before filing. |

## Related chapters

- [Tasks, calendar & communications](/guide/tasks-calendar-communications)
- [Matters & documents](/guide/matters-and-documents#correspondence-and-matter-email)
