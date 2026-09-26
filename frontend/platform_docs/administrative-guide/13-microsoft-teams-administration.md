---
slug: microsoft-teams-administration
title: Microsoft Teams administration
description: Link matters to Teams channels, route firm-wide notifications, and capture Teams Phone calls into intake.
order: 130
read_time: 13 min
icon: network
---

# Microsoft Teams administration

[Integrations > Teams](/admin?tab=integrations&integration=teams) connects LawHand to Microsoft Teams. It has three tabs: **Channels** (link a matter to a channel), **Notifications** (firm-wide routing), and **Voice** (Teams Phone call capture).

## Before you start

1. Connect Microsoft 365 under [Integrations > Cloud](/admin?tab=integrations&integration=cloud) with an approved organization account. See [Integrations](/admin?tab=guide&chapter=integrations).
2. If the Teams card says **Reconnect to enable Teams**, re-authorize Microsoft and accept the Teams permissions. The section shows **Teams connected** when it is ready.
3. Make sure the team, the channel, the matter, and the people involved already exist.

Teams is an explicit addition to the Microsoft grant. It asks for three permissions: read basic team information (`Team.ReadBasic.All`), read basic channel information (`Channel.ReadBasic.All`), and send channel messages (`ChannelMessage.Send`). Channel creation (`Channel.Create`) is added only when the firm opts into creating matter channels. Teams does not ask to read or write chats or to send activity-feed notifications; LawHand posts only to the channels you link or route. See [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility).

A firm that connected Teams before these permissions were narrowed keeps working without re-approving: its existing grant already covers them. Microsoft keeps the chat and activity permissions from that earlier consent until an administrator removes them in the Microsoft Entra admin center (**Enterprise applications** > LawHand > **Permissions**); LawHand does not use them.

Microsoft's permissions and LawHand's matter access are separate: a channel member may not have access to the matter in LawHand, and a matter member may not be in the channel. Test both before sending real matter content.

## Link a matter to a channel

1. Open the **Channels** tab.
2. Choose the matter under **Select matter…**.
3. Choose the team under **Select team…**, then the channel under **Select channel…**. To make a new one, enter a **New channel name** (or leave it to name the channel after the matter) and select **Create channel**.
4. Select **Link matter to channel**. "Matter linked. Its notifications now post to that channel."
5. Select **Send a test card** and check it arrives in the right channel.

Watch for similarly named teams, archived channels, and private or shared channels, and save one link for the intended collaboration space. Then test with:

1. a matter member who is in the channel;
2. a matter member who is not in the channel;
3. a channel member without matter access; and
4. an administrator reviewing the link.

No test person should see matter content they should not.

### Maintain links

Review links when a matter closes, a team is renamed or archived, channel membership changes, or the responsible group changes. **Unlink**, then **Confirm unlink**, removes a stale link; "Matter unlinked. It no longer posts to that channel."

Never fix a membership problem by linking the matter to a broader channel. Treat a wrong link as a possible disclosure: stop using it, unlink or correct it, work out what was visible, and follow your incident process when necessary.

## Route firm-wide notifications

The **Notifications** tab points each notification LawHand raises at one team and channel.

1. For each event you want in Teams, choose the team and then the channel.
2. Select **Save routing**. Every enabled event needs a team and channel.

A matter linked to its own channel always posts there instead, so a matter link overrides the firm-wide route for that matter. Only events LawHand actually raises can be routed.

Tell people which kinds of updates go to Teams, that Teams messages are notifications rather than the record, and that the official file stays in LawHand. Keep cards to the detail the channel audience needs.

After any change, check the grant owner, the permissions shown, the team and channel, membership, a non-sensitive test delivery, that duplicates are not posted, and how to remove the link. Revoking Microsoft access stops future delivery but does not remove messages already posted.

## Capture Teams Phone calls

Firms whose phones run on Teams Phone can capture inbound calls into [Call Intake](/intake/dashboard) alongside Zoom Phone calls, in one feed with one set of follow-up tasks and one export. Outbound and internal Teams calls are not captured.

Call records are metadata: numbers, participants, timing, and outcome. They are not recordings or transcripts.

### Why voice needs its own consent

Teams channel messaging uses the delegated Microsoft grant. Microsoft exposes call records only through the application permission `CallRecords.Read.All`, which has no delegated equivalent, so voice capture runs on a separate application-only credential with its own administrator consent. Turning voice on does not widen the channel-messaging grant, and turning it off does not affect channel messages.

### Set up voice capture

On the **Voice** tab, under **Setup**:

1. **Name the Microsoft Entra directory.** Enter the directory (tenant) ID from the Entra admin center's **Overview**, and select **Save directory**. The shared `common` endpoint cannot issue application-only tokens, so it is rejected.
2. **Grant the permission.** A Microsoft 365 global administrator consents once, through the link the panel builds for your directory. `CallRecords.Read.All` is the only permission voice capture uses.
3. **Turn it on.** Select **Enable voice capture**, then **Start live notifications**. Microsoft validates LawHand's notification address before it starts sending; the panel shows the address if you need it for a change ticket.

Firms that prefer to own the app registration can register a single-tenant Entra app holding only `CallRecords.Read.All` and enter its credentials; otherwise LawHand's own app is used.

### Verify it works

Under **Verify**, **Test connection** proves the credential and permission by reading the last 24 hours of usage, without changing anything. **Import last 7 days** reruns the catch-up pass over the past week.

The section's status shows **Voice capture live** when notifications are flowing, **Voice capture on (hourly)** when only the hourly catch-up is running, or **Voice capture off**.

### How calls arrive

Calls arrive two ways. Live notifications from Microsoft deliver a call moments after it ends. An hourly pass over the Teams PSTN usage report fills in anything the live path missed; Microsoft publishes that report with a delay, which is why it is the backstop. LawHand matches a call across both on the caller's number and start time, so it is stored once. If live notifications lapse, capture continues hourly.

Microsoft expires the call-record subscription after about three days. LawHand renews it well before then; a failed renewal is shown on the **Voice** tab (**Last background run failed**) while hourly capture continues. Pointing the integration at a different directory clears the old subscription.

**Stop live notifications** and **Disable voice capture** remove the subscription at Microsoft. Calls already captured stay in Call Intake under their normal retention.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| **Reconnect to enable Teams** | The Microsoft grant lacks the Teams permissions | Re-authorize Microsoft and accept the Teams permissions. |
| "Microsoft Graph could not list your teams." | The Teams permission was revoked or expired | Reconnect Teams and try again. |
| A test card does not arrive | The channel was archived or the link is stale | Check the channel in Teams, then relink. |
| **Voice capture on (hourly)** instead of live | Live notifications stopped or failed to renew | Select **Start live notifications** again; capture continues hourly meanwhile. |
| **Test connection** fails | The directory ID is wrong or consent was not granted | Check the directory ID and have a global administrator consent. |

## Related chapters

- [Integrations](/admin?tab=guide&chapter=integrations)
- [Zoom Phone administration](/admin?tab=guide&chapter=zoom-phone-administration)
- [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility)
