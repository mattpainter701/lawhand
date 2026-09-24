---
slug: mcp-server-operations
title: MCP server operations
description: Let approved people connect outside assistants to their own workspace, issue and govern Research MCP keys, and respond when something looks wrong.
order: 120
read_time: 16 min
icon: network
---

# MCP server operations

MCP (Model Context Protocol) lets an outside AI assistant, such as Claude, ChatGPT, or Codex, use LawHand tools. [Integrations > MCP servers](/admin?tab=integrations&integration=mcp) is the home for both kinds of MCP access, under **Advanced** for administrators who hold `manage_integrations`:

| | **LawHand Platform MCP** (Workspace) | **LawHand Research MCP** |
| --- | --- | --- |
| What it reaches | The person's own workspace: clients, intakes, matters, tasks, documents, templates | Public legal authority only, never workspace matters |
| How it signs in | OAuth 2.1, as the person, after their consent | A product key (`lhrk_…`) or OAuth, per key |
| Who controls it | Firm switch, new-user default, and per-person access | Keys you issue, with budgets and allowed tools |
| What it can do | Read, and propose work for human review | Search and read authority |

The two are independent: turning off Workspace MCP does not revoke Research keys, and a Research key never grants workspace access.

## Workspace MCP: set up access

Three independent gates decide whether a person can connect an assistant. All three must be open, and the person must be active, licensed, and complete the consent step in their assistant.

1. **Turn it on for the firm.** Under **Tenant controls**, turn on **Enable Platform MCP for this tenant**. This is the master switch; turning it off revokes every active Workspace MCP connection.
2. **Choose the default for new people.** **Enable Platform MCP for new users** applies to people invited, created through sign-in, or synchronized from your directory later. It never changes existing people.
3. **Allow each existing person.** On [Users](/admin?tab=users), turn on the toggle in the **MCP access** column for each person whose work needs it. See [Control connected assistants](/admin?tab=guide&chapter=users-roles-and-licensing#control-connected-assistants).

**Manage existing users** takes you to the Users list. There, **Manage** on a person shows their connected assistants, when each was last used and expires, and lets you revoke one.

Turning off the firm switch or a person's access revokes their active connections. Turning it back on does not restore them; the person must reconnect and consent again.

**Privacy Mode** (the person's **Protect private details** setting) always blocks outside access to their workspace. You can see that it is blocking, but only the person can turn it off, from their profile.

## Workspace MCP: help someone connect

The **Connection and setup** section shows the endpoint and instructions for each assistant. The endpoint is:

```text
https://mcp.getlawhand.com/api/mcp/workspace
```

- **Codex CLI:**

  ```powershell
  codex mcp add lawhandWorkspace --url https://mcp.getlawhand.com/api/mcp/workspace
  codex mcp login lawhandWorkspace
  codex mcp list
  ```

- **Claude Code:**

  ```bash
  claude mcp add --transport http --scope user lawhand https://mcp.getlawhand.com/api/mcp/workspace
  ```

- **Claude Desktop:** **Settings** > **Connectors** > **Add custom connector**, with the same URL.
- **ChatGPT workspace apps:** a ChatGPT workspace administrator first allows custom MCP apps under **Workspace Settings** > **Permissions & Roles** > **Connected Data**. The person then turns on Developer mode under **Settings** > **Apps** > **Advanced Settings**, chooses **Apps** > **Create**, enters the endpoint, chooses OAuth, and scans the tools.

In every client, the person signs in with OAuth and checks the tool list shown. LawHand offers optional offline access with rotating refresh tokens so hosted clients stay connected without any extra capability.

> [!WARNING]
> Never put a Research key or any static bearer token in a Workspace MCP configuration. If an older connection shows only `find_matter`, remove it and connect again: LawHand never silently enlarges an existing grant.

## What Workspace tools can do

The catalog is review-first:

- **Reads:** `search_clients`, `get_client`, `search_intakes`, `get_intake`, `search_matters`, `find_matter`, `get_matter_context`, `search_tasks`, `search_firm_memory`, `get_task`, `list_matter_tasks`, `list_matter_recipients`, `list_matter_documents`, `get_matter_document_text`, `list_document_templates`, and `get_document_template_text`.
- **Proposals:** `propose_task`, `propose_client_email`, and `propose_matter_document`; `propose_document_from_template` fills an active Word or Markdown firm template into the same review.
- **Documents the assistant wrote:** `propose_matter_document_file` accepts a Word file. LawHand builds the reviewer's preview from those exact bytes, refuses macros, encryption, and embedded objects, and sends it through staff and then attorney review.
- **Evidence and correspondence:** `propose_matter_file` attaches screenshots and scanned exhibits (PNG, JPEG), PDFs, saved emails (`.eml`, `.msg`), CSV, TXT, ICS, and media files. LawHand checks the bytes match the file extension, so a renamed executable, an archive, or a macro-bearing Office file is refused. The file is attached as not portal-visible, waiting for a person to triage it.
- **Templates:** `propose_document_template` saves an **inactive draft** template that cannot be used until someone with template permissions publishes it in Template Studio. Fillable PDFs work best; flat or scanned PDFs are refused. A proposed replacement for a template in use is saved as a separate draft.

There are no tools to approve, publish a template, file, send, deliver, or execute anything. Proposals become Review work that a person must complete. Document and template text is treated as untrusted evidence, never as instructions.

## Research MCP: issue a key

Research MCP is a separate, public-authority-only product at:

```text
https://research.getlawhand.com/api/mcp
```

Hosted clients use the LawHand OAuth consent flow. For API clients, you issue product keys.

Before creating a key, write down its owner, the client application, the environment, the tools it needs, the expected volume, and who approves it. Use separate keys for development, testing, and production.

1. Under **Keys and usage**, select **Create key**.
2. In **Create Research product key**, enter a **Name** and **Purpose**, and choose the **Assigned staff member** who holds it.
3. Choose a **Duration / expiration date**.
4. Under **Allowed tools**, keep only the tools the use case needs. New keys allow every published tool unless you remove some.
5. Set a **Monthly budget (USD)**, a **Monthly call limit**, and a **Burst limit per minute**. The key stops at whichever limit comes first.
6. Select **Create key**. The secret is shown **once**: deliver it through your approved secret manager, never by email, chat, ticket, screenshot, or source control.

API clients send it as `Authorization: Bearer lhrk_…` (the older `X-MCP-API-Key` header still works). Each successful tool call costs $0.45; failed calls are shown but not billed.

## Research MCP: monitor, change, and revoke

The key list shows each key's masked identifier, assigned staff, purpose, creator, expiry, last use, allowed tools, this month's successful and failed calls, charges, and remaining budget.

- Open a key (**Manage Research product key**) to change who holds it, its tools, expiry, budget, call limit, or burst limit, then select **Save controls**. Changes apply immediately; extending an expired key restores it.
- **Revoke** a key immediately for suspected exposure, a departed owner, an abandoned application, or unauthorized tools. Revocation is permanent: issue a replacement rather than trying to reactivate it. Confirm the old key no longer works, and watch for attempted reuse.
- Deactivating the assigned person stops their keys, but a key is still a bearer credential: use OAuth when you need calls tied to an individual.

Investigate repeated failures before raising limits. A source's health shows whether it is available; it does not mean a returned authority is current, controlling, or correctly applied.

## If something looks wrong

If MCP output or activity suggests data from another firm, or an unauthorized external action:

1. stop the client;
2. turn off the person's MCP access or revoke the key;
3. keep the request IDs and times; and
4. follow your incident process and contact [LawHand support](/admin?tab=support).

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| A person's status says **Disabled by firm** | **Enable Platform MCP for this tenant** is off | Turn it on under **Tenant controls**. |
| A new hire cannot connect | **Enable Platform MCP for new users** was off when they joined | Turn on their access in the **MCP access** column. |
| **Paused by Privacy Mode** | The person turned on **Protect private details** | Only they can turn it off, from their profile. |
| A client lists only `find_matter` | The connection predates the current tools | Remove it and connect again. |
| A Research key stopped working | It expired, hit its budget or call limit, or was revoked | Check the key's usage and expiry; extend or replace it. |

## Related chapters

- [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing)
- [AI, search & MCP](/admin?tab=guide&chapter=ai-search-and-mcp)
- [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility)
