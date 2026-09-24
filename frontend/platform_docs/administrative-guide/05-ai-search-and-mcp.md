---
slug: ai-search-and-mcp
title: AI, search & MCP
description: Decide which AI models, sources, search boundaries, and outside assistants your firm uses, and where each is controlled.
order: 50
read_time: 7 min
icon: sparkles
---

# AI, search & MCP

The quality and safety of AI work depend on four things together: who is asking, which sources the assistant may use, which tools it may call, and who reviews the result. Configure them as one system rather than tuning a prompt in isolation.

## Where each control lives

| Decision | Where | Chapter |
| --- | --- | --- |
| Who gets premium models | [Licensing](/admin?tab=licensing) > **Premium AI** | [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing) |
| Whether public case law is searched | [Settings](/admin?tab=settings) > **Public case law search** | [Tenant settings & branding](/admin?tab=guide&chapter=tenant-settings-and-branding) |
| Memory, PII detection, skill routing, matter context | [Settings](/admin?tab=settings) > **Feature Flags** | [Tenant settings & branding](/admin?tab=guide&chapter=tenant-settings-and-branding) |
| Instructions the assistant follows | [Prompts](/admin?tab=prompts) | [Prompt management](/admin?tab=guide&chapter=prompt-management) |
| Which mail and cloud files are searchable | [Cloud Search](/admin?tab=integrations&integration=cloud-search) | [Cloud Search operations](/admin?tab=guide&chapter=cloud-search-operations) |
| Which on-premises shares are searchable | [File shares](/admin?tab=integrations&integration=file-shares) | [File Share operations](/admin?tab=guide&chapter=file-share-operations) |
| Who may search historic firm files, and which folders feed Firm Memory | The `search_firm_memory` capability in [Roles](/admin?tab=roles) and each matter's file-share folder binding | [Firm Memory source policy](/admin?tab=guide&chapter=firm-memory-source-policy) |
| Outside assistants and product keys | [MCP servers](/admin?tab=integrations&integration=mcp) and the **MCP access** column in [Users](/admin?tab=users) | [MCP server operations](/admin?tab=guide&chapter=mcp-server-operations) |
| Spend and rate limits | [Settings](/admin?tab=settings) > **Alerts & Budgets** and **Rate limits** | [Subscription, usage & alerts](/admin?tab=guide&chapter=subscription-usage-alerts) |

## Sources: keep search boundaries narrow

Search can only be as safe as the sources it reaches.

1. Connect only approved accounts, and bind Cloud Search to the approved sites, drives, and mailboxes.
2. Add file shares by specific path, not whole servers, and only the file types the firm needs.
3. After any binding or permission change, run a narrow test with accounts that represent real roles.

Search results must respect both the provider's permissions and LawHand's. An unexpected result from a site or matter someone should not see is a stop-work issue: pause the source and investigate before anyone continues.

## Two kinds of MCP access

LawHand offers two separate MCP surfaces. Keep them distinct, because they authenticate differently and reach different data.

- **Product keys (Research MCP).** A named system connects with a scoped key, an allowlist of tools, and bounded usage. Grant only the tools the use case needs, review activity and errors, and rotate or revoke the key when its owner, scope, or environment changes.
- **Workspace MCP.** A person connects an outside assistant, such as Claude or ChatGPT, to their own workspace after an explicit consent step. There is no shared key: the assistant acts as that person, within their permissions, for the scopes they approved. You decide who may do this in the **MCP access** column of [Users](/admin?tab=users). The firm-wide switch and the default for new users are under **MCP servers** > **Tenant controls**.

MCP access never authorizes an action by itself. Anything destructive, external, or high-impact still goes through the same approvals as the underlying task: the assistant's proposals wait for a person to approve them.

## Premium AI

Assign **Premium AI** in [Licensing](/admin?tab=licensing) to the people whose work needs the more capable models, and watch its consumption in [Usage](/admin?tab=usage). High usage is often legitimate; look at the context, such as a large document review, before treating it as misuse.

## Review AI output as a firm

Whatever you configure, the rules for people stay the same: every answer shows its sources, and nothing the assistant proposes is sent, filed, or saved until a person approves it. Make sure staff know the [Assistant chapter](/guide/assistant-and-add-ons) of the user guide, especially how to read cited sources and review tags.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| The assistant never cites public case law | **Public case law search** is off | Turn it on in Settings if your firm allows it. |
| Search returns a file from a site that should be excluded | A binding or provider permission is broader than intended | Pause the source, narrow the binding, and retest. |
| A person cannot connect an outside assistant | MCP access is off for them, off for the firm, or paused by Privacy Mode | Check their status in the **MCP access** column. |
| Premium responses are unavailable to someone | They have no **Premium AI** license | Assign it in Licensing. |

## Related chapters

- [MCP server operations](/admin?tab=guide&chapter=mcp-server-operations)
- [Prompt management](/admin?tab=guide&chapter=prompt-management)
- [Firm Memory source policy](/admin?tab=guide&chapter=firm-memory-source-policy)
