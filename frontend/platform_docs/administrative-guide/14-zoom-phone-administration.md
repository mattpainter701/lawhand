---
slug: zoom-phone-administration
title: Zoom Phone administration
description: Create the firm's Zoom app, connect Zoom Phone for call intake and Zoom Meetings for meeting links, and verify real-time call delivery.
order: 140
read_time: 12 min
icon: phone
---

# Zoom Phone administration

[Integrations > Zoom](/admin?tab=integrations&integration=zoom) connects two separate Zoom services:

- **Zoom Phone** brings completed calls into [Call Intake](/intake/dashboard).
- **Zoom Meetings** creates meeting links for events. It is optional (**Meetings optional**) and not needed for call intake.

Each has its own app and grant; connecting one never connects the other.

## What Zoom Phone can expose

The Phone workflow can receive the provider call ID, caller and recipient names and numbers, direction, result, duration, and time, plus the provider's call record. When Zoom supplies them for the account and call, LawHand may also receive summary text, transcript text, and recording and transcript links.

LawHand stores this as a communication record that can be matched to a contact and linked to a matter. It never places or records calls itself. See [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility) for the full disclosure.

## Before you start

Decide, and write down:

- the firm's lawful basis and notice or consent procedure for call recording and transcription in every jurisdiction you call;
- who may see call details, transcripts, and recording links; and
- how long imported calls and provider data are kept.

## Set up Zoom Phone

The panel's progress row has four stages. Each is separate: a saved app is not yet authorized, and a working history sync does not prove real-time delivery.

### 1. Create the app in Zoom

1. Sign in to the Zoom App Marketplace as the firm's approved Zoom administrator.
2. Create a private, admin-managed **General App**.
3. Enter the **Callback URL** and **Webhook URL** shown in the LawHand panel.
4. Under **Zoom Phone** > **Call Logs**, add exactly these two scopes (the panel lists them under **Required Phone scope list**):
   - `phone:read:list_call_logs:admin` ("Get account's call history"); and
   - `phone:read:call_log:admin` ("Get call history detail and call element").
5. Subscribe to the events under **Required event list**.

Do not add classic, write, delete, or manage scopes. Use one Zoom environment (Development or Production) throughout: the callback, scopes, webhook, and credentials must all come from the same one.

### 2. Save the app credentials

1. In LawHand, select **Add Phone app**.
2. Enter the **Client ID**, **Client secret**, and the webhook **Secret token** from the same Zoom environment.
3. Save. The panel shows **Tenant app saved**.

Replacing a saved client ID and secret disconnects the previous grant on purpose. Enter secrets only in these protected fields, and keep recovery copies in your approved secret manager.

### 3. Authorize the account

Select **Connect Zoom Phone** in LawHand and approve in Zoom. You return to the Zoom panel with "Zoom Phone is authorized. LawHand verified access to Phone call history." or a specific message saying what to fix.

> [!IMPORTANT]
> Always start from **Connect Zoom Phone** in LawHand. The **Add** button and the generated authorization URL in the Zoom Marketplace do not start LawHand's firm-bound request, so they fail.

### 4. Verify the scopes and real-time calls

1. Check that the status reads **Phone API connected**, not **Missing permissions**.
2. Select **Test connection**.
3. Make an approved demo call that contains no client information, and check that:
   - the call appears in [Call Intake](/intake/dashboard) and the status moves to **Real-time calls verified**;
   - the caller and direction are correct;
   - only the intended account's calls are visible;
   - matching does not attach an unrelated contact or matter; and
   - follow-up routing behaves as configured.

## Set up Zoom Meetings (optional)

To let people add Zoom links when they create events, select **Add Zoom app**, save that app's credentials, and select **Connect Zoom**. The status reads **Meetings connected** when it is ready. People then see **Zoom** as an online meeting option on the [Calendar](/calendar).

## Keep it healthy

Real-time webhook delivery and API access are separate. A connected account can still have missing calls if event delivery broke, and working events do not guarantee future API access. After changing the Zoom app, secret token, grant, or scopes, run **Test connection** and make another demo call.

Completed-call webhooks are signature-checked and matched to your Zoom account and firm. LawHand then fetches the exact call through the API instead of trusting the event body.

Phone API access refreshes automatically during history sync and connection tests. If the status reads **Phone needs re-authorization**, select **Re-authorize Phone**.

## Disconnect or contain

1. Tell the reception team and stop workflows that depend on call capture.
2. Select **Disconnect** in the Phone section, and revoke the app in Zoom if your policy requires it.
3. Confirm that no new calls arrive.

Disconnecting stops future imports. It does not delete calls, transcripts, links, or audit history already in LawHand; apply your retention and deletion process separately.

Unexpected call history from another account, data from another firm, or unexplained webhook traffic is a security issue. Keep identifiers and times, without copying call content into an unrestricted ticket.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "Zoom could not complete authorization." | Environment, callback URL, or credentials do not match | Copy the client ID and secret from the same Zoom environment, save both, and reconnect. |
| "That authorization request expired or was not started from LawHand." | Authorization started from the Zoom Marketplace | Start again with **Connect Zoom Phone**. |
| **Missing permissions** | A required scope is missing in the Zoom app | Add both Call Logs scopes and re-authorize. |
| **Real-time webhook pending** | Zoom has not delivered an event yet, or the webhook is misconfigured | Check the webhook URL, secret token, and events; make a demo call. |
| Calls appear late or not at all | Webhook delivery broke | Run **Test connection** and check the webhook settings in Zoom. |

## Related chapters

- [Integrations](/admin?tab=guide&chapter=integrations)
- [Microsoft Teams administration](/admin?tab=guide&chapter=microsoft-teams-administration)
- [Intake & call reception](/guide/intake-and-call-reception)
