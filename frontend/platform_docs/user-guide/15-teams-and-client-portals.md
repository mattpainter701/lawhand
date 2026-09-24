---
slug: teams-and-client-portals
title: Teams & client portals
description: Work with matters from Microsoft Teams, invite clients to a secure portal, share the right documents, and control who has access.
order: 150
read_time: 9 min
icon: plug
---

# Teams & client portals

LawHand reaches people outside the app in two ways: a LawHand tab inside [Microsoft Teams](/teams) for your colleagues, and a secure portal for each client or participant on a matter. Both help only when it is clear who can see what.

## Use LawHand in Microsoft Teams

When your firm links a Teams channel to a matter, the LawHand tab in that channel shows the **Linked channels** and the matter's context, with shortcuts to **Open matter workspace** and **Open deadlines and events** in LawHand.

- Before you post or act, confirm the team, the channel, and the matter. A channel's Microsoft membership and LawHand's matter permissions are separate controls and may not match.
- Collaborate in the channel, but keep official documents, decisions, and tasks in the matter. A chat message does not become part of the client file.
- If a channel is missing or linked to the wrong matter, stop using it and tell an administrator. Never copy sensitive material into a broader channel to work around a mapping problem.

## Client and participant portals

Each matter's **Client Portal** section invites clients and shows every invitation. Mediation cases have their own participant portal; see [Mediation workflows](/guide/mediation-workflows#invite-parties-to-the-portal).

### Invite a client

Before you invite anyone:

1. verify the recipient's identity and email address;
2. make sure you are on the right matter;
3. review what the portal will already show them; and
4. test a new portal workflow with a separate test identity first.

To send the invitation:

1. Open the matter from [My Matters](/matters) and go to **Client Portal**.
2. Enter the **Client email**.
3. If you are re-issuing a link to the same person, tick the option to revoke the live invitations on this matter when sending. Leave it clear to give a second person their own access.
4. Select **Send portal invite**.

LawHand shows the link once, with **Copy link**. The link grants access to the matter: share it with the client directly, never in a group thread. If the email could not be confirmed, LawHand says so; copy the link and send it through an approved channel.

Client paperwork sent from **Start this case** carries its own portal link. See [Send the client paperwork](/guide/intake-and-call-reception#send-the-client-paperwork).

### Track and revoke invitations

**Invitations** lists each recipient with its state: **Awaiting first sign-in**, **Active**, **Expired**, or **Revoked**, when it expires, and when the portal was **Last active**. An invitation marked **Never opened** usually means the link did not reach its recipient.

Select **Revoke** to end an invitation. Revoking ends every session on it immediately. Clients can also sign out from the portal header, which ends that session.

### Share documents

Documents reach the portal only when you mark them portal-visible on the matter's **Documents** section; see [Share a document with the client](/guide/matters-and-documents#share-a-document-with-the-client). Documents the client uploads appear there automatically.

Before sharing, confirm each file is final and right for this recipient. Never expose internal notes, another party's materials, draft strategy, or documents from another matter.

### What the client sees

The portal opens on a summary of the matter: its status and stage, the next key date, the assigned legal team, and counters for unread messages, documents awaiting signature, and any balance due. From there the client can:

- exchange secure messages with the team;
- download what the firm has shared, and upload documents of their own;
- sign documents and acknowledgments; and
- download a firm-branded invoice PDF and pay invoices.

Invoice downloads are limited to the matter and recorded in the firm's audit history; the PDF is generated for the client and not kept as a second copy.

## Signatures through the portal

Clients sign inside the document in their portal. After everyone signs, the signed PDF and its evidence certificate are filed to the matter and appear in the client's **Documents** tab.

If storage is briefly unavailable, the request shows **Signed — filing**: the answers and signatures are recorded and filing is pending. Automatic retries reuse the saved evidence, so the client does not sign again. Check that both files appear on the matter before treating filing as complete. To send a request, see [Send a document for signature](/guide/document-automation-and-esignature#send-a-document-for-signature).

## When access is wrong

Revoke or correct access as soon as a recipient, matter, or sharing decision is wrong. Keep the audit history, and report any suspected access to another matter immediately.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| The client never received the invitation | Email delivery was not confirmed, or the message was filtered | Copy the link and share it directly, or send a new invitation. |
| An invitation shows **Expired** | The link passed its expiry date | Send a new invitation. |
| The client cannot see a document | It is not marked portal-visible | Mark it portal-visible on the matter's **Documents** section. |
| Two people need access | One invitation is for one person | Send a second invitation without ticking the revoke option. |
| A Teams channel shows the wrong matter | The channel is mapped incorrectly | Stop using the link and tell your administrator. |

## Related chapters

- [Matters & documents](/guide/matters-and-documents)
- [Template Studio & e-signature](/guide/document-automation-and-esignature)
- [What connected integrations can view](/guide/integration-transparency)
