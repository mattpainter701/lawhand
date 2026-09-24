---
slug: admin-overview
title: Administrator overview
description: Find your way around Administration, set up a new firm in the right order, and change tenant settings safely.
order: 10
read_time: 8 min
icon: layout
---

# Administrator overview

**Administration** controls everything that affects the whole firm: who can sign in and what they can do, the firm's profile and settings, connected services, billing, and AI behaviour. A change here can affect every user, so use a named administrator account and record why you made consequential changes.

## Open Administration

Select **Administration** in the navigation (under **Administration**), or go to [/admin](/admin?tab=users). Administrators see every tab. Accountants see only the finance tabs: **Integrations**, **Subscription**, **Licensing**, and **Usage**.

The tabs are grouped by what you are trying to do:

| Group | Tabs | Use it to |
| --- | --- | --- |
| **People** | [Users](/admin?tab=users), [Roles](/admin?tab=roles) | Invite, activate, and deactivate people; manage roles and permissions. |
| **Firm** | [Integrations](/admin?tab=integrations), [Firm Profile](/admin?tab=firm), [Settings](/admin?tab=settings) | Connect cloud services; set the firm's name, contact details, and branding; set defaults and feature controls. |
| **Billing** | [Subscription](/admin?tab=billing), [Licensing](/admin?tab=licensing), [Usage](/admin?tab=usage) | Review the plan, assign seats, and watch AI usage and spend. |
| **Support** | [Admin Guide](/admin?tab=guide), [Support](/admin?tab=support), [Tenant](/admin?tab=tenant), [Prompts](/admin?tab=prompts) | Read this guide, contact LawHand support, check the organization record, and manage AI instructions. |

**Prompts** is marked **ADV** because it changes AI behaviour for everyone; it appears only for administrators with the `admin_settings` capability. Within **Integrations**, MCP servers, storage migration, data import, and provider readiness sit under **Advanced** for administrators with the `manage_integrations` capability. Select **Hide tabs** to collapse the tab bar.

A firm on the intake-only plan sees a shorter list, and your plan may hide features that do not apply to your firm.

## Use this guide from anywhere

- The **Guide** button in the top bar opens the chapter for the screen you are on. On an Administration tab, it opens this guide at that tab's chapter.
- In the **Admin Guide** tab, **Search this guide** finds any chapter by its text.
- Most chapters end with **Open in LawHand** buttons that take you straight to the screens they describe, and **Still stuck?** points to [Support and escalation](/admin?tab=guide&chapter=support-and-escalation).

## Set up a new firm

Work through these steps in order the first time; each links to its chapter.

1. **Run the setup wizard.** [Onboarding](/onboarding) connects the firm's document storage and records the basics. See [Onboarding & storage setup](/admin?tab=guide&chapter=onboarding-and-storage-setup).
2. **Complete the firm profile.** Name, address, contact details, and logo appear on invoices, emails, and the client portal. See [Tenant settings & branding](/admin?tab=guide&chapter=tenant-settings-and-branding).
3. **Invite your team and assign roles.** See [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing).
4. **Assign licenses.** Give each person the right seat and premium AI access in **Licensing**.
5. **Connect services.** Microsoft 365 or Google Workspace, then the optional services your firm uses. See [Integrations](/admin?tab=guide&chapter=integrations).
6. **Turn on firm email intake** if you want staff to forward email into LawHand. See [Firm email intake](/admin?tab=guide&chapter=email-intake).
7. **Review settings and alerts.** Set usage alerts and budgets. See [Subscription, usage & alerts](/admin?tab=guide&chapter=subscription-usage-alerts).
8. **Test as a regular user.** Sign in with a non-administrator test account and check what a typical person sees.

## A safe change pattern

1. Write down why the change is needed and who it affects.
2. Confirm you are in the correct firm. The **Tenant** tab shows the organization record.
3. Record the current setting when you may need to roll back.
4. Make the smallest change that achieves the goal.
5. When the change affects what users see, test with a non-administrator account.
6. Record who approved the change and when you verified it.

> [!WARNING]
> Never paste secrets, private keys, recovery codes, infrastructure addresses, or incident-response procedures into LawHand notes, prompts, or this guide. Keep privileged runbooks in your firm's approved restricted system.

## Review cadence

Review these regularly, and immediately after a staff departure, a vendor change, a suspected compromise, or a plan change:

- active users, pending invitations, and administrator assignments;
- licensed seats against actual users;
- connected services and any failed health checks;
- usage anomalies and budget alerts; and
- feature settings and AI instructions.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| **Administration** is not in the navigation | Your role is not administrator or accountant | Ask an existing administrator to assign the role. |
| A tab mentioned in this guide is missing | Your role, capability, or plan does not include it | Check your roles; **Prompts** needs `admin_settings`. |
| A setting change did not reach users | The browser has an older copy of the settings | Ask the user to reload; check again as a test user. |

## Related chapters

- [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing)
- [Integrations](/admin?tab=guide&chapter=integrations)
- [Support and escalation](/admin?tab=guide&chapter=support-and-escalation)
