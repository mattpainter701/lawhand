---
slug: tenant-settings-and-branding
title: Tenant settings & branding
description: Set the firm's name, contact details, and branding, and manage alerts, feature flags, rate limits, and case-law retrieval for everyone.
order: 30
read_time: 10 min
icon: settings
---

# Tenant settings & branding

Firm-wide settings shape what every person and client sees. Change them in a communicated window when they affect navigation, billing, generated documents, notifications, or AI behaviour.

## Firm Profile

[Firm Profile](/admin?tab=firm) holds how the firm is named and presented. It is the first thing to set on a new firm.

![The Identity card of the Firm Profile tab with the Account name and Display name fields and the Clients will see preview](/guide-assets/admin-firm-profile.webp "Firm Profile: Identity")

1. **Account name** is the firm's name of record.
2. **Display name** optionally replaces it wherever clients see it.
3. **Clients will see** previews the name clients will actually see.

### Set the firm's identity

1. Correct the **Account name**. Sign-up derives it from the first account's email domain, so a firm that signed up from `painterlaw.com` starts out as "Painterlaw"; fix it here to the full legal name, such as "Painter Law Group, PLLC".
2. Leave **Display name** blank unless your letterhead name differs from the name of record. When set, clients see it instead.
3. Check **Clients will see**.

**Tenant domain** is the account's permanent identifier. It cannot be changed and is never shown to clients.

### Contact details and branding

1. Under **Contact details**, enter the **Phone**, **Email**, **Website**, and **Address** clients should use. A blank address falls back to the one captured at sign-up.
2. Under **Branding**, enter a **Logo URL**: a publicly reachable image, shown in the client portal header and on invoice and statement PDFs.
3. Enter **PDF footer text** if your documents need one, such as "Confidential — Attorney/Client Privileged Communication".
4. Select **Save firm profile**. "Firm profile saved." confirms it.

The name and details flow into client portal invitations, intake and engagement emails, invoices, trust statements, and templates that use firm profile fields. Invoice and statement PDFs use the name, logo, address, phone, email, website, and footer; amounts are shown in USD. If the logo cannot be fetched, the PDF is still produced with the rest of the firm's details.

Changes apply to future documents and portal pages. Documents already generated, and matter numbers already issued, keep the values they were created with. After a branding change, generate a representative document and check it.

## Settings

[Settings](/admin?tab=settings) holds firm-wide controls. Read each description and the current value before you change anything.

### Case-law retrieval

**Public case law search** includes CourtListener public opinions when the assistant retrieves sources. Turning it off makes the assistant answer from firm and matter sources only, and people see that public case law is off in their response settings.

### Alerts and budgets

1. Under **Alerts & Budgets**, enter a **Monthly spend alert threshold (USD)**, or leave it blank to turn off firm-wide spend alerts.
2. Choose **Alert at**, the percentage of the threshold that triggers an alert.
3. Enter **Alert recipients** as comma-separated addresses, such as a monitored billing group. Leave it blank to alert every administrator.
4. Turn on **Weekly usage digest** to email a weekly summary of token usage and costs to the recipients.
5. Select **Save alerts**.

Use a monitored group address rather than one person's mailbox. See [Subscription, usage & alerts](/admin?tab=guide&chapter=subscription-usage-alerts).

### Feature flags

**Feature Flags** turn platform features on or off for everyone at the firm:

| Flag | What it does |
| --- | --- |
| **Auto memory** | Builds per-user memory from conversations. |
| **PII detection** | Flags and suppresses personal information in outputs. |
| **Skill routing** | Sends questions to domain-specific legal skills automatically. |
| **Matter context** | Adds the active matter's context to chat and skills. |
| **Legal Work Board** | Offers the work board alongside the deadline list on Tasks. |

Feature flags are rollout tools, not permissions. Before turning one on, name its owner and audience, confirm any data or integration prerequisites, decide how you would roll it back, and test it with representative roles.

### Rate limits

**Requests / minute** and **Tokens / day** cap AI use across the firm. Leave them at **No limit** unless you need a hard ceiling; a limit that is too low interrupts people mid-task.

### Advanced: AI gateway alias

The **Advanced** section holds the **Standard alias override** for the AI gateway. Changing it affects every user. Leave it blank unless LawHand support asked you to set it.

The bottom of Settings shows the **Deployed version** and the release notes.

## Tenant

[Tenant](/admin?tab=tenant) is a read-only view of the organization record: **Tenant ID**, **Name**, **Domain**, **Billing Tier**, **Max Users**, **Max Documents**, when it was **Created**, and its **Status**. Check it before any bulk change or integration action to confirm you are working in the right firm, and quote the tenant ID when you contact support.

## Onboarding

[Onboarding](/onboarding) guides a new firm's setup. Returning to it later can show incomplete prerequisites, but do not repeat connection or completion steps without understanding their effect on the current configuration. See [Onboarding & storage setup](/admin?tab=guide&chapter=onboarding-and-storage-setup).

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "Account name cannot be blank." | The account name was cleared | Enter the firm's name of record. |
| The logo is missing from PDFs | The logo URL is not publicly reachable, or is not an image | Use a public HTTPS image URL; the PDF still renders without it. |
| Clients still see the old name | They are looking at a document generated before the change | Generate the document again; new documents use the new name. |
| Nobody received a spend alert | No threshold is set, or recipients are wrong | Check the threshold, **Alert at**, and **Alert recipients**. |

## Related chapters

- [Administrator overview](/admin?tab=guide&chapter=admin-overview)
- [Subscription, usage & alerts](/admin?tab=guide&chapter=subscription-usage-alerts)
- [Prompt management](/admin?tab=guide&chapter=prompt-management)
