---
slug: billing-usage-and-governance
title: Billing, usage & governance
description: Investigate usage anomalies, keep evidence of consequential changes, and run a periodic review of access, licenses, connections, and spend.
order: 60
read_time: 6 min
icon: shield
---

# Billing, usage & governance

Commercial controls and operational governance meet in Administration. Review them together: a cost spike can mean a workflow change, a configuration error, a compromised credential, or simply legitimate growth. For the screens themselves, see [Subscription, usage & alerts](/admin?tab=guide&chapter=subscription-usage-alerts).

## When usage looks wrong

1. Identify the affected person, tool, and period on [Usage](/admin?tab=usage). Compare the same length of period, such as the last 30 days against the 30 before.
2. Check for retries, automation loops, a recently connected integration, or a new MCP product key.
3. Keep the request and error identifiers you find.
4. If a compromise is plausible, contain it: turn off the person's MCP access, revoke the product key, or deactivate the account.
5. Escalate through your approved operational or security process, and contact [LawHand support](/admin?tab=support) if the cause is on the platform side.

Do not deactivate a person or delete evidence just because a chart looks unusual, and do not raise a budget until you understand the activity behind it. Per-person usage supports investigation and coaching; it is not a measure of productivity or professional value.

## Keep evidence of consequential changes

For each consequential change, record the reason, the approver, who made the change, the previous and new values, the time, how you verified it, and the rollback result if you rolled back. Use the product's audit facilities and keep complementary evidence in your restricted operations system. Never make seat or billing changes from a shared administrator account.

## Periodic review

Once a quarter, and after staff departures, vendor changes, or a suspected compromise, review:

- [ ] active and dormant users, and pending invitations ([Users](/admin?tab=users));
- [ ] administrators and powerful custom roles ([Roles](/admin?tab=roles));
- [ ] standard and premium licenses against actual need ([Licensing](/admin?tab=licensing));
- [ ] connected providers, granted permissions, and failed health checks ([Integrations](/admin?tab=integrations));
- [ ] MCP product keys, tool allowlists, and people with MCP access;
- [ ] Cloud Search and file-share boundaries;
- [ ] billing status and usage anomalies ([Subscription](/admin?tab=billing), [Usage](/admin?tab=usage)); and
- [ ] that alert recipients still exist and someone reads them ([Settings](/admin?tab=settings)).

Record who ran the review, what changed, and when the next one is due.

## Keep this guide current

Update the matching chapter whenever a workflow or setting changes. Documentation is part of a feature being finished, not cleanup after release.

## Related chapters

- [Subscription, usage & alerts](/admin?tab=guide&chapter=subscription-usage-alerts)
- [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing)
- [Support and escalation](/admin?tab=guide&chapter=support-and-escalation)
