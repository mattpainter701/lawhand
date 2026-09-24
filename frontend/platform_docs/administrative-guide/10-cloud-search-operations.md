---
slug: cloud-search-operations
title: Cloud Search operations
description: Check Cloud Search's connection, test what it can find, synchronize metadata, and clear its cache safely.
order: 100
read_time: 9 min
icon: search
---

# Cloud Search operations

Cloud Search lets people and the assistant find authorized Gmail, Outlook, Google Drive, OneDrive, and SharePoint content. It uses the connected provider's permissions; it does not create a separate permission boundary, so broad access at the provider becomes broad search unless you bind it narrowly.

Open [Integrations > Cloud Search](/admin?tab=integrations&integration=cloud-search). It has four tabs: **Status**, **Test Search**, **Sync**, and **Metadata**.

## Before you start

1. Connect the provider in [Integrations > Cloud](/admin?tab=integrations&integration=cloud) and choose the storage binding. See [Integrations](/admin?tab=guide&chapter=integrations).
2. Agree the source boundary (which sites, drives, and mailboxes) with the information owner.
3. Pick a distinctive, non-sensitive document you can search for as a known answer.

## Check the status

The **Status** tab shows, for **Microsoft** and **Google**, whether each is **Connected**, the granted **Scopes**, and when the token expires (**Token expires**). If it says "No admin token. Connect in Settings → Integrations.", connect the provider first.

## Test what search can find

1. Open **Test Search**.
2. Under **Search sources**, tick the sources to test: **Gmail**, **Outlook**, **Google Drive**, **OneDrive**, or **SharePoint**. At least one is required.
3. Type a query, such as "Find the latest renewal discussion with Acme and the attached SOW", and set **Max hits**.
4. Select **Run Search** and open **Search details** to see where each result came from.

For PDF and Word files, ask about a fact inside the file, not just its title. Supported downloads are read up to 10 MiB with format-aware text extraction; unsupported, oversized, or textless files provide only their metadata, so a listed result does not prove its contents were read. Email uses decoded headers and body text; attachments and attached messages are not part of the body excerpt, so check them separately.

Test both sides:

- an authorized person finds the expected document;
- an unauthorized person cannot;
- similarly named documents keep their correct source; and
- deleted or moved content behaves as your synchronization and retention settings expect.

When Cloud Search plans a query for the assistant, it uses the person's chosen chat route and that route's policy for confidential context, so a Premium chat plans with Premium. Empty queries, and plans without meaningful keywords, are rejected rather than widened into a mailbox-wide search.

## Synchronize metadata

**Sync** keeps LawHand's lightweight index of titles, paths, owners, and dates current.

1. Check the **Metadata** tab first and note the current counts.
2. On **Sync**, select **Sync Metadata Now**. **Sync Results** reports what changed.
3. Check for errors and spot-check a few results.

A sync adds load at the provider and churn in search, so run it for a reason (such as a new binding) rather than routinely.

## Browse indexed metadata

The **Metadata** tab lists what is indexed, filterable by provider and type (**Files**, **Emails**, **Folders**) and searchable by title, with each item's size and modified date. Use it to diagnose stale paths, unexpected sources, missing titles, and gaps. It is an operational signal, not a replacement for reviewing permissions at the source.

## Clear the cache

On **Sync**, **Invalidate Cache** clears cached search results. Use it only for a specific reason, such as stale results after a permission or binding change. Expect slower searches for a while afterwards, and test again.

> [!CAUTION]
> A result from another firm, another site, or a source someone is not authorized to see is a security incident. Stop, keep the query, person, time, result details, and request ID, restrict the affected access, and follow your incident process.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "No admin token" on Status | The provider's firm-wide connection is missing | Connect it in Integrations > Cloud. |
| A known document is not found | It is outside the binding, unsupported, over 10 MiB, or not yet synchronized | Check the binding and the file, then **Sync Metadata Now**. |
| Results show stale titles or paths | The metadata index is behind | Run **Sync Metadata Now**; clear the cache only if results stay stale. |
| "Select at least one source to run a search." | No source is ticked | Tick at least one source. |

## Related chapters

- [Integrations](/admin?tab=guide&chapter=integrations)
- [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility)
- [File Share operations](/admin?tab=guide&chapter=file-share-operations)
