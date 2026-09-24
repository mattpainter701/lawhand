---
slug: file-share-operations
title: File Share operations
description: Install a file-share agent, store share credentials, add and scan shares, and diagnose on-premises search safely.
order: 110
read_time: 14 min
icon: network
---

# File Share operations

[Integrations > File shares](/admin?tab=integrations&integration=file-shares) connects network file shares that stay on your premises, such as large, long-lived document stores that are not moving to the cloud. A small agent on your network reads them, so their contents can be searched and brought into matter context without being copied wholesale. Only file details and a short snippet are synchronized on a schedule; full text is fetched on request and recorded in the access log.

The section has five tabs: **Status**, **Agents**, **Credentials**, **Shares**, and **Activity**. Set them up in that order.

## 1. Install and register an agent

The agent runs on a machine that can already reach the share. It needs no inbound firewall rule, only outbound HTTPS.

1. Open the **Agents** tab and select **Generate Pairing Code**.
2. Under **Install the agent**, copy the command for the host with **Copy command**. The pairing code is already filled in:
   - **Windows**: one PowerShell block installs or upgrades the auto-starting service, then registers it as a separate step.
   - **Linux**: the package installs a systemd service.
3. Run the command on the host as an administrator.
4. Back on **Agents**, confirm the new agent appears with its **Hostname**, **Version**, and a recent **Last Heartbeat**.

Check that the agent belongs to the intended environment and firm before assigning shares to it. **Pause** stops an agent temporarily; **Revoke** permanently removes a decommissioned host's access. **Update** installs a newer agent version; the service restarts briefly and its shares resume automatically. On Windows, **Copy log command** gives you the command that shows the agent log.

## 2. Store share credentials

The **Credentials** tab holds the identities agents use to reach shares. Each credential is encrypted with your firm's key and delivered only to your paired agents; the password is never shown again.

1. Select **Add a new credential** (**New credential**).
2. Enter a **Credential name**, such as "svc-lawhand (CORP)". Never put the password in the name.
3. Choose the **Authentication**:
   - **Username and password (NTLM)** for a dedicated service account, with an optional **Domain** (blank for an account local to the file server);
   - **Kerberos (agent host ticket)** where the agent host holds a ticket, so no secret is stored; or
   - **Guest / anonymous** only for shares that are already open.
4. Optionally restrict the credential to one agent when the secret should only ever reach one office or server; otherwise leave **Any agent in this tenant**.
5. Select **Save credential**.

Give the service account only the read permissions the workflow needs. To rotate a password, edit the credential and enter the new one (leave it blank to keep the stored password); agents pick it up on their next check-in. Deleting a credential leaves its shares running under the agent's own identity, so check those shares afterwards.

## 3. Add a share

1. On **Shares**, select **Add share**.
2. Enter the **Share path**, a UNC path such as `\\FS01\Legal\Clients`, scoped to the narrowest approved folder.
3. Choose the **Agent** that can reach it, and a recognizable **Display name**, such as "Legal Documents".
4. Under **Credential**, choose **Use a stored credential** and select it, or **Use the agent's own identity (machine or service account)**.
5. Under **Scan scope**, set the **File types** (blank uses the default legal document set), **Exclude patterns** such as `~$*, *\Backups\*`, the **Maximum folder depth**, and the **Scan schedule (cron)**; the default is every six hours.
6. Select **Add share**, then **Test** on its row right away.

**Test** asks the agent to connect with the configured credential and reports which identity it used and whether it could list the folder, so a wrong password or missing permission shows up at once rather than as an empty index hours later.

Avoid drive roots, broad departmental shares, home directories, backup targets, and paths that hold unrelated clients.

Use **Edit** to correct the path or move the share to another agent. Changing either clears the previous scan result and removes the old file details from search until the new location is scanned, so stale matter context cannot survive a move. **Delete** removes the share and its indexed entries.

## 4. Scan and test search

1. Pick an approved window and select **Scan now** on the share, rather than waiting for the schedule.
2. Note the starting file count and watch the row: it shows the **Last Scan**, its status, the **Files** count, and the error text if a scan fails.
3. When the scan finishes, search for a known allowed document and confirm a known excluded location returns nothing.

Search over shares requires a matter binding: each matter's bound folder decides who can find what, because one service account reads the whole share. Bind the narrowest folder that holds each matter's files. See [Firm Memory source policy](/admin?tab=guide&chapter=firm-memory-source-policy).

Results are short ranked passages with page hints and the file's UNC path; LawHand re-checks the firm, matter, share, folder, and file before showing a path, and never turns it into a browser file link.

File permissions change after indexing. Decide how rescans, deletions, renamed folders, and permission updates are handled so search never keeps content beyond its intended availability.

### Pilot and scale

Treat early indexing as a representative sample, not proof that a multi-terabyte archive is ready. Before relying on a large share, measure text-extraction coverage, whether the right page is found, restart behaviour, load on the file server, and authorization failures. OCR for scans, robust conversion of older Office formats, per-file Windows permission snapshots, and a dedicated large-scale index are separate readiness steps.

### The Firm Memory search page

The query-first [Firm Memory](/firm-memory) page is off by default. It appears only when your firm has both the search entitlement and the generalized-search rollout turned on; otherwise the page asks for a matter first, as before. Turning it on does not change who may see what: every search is still checked against the person's matters and each source's policy, and anything unknown is denied. Do not assume the rollout is on just because people hold the `search_firm_memory` capability.

## Diagnose problems

Start with **Status**. It counts **Agents**, **Shares** (and how many use the agent's own identity), **Indexed files**, and **Shares needing attention**, and shows whether retrieval is enabled. **Retrieval disabled** stops indexed share results from reaching search and matter context, but does not erase the inventory.

**Activity** is the firm's operational timeline: agent registrations and heartbeats, updates, share changes, scans and tests, credential verification and delivery, and audited full-document access. It never includes passwords, keys, or document contents.

- **An agent is offline.** Check its registered identity, the network path, the service, and its last heartbeat through your restricted operations procedure.
- **A share stopped indexing.** Read the error on the share row, then run **Test** to separate a credential problem from a path or permission problem.
- **Test passes but the scan fails.** The file server accepted the identity, but the later sync was rejected. If the error mentions HTTP 422, the credentials work and the agent or server needs a compatible update.
- **A file fails to index.** Keep its relative path and error category, without copying sensitive contents into support notes.

Disable or remove a share when its owner, path, firm, or data classification changes, and confirm what indexed data remains under your retention policy.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "Register an agent first — see the Agents tab." | No agent is registered | Install and register an agent. |
| **Test** reports access denied | The credential is wrong or lacks read permission | Fix the credential or the service account's permission, then **Test** again. |
| "The agent has not responded yet." | The agent is offline or busy | Check the host and service; try again. |
| Search finds nothing on a scanned share | The matter's folder is not bound, or retrieval is disabled | Check the matter binding and the **Status** retrieval badge. |

## Related chapters

- [Firm Memory source policy](/admin?tab=guide&chapter=firm-memory-source-policy)
- [AI, search & MCP](/admin?tab=guide&chapter=ai-search-and-mcp)
- [Support and escalation](/admin?tab=guide&chapter=support-and-escalation)
