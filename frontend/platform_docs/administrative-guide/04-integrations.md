---
slug: integrations
title: Integrations
description: Authorize cloud, collaboration, phone, and accounting providers with clear ownership.
order: 40
read_time: 12 min
icon: plug
---

# Integrations

**Email intake** provides one firm-wide forwarding contact for matter to-dos. Configure it under [Integrations → Email intake](/admin?tab=integrations&integration=email-intake), then read the **Firm email intake** chapter in this Admin Guide for sender requirements and rollout checks.

An integration extends the tenant's data boundary. Connect only approved organization accounts, request the minimum scopes required by the intended workflow, and identify an owner who can maintain consent and respond to failures.

## How the hub is organized

[Integrations](/admin?tab=integrations) opens on an overview. Each card carries a status pill — **Connected**, **Needs attention**, **Not connected** or **Not configured** — so the question "is this working?" is answered without opening anything. Permissions and setup notes stay collapsed under each card; **Open** or **Set up** goes to that section.

Sections are grouped by audience:

- **Firm sections** (Email intake, Cloud, Cloud Search, File shares, Teams, Zoom, QuickBooks) are what a firm administrator connects and reviews day to day.
- **Advanced** holds operator tools: MCP servers, Storage migration, Data import and Provider app readiness. It is collapsed on the overview and in the section navigation, and it is only rendered for administrators who hold the `manage_integrations` capability. The disclosure is presentation; the capability is the authorization. A role without that capability never sees these sections.

Accountants see QuickBooks only. The intake-only plan sees Zoom only.

## Integration readiness

Start at [Integrations](/admin?tab=integrations), then open [Cloud](/admin?tab=integrations&integration=cloud). Review provider status, permissions, and health before asking users to depend on synchronized content. A connection can be technically present while a required scope, site binding, mailbox, webhook, or provider setting remains incomplete.

## Reading a provider card

Each cloud provider card answers three questions in order: is the firm-wide connection usable, are users' own connections usable, and what was consented.

**Firm-wide connection.** This is the administrator grant that runs directory sync, firm mailboxes, folder provisioning and scheduled cloud sync. Its health is one of:

| Health | Meaning | Remedy |
| --- | --- | --- |
| Healthy | The last token refresh succeeded and every required scope is granted. | None. |
| Missing Scopes | Usable, but a required permission was declined at consent. The card lists which. | Re-authorize as an administrator and accept every requested permission. |
| Refresh Failed | LawHand could not refresh the token; the provider returned an error other than revocation. | Re-authorize. If it recurs, check the provider app under Advanced → Provider app readiness. |
| Reconnect Required | The provider revoked the grant (for example `invalid_grant`). Nothing that depends on the firm-wide connection runs until it is renewed. | Re-authorize as an administrator. |
| Disconnected | No firm-wide connection. | Connect. |

When the connection is **Reconnect Required** or **Refresh Failed** the card leads with the remedy and hides the scope tally. Scope counts describe what was once consented; they say nothing about whether the credential works now, so an unusable connection never shows a full green grant. The detail remains under **Scope detail for support**.

**A successful re-authorization clears the failure immediately.** If a card still shows a stale error after you re-authorize, the consent did not complete — look for a provider error in the address bar or try again.

The refresh line is worded exactly: **Last successful token refresh** when the last attempt worked, or **Last token refresh attempt … failed** beside the recorded error when it did not. A failed attempt also updates the timestamp, so the time alone is not evidence of health.

**Per-user connections.** Users connect their own mailbox and calendar from their profile. Those tokens refresh through a separate path and fail independently of the firm-wide grant: the firm-wide grant can be revoked for weeks while users' own sync keeps running clean, and the reverse. The card shows how many users are connected and how many need to reconnect. An administrator cannot reconnect a user's token; the user does it from their profile.

**Sync now** appears only when directory sync is available on the account tier. Personal Google and Microsoft accounts have no directory to import; the card says so and does not treat it as a failure.

## Document storage

The **Document storage** disclosure on the Cloud section holds the settings that are rarely changed and unsafe to change casually:

- **Primary provider for matter documents.** Changing it repoints where every new matter document is written. The panel asks for confirmation and warns that existing folders are not moved; use Storage migration under Advanced to rebind existing matters. Cloud-bound writes fail rather than fall back to LawHand storage, so choosing a provider that is not connected breaks uploads until it is.
- **Create missing matter folders.** Re-creates the root and any missing matter subfolders. Safe to repeat: existing folders are detected and reused.
- **SharePoint library.** Shown only when Microsoft 365 is connected. Narrows normal workflows to an approved site and library.

New firms choose their provider and create the root during setup; see [Onboarding & storage setup](/guide/onboarding-and-storage-setup).

## Microsoft and Google

Use an authorized administrator account during consent. Confirm the organization and scope shown by the provider. After connection, test with a non-sensitive record and verify both read and write behavior expected by your workflow.

For Microsoft 365, **Auto** storage binds matter files to the connected identity's OneDrive unless an administrator explicitly selects SharePoint or Google Drive. Use an organization-owned service identity whose ownership will survive staff turnover, or select an approved SharePoint site/drive. The current delegated file permission follows everything that identity can access; connection alone is not proof that the intended matter folders are writable.

For collaboration configuration, use [Integrations → Teams](/admin?tab=integrations&integration=teams). Treat team/channel mappings and notification destinations as data-routing decisions.

## Zoom Phone

Use [Integrations → Zoom](/admin?tab=integrations&integration=zoom) for phone integration configuration and health. Confirm the Zoom account, required administrative grant, webhook configuration, and call visibility. Test inbound data using an approved demo call; do not expose unrelated account call history.

## QuickBooks Online

Use [Integrations → QuickBooks](/admin?tab=integrations&integration=quickbooks) with an Intuit administrator for the intended company. Verify the company identity before any synchronization. Establish ownership for mapping, reconciliation, and error review. LawHand should not become an unexplained alternate ledger.

## Connection lifecycle

For each integration, record the business owner, technical owner, granted scopes, affected data, renewal or consent expectations, and disconnect procedure in your restricted operations system.

When disconnecting:

1. communicate the impact;
2. stop dependent workflows;
3. disconnect through the supported interface;
4. revoke provider-side access when required; and
5. confirm what synchronized data remains under retention policy.

Never paste client secrets, webhook secrets, tokens, or certificates into this guide or a support screenshot.
