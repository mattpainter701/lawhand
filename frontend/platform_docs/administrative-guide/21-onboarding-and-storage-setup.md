---
slug: onboarding-and-storage-setup
title: Onboarding & storage setup
description: What the setup wizard does at each step, why document storage is confirmed before any matter exists, and how to re-run or repair setup.
order: 210
read_time: 9 min
icon: compass
---

# Onboarding & storage setup

The setup wizard runs once for a new firm, after the first administrator signs in. It connects the firm's cloud provider, confirms where matter documents will live, imports the team, and hands off to the Administration portal. Every step is persisted, so an administrator can close the browser and resume; nothing is created silently in the background.

The wizard is reachable at `/onboarding` for administrators. Users are redirected to it after sign-in until setup is complete or skipped.

## The six steps

| Step | Name | What happens | What must be true to continue |
| --- | --- | --- | --- |
| 1 | Welcome | Explains the setup. | — |
| 2 | Connect | Accept the tenant agreements, then connect Microsoft 365 or Google Workspace with **administrator consent**. | At least one provider connected and agreements accepted. |
| 3 | Storage | Choose the provider for matter documents and create the root folder. LawHand shows the folder it created and links to it. On Google Workspace it first creates an organisation-owned Shared Drive so the root survives staff turnover. | A root folder exists for the chosen provider. |
| 4 | Sync Users | Import the directory into LawHand. | — (personal accounts have no directory; invite users later instead). |
| 5 | Review | Shows imported user counts and confirms storage is set. | Storage confirmed. |
| 6 | Complete | Marks the firm live and links to the Administration portal. | — |

Behind each step the tenant record stores an `onboarding_step` number from 0 to 5. Connecting a provider advances the tenant to the Storage step automatically; a finished directory sync advances from Sync Users to Review, and never skips Storage.

## Why storage is its own step

The firm's connected cloud account is the matter-document system of record. Setup cannot complete until its root folder is confirmed; operational processing and configured reconciliation or fallback paths remain governed separately. Previously the root folder was created quietly when setup completed, so a firm never chose the provider, never saw the folder, and could finish setup with no working storage. Now:

- the administrator chooses **Google Drive** or **Microsoft OneDrive** from the providers actually connected;
- LawHand creates `lawhand-records` in that account and shows its name and link;
- the choice is saved as the firm's **primary provider** (the same setting shown under Administration → Integrations → Cloud → Document storage);
- setup cannot complete until a root folder exists.

SharePoint is chosen after setup: finish with OneDrive, then select the site and library under **Document storage**. The migration tooling (below) can rebind matters afterwards if needed.

## Who owns the root folder

The root should belong to the **organisation**, not to the administrator who happened to connect the account. If it does not, deactivating or losing that person breaks the firm's access to every matter document.

- **Google Workspace.** When an administrator connects, LawHand creates an organisation-owned Shared Drive (`LawHand Firm Records`) and adds LawHand's own service account as a member, then creates `lawhand-records` inside it. Nothing is configured in the customer's Google Cloud; the account is only asked to sign in. The drive survives the connecting admin leaving.
- **Microsoft.** The root belongs in a SharePoint site library rather than a personal OneDrive. Until an app-only identity is bound, access still uses the connecting administrator's delegated token; if that account is removed, reconnect another administrator from Integrations → Cloud.
- **Personal Google.** There is no organisation and no Shared Drive, so the root lives in the individual's own Drive. It is reported `at_risk`: the owner should share the root with a second account, and it is important to inventory the folders if the account changes (an export manifest is planned, below).

The onboarding status reports this as `root_ownership`: `durable` when every bound root is organisation-owned, `at_risk` when any root lives in one person's drive, and `unbound` when no root exists yet. LawHand never deletes or destructively renames a customer's cloud folders.

## What "Folder exists" means

When the Storage step shows **Folder exists** next to a provider, the tenant already has a root binding for it — from an earlier run, a re-entered setup, or an administrator repair. LawHand keeps that folder and never recreates or repoints it: folder IDs are the authority for every matter folder underneath. Choose **Continue** to keep it.

If a saved root is malformed (a provider entry without a folder ID), the step reports **repair needed** and refuses to rebind. Repair it under Administration → Integrations → Advanced → Storage migration, or ask support.

## Failures at the Storage step

A failure here is honest and retryable. The two common causes:

- **The connected account cannot create the folder.** The consent may have been granted by an account without Drive or OneDrive access, or a required scope was declined. Re-authorize from Administration → Integrations → Cloud and try again.
- **SharePoint chosen before a library is bound.** Choose OneDrive for now, or bind the site and library first.

An organisation-owned Shared Drive can also be blocked by Workspace policy: Shared Drive creation may be limited to certain administrators, or sharing with LawHand's service account may be disabled. LawHand then falls back to the connecting administrator's My Drive and reports `root_ownership.status = at_risk` rather than claiming durability. A Google Workspace super-administrator can usually create the Shared Drive and add the service account directly under **Document storage**.

A failed attempt records nothing: no half-created root, no primary provider change. **Try again** repeats the same request.

## Handoff when a tenant leaves

LawHand never deletes a customer's cloud folders, on churn or at any other time. An XLSX handoff manifest of roots and matter folders (provider, folder name, ID, path, URL, and owning identity) is planned so the folders can be located and kept after access is revoked; until it ships, inventory the folders from **Document storage** before LawHand-side cleanup. See [Cloud root ownership and tenant handoff](https://github.com/mattpainter701/lawhand/blob/main/docs/storage-root-ownership-and-handoff.md).

## Re-running setup

**Restart setup** on the Complete screen (or `POST /api/admin/onboarding/reenter`) reopens the wizard at Connect while keeping the firm live. The existing root is preserved and audited; the Storage step shows it as **Folder exists**. Completing setup again records an `onboarding_rerun` audit entry against the root and does not change it.

Re-entry also reports **storage ownership** on the Storage and Review steps. When a bound root lives in a personal drive it is flagged **at risk** with the provider named, and the administrator is pointed to **Storage migration** to move matters to an organisation-owned location. `POST /api/admin/onboarding/reenter` returns the same `root_ownership` summary so the wizard can show it without a second request.

Re-entry with a target provider starts a storage migration instead of a plain re-run. Use Administration → Integrations → Advanced → Storage migration for that flow; it discovers and reconciles existing folders before any cutover, and requires explicit confirmation.

## Skipping setup

**Skip setup** marks the firm complete without any connection or storage. Use it only for evaluation tenants. A skipped firm has no document storage until an administrator connects a provider and runs **Create missing matter folders** under Document storage.

## After setup: where things live

| Need | Where |
| --- | --- |
| Is the connection healthy? | Administration → Integrations → Cloud, provider cards (see [Integrations](/admin?tab=guide&chapter=integrations)). |
| Which provider holds documents? | Administration → Integrations → Cloud → Document storage. |
| Create folders for matters made before storage existed | Document storage → **Create missing matter folders**. Safe to repeat. |
| Move matters to another provider | Administration → Integrations → Advanced → Storage migration. |
| Import the team again | Provider card → **Sync now** (workspace tiers only). |

## Endpoints, for support reference

| Endpoint | Purpose |
| --- | --- |
| `GET /api/admin/onboarding/status` | Step, connections, synced user counts, primary provider, saved root bindings, `storage_ready`, and `root_ownership` (durable / at_risk / unbound). |
| `POST /api/admin/onboarding/step/{n}` | Persist wizard progress (0–5). |
| `POST /api/admin/onboarding/storage` | Choose a provider and create or confirm its root. Returns `ready`, `failed` or `repair_needed`. |
| `POST /api/admin/onboarding/complete` | Finish setup. Rejected until a root exists. |
| `POST /api/admin/onboarding/reenter` | Reopen setup without discarding the root. |
| `POST /api/admin/onboarding/skip` | Finish without connections. |

None of these expose tokens or provider secrets, and none delete provider content.
