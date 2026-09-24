---
slug: storage-imports-and-readiness
title: Storage, imports & readiness
description: Choose and bind document storage, move existing matters to another provider, import Tabs3 data, and check provider app readiness.
order: 70
read_time: 15 min
icon: cloud
---

# Storage, imports & readiness

Matter documents live in your firm's own Microsoft or Google storage, not in a LawHand datastore. This chapter covers where that storage is set, how to move existing matters between providers, how to import data from Tabs3, and how to check that the provider apps are registered correctly.

![How tasks and customer-owned document storage are separated](/guide-assets/customer-data-task-lifecycle.svg)

## Where these controls live

- **Document storage** is on [Integrations > Cloud](/admin?tab=integrations&integration=cloud), collapsed below the provider cards. See [Choose where matter documents live](/admin?tab=guide&chapter=integrations#choose-where-matter-documents-live).
- [Storage migration](/admin?tab=integrations&integration=storage-migration), [Data import](/admin?tab=integrations&integration=data-import), and [Provider app readiness](/admin?tab=integrations&integration=readiness) are under **Advanced** on the Integrations overview, for administrators who hold the `manage_integrations` capability.
- New firms choose their provider and create the root folder in [Onboarding](/onboarding); see [Onboarding & storage setup](/admin?tab=guide&chapter=onboarding-and-storage-setup).

## Cloud document storage

Choose the primary provider only after confirming who owns the account, its tier, the granted permissions, and which features it supports. The selector is authoritative:

- **Auto** uses OneDrive when Microsoft 365 is connected, otherwise Google Drive when Google is connected.
- **OneDrive**, **SharePoint**, or **Google Drive** is an explicit override.
- A write never spills into another provider or into LawHand's own storage. If the chosen provider is unavailable, the request fails with an error people can retry.

Set up and test storage before turning on portal uploads, inbound filing, document generation, or e-signature. In the readiness matrix, treat **not applicable** differently from **failed**: the first means the provider or tier does not offer the feature; the second means an expected feature needs attention.

### Microsoft 365 notes

The firm grant requests directory read, mail read, file read and write, SharePoint site read, calendar read and write, and offline access. Personal grants omit directory read but still authorize that person's mail, files, and calendar. These are delegated permissions: what LawHand can reach follows the connected identity's access.

LawHand uses them to list directory users; search Outlook message details and previews; capture a selected full message; list, search, download, and index supported OneDrive or SharePoint files; write matter folders and files in enabled workflows; and maintain calendar events for tasks and key dates.

The file permission (`Files.ReadWrite.All`) is broader than the LawHand records folder. Bind the root to a SharePoint site library rather than a personal OneDrive, so the firm keeps custody, and prefer an organization-owned identity with only the access it needs. Verify create, read, update, and delete with a non-sensitive file. If the administrator who connected Microsoft leaves, reconnect another administrator from Integrations > Cloud.

### Google Workspace notes

The administrator grant requests identity and profile, read-only directory users, read-only Gmail, Drive read and write, Calendar read and write, and offline access. Directory access does not authorize every person's Gmail; mail, Drive, and Calendar act as the account that connected.

On Google Workspace, LawHand creates an organization-owned Shared Drive named `LawHand Firm Records`, adds its own service account as a member, and keeps the firm's root inside it. That service account performs storage operations, so deactivating the connecting administrator does not interrupt access. You configure nothing in Google Cloud.

If your Workspace policy blocks Shared Drive creation or the service-account membership, LawHand removes the unused drive and falls back to the administrator's My Drive, and onboarding reports the root ownership as at risk. Treat that as a retention risk to fix, not a normal end state.

For every field LawHand reads and keeps, see [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility).

## Bind a SharePoint library

A SharePoint binding limits everyday LawHand workflows to an approved site and library. It does not narrow the Microsoft permission itself.

1. Under **Document storage**, open **SharePoint library**.
2. Search for the site, and confirm its organization and purpose.
3. Choose the correct library (drive) and save the binding.
4. Upload a non-sensitive test document to a test matter and confirm where it lands.

Before rebinding, list the workflows that depend on the current location; changing it can change what people find, upload, or retrieve.

## Portal upload folder

Cloud setup creates a `client_uploads` folder in each matter. Portal originals stay there so their provider IDs and intake history stay stable. Save reviewed or revised work as a new document in the right matter folder rather than moving the original.

For matters created before this folder existed, select **Create missing matter folders** under **Document storage**, check the new folder, and test a portal upload. SharePoint uploads fail rather than use a general documents folder when the approved library details are missing.

## Move existing matters to another provider

[Storage migration](/admin?tab=integrations&integration=storage-migration) rebinds existing matter folders and files to another connected provider. LawHand discovers and verifies what is already there; it does not copy files. Copy the files with your provider's own tools first.

1. Make sure both providers are connected and a primary provider is chosen. Migration needs an explicit provider; **Auto** does not identify a source.
2. **Choose provider** for the destination, and identify the **Target connected root**: its root folder ID, and for SharePoint the drive ID and root item ID.
3. Select **Start migration**. LawHand discovers each matter's folders at the destination and marks each one **Matched**, **Ambiguous**, or **Missing**.
4. Resolve the **Unresolved items**, then select **Reconcile connected root** to verify again.
5. When everything matches, select **Confirm cutover**. LawHand reports **Cutover complete. Reindex is pending.** while search is rebuilt; use **Retry reindex** if reindexing stalls.

Use **Refresh status** to see progress, and **Abandon** to stop a migration you started by mistake. Plan the cutover for a quiet period and tell staff in advance.

## Import from Tabs3

[Data import](/admin?tab=integrations&integration=data-import) loads a Tabs3 export bundle.

1. Run the approved Tabs3 export, and have the bundle and its **Passphrase** ready.
2. Choose the **Accounting mode**: **LawHand native**, or **QuickBooks Online** if QuickBooks remains your ledger.
3. Select the **Export bundle** and **Upload**. LawHand lists each table with its rows, checksum, and any warnings.
4. Review the counts and warnings. Rehearse with a redacted or test bundle first.
5. Select **Run** to import.
6. Afterwards, reconcile contacts, matters, time, billing, and identifiers against the source, and keep the export and import evidence.

Never upload an unencrypted production export through an unapproved channel. A technically successful import still needs business reconciliation.

## Check provider app readiness

[Provider app readiness](/admin?tab=integrations&integration=readiness) shows **Cloud Integration Readiness** for the deployment: the **Environment** and the **Expected Redirect URIs**. Compare those URIs with your Google and Microsoft app registrations; anything marked **Missing** must be fixed in the provider's console before consent will work.

## Troubleshoot readiness

When a feature is unavailable, check in order: the provider identity, the account tier, administrator consent, granted permissions, credential health, the selected storage, the site or library binding, and the last synchronization result. Reconnect only when renewal is actually needed; repeated consent attempts can hide the original fault.

Production checks also cover document automation. They fail when a generated file has an unresolved storage record, or when an active PDF or Word template is missing its retained source file or its fingerprint. Resolve the underlying file deliberately; never clear a marker just to make a check pass. Recreate an invalid template from its original source and test it before publishing it again.

Record provider identifiers and diagnostic timestamps in your restricted operations system, not in this guide.

## Retention and disconnecting

Provider tokens are stored encrypted. For cloud-bound matter files, the file contents live in your storage. LawHand keeps the records it needs to run: firm, client, and matter details, tasks, provider object identifiers, file hashes and sizes, audit history, and, when enabled, captured email and extracted or indexed text. It is a customer-owned document architecture, not a zero-data one.

Disconnecting a provider stops future access; it does not delete records already imported. Confirm your retention decision before disconnecting, and use the supported deletion process when removal is required.

LawHand never deletes or destructively renames your cloud folders: not on disconnect, matter close, provider change, or when your firm leaves. The folders stay in your account. Before any cleanup, inventory the root and matter folders from **Document storage**, and ask [LawHand support](/admin?tab=support) for the handoff procedure.

## Related chapters

- [Integrations](/admin?tab=guide&chapter=integrations)
- [Onboarding & storage setup](/admin?tab=guide&chapter=onboarding-and-storage-setup)
- [Cloud provider support](/admin?tab=guide&chapter=cloud-provider-support)
