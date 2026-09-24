---
slug: intake-and-call-reception
title: Intake & call reception
description: Capture new inquiries, move leads through qualification and conflict checks, open the matter, send the client paperwork, and route incoming calls.
order: 80
read_time: 12 min
icon: checklist
---

# Intake & call reception

LawHand has two intake screens:

- [Client Intake](/intake) tracks each prospective client, or lead, from first contact to an engaged matter.
- [Call Intake](/intake/dashboard) is the reception desk: it matches callers to existing records, captures calls, routes them to the right attorney, and keeps the partner log.

Whichever you use, capture facts neutrally, keep a prospective client separate from an existing client, and never promise representation or an outcome.

## Track a lead

Open [Client Intake](/intake). The counters show how many leads are at each stage; select one to show only that stage, and select it again to show every active lead.

![The Client Intake page with the New Lead button, stage counters, and five leads each at a different stage, with Advance and Convert to Matter buttons](/guide-assets/intake-pipeline.webp "Leads moving through the intake stages")

1. **New Lead** records a new inquiry.
2. **Advance** moves a lead to the next stage.
3. **Convert to Matter** opens the matter once a lead is engaged.

The stages are:

1. **New**: captured, not yet contacted or assessed.
2. **Contacted**: the firm has spoken with the person.
3. **Qualified**: the fit and the information needed have been reviewed.
4. **Conflict Checked**: the firm's conflict process is complete.
5. **Engaged**: the firm has accepted the representation.

A stage records that a step is done; it is not a shortcut around the step. Leads that became matters or were declined move to **Closed**, with the reason a lead was declined.

### Record a new inquiry

1. Search [Contacts](/contacts) first, so a returning client is not entered twice.
2. On [Client Intake](/intake), select **New Lead**.
3. Enter the **First Name**, **Last Name**, **Email**, and **Phone**.
4. Enter the **Practice Area**, such as "litigation", and choose the **Source**: referral, website, cold call, existing client, bar referral, or other.
5. In **Description**, record what the person needs in their own words. Separate what they know from what they allege, and note the jurisdiction, the other parties, and any urgency.
6. Select **Create Lead**.

### Qualify and check conflicts

Work each lead through the stages, selecting **Advance** only when the step is actually complete:

- Contact the person and gather what is missing before **Contacted** and **Qualified**.
- Run a [conflict search](/guide/contacts-and-client-relationships#run-a-conflict-search) on the person, the other parties, and related organizations, and have an attorney record the decision, before **Conflict Checked**.
- Move to **Engaged** only after the firm has accepted the representation under its engagement process.

Do not give legal advice or mark a lead conflict-checked unless the responsible person completed the review.

### Open the matter

1. On an engaged lead, select **Convert to Matter**.
2. Check the **Matter Name**, which starts as the client's name followed by "Matter".
3. Choose or type the **Matter Type**, **Our Role**, the **Jurisdiction**, and the **Counterparty**. Each list offers values your firm already uses; type a new one to add it.
4. Select **Create Matter**.

The lead moves to **Closed**, and the new matter keeps the intake history.

## Send the client paperwork

A new matter's Overview shows a **Start this case** card for the engagement paperwork: an optional fee agreement, a client questionnaire, a client intake form, and any records you want the client to send.

1. On the matter's Overview, select **Send client paperwork**.
2. Under **Documents**, choose what to send:
   - **Fee agreement**: an attorney-reviewed agreement from the matter's documents, or an uploaded PDF. Signing it opens the client portal and starts the follow-up clock. Leave it out when the matter already records its engagement.
   - **Additional forms**: the **Client questionnaire** and **Client intake form**. Each form gets its own signature request and status.
   - **Requested records**: one record per line, such as "Copies of any existing court orders".
3. Select **Next**. Under **Deadlines**, set when each item is due, enter the **Client email**, and choose the **Responsible staff** (or **Assign to me**).
4. Select **Next** again.
5. Under **Send**, read **Message the client will receive**. The **Email** tab shows the branded email with the firm's details and the portal button; the **Text** tab shows the shorter text message. The link in the preview is a sample; the real one is created when you send.
6. Select **Send paperwork**.

Someone must follow up with the client within 24 hours: after the fee agreement is signed, or, with no fee agreement, after the packet is sent. If the client already signed an engagement letter outside LawHand, use **Already engaged — record it** instead, and **Add signed copy** to attach it.

The standard questionnaire comes from the matter type: family, criminal, personal injury, estate, employment, business, real estate, immigration, bankruptcy, litigation, mediation, or general. On the matter's intake panel, **Use the standard questions for this matter type** loads them so you can edit them.

> [!NOTE]
> An administrator can add a standard fee agreement and client intake form to the firm library with **Add the standard client paperwork** in [Template Studio](/templates). Both arrive as drafts. Fee, trust-account, and contingency terms differ by jurisdiction, so an attorney must review and approve them, and fill in the jurisdiction-specific placeholders, before either is sent.

## Answer and capture a call

Open [Call Intake](/intake/dashboard). When your firm has connected Zoom Phone, incoming calls appear in the live call feed with the caller's number and any prior attorney. Otherwise, capture calls by hand.

### Find the caller

1. Under **History Matches**, search by caller name, matter, or case number (the most reliable), and add any phone context.
2. Select **Search**. Results are labeled **Current contact**, **Active lead**, **Matter history**, **Call log**, or **Legacy call**.
3. Select a result only when you are sure it is the same person. "Recent caller selected. Verify identity before relying on phone-only history."

### Capture the call

1. Under **Call Capture**, confirm the **Caller** and the callback number.
2. Choose the **Practice Area**.
3. In **Purpose**, write a concise, neutral summary, such as "Needs divorce attorney; no prior history". Keep anything only staff should see in **Internal Notes**.
4. Choose the outcome: **Log only** for an existing client or a call that needs no lead, or **Create lead** for a new inquiry.
5. Under **Task / Routing**, choose:
   - **Assign partner / prior attorney** to route the lead through the firm's rotation, or to the attorney who handled the caller before;
   - **General task to staff** to assign follow-up to a colleague, then choose **Assign To** and the **Task** (**Call back caller**, **Schedule consultation**, **Conflict check**, **Route to service provider**, or **Custom task**); or
   - **No task, log only**.
6. Select the button, which names what will happen: **Create Lead + Log Call**, **Create Lead + Staff Task**, **Log Call + Staff Task**, or **Log Call Only**.

Tell the caller only what your role and firm policy permit. Tasks created from a call offer **Qualify lead** and **Open matter** on the [Tasks](/tasks) page.

### Route calls fairly

**Partner Log** lists each routed lead, who it went to, and the outcome, and can be exported with **Export CSV**. Administrators set the rotation under **Rotation**: choose a practice area, choose the attorneys who share it, and save. Rotation never overrides a conflict, an existing attorney relationship, subject-matter fit, availability, or emergency procedures.

### Export call records

Under **Call records**, **Export CSV** downloads the call log. Export only for an approved business purpose and store the file in an authorized location: call notes can contain personal or privileged information.

## Route incoming text messages

Text messages that LawHand cannot match to a client appear on [Client Intake](/intake) under **Inbound SMS routing review**. They are not on any client or matter timeline until someone routes them.

1. Choose the contact and the matter the message belongs to. Suggested matches are listed.
2. Select **Resolve route**, or **Reject** a message that does not belong in the firm's records.

**SMS delivery reconciliation** lists outgoing messages whose delivery LawHand could not confirm. Check the provider's record for the exact message; never resend from this list.

## Sensitive calls

Escalate threats, emergencies, imminent deadlines, complaints, subpoenas, law-enforcement contacts, and suspected conflicts according to firm policy. If the live feed or caller matching shows unrelated or unexpected data, stop and tell an administrator.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| **Convert to Matter** is missing | The lead is not yet **Engaged** | Complete the remaining stages and select **Advance**. |
| "The lead stage could not be updated" | A brief connection problem or a permission change | Try again; if it repeats, ask your administrator. |
| The live call feed is empty | Zoom Phone is not connected | Capture calls by hand, and ask your administrator to finish the Zoom Phone setup. |
| **Send paperwork** is disabled | No form or requested record is chosen, or the client email is missing | Add at least one item and the client's email. |
| An inbound text is not on the matter | It is waiting in **Inbound SMS routing review** | Choose the contact and matter, then **Resolve route**. |

## Related chapters

- [Contacts & client relationships](/guide/contacts-and-client-relationships)
- [Matters & documents](/guide/matters-and-documents)
- [Teams & client portals](/guide/teams-and-client-portals)
