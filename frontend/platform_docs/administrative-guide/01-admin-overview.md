---
slug: admin-overview
title: Administrator overview
description: Operate the tenant deliberately, separate duties, and know where configuration lives.
order: 10
read_time: 5 min
icon: layout
---

# Administrator overview

The Administration portal controls tenant-wide access, commercial settings, integrations, and AI infrastructure. Changes here can affect every user, so use named administrator accounts and document consequential decisions.

## Administrative map

- [Admin Guide](/admin?tab=guide) — search operating guidance and jump directly to each control.
- [Users](/admin?tab=users) — invite, activate, deactivate, and update people.
- [Roles](/admin?tab=roles) — manage permission bundles and assignments.
- [Licensing](/admin?tab=licensing) — allocate seats and premium AI access.
- [Subscription](/admin?tab=billing) and [Usage](/admin?tab=usage) — review commercial status and consumption.
- [Firm Profile](/admin?tab=firm) — the firm's name, contact details, and branding, as clients see them.
- [Tenant](/admin?tab=tenant) and [Settings](/admin?tab=settings) — review the organization record, and maintain defaults, alerts, and feature controls.
- [Integrations](/admin?tab=integrations) — authorize cloud services and review their health; Cloud Search, file shares, collaboration, communications, and accounting connections are firm sections, while MCP servers, storage migration, data import and provider readiness sit under **Advanced** for administrators with the `manage_integrations` capability.
- [Prompts](/admin?tab=prompts) governs AI instructions and is listed under **Advanced** in the portal navigation; it requires the `admin_settings` capability.
- [Onboarding](/onboarding) — the setup wizard for a new firm; see [Onboarding & storage setup](/guide/onboarding-and-storage-setup) to re-run or repair it.

The portal navigation groups tabs as **People** (Users, Roles), **Firm** (Integrations, Firm Profile, Settings), **Billing** (Subscription, Licensing, Usage) and **Support** (Admin Guide, Support, Tenant, Prompts). Tab links such as `/admin?tab=users` are unchanged.

Your plan may intentionally hide features that do not apply to the tenant. Accountant access is limited to the finance-oriented administrative tabs.

## A safe change pattern

1. Define the operational reason and affected users.
2. Confirm that you are in the correct tenant.
3. Record the current setting when rollback may be necessary.
4. Make the smallest change that achieves the goal.
5. Test with a non-administrator account when user visibility is involved.
6. Record who approved the change and when it was verified.

## Keep sensitive operations elsewhere

This guide is delivered with the web application. It must not contain secrets, private keys, recovery codes, customer-specific configuration, infrastructure addresses, exploit details, or incident response procedures. Store privileged operational runbooks in your approved restricted system.

## Review cadence

At least periodically, review active users, administrator assignments, licensed seats, connected services, usage anomalies, feature settings, and failed integration health checks. Also review immediately after staff departures, vendor changes, suspected compromise, or major plan changes.
