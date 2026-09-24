---
slug: integrations
title: Integrations
description: Connect Microsoft 365 or Google Workspace and the other services your firm uses, read each connection's health, and choose where matter documents live.
order: 40
read_time: 14 min
icon: plug
---

# Integrations

An integration extends where your firm's data goes. Connect only approved organization accounts, accept only the permissions the workflow needs, and name an owner who can maintain the connection and respond when it fails.

## The Integrations hub

Open [Integrations](/admin?tab=integrations). It opens on an overview of every connection.

![The Integrations overview with the section buttons, the Advanced button, and cards for Email intake, Cloud accounts and storage, Cloud Search, and File shares, each with a status and a Permissions and setup disclosure](/guide-assets/admin-integrations.webp "Administration: Integrations overview")

1. **Advanced** reveals the operator tools, for administrators who hold the `manage_integrations` capability.
2. Each card's status answers "is this working?": **Connected**, **Needs attention**, **Not connected**, or **Not configured**.
3. **Open** (or **Set up**, for a connection that is not set up yet) goes to that section.
4. **Permissions & setup** lists what the connection can access and what it needs before you start, with a link to its guide chapter.

The sections are grouped by who uses them:

- **Firm sections**: [Email intake](/admin?tab=integrations&integration=email-intake), [Cloud](/admin?tab=integrations&integration=cloud), [Cloud Search](/admin?tab=integrations&integration=cloud-search), [File shares](/admin?tab=integrations&integration=file-shares), [Teams](/admin?tab=integrations&integration=teams), [Zoom](/admin?tab=integrations&integration=zoom), and [QuickBooks](/admin?tab=integrations&integration=quickbooks).
- **Advanced**: MCP servers, Storage migration, Data import, and Provider app readiness. These change every matter, so they are collapsed and only shown to administrators with `manage_integrations`. Hiding is presentation; the capability is the control.

Accountants see QuickBooks only. The intake-only plan sees Zoom only. **Full data visibility guide** opens [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility).

## Connect Microsoft 365 or Google Workspace

Most firms connect one of these first: it provides sign-in, directory sync, mail, calendar, and document storage.

1. Open [Cloud](/admin?tab=integrations&integration=cloud).
2. On the provider's card, select **Connect** under **Firm-wide connection**.
3. Sign in with an administrator account of your organization's Microsoft or Google tenant. Check that the organization named on the consent screen is yours.
4. Accept every requested permission. Declining one leaves the connection with **Missing Scopes**.
5. You return to the Cloud section. Confirm the health reads **Healthy**.
6. Test with a non-sensitive record: capture a test email, create a test matter folder, and check that it appears where you expect.

Use an organization-owned administrator or service identity whose ownership survives staff turnover. Deactivating the person who granted consent can break the connection; LawHand warns you before it happens.

### Read a provider card

Each provider card answers three questions in order.

**Is the firm-wide connection usable?** This administrator grant runs directory sync, firm mailboxes, folder provisioning, and scheduled cloud sync. Its health is one of:

| Health | Meaning | What to do |
| --- | --- | --- |
| **Healthy** | The last token refresh succeeded and every required permission is granted. | Nothing. |
| **Missing Scopes** | Usable, but a permission was declined at consent. The card lists which. | **Re-authorize** as an administrator and accept every permission. |
| **Refresh Failed** | LawHand could not refresh the token for a reason other than revocation. | **Re-authorize**. If it recurs, check Advanced > Provider app readiness. |
| **Reconnect Required** | The provider revoked the grant. Nothing that depends on it runs until it is renewed. | **Re-authorize** as an administrator. |
| **Disconnected** | There is no firm-wide connection. | **Connect**. |

When the connection is **Reconnect Required** or **Refresh Failed**, the card leads with the fix and hides the permission count, because a past grant says nothing about whether the credential works now. The detail stays under **Scope detail for support**.

A successful re-authorization clears the failure immediately. If a card still shows an error afterwards, the consent did not complete; look for a provider error in the address bar and try again.

The refresh line reads **Last successful token refresh** when the last attempt worked, or **Last token refresh attempt … failed** with the recorded error. A failed attempt also updates the time, so the time alone is not proof of health.

**Are people's own connections usable?** Each person connects their own Microsoft or Google account from [Calendar](/calendar) with **Connect Calendar**. These **Per-user connections** refresh separately and fail independently: the firm grant can be revoked while people's own sync keeps working, and the reverse. The card shows how many people are connected and how many need to reconnect. You cannot reconnect someone else's account; ask them to reconnect from Calendar.

**What was consented?** The permission list shows what the grant allows. **Sync now** runs directory sync when your account tier supports it; personal Google and Microsoft accounts have no directory, and the card says so rather than reporting a failure.

## Choose where matter documents live

The **Document storage** disclosure on the Cloud section holds settings that are rarely changed and unsafe to change casually:

- **Primary provider for matter documents** decides where every new matter document is written. LawHand asks you to confirm and warns that existing folders do not move; use **Storage migration** under Advanced to rebind existing matters. Cloud writes fail rather than fall back to LawHand storage, so choosing a provider that is not connected stops uploads until it is.
- **Create missing matter folders** recreates the root folder and any missing matter folders. It is safe to repeat: existing folders are found and reused.
- **SharePoint library** (shown when Microsoft 365 is connected) limits everyday workflows to an approved SharePoint site and library.

For Microsoft 365, **Auto** storage uses the connected identity's OneDrive unless you choose SharePoint or Google Drive. Prefer an approved SharePoint site library or an organization-owned identity. The file permission follows everything that identity can access, so a connection alone does not prove that the intended matter folders are writable.

New firms choose their provider and create the root folder during setup; see [Onboarding & storage setup](/admin?tab=guide&chapter=onboarding-and-storage-setup).

## Other services

- **Email intake** gives staff one forwarding contact for matter to-dos. See [Firm email intake](/admin?tab=guide&chapter=email-intake).
- **Cloud Search** searches connected mail and files. See [Cloud Search operations](/admin?tab=guide&chapter=cloud-search-operations).
- **File shares** connects on-premises SMB shares through a firm-managed agent. See [File Share operations](/admin?tab=guide&chapter=file-share-operations).
- **Teams** routes matter updates to Teams channels. Treat channel mappings and notification destinations as data-routing decisions. See [Microsoft Teams administration](/admin?tab=guide&chapter=microsoft-teams-administration).
- **Zoom** connects Zoom Meetings and Zoom Phone as separate grants. Test with an approved demo call, and never expose unrelated call history. See [Zoom Phone administration](/admin?tab=guide&chapter=zoom-phone-administration).
- **QuickBooks** exports clients, time, invoices, and payments. Confirm the company with your Intuit administrator before any sync, and name who reviews sync errors so LawHand never becomes an unexplained second ledger. See [QuickBooks administration](/admin?tab=guide&chapter=quickbooks-administration).

## Connection lifecycle

For each integration, record in your restricted operations system the business owner, technical owner, granted permissions, affected data, renewal expectations, and how to disconnect.

To disconnect a service:

1. tell the people who depend on it;
2. stop workflows that use it;
3. disconnect through the service's section in Integrations;
4. revoke LawHand's access in the provider's own admin console if your policy requires it; and
5. confirm which synchronized records remain under your retention policy. Disconnecting stops future access; it does not delete what was already imported.

> [!WARNING]
> Never paste client secrets, webhook secrets, tokens, or certificates into this guide, a support message, or a screenshot.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| A card says **Needs attention** | The firm-wide connection is missing permissions or failing to refresh | Open the section and follow the fix the card leads with. |
| Uploads to matters fail | The primary provider is not connected, or the root folder is missing | Reconnect the provider, then **Create missing matter folders**. |
| People say their calendar or mail stopped | Their own connection expired | Ask them to reconnect from Calendar; you cannot do it for them. |
| **Advanced** is missing | Your role lacks `manage_integrations` | Ask an administrator who holds it. |
| The card still shows an error after re-authorizing | The consent did not complete | Look for a provider error in the address bar and try again. |

## Related chapters

- [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility)
- [Storage, imports & readiness](/admin?tab=guide&chapter=storage-imports-and-readiness)
- [Cloud provider support](/admin?tab=guide&chapter=cloud-provider-support)
