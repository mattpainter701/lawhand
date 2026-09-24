---
slug: onboarding-and-storage-setup
title: Onboarding & storage setup
description: Run the setup wizard for a new firm, choose where matter documents live and who owns them, and re-run or repair setup later.
order: 210
read_time: 12 min
icon: rocket
---

# Onboarding & storage setup

[Onboarding](/onboarding) is the setup wizard a new firm runs once, after the first administrator signs in. It connects the firm's cloud provider, confirms where matter documents will live, imports the team, and hands off to Administration. Every step is saved, so you can close the browser and resume; nothing is created silently in the background.

Only administrators can open it. Other people are sent to it after signing in until setup is complete or skipped.

## Run the wizard

The wizard has six steps across the top: **Welcome**, **Connect**, **Storage**, **Sync Users**, **Review**, and **Complete**.

1. **Welcome** explains the setup.
2. **Connect Your Firm**: accept the firm's agreements, then connect **Microsoft 365** or Google with administrator consent. For Google, choose **Google Workspace** (administrator consent enables directory sync, Gmail, Drive, and Calendar) or **Personal Google / Google One** (Gmail, Drive, and Calendar without a directory; you will invite teammates yourself). You need at least one connection to continue.
3. **Storage**: choose where documents live and create the root folder (below).
4. **Sync Users** (**Import Your Team**): select **Sync Users** to import your directory. Personal accounts have no directory; invite people from [Users](/admin?tab=users) instead.
5. **Review** shows the imported user counts and confirms storage is set.
6. **Complete** (**Setup Complete!**) marks the firm live and takes you to Administration.

Connecting a provider moves you to **Storage** automatically, and a finished directory sync moves you to **Review**; the wizard never skips **Storage**.

## Choose where documents live

![The Storage step of the setup wizard with Google Drive and Microsoft OneDrive as storage choices, an organisation-owned storage confirmation, the confirmed lawhand-records folder, and the Continue button](/guide-assets/onboarding-storage.webp "Setup wizard: Storage")

1. Choose the provider under **Where Should Documents Live?**. Only connected providers are listed; **Folder exists** marks one that already has a root folder.
2. The ownership panel says whether the storage belongs to the firm (**Organisation-owned storage**) or to one person (**This storage is tied to one person's account**).
3. After **Create folder**, LawHand shows the folder it created or confirmed, `lawhand-records`, with a link to open it.
4. **Continue** moves on to **Sync Users**.

Your connected cloud account is the system of record for matter documents, so setup cannot finish until its root folder is confirmed. The provider you choose becomes the firm's **primary provider**, the same setting shown under **Document storage** on [Integrations > Cloud](/admin?tab=integrations&integration=cloud).

Want a SharePoint library instead? Finish setup with OneDrive, then choose the site and library under **Document storage**. The storage migration tool can rebind matters later if needed.

## Who owns the root folder

The root should belong to the firm, not to the administrator who happened to connect the account. Otherwise deactivating or losing that person breaks access to every matter document.

- **Google Workspace.** LawHand creates an organization-owned Shared Drive, `LawHand Firm Records`, adds its own service account as a member, and creates `lawhand-records` inside it. You configure nothing in Google Cloud; the drive survives the connecting administrator leaving.
- **Microsoft.** Put the root in a SharePoint site library rather than a personal OneDrive. Until then, access uses the connecting administrator's token; if that account is removed, reconnect another administrator from Integrations > Cloud.
- **Personal Google.** There is no organization or Shared Drive, so the root lives in one person's Drive and is reported as at risk. Share the root with a second account, and keep an inventory of the folders.

Setup reports ownership as **durable** when every root is organization-owned, **at risk** when any root lives in one person's drive, and **unbound** when no root exists yet. LawHand never deletes or destructively renames your cloud folders.

### What "Folder exists" means

**Folder exists** means the firm already has a root for that provider, from an earlier run, re-entered setup, or a repair. LawHand keeps that folder and never recreates or repoints it, because every matter folder underneath depends on it. Choose **Continue** to keep it.

If a saved root is damaged (a provider entry without a folder ID), the step reports that a repair is needed and refuses to rebind. Repair it with [Storage migration](/admin?tab=integrations&integration=storage-migration) under **Advanced**, or ask [LawHand support](/admin?tab=support).

### If creating the folder fails

A failure here is honest and retryable, and records nothing: no half-created root and no change of primary provider. **Try again** repeats the same request. The usual causes:

- **The connected account cannot create the folder.** The consent came from an account without Drive or OneDrive access, or a permission was declined. Re-authorize from Integrations > Cloud and try again.
- **SharePoint was chosen before a library was bound.** Choose OneDrive for now, or bind the site and library first.
- **Workspace policy blocks the Shared Drive.** Shared Drive creation may be limited to certain administrators, or sharing with LawHand's service account may be off. LawHand falls back to the administrator's My Drive and reports the root as at risk. A Google Workspace super-administrator can usually create the Shared Drive and add the service account under **Document storage**.

## Re-run or skip setup

**Restart setup** on the **Complete** screen reopens the wizard at **Connect** while keeping the firm live. The existing root is kept (the Storage step shows **Folder exists**), and completing setup again records an audit entry without changing it. Re-entry also shows storage ownership, and points you to **Storage migration** if a root lives in a personal drive.

To move matters to a different provider, use [Storage migration](/admin?tab=integrations&integration=storage-migration) rather than re-running setup; it discovers and reconciles existing folders and requires your confirmation before cutting over. See [Move existing matters to another provider](/admin?tab=guide&chapter=storage-imports-and-readiness#move-existing-matters-to-another-provider).

Skipping setup marks the firm complete without any connection or storage. Use it only for evaluation firms: a skipped firm has no document storage until an administrator connects a provider and runs **Create missing matter folders** under **Document storage**.

## After setup: where things live

| Need | Where |
| --- | --- |
| Is the connection healthy? | [Integrations > Cloud](/admin?tab=integrations&integration=cloud), provider cards. See [Integrations](/admin?tab=guide&chapter=integrations). |
| Which provider holds documents? | Integrations > Cloud > **Document storage**. |
| Folders for matters created before storage existed | **Document storage** > **Create missing matter folders**. Safe to repeat. |
| Move matters to another provider | Integrations > **Advanced** > [Storage migration](/admin?tab=integrations&integration=storage-migration). |
| Import the team again | The provider card's **Sync now** (organization accounts only). |

## When your firm leaves

LawHand never deletes your cloud folders, when you leave or at any other time. Before any LawHand-side cleanup, inventory the root and matter folders from **Document storage** and ask [LawHand support](/admin?tab=support) for the handoff procedure.

## For LawHand support

These endpoints are listed so support conversations can refer to them; none exposes tokens or provider secrets, and none deletes provider content.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/admin/onboarding/status` | Step, connections, synced user counts, primary provider, saved roots, storage readiness, and root ownership. |
| `POST /api/admin/onboarding/step/{n}` | Save wizard progress (0–5). |
| `POST /api/admin/onboarding/storage` | Choose a provider and create or confirm its root; returns ready, failed, or repair needed. |
| `POST /api/admin/onboarding/complete` | Finish setup; refused until a root exists. |
| `POST /api/admin/onboarding/reenter` | Reopen setup without discarding the root. |
| `POST /api/admin/onboarding/skip` | Finish without connections. |

## Related chapters

- [Administrator overview](/admin?tab=guide&chapter=admin-overview)
- [Integrations](/admin?tab=guide&chapter=integrations)
- [Cloud provider support](/admin?tab=guide&chapter=cloud-provider-support)
