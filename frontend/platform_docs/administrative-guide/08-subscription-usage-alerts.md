---
slug: subscription-usage-alerts
title: Subscription, usage & alerts
description: Review the firm's plan and charges, set the default billing rate and increment, read AI usage, and set spend alerts that someone will act on.
order: 80
read_time: 8 min
icon: chart
---

# Subscription, usage & alerts

Four screens work together:

- [Subscription](/admin?tab=billing) shows the plan, estimated charges, and the firm's time and billing defaults.
- [Usage](/admin?tab=usage) shows AI requests, tokens, and cost, for the firm and per person.
- [Licensing](/admin?tab=licensing) assigns seats and premium AI; see [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing#licensing).
- [Settings](/admin?tab=settings) holds spend alerts, recipients, and rate limits.

## Subscription

Open [Subscription](/admin?tab=billing). **Subscription Billing** shows the firm's plan: a **Free trial**, a **Flat-seat subscription**, or **Pay-as-you-go**.

- **Upgrade to Flat-seat Plan** starts checkout for a seat-based plan. After paying, the plan updates within moments; check the plan and seats before telling staff.
- **Open Billing Portal** manages the payment method and invoices for the subscription.
- **Estimated charges** lists model usage by tier (**Standard** and **Premium**), with rates recorded when the usage occurred. Product-key calls are metered separately; failed calls are visible but not billed. Usage charges are invoiced separately, and these estimates are not payments collected.
- **Pricing reference** shows the current rates, including the pay-as-you-go multiplier.

Confirm the firm, the current plan, and that you are authorized to buy before changing anything with a commercial effect.

### Time and billing defaults

Below the subscription, **Time and billing defaults** apply to every timekeeper:

1. Enter the **Firm default hourly rate**. A matter's rate, then the timekeeper's own rate, both take priority over it. Leave it blank if every rate is set elsewhere.
2. Choose the **Billing increment**: **6 minutes (0.1 hour)**, **10 minutes**, **15 minutes (0.25 hour)**, **30 minutes**, or **60 minutes**. Time entries and stopped timers round up to it, with one increment as the minimum, and people see it as "Billed in N-minute units" when they log time.
3. Select **Save defaults**.

Change the increment at the start of a billing period, and tell timekeepers, because it changes how every new entry is rounded.

## Usage

Open [Usage](/admin?tab=usage). Choose **7**, **30**, or **90** days. The summary shows **Total Requests**, **Tokens In**, **Tokens Out**, and **Total Cost** (estimated, in USD), and **Per-User Breakdown** lists each person's requests, tokens, and cost.

Compare the same length of period each time. Unusual shape or timing, such as heavy use overnight or a sudden jump from one person, is a stronger signal than a high total. See [When usage looks wrong](/admin?tab=guide&chapter=billing-usage-and-governance#when-usage-looks-wrong).

## Set spend alerts

1. Open [Settings](/admin?tab=settings) and find **Alerts & Budgets**.
2. Enter a **Monthly spend alert threshold (USD)**.
3. Choose **Alert at**, the percentage of the threshold that sends the alert.
4. Enter **Alert recipients**, comma-separated. Use a monitored group address; leave it blank to alert every administrator.
5. Turn on **Weekly usage digest** for a weekly summary of usage and cost.
6. Select **Save alerts**.

Alerts are sent through the connected Microsoft or Google account, with the configured SMTP service as a fallback. After changing recipients or the mail connection, confirm the next alert or digest actually arrives.

On pay-as-you-go plans you can also cap an individual's spend with a **Budget cap** in [Licensing](/admin?tab=licensing). **Rate limits** in Settings (**Requests / minute** and **Tokens / day**) set a hard ceiling for the whole firm; set them only when you need one.

## Respond to an alert

1. Confirm the firm, the period, the metric, and the threshold.
2. Look at per-person and per-tool activity.
3. Look for repeated failures, loops, new integrations, or exposed keys.
4. Contain access if a compromise is plausible.
5. Keep request IDs and audit evidence.
6. Record the outcome and any budget change.

Never simply raise a limit until you understand the activity behind it.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| The plan did not change after paying | The update arrives from the payment provider a moment later | Wait, reload Subscription, and check the plan and seats. |
| "Stripe portal unavailable" | Online billing is not set up for your firm | Contact LawHand support. |
| No alert arrived when spend passed the threshold | No threshold, a wrong recipient, or mail delivery failed | Check **Alerts & Budgets** and the mail connection. |
| Timekeepers' entries round differently than expected | The **Billing increment** changed | Check **Time and billing defaults**. |

## Related chapters

- [Billing, usage & governance](/admin?tab=guide&chapter=billing-usage-and-governance)
- [Users, roles & licensing](/admin?tab=guide&chapter=users-roles-and-licensing)
- [Tenant settings & branding](/admin?tab=guide&chapter=tenant-settings-and-branding)
