---
slug: firm-memory-source-policy
title: Firm Memory source policy
description: Decide who can search historic firm files, bind each matter to the narrowest folder, and read search coverage honestly.
order: 170
read_time: 9 min
icon: search
---

# Firm Memory source policy

[Firm Memory](/firm-memory) searches authorized firm knowledge across your configured sources, such as on-premises file shares bound to matters. Choosing **All** sources never bypasses permissions: it means every source the signed-in person may search. A matter is an optional filter that narrows the search.

The generalized, query-first search is off by default. Existing matter-scoped file-share search keeps working either way. See [The Firm Memory search page](/admin?tab=guide&chapter=file-share-operations#the-firm-memory-search-page).

## Decide before enabling a source

For each source, decide:

- who receives the `search_firm_memory` capability ([Roles](/admin?tab=roles));
- whether the source is firm-wide, bound to matters, explicitly granted, or governed by a native authorization provider;
- which collections it belongs to;
- whether any linked matters are assigned-only or restricted behind an ethical wall; and
- whether its coverage is actually ready, or still partial, indexing, stale, offline, or unsupported.

Unknown authorization is always denied. A missing native provider is never treated as a temporary firm-wide allow. Restricted matters require explicit grants, and an explicit deny always overrides an allow.

## The matter binding is the boundary

LawHand reads a file share through one service account, and firm sign-ins do not map one-to-one onto Windows accounts, so file permissions cannot decide who sees a document. The matter does: who is authorized on it, and which folder on the share is bound to it.

Two consequences follow:

- **Bind every share you want searched.** An unbound share is reported as unsupported and never searched, whatever its source policy says.
- **The folder binding is a security control.** Anyone authorized on a matter can find anything under its bound folder. Bind the narrowest folder that holds the matter's files, and keep material that must not follow the matter outside it.

### Bind a matter's folder

1. Open the matter, select **Matter settings**, then **File Shares**.
2. Choose the **Share** (**Select share…**) and enter the **Folder Path**, such as `/Clients/Harlow/2026CV001482`.
3. Give it a **Display Label**, and tick **Auto-scan for new documents** if new files should be indexed automatically.
4. Select **Bind Share**.
5. As someone authorized on the matter, search for a known document in that folder; as someone who is not, confirm it is not found.

Every result is checked again against the bound folders of the person's authorized matters before it leaves the server, so a misconfigured agent cannot widen what a search returns.

## What a search without a matter covers

Leaving the matter filter empty does not search everything. A matter-bound source is searched across the matters that person is already authorized on, under the same rules as a chosen matter, and nothing else. Someone with no authorized matter on a share sees that share reported as not covered, rather than silently missing.

On-premises results come from the firm's own search node, with document text, passages, and page numbers. If that node is unreachable, the search falls back to the file-name and preview index kept in LawHand and says so; that fallback is never reported as complete coverage.

If your firm uses per-user native authorization, a firm-wide search also needs agent version 0.17.0 or newer. An older agent cannot tie a multi-matter request to its signed authorization, so its shares are reported as not covered rather than searched with a weaker check. Firms on the service-account model are not affected.

## Coverage is part of the answer

Search coverage is part of every result. When any selected source is partial, stale, offline, indexing, or unsupported, people are told the answer covers only the available sources, in one sentence saying why. "No matches" appears only when coverage is complete. Teach people to read that sentence before relying on a "not found".

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| A share is reported as unsupported | No matter is bound to it | Bind the relevant matters' folders. |
| Someone sees "not covered" for a share | They are not authorized on any matter bound to it | Add them to the matter if appropriate. |
| Results come only from file names | The on-premises search node is unreachable | Check the agent and search node; see [File Share operations](/admin?tab=guide&chapter=file-share-operations). |
| A person cannot open Firm Memory | They lack `search_firm_memory` | Add the capability to one of their roles. |

## Related chapters

- [File Share operations](/admin?tab=guide&chapter=file-share-operations)
- [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing)
- [Matters & documents](/guide/matters-and-documents#search-historic-firm-files)
