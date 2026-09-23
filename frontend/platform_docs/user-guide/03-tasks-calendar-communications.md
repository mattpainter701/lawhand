---
slug: tasks-calendar-communications
title: Tasks, calendar & communications
description: Own the next action, keep deadlines visible, and keep a clean record of what was said.
order: 30
read_time: 11 min
icon: checklist
---

# Tasks, calendar & communications

Tasks answer **who owns the next action**. Calendar answers **when something happens**. Communications preserve **what was said**. Use all three deliberately; none of them alone is a complete case history.

For a quick way to turn email into tasks from your phone, see [Email tasks](/guide/email-intake).

![How task requests become authoritative work and calendar projections](/guide-assets/customer-data-task-lifecycle.svg)

## Tasks

Open [Tasks](/tasks). The page, **Tasks & Deadlines**, is your personal work queue: everything assigned to you, grouped by when it is due.

![The Tasks list with the New Task button, the Board and List toggle, the filters, and a task row showing its Close action](/guide-assets/tasks-list.webp "Tasks in list view")

1. **New Task** creates a task.
2. **Board / List** switches between the grouped list and the work board.
3. Filters narrow the list by status, priority, type, and matter.
4. Point at a task to show its actions, such as **Reassign** and **Close**.

The list groups work under **Overdue**, **Due Today**, **Upcoming**, and **No Due Date**, with finished work folded under **Closed**. Each row shows the due date, the priority (**urgent**, **high**, **medium**, or **low**), and any status other than to-do, such as **in progress**, **waiting**, or **review**. For a task you assigned to someone else, **Seen** or **Unread** tells you whether they have opened it; **Contacted** means someone logged a call or email back to the customer.

A useful task has a clear action, one accountable owner, a realistic due date, and a link to the relevant matter.

### Create a task

1. Select **New Task**.
2. Enter a **Title** that says what needs to happen, for example "Call Lena Ortiz about the hearing".
3. Choose the **Type** (general, deadline, hearing, filing, deposition, call, follow up, intake, or review) and the **Priority**.
4. Set the **Due Date** if there is one.
5. Optionally choose a **Linked Contact**.
6. To give the task to a colleague, search for them under **Assign To**. An email alert is attempted when outbound email is configured, and you can add a **Message to Assignee**.
7. Add **Notes** if they help, then select **Create Task**.

> [!TIP]
> To create a task that belongs to a matter, select **Add Task** in the matter's Quick Actions, or choose the matter in the **All matters** filter before you select **New Task**. Tasks linked to a matter appear on its Overview under **Next work**.

### Complete, reassign, or close a task

- **Complete.** Tick the checkbox at the start of the row. Tick it again to reopen the task.
- **Edit.** Change the title, dates, or details.
- **Reassign.** Choose the **New Assignee**, explain why under **Reason / Message**, and select **Reassign**. The reason is included in the assignment email and the history.
- **Close.** Choose the **Outcome** (**Completed — work is done** or **Cancelled — no longer needed**), enter the required **Reason**, and select **Close Task**.
- **Remind.** The bell sends the assignee a reminder email; the row shows **Sent!** when it goes.
- **Log contact.** On a task linked to a contact, records that the customer was called or emailed back.
- **Delete.** The bin asks **Delete?** first. Prefer **Close** with a reason: a deleted task leaves no explanation behind.

Tasks created by Call Intake also offer **Qualify lead** and **Open matter**. See [Intake & call reception](/guide/intake-and-call-reception).

### Use the work board

Select **Board** to see tasks as cards in **To Do**, **In Progress**, **Waiting**, **Review**, and **Done** columns. **My Work** shows your tasks; **Firm Work** shows everyone's, with a **Filter by assignee** search. The counters at the top show what is **Overdue**, **Due today**, **Unassigned**, and **Waiting follow-up**, and the **Any due date** filter narrows the board to overdue work or the next 7 or 30 days.

Drag a card to another column to move it. LawHand asks you to confirm the move, and some moves need a note:

- moving to **Waiting** asks what the task is waiting on;
- cancelling asks for a **Cancellation reason**; and
- completing accepts an optional **Completion note**.

Tasks in **Review** can carry work that needs approval before anything is sent, such as an assistant-drafted client email, text message, or document. Open the card to read the exact draft and approve it; nothing is sent or filed until a person approves it.

**LawHand Tasks is the source of truth for work state.** Outlook and Google calendar entries are projections that help you work in your usual calendar. Change the owner, due date, or status in LawHand: an edit or deletion made only in Outlook or Google does not update the task.

## Calendar

Open [Calendar](/calendar). The **Deadline Calendar** shows task due dates, matter key dates, renewals, estate deadlines, your synced calendar, and scheduled events together.

![The Deadline Calendar month view with the New Event and Sync Calendar buttons and the Day, Week, Month, and List view switch](/guide-assets/calendar-month.webp "The Deadline Calendar in month view")

1. **New Event** schedules a meeting or event, with an optional Teams or Zoom link.
2. **Sync Calendar** pushes matter deadlines to your connected calendar. If you have not connected one yet, this button reads **Connect Calendar**.
3. The view switch: **Day**, **Week**, **Month**, and **List**. Use **Today** and the arrows to move around.

Each item is labeled by type: **Task**, **Key Date**, **Renewal**, **Estate**, **Synced** (from your own calendar), **Event**, or **Work Block** (time you blocked out to work on a task). Select a day number in the month view to open that day, and **+N more** when a day is full.

### Connect your own calendar

1. Select **Connect Calendar** and sign in to your Microsoft or Google account.
2. Approve the permissions the provider shows you.
3. You return to the calendar with a message such as "Microsoft Calendar connected successfully." If the connection was cancelled or failed, the message says so and offers **Reconnect**.

This connection is yours alone; your administrator cannot connect it for you. It also lets LawHand capture email into your matters when you **Scan now** on a matter's Correspondence.

### Create an event

1. Select **New Event**.
2. Enter the **Event title**, an optional description, the date, and the start and end times.
3. Choose where the event lives: **App calendar only**, **Microsoft Calendar**, or **Google Calendar**.
4. Choose an online meeting, if any: **Microsoft Teams** or **Zoom**. (If Zoom is not connected, **Connect Zoom** appears.)
5. Link the event to a matter, or leave **No matter link**.
6. Add attendee emails, separated by commas, and select **Create event**.

### Reading a new event's save result

The message after **Create event** separates saving in LawHand from synchronization to a connected calendar. A Zoom meeting can be created without a calendar copy. If Zoom fails after the calendar updates, the message keeps that calendar success. If calendar synchronization is unconfirmed or fails, the local event remains saved; check its result before creating another copy.

The List heading shows the complete displayed date range, which can span two months or cross into a new year.

### Dragging a task on the calendar

Drag an open task deadline to another day in the month view, or to an hour in the day or week view. Because the same gesture can mean two things, LawHand asks **What should this drop do?**:

- **Move the due date.** The deadline moves to where you dropped it. Dropping on an hour also sets the due time; you can adjust either before confirming with **Move due date**. The due-date reminder is re-armed for the new date, and the Outlook or Google copy follows.
- **Block time to work on it.** A **Work Block** event is added for that slot and linked to the task. The due date, its reminders, and its calendar copy stay where they are. Choose a connected calendar if you want the block in Outlook or Google too, then select **Block the time**.

Only open task deadlines and events created in LawHand can be dragged. Completed tasks, matter key dates, renewals, and events synced in from Outlook or Google stay where their source put them. You can also change a due date directly in [Tasks](/tasks); the drag is a shortcut.

> [!WARNING]
> Moving a chip on the calendar does not move the underlying obligation. Verify any court or statutory deadline against the controlling rule and source, following your firm's procedure, before relying on a new date.

## Communications

Open [Communications](/communications) for the firm's logged communication history: calls, meetings, emails, texts, letters, portal messages, and notes. Filter by **All Channels** and **All Directions** (**Inbound** or **Outbound**), or by matter and contact.

Email that belongs to one file lives on that matter's **Correspondence** section rather than here: open the matter from [My Matters](/matters) to capture mail from a connected mailbox, forward a message to the matter, and review what is waiting to be filed.

### Log a communication

The easiest place to log a call or meeting is the matter itself, because the entry is linked to the matter automatically:

1. Open the matter and go to its **Activity** section.
2. Select **Log Comm**.
3. Choose the channel and direction, enter a subject and the details, and save.

The **Activity** section shows the timeline, notes, and communications together; switch between **All**, **Timeline**, and **Comms**. **Add Note** records an internal note on the same timeline.

To log from the Communications page instead, select **Log Communication**, fill in the **Channel**, **Direction**, **Subject**, **Body**, and **Summary**, and set **Occurred At** to when it happened.

### Request work from matter email

To request work from reviewed matter email, start the subject with `[TASK]`, `[REVIEW]`, or `[DEADLINE]`. For example, `[TASK] Meet with Nigel in two weeks` previews a task and due date on the review card. Confirm the title and date before filing. Filing the message creates the task and, when a due date is present, mirrors it to the reviewer's connected Outlook or Google calendar. Untagged text, replies, forwards, and AI-only date detection do not create work automatically, and a deadline cannot be filed without a reviewer-confirmed date.

### Before sending any draft

1. Confirm the recipients and attachments.
2. Check that privileged or confidential content is appropriate for each recipient.
3. Review any AI-assisted text as a draft.
4. Use the product's approval step when one is presented.

**Email Client** on a matter sends from your connected Microsoft or Google mailbox (or a firm mailbox when you have none) and records the message on the matter's Correspondence. If delivery is unconfirmed, check your Sent Items before sending again.

## Intake and calls

The [Intake workspace](/intake) captures new requests, and firms using reception workflows may also have [Call Intake](/intake/dashboard) for recent callers, assignments, and follow-up. Capture facts neutrally, distinguish a prospective client from an active client, and do not promise representation or an outcome. Escalate conflicts, urgent deadlines, threats, emergencies, or uncertain engagement status according to firm policy. See [Intake & call reception](/guide/intake-and-call-reception) for the full workflow.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| A task you edited in Outlook or Google did not change | Calendar copies are projections of LawHand tasks | Make the change in [Tasks](/tasks); the calendar copy follows. |
| **Board** is missing on the Tasks page | Your firm has the work board turned off | Use the list view; ask your administrator if you need the board. |
| A card will not move to **Waiting** | A waiting reason is required | Enter what the task is waiting on and confirm the move. |
| A calendar item cannot be dragged | It is a key date, renewal, completed task, or synced event | Change it at its source, such as the matter or your own calendar. |
| The calendar shows "needs to be reconnected" | Your Microsoft or Google sign-in expired or was revoked | Select **Reconnect** in the message and sign in again. |

## Related chapters

- [Email tasks](/guide/email-intake)
- [Matters & documents](/guide/matters-and-documents)
- [Intake & call reception](/guide/intake-and-call-reception)
