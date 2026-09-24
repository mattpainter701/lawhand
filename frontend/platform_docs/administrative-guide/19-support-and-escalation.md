---
slug: support-and-escalation
title: Support and escalation
description: Try the guides first, then file a classified support request with the right severity and no secrets, and track it to resolution.
order: 190
read_time: 8 min
icon: lifebuoy
---

# Support and escalation

Most questions have an answer in these guides. When they do not, [Support](/admin?tab=support) files a request with LawHand that is classified, recorded, and tied to a published acknowledgement objective. Email reaches the same queue, but a request filed here records the objective and the policy version in writing, so there is never doubt later about when it was picked up or which policy applied.

## Before you file

1. Use the **Guide** button on the screen that is causing trouble; it opens the matching chapter.
2. Search the [Admin Guide](/admin?tab=guide) and the [User guide](/guide/getting-started) for the error message or feature name.
3. Check the relevant settings page: for connections, the card's health on [Integrations](/admin?tab=integrations); for a person, their row on [Users](/admin?tab=users).
4. Note the version from [Settings](/admin?tab=settings) (**Deployed version**) and the tenant ID from [Tenant](/admin?tab=tenant).

## File a request

![The Support tab with the Severity and Channel fields, the severity's definition and acknowledgement objective, the Subject and Summary fields, the File request button, and the firm's requests with their status and acknowledgement due times](/guide-assets/admin-support.webp "Administration: Support")

1. **Severity** sets the acknowledgement objective and the first owner. The definition for the level you choose appears below it.
2. **Subject** names the problem in one line.
3. **File request** records the request.
4. **Your firm's requests** tracks every request and its status.

Step by step:

1. Open [Support](/admin?tab=support).
2. Choose the **Severity** (see below) and the **Channel** you want replies on: workspace, email, or phone.
3. Enter a **Subject**, such as "Portal invitations not arriving for one client".
4. In **Summary**, describe what you expected, what happened, roughly when (with your time zone), how many people are affected, and whether there is a workaround.
5. Select **File request**. The confirmation shows the acknowledgement objective and when acknowledgement is due.

## Choose the severity honestly

| Severity | Use it for | Acknowledgement objective |
| --- | --- | --- |
| **S1** | A confirmed or credibly suspected confidentiality breach, a destructive data-integrity event, or production-wide unavailability with no safe workaround | 60 minutes |
| **S2** | Material degradation, or a blocked critical workflow affecting several people with no reasonable workaround | 240 minutes |
| **S3** | A non-critical defect with a workaround, an isolated integration problem, or a question needing investigation | 480 minutes |
| **S4** | A how-to question, a cosmetic issue, or non-urgent feedback | 960 minutes |

The tab always shows the current definitions and objectives; if they differ from this table, the tab and the public policy at `/support` are authoritative.

Overstating severity does not make a request move faster; it pulls the wrong people onto it and delays requests that genuinely need them. Understating a confidentiality or data-integrity concern is the more serious mistake: if you are unsure whether something is S1, file it as S1 and say why.

## What an acknowledgement objective means

It is the time within which LawHand aims to pick up and own the request. It is not a resolution time, and it is not a service-level agreement, warranty, or service-credit commitment unless your signed terms say so.

Objectives run within standard coverage hours, Monday to Friday, 08:00–17:00 America/Chicago. A request filed outside them enters the next covered period, except S1, which uses the emergency channel named in your order form.

## Keep secrets and client content out

Support records are stored without secrets or unnecessary client content. A request that looks like it contains a credential is rejected with an explanation rather than stored.

Do not paste passwords, API keys, tokens, authorization codes, privileged or confidential client material, or full document contents. An identifier, a time, and a description are enough to start. Use redacted screenshots when they help.

## After filing

The request appears under **Your firm's requests** with its **Severity**, **Status**, **Acknowledgement due**, and when it was **Filed**. Its status moves through acknowledged, mitigated, and resolved; each change is recorded rather than edited in place.

When an issue affects the shared service rather than only your firm, it may also appear as a sanitized public incident. Public updates never carry firm-specific detail, so keep tracking your own request here.

## Escalate inside your firm

Some problems are yours to handle before or alongside a support request:

- **Suspected unauthorized access to an account:** follow [If you suspect unauthorized access](/guide/account-safety-and-support#if-you-suspect-unauthorized-access), and deactivate the account if needed.
- **An outside assistant misbehaving:** turn off the person's MCP access or revoke the key. See [MCP server operations](/admin?tab=guide&chapter=mcp-server-operations#if-something-looks-wrong).
- **Search showing content someone should not see:** pause the source. See [Cloud Search operations](/admin?tab=guide&chapter=cloud-search-operations).

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "The support request could not be filed." | A brief connection problem, or the text looked like a credential | Remove anything secret-looking and try again. |
| The request seems stuck | It is outside coverage hours, or waiting on information from you | Check its status; reply on the channel you chose. |

## Related chapters

- [Administrator overview](/admin?tab=guide&chapter=admin-overview)
- [Billing, usage & governance](/admin?tab=guide&chapter=billing-usage-and-governance)
- [Account safety & help](/guide/account-safety-and-support)
