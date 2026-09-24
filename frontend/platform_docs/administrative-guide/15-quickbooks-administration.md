---
slug: quickbooks-administration
title: QuickBooks administration
description: Connect the firm's QuickBooks Online company, map LawHand charges to service items, sync invoices safely, and reconcile.
order: 150
read_time: 10 min
icon: receipt
---

# QuickBooks administration

[Integrations > QuickBooks](/admin?tab=integrations&integration=quickbooks) sends LawHand billing data to your QuickBooks Online company. QuickBooks stays the accounting system of record and still needs reconciliation; LawHand must never become an unexplained second ledger. Accountants can open this section too.

## What LawHand can read and write

Intuit grants a broad accounting permission (`com.intuit.quickbooks.accounting`) for the chosen company, plus sign-in scopes. The grant is not limited to invoices, but LawHand uses it narrowly: it reads active service items, accounts, matching customers, and the state of invoices it already synced, and it writes customers, time activity, invoices, and payments.

| LawHand record | QuickBooks record | What is sent |
| --- | --- | --- |
| Client and matter | Customer | Display name, company or counterparty, and notes with the matter name, type, jurisdiction, and status |
| Final billable time | TimeActivity | Customer, service item, date, duration, rate, description, billable status |
| Sent invoice | Invoice | Invoice number, dates, customer, service-item lines, descriptions, quantities, rates, amounts, private notes |
| Payment | Payment | Customer, amount, date, method, linked invoice |

Matter descriptions and notes can contain client context, so review them before exporting. See [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility) for the full disclosure.

## Connect the company

1. Work with an Intuit administrator for the intended company.
2. Select **Connect to QuickBooks** and sign in to Intuit.
3. On the consent screen, check the company name. Never connect a sandbox, a former company, an accountant's test file, or a similarly named entity to your live firm.
4. Back in LawHand, "QuickBooks Online connected successfully." appears. Confirm the company shown before configuring or syncing anything.

## Map charges to service items

Under **Field Mapping**, choose the QuickBooks service item for each kind of LawHand charge:

- **Time Entry (billable hours)**, **Flat Fee**, and **Adjustment / Discount**; and
- each expense type, such as **Expense — Court / Filing Fee**, **Expense — Courier**, or **Expense — Travel / Mileage / Parking**.

Then choose the **Accounts receivable** account, or **Use the QuickBooks default**, and select **Save Mappings**. Record the accounting owner's approved choices. If QuickBooks data fails to load, select **Retry QuickBooks data**.

Test edge cases before going live: a new client, several matters for one client, discounts, taxes, trust-related activity, a voided invoice, and an invoice that was already synced.

## Sync invoices

LawHand syncs invoices once they are sent; drafts never sync.

- **One invoice:** on the invoice in [Invoices](/invoices), select **Sync** under **Accounting**. See [Sync with QuickBooks](/guide/time-billing-and-reports#sync-with-quickbooks).
- **All at once:** under **Sync Invoices**, select **Sync All** to push every unsynced invoice. The result reads "Synced N invoices successfully." or "Partial sync: N synced, N error(s)."

Start with a small approved batch. Compare the invoice number, client, dates, line descriptions, quantities, rates, adjustments, taxes, totals, and status, and note the QuickBooks identifiers.

LawHand keeps each record's sync state to prevent duplicates. If a sync times out, check QuickBooks for the record before retrying.

## Reconcile and recover

Reconcile every first sync, and every sync with errors, in QuickBooks. For a mapping or validation error, fix the source record or the mapping and retry only the affected record. Never post a manual offsetting entry to hide an integration error.

If you suspect data went to the wrong company, stop syncing, disconnect, and escalate to your accounting and security owners immediately.

## Tell your billing team

Explain which records are eligible for export and when, who may start a sync, and whether corrections are made in QuickBooks or in LawHand.

## Disconnect

Select **Disconnect** and confirm **Disconnect QuickBooks Online?**. Existing synced data in QuickBooks remains.

LawHand keeps the encrypted connection details, the company identifier, mappings, QuickBooks record identifiers, sync state, and error history. Disconnecting stops future access; it does not remove transactions from QuickBooks or erase LawHand's billing records and sync history. Before disconnecting or reconnecting, keep the mapping and sync evidence, and understand how existing QuickBooks identifiers will be treated.

## Go-live checklist

- [ ] The connected company is the correct live company.
- [ ] Service items and the receivables account are mapped and approved.
- [ ] A known customer, one time entry, one invoice, and one payment synced correctly.
- [ ] Updating a synced invoice behaves as expected, with no duplicates.
- [ ] The accounting owner has signed off the reconciliation.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| **Sync** is disabled on an invoice | It is a draft, or QuickBooks is not connected | Send the invoice first, or connect QuickBooks. |
| "Partial sync" | Some invoices failed validation or mapping | Fix the named records or mappings and sync them again. |
| Service items do not load | QuickBooks was unavailable | Select **Retry QuickBooks data**. |
| A duplicate appears in QuickBooks | A timed-out sync was retried after QuickBooks created the record | Void the duplicate in QuickBooks and reconcile; check before retrying next time. |

## Related chapters

- [Integrations](/admin?tab=guide&chapter=integrations)
- [Time, billing & reports](/guide/time-billing-and-reports)
- [Integration permissions and data visibility](/admin?tab=guide&chapter=integration-data-visibility)
