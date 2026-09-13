# Flexible matter billing

Billing → Ready to bill lists eligible work through the selected cutoff, including older unbilled entries and final charges on closed matters. Review work opens the existing draft composer. Its invoice date and work cutoff initially move together; changing the cutoff makes it independent. A blank start includes all older unbilled work. Saving does not send or collect payment.

## Fixed and stage fees

Add fixed fee creates an invoice without requiring time or expenses. Agreed stage fees start pending; Mark ready makes a fee selectable. Generating reserves selected fees; another generator cannot bill them again. Removing a draft line or voiding an unpaid bill releases its fee. Cancelled fees cannot be reopened. Time tracked for a fixed-fee matter must be marked non-billable when included in its agreed fee.

## Recurring drafts

Enable recurring drafts is an explicit per-matter choice with timezone, first invoice date, monthly/quarterly frequency and optional end date. Fixed service fees are billed in arrears, optionally with unbilled hourly work/expenses before the invoice date. Pause stops new drafts; resume catches up missed periods, bounded to twelve periods per scheduler pass. Closed matters or an inactive/unauthorized billing owner pause processing. Existing billing-cycle fields never enable this schedule. Review every draft before sending. Schedule changes beyond pause/resume and advance billing/proration are not yet exposed.

## Installments

On an invoice, Payment installments records dates/amounts totaling the existing invoice. It never creates another principal charge. Recorded payments allocate oldest-first; the portal pays past/current installments together or the next installment early. Payment plans cannot be rescheduled after payments. Changing draft charges clears the plan; staff must set it again. Autocharge is not enabled.

## QuickBooks and manual workflows

All charges use the existing Invoice, InvoiceLineItem and Payment records. Fixed/stage charges use the existing flat_fee service-item mapping. Draft generation does not sync, send, or charge. Explicitly released invoices retain their chosen issue/due dates. Subsequent sync updates the known QBO invoice using its current SyncToken. Manual recording, exports, existing retainer application and portal payments remain on their established paths.

No live QuickBooks company is modified by tests. Payload/ledger tests verify mapped fixed-fee export and repeat sync. Tax/account mappings and provider configuration still belong to the firm's existing integration setup.

## Delivery scope and remaining plan

This PR implements manual/fixed/stage generation, the ready-work list, opt-in recurring drafts and installment records. The approved roadmap also includes formal second-person approval, immutable issued PDF versions, batch send, trust-account/retainer ledger reconciliation and funding requests, collection reminders, statements, credits/refunds, split/multi-matter bills and full LEDES parity. These remain acceptance work before broad parity is claimed; no migration silently reclassifies existing money.
