---
slug: time-billing-and-reports
title: Time, billing & reports
description: Record time and expenses, turn unbilled work into invoices, keep trust ledgers reconciled, and read the firm's financial reports.
order: 40
read_time: 14 min
icon: clock
---

# Time, billing & reports

This chapter follows money through LawHand: you record time and expenses on a matter, a billing person turns the unbilled work into an invoice, payments and client funds settle it, and reports show the result.

What you can open depends on your role and your firm's modules:

| Screen | Who usually uses it |
| --- | --- |
| [Time Tracking](/time-tracking) | Everyone who records time |
| [Trust Accounting](/trust) | People your firm has trained and authorized to handle client funds |
| [Invoices](/invoices) | Billing administrators and accountants |
| [Reports](/reports) | Billing administrators and accountants |

If a screen in this chapter is missing from your navigation, your role or your firm's modules do not include it. Ask your administrator.

## Record time

Open [Time Tracking](/time-tracking). The page lists recent entries with their billing status and totals for the current view.

![The Time tracking page with the Add entry button, a running timer with its description box, and the entries table showing unbilled, non-billable, and invoiced time](/guide-assets/time-tracking.webp "Time tracking with a timer running")

1. **Add entry** opens the form for work you have already done.
2. A running timer shows the matter and the elapsed time, with a box for describing the work.
3. **Stop & log** turns the timer into a time entry. **Discard** throws the timer away without logging anything.

The three figures above the list are **Hours logged**, **Recorded value**, and **Unbilled value** for the entries in view. Each entry shows its status: **Unbilled**, **Invoiced**, or **Non-billable**.

### Log time you have already worked

1. Select **Add entry**. The **Add billable time** form opens.
2. Choose the **Matter**.
3. Write a **Description** that a client would understand, such as "Draft response to motion to compel; review scheduling order".
4. Enter the **Time** as decimal hours, hours and minutes, or minutes: `1.5`, `1:30`, and `90m` all mean ninety minutes.
5. Check the **Date**. It defaults to today.
6. Leave **Rate** empty to use the matter or profile rate, or enter a rate for this entry.
7. Clear **Billable time** for internal work that should never be billed.
8. Select **Save entry**.

LawHand rounds time up to your firm's billing increment, shown under the field as, for example, "Billed in 6-minute units". A 20-minute call becomes 0.4 hours in 6-minute units.

> [!TIP]
> On a matter, open the **Billing** section and select **Log Time**. Time Tracking opens with that matter already chosen.

### Time work as you do it

1. Select **Add entry** and choose the **Matter** (and a description if you already know it). The timer needs a matter.
2. Select **Start timer**. The running timer appears at the top of the page and keeps counting if you leave the page.
3. When you finish, describe the work under **What are you working on?**. LawHand will not log a timer without a description.
4. Select **Stop & log**. The entry appears in the list, rounded to the firm's increment.

Select **Discard**, then **Discard timer**, only if the time should not be recorded at all; the elapsed time is lost.

### Write a narrative a reviewer can bill

A good narrative says what professional work you did and why, in plain words, without unnecessary sensitive detail:

- **Useful:** "Review settlement agreement draft; redline indemnity terms."
- **Too vague:** "Work on file."
- **Too revealing:** including a client's medical details or privileged strategy that the invoice does not need.

Invoice lines use your description, so write it once, correctly, at the time.

### Find, correct, or delete an entry

- Use **All**, **Unbilled**, and **Invoiced** to filter by status. Narrow the list with **All matters**, switch **All timekeepers** to **My entries**, or set a date range.
- Select the pencil on an entry to open **Edit time entry**. Change the description, time, date, rate, or billable setting and save.
- Select the bin to delete an entry, then **Delete entry** to confirm.

Only unbilled entries can be changed. Invoiced time is fixed; to correct it, a billing person voids the invoice (which returns its work to the unbilled queue) or follows your firm's credit procedure. Never offset a mistake with an unexplained negative or duplicate entry.

## Record matter expenses

Costs you pay on a client's behalf, such as filing fees, courier charges, or records retrieval, are recorded on the matter:

1. Open the matter, go to **Billing**, and find **Expenses**.
2. Select **Add expense**. Enter the date, a description of what was purchased, the amount, and the vendor, and choose a category and **Payment method**.
3. Leave **Billable to client** on for a cost the client reimburses. **Client amount** defaults to the firm's cost; enter a different figure only when your firm's policy allows a markup or discount.
4. Turn **Billable to client** off for internal spend. Those expenses are marked **Internal only** and never reach an invoice.
5. Select **Add expense**.

**Expense notes** stay internal; they are never shown on the client invoice.

### Email receipts to a matter

Select **Create receipt address** under **Email receipts to this matter** to get an address for that matter, then forward one receipt or vendor invoice per email. LawHand reads the receipt into a draft expense marked **Needs review**. Open it, check the extracted amount and vendor under **Review the receipt extraction**, decide whether it is billable, and select **Approve expense**. Only approved, billable expenses become ready to bill.

## Invoices

Open [Invoices](/invoices). The page shows what is outstanding, what is overdue, and which drafts need review, followed by the work that is ready to bill and every invoice.

![The Invoices page with the Generate invoice button, the Outstanding, Overdue, and Drafts to review figures, the Ready to bill list of matters, and the invoice table with draft, sent, overdue, and paid invoices](/guide-assets/invoices-list.webp "Invoices, ready-to-bill work, and payment status")

1. **Generate invoice** opens the draft form.

The **Ready to bill** panel lists every matter with unbilled billable time, approved expenses, or ready fixed fees, with the item count, the oldest item's date, and the amount before tax. Use **Find matter** to search, and **Refresh unbilled work** after colleagues log more time.

Filter the invoice list by **All**, **Draft**, **Sent**, **Part paid**, **Paid**, or **Overdue**. The **QuickBooks** column shows whether each invoice is synced.

### Generate a draft invoice

1. Select **Review work** on a matter in **Ready to bill**, or select **Generate invoice** and choose the **Matter**.
2. Set **Work through** to the last date to include. Set **Work from (optional)** only when earlier unbilled work should wait for a later bill; otherwise all older unbilled work is included.
3. Check the **Issue date**, **Payment terms**, and **Due in (days)**.
4. Enter the **Sales tax rate (%)**. Use `0` for non-taxable services; QuickBooks receives the same taxable status.
5. Under **Selected work**, clear **Include** for any time or expense entry that should not be on this bill. The **Draft total** updates as you go.
6. To bill a flat amount, select **Add fixed fee** and enter a description, quantity, and unit price. A draft can consist only of fixed fees.
7. Add an optional **Invoice notes** message for the client.
8. Select **Generate draft**.

Generating a draft does not send anything. The work you included is reserved for this invoice and leaves the ready-to-bill list.

### Review the draft

Open the invoice from the list. While it is a draft:

- **Edit draft** changes the **Issue date**, **Due date**, **Payment terms**, and **Client-facing note**. Select **Save details** when you finish.
- Under **Invoice charges**, **Add charge** adds a flat fee, discount, or adjustment, and each line can be removed. "Charges can be edited while this bill is a draft."
- Select **PDF** to see exactly what the client will receive.

Treat the draft, including descriptions written with assistant help, as reviewable work until the responsible lawyer approves it.

### Send the invoice

There are two ways to move a draft to **Sent**, and they do different things:

- **Email invoice** emails the invoice PDF to the client and records it as sent. LawHand asks **Email this invoice?** before sending.
- **Mark as sent** records that you delivered the invoice some other way, such as by post or through a client's billing portal. It does **not** send an email.

Either one starts accounts-receivable tracking. **Collect & deliver** also offers **Open print-ready PDF**, **Export CSV**, and **Export LEDES 1998B** for printing and for clients that require electronic billing files.

### Record a payment

A payment record is what moves an invoice to **Part paid** or **Paid**.

1. On a sent invoice, select **Record payment**.
2. Enter the **Amount** and **Payment date**, and choose the **Method**: **Bank transfer**, **Cash**, **Check**, **Credit card**, **Stripe**, **Retainer drawdown**, or **Other**.
3. Add a **Reference**, such as the check number, and save.

**Client funds on hand.** When the client has a retainer with money available, the invoice shows it with an **Apply** button for the amount that can be used. Applying funds draws the retainer down and records the payment in one step, after you confirm **Apply client funds to this invoice?**. If a retainer is below its minimum balance, the panel says so, so you can request a top-up.

**Online payment.** Select **Create payment link** to create a Stripe payment page for the balance, then **Open payment link** to copy or share it. Your firm must have Stripe set up; otherwise LawHand says the link was not created.

### Sync with QuickBooks

If your firm uses QuickBooks Online, the **Accounting** panel shows the invoice's sync status. Select **Sync** to send a sent invoice to QuickBooks. A draft cannot be synced, and the button explains when QuickBooks is not yet connected. Administrators connect QuickBooks under Administration.

### Void or write off an invoice

- **Void invoice** cancels a draft or sent invoice that has no payments. Its time entries and expenses return to the unbilled work queue, so you can correct them and bill again.
- **Write off balance** forgives what is still outstanding on a sent or part-paid invoice. The invoice stays on record but leaves accounts receivable.

Both ask for confirmation. Follow your firm's approval policy before forgiving a balance.

### How the invoice PDF is branded

Invoice PDFs use the firm name, logo, address, contact details, and optional PDF footer your administrator configured. The PDF shows the matter name and the current balance but does not expose internal tenant or matter identifiers. If the branding is wrong, ask an administrator to correct it rather than editing each exported copy.

## Trust accounting

Use [Trust Accounting](/trust) only if you are authorized and trained for your jurisdiction and your firm's procedures. Trust funds must stay separate from operating funds and be reconciled regularly. LawHand keeps the records; it does not decide whether a transfer is ethically or legally permitted.

The page lists each trust account with its bank, balance, and status, and the **Total Trust Balance** across them.

### Open a trust account for a matter

1. Select **New Trust Account**.
2. Choose the **Matter**. Each matter has at most one trust account.
3. Enter an **Account Name**, such as "Keller v. Northgate IOLTA", and optionally the **Bank Name** and the last four digits of the account number.
4. If the engagement sets a **Minimum Balance** or an **Auto-Replenish Amount**, record them so colleagues can see the agreed figures.
5. Save the account.

### Post a transaction

1. Open the account and select **Post Transaction**.
2. Choose the **Transaction Type**:
   - **Deposit**, **Transfer In**, and **Replenishment** add to the balance.
   - **Disbursement**, **Transfer Out**, and **Fee** take money out.
   - **Adjustment** corrects the balance up or down, using the sign of the amount.
3. Enter the **Amount**, a **Description** such as "Settlement deposit", and the **Date**, plus any **Reference #** or **Check #**.
4. Select **Post Transaction**.

LawHand refuses a withdrawal larger than the account balance with "Insufficient trust balance". The **Ledger** tab lists every transaction with **Total Deposits**, **Total Disbursements**, and **Net Change**, and **Download PDF** produces a statement of the account.

> [!CAUTION]
> Never post an **Adjustment** to hide a difference you cannot explain. Record the real transaction, keep the source documentation, and escalate unexplained differences under your firm's procedure.

### Reconcile an account

1. Open the account and select the **Reconciliation** tab.
2. Enter the **Bank Balance** from the bank statement and its **As of Date**.
3. Enter **Outstanding Deposits** (received but not yet on the statement) and **Outstanding Disbursements** (checks written but not yet cleared).
4. Add **Notes** and select **Reconcile**.

The result says **Reconciled**, or **Out of balance by** the difference. It shows the **Bank Balance**, the **Trust Liability** (what the ledger says you hold for clients), the **Adjusted Bank Balance** after outstanding items, and anything **Unallocated**. The most recent result stays on the tab as **Last Reconciliation**.

### Close an account

An account can be closed only when its balance is zero; LawHand refuses to close an account that still holds funds. Disburse or transfer the remaining balance first, then select **Close Account** and confirm. Closing cannot be undone.

## Reports

Open [Reports](/reports). **Firm Reports** has four tabs:

- **Overview**: total matters by status, type, and risk level, leads and the conversion rate, and overdue tasks.
- **Realization**: for each matter, **Worked Hours** and **Worked Value**, what was **Invoiced** and **Collected**, and the **Billed %** and **Collected %**.
- **WIP**: work in progress, as **WIP Hours** and **WIP Value** that are recorded but not yet invoiced.
- **A/R Aging**: unpaid invoice balances grouped as **Current**, **1–30**, **31–60**, **61–90**, and **90+** days past due, with the **Total Due**.

On **Realization** and **WIP**, choose a period with **This month**, **Last month**, **Year to date**, or **All time**, or enter a **Start date** and **End date**; a custom range overrides the preset. **A/R Aging** always shows balances as of today. **Download CSV** exports the report you are viewing, and each table includes column totals.

A report reflects the records entered and the period selected. If a number looks wrong, trace it back to the matter, time entry, invoice, or payment and correct the source rather than editing an exported copy.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "Select a matter to start the timer." | The timer needs a matter | Choose the **Matter** in the entry form, then select **Start timer**. |
| "Describe the work before logging this time." | The running timer has no description | Describe the work under **What are you working on?**, then **Stop & log**. |
| You cannot edit or delete an entry | It is invoiced, or it belongs to another timekeeper | Ask a billing administrator; invoiced work changes only by voiding the invoice. |
| Time shows more hours than you entered | Entries round up to the firm's billing increment | Check the "Billed in N-minute units" note under **Time**. |
| An expense is not in **Ready to bill** | It still **Needs review**, it is internal only, or it is already invoiced | Open the expense on the matter's **Billing** section and approve it as billable. |
| The client did not receive an invoice | It was **Marked as sent**, which does not email | Use **Email invoice**, or deliver the PDF yourself. |
| **Sync** is disabled | The invoice is a draft, or QuickBooks is not connected | Send the invoice first; ask an administrator to connect QuickBooks. |
| A trust withdrawal is refused | The amount exceeds the account balance | Check the ledger; post the deposit first if it is missing. |
| A trust account cannot be closed | It still has a balance | Disburse or transfer the remaining funds, then close it. |

## Related chapters

- [Matters & documents](/guide/matters-and-documents)
- [Contacts & client relationships](/guide/contacts-and-client-relationships)
- [Account safety & help](/guide/account-safety-and-support)
