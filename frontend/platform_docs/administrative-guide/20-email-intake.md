---
slug: email-intake
title: Firm email intake
description: Turn on the firm's forwarding address, set the time zone, make sure staff mail is signed, and manage the address over time.
order: 200
read_time: 9 min
icon: mail
---

# Firm email intake

Firm email intake gives everyone at the firm one forwarding address, saved as **LawHand Tasks** on phones and in mail apps. Staff forward a client email there with `[TASK]`, `[REVIEW]`, or `[DEADLINE]` at the start of the subject, and it waits in **Needs review** until someone confirms the matter, owner, and date. The staff side is covered in the user guide chapter [Email tasks](/guide/email-intake).

## The Email intake section

Open [Integrations > Email intake](/admin?tab=integrations&integration=email-intake).

![The Email intake section with its Guide link, the Needs review button, the forwarding address with Copy address and Save LawHand Tasks contact, the Firm time zone, the Replace and Disable address buttons, and the expanded list of authorized staff senders](/guide-assets/admin-email-intake.webp "Administration: Email intake")

1. **Guide** opens this chapter.
2. **Needs review** opens the queue of forwarded requests, with the number waiting.
3. **Save time zone** saves the firm's time zone for relative dates.
4. **Replace address** issues a new address; **Disable address** stops intake.
5. **Authorized staff senders** lists the addresses LawHand accepts forwards from.

## Turn it on

1. Select **Enable firm address**. LawHand creates one private address for your firm on the shared intake domain.
2. Enter the **Firm time zone** as an IANA name, such as `America/Chicago`, and select **Save time zone**. It is used for "tomorrow" and "in two weeks", based on when LawHand receives the email.
3. Check your staff's mail signing (below).
4. Select **Save LawHand Tasks contact** to download the contact card (`LawHand Tasks.vcf`), or **Copy address**, and share it with staff. Staff can also save it themselves from [Tasks](/tasks).
5. Forward a test email with `[TASK]` at the start of the subject from a registered address, open **Needs review**, and file it to a test matter.

The address is not a Microsoft 365 or Google mailbox: it needs no mailbox password or extra license, and your MX records do not change. Receiving infrastructure is shared, but each address routes only into its own firm.

## Who can forward

Only registered, active staff addresses are accepted; **Authorized staff senders** lists them. Disabled accounts, service identities, and client or portal accounts are excluded, and no domain-wide access is granted.

- A person's registered address is the email on their LawHand account. Change it through [Users](/admin?tab=users).
- A person's other addresses are not accepted automatically.

Only administrators can turn intake on, replace or disable the address, or change its settings. Any active staff member can see the address and review requests.

## Make sure staff mail is signed

LawHand verifies each forward's DKIM signature itself, covering the From, Subject, and the whole body. The signature must use RSA-SHA256, with a signing domain exactly matching the registered address's domain. Authentication headers supplied by the sender are not trusted.

- Mail that is unsigned, signed by another domain, or checked only by SPF is rejected.
- Microsoft 365 custom domains may need DKIM signing turned on. Ask your mail administrator to configure it and test each sending setup before rollout.
- The client or court never needs an account: the staff member's authenticated forward is what counts.

## How requests behave

- The tag must start the subject. A name before the comma suggests an owner; with no name, LawHand suggests the sender.
- Relative dates use the receipt date in the firm time zone. Changing the time zone affects new requests, not ones already waiting.
- A deadline cannot be filed until a reviewer confirms its date. LawHand never calculates or verifies a court deadline from email.
- Every request waits in **Needs review**. Filing stores the email and the task together; the assignment notice and calendar entry follow only after that is saved.
- LawHand never runs instructions from an email body or its attachments. Untagged forwards and ones it cannot match to a matter stay in the queue for manual review.

## Replace, disable, and troubleshoot

- **Replace address** revokes the current address and creates a new one after you confirm the replacement. Staff must update their saved contact; requests already waiting stay available.
- **Disable address** stops new intake. Requests already waiting stay available.
- **Needs review** shows the pending count and the oldest 50 requests; more appear as those are processed.
- An identical copy delivered again is ignored; an edited forward can create a separate request.
- If filing fails, the request stays reviewable. Check the matter's storage, then retry rather than forwarding another copy.

If the section says "Email intake is not configured on this deployment", intake has not been enabled for your LawHand environment; contact [LawHand support](/admin?tab=support).

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| A forward never reaches the queue | Sent from an unregistered address, unsigned or wrongly signed, or to a replaced address | Check **Authorized staff senders**, DKIM for that domain, and the current address. |
| Dates are a day off | The firm time zone is wrong | Set the correct IANA time zone and **Save time zone**. |
| Staff still use the old address | The address was replaced | Share the new contact card. |
| Filing fails for one matter | The matter's storage is not ready | Check **Document storage** on Integrations > Cloud, then retry. |

## Related chapters

- [Email tasks](/guide/email-intake) (user guide)
- [Integrations](/admin?tab=guide&chapter=integrations)
- [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing)
