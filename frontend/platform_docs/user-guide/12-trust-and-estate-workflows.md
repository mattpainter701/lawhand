---
slug: trust-and-estate-workflows
title: Trust, estate & probate workflows
description: Open a probate, decide the proceeding from the intake, pre-fill the court forms, and maintain estate details, fiduciaries, beneficiaries, assets, claims, deadlines, and distributions.
order: 120
read_time: 10 min
icon: briefcase
---

# Trust, estate & probate workflows

The [Estate Portfolio](/plugins/trust-estate/estates) organizes estate plans, probate estates, trust administrations, small estates, guardianships, and conservatorships. Each estate record tracks the people, property, claims, deadlines, and distributions alongside the matter and its source documents. It is part of the trust and estate add-on; if you cannot open it, see [Add-on module management](/guide/add-on-module-management).

## Read the portfolio

The counters at the top show **Active Plans**, estates **In Probate**, **Overdue Deadlines**, and **Missing Opening Facts**. The list shows each estate's type, client, jurisdiction, estimated value, status, what **Needs Attention**, beneficiaries, and the **Next Key Date**.

- Search by estate name.
- Filter by status, and by what needs work: **Overdue Deadlines**, **Missing Facts**, or **Unresolved Claims**. **All Work** shows everything.

Start each day with **Overdue Deadlines**, then **Missing Facts**.

## Create an estate record

1. Select **New Estate**.
2. Enter the **Estate / Trust Name**, such as "Estate of Jane Doe".
3. Choose the **Type**: **Estate Planning**, **Probate**, **Trust Administration**, **Small Estate**, **Guardianship**, or **Conservatorship**.
4. Enter the **Jurisdiction**, such as "CA — Los Angeles County", and the **Gross Estate Value (USD)** if known.
5. Select **Create Estate**.

Then open the record and complete the details from source documents: the decedent or grantor, domicile, date of death, representative type, court, and case number. Use the legal names and dates exactly as the documents show them.

## Work through the estate tabs

An estate record has these tabs:

- **Overview**: the summary, key facts, the next deadlines, and the **Linked Matter**.
- **Probate**: the opening workbench described below.
- **Fiduciaries**: the executor, trustee, attorney, or CPA, with appointment details and compensation.
- **Beneficiaries**: who inherits and what, including charities.
- **Assets**: what the estate owns, with date-of-death and current values.
- **Claims**: creditor claims, amounts, priority, and how each was resolved.
- **Deadlines**: filings, tax due dates, and other dates, with their status.
- **Distributions**: planned and completed distributions, approvals, and check numbers.
- **Accounting**: ledger entries for the estate.
- **Activity**: drafting steps, filings, and distributions, recorded with **Save Entry**.

Mark one fiduciary as primary only when the documents support it. Keep estimates separate from appraised or filed values.

## Open a probate

For a North Dakota estate, the **Probate** tab does the opening work. For other jurisdictions the tab says the workbench does not support them yet.

1. **Send probate intake** opens the matter's paperwork drawer with the probate questionnaire. The client can answer in the portal, on a printed copy you mail, or by phone while staff type into the facts form; the questions are the same.
2. **Pull from client questionnaire** brings the client's answers into the estate's facts without overwriting what staff already entered.
3. **Save facts and determine track** works out which proceeding applies (informal probate of a will, informal appointment in intestacy, a formal proceeding after three years, a small-estate affidavit, or no North Dakota proceeding) and explains why, citing the statute. Correct a fact to change the answer.
4. **Court forms** lists the forms the track requires and the pages to print for each. The court's packet is added to your templates as a draft the first time you open the tab; an attorney publishes it in [Template Studio](/templates), then **Generate filled packet** fills every form from the estate record for review.
5. **Deadline clock** turns the date of death, the appointment date, and the first publication of the notice to creditors into the statutory deadlines, optionally as matter tasks. Running it again after a date changes moves open deadlines and leaves completed ones alone.

For a formal proceeding the court publishes no forms; the tab lists the pleadings the firm drafts and uploads as its own templates.

## Client estate inventory

Once the personal representative is appointed (or earlier, if you open it from the probate facts), the client's portal shows an **Estate inventory** tab. There the client lists what the estate owns in plain words, with a rough value and an optional statement or photo.

Each item waits on the **Assets** tab until staff **Verify** it or **Reject** it and follow up with the client. Only verified items count toward the inventory.

## Deadlines and claims

Record the source and status of every deadline. Check publication, notice, inventory, tax, accounting, and distribution dates against the governing law and any court order. For claims, keep the creditor, claim type, amount, date received, priority, and how it was resolved.

## Distributions

Before marking a distribution approved or paid, confirm the beneficiary's identity, the authority to distribute, available funds, reserves, tax and claim effects, and the required receipts. The workflow tracks activity; it does not decide whether a distribution is lawful.

Use [Trust Accounting](/trust) for client-fund ledger activity. Estate asset values in this workflow do not replace trust or bank reconciliation; see [Trust accounting](/guide/time-billing-and-reports#trust-accounting).

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| The **Probate** tab says the jurisdiction is not supported | The workbench currently covers North Dakota | Set the estate's jurisdiction correctly; for other states, use your own templates and deadlines. |
| **Generate filled packet** is disabled | The estate is not linked to a matter, or the court packet is not installed or not yet published | Point at the button to see which. Link the matter, or ask an attorney to publish the packet in Template Studio. |
| A client's inventory item is not in the totals | It has not been verified | Open **Assets** and **Verify** or **Reject** it. |
| "Trust, Estate & Probate data could not be loaded" | The add-on is not available for your firm | Ask your administrator. |

## Related chapters

- [Add-on module management](/guide/add-on-module-management)
- [Template Studio & e-signature](/guide/document-automation-and-esignature)
- [Time, billing & reports](/guide/time-billing-and-reports)
