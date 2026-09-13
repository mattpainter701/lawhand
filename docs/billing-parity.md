# Flexible matter billing

Billing → Ready to bill lists eligible work through the selected cutoff, including older unbilled entries and final charges on closed matters. Review work opens the existing draft composer. Its invoice date and work cutoff initially move together; changing the cutoff makes it independent. A blank start includes all older unbilled work. Saving does not send or collect payment.

## Fixed and stage fees

Add fixed fee creates an invoice without requiring time or expenses. Agreed stage fees start pending; Mark ready makes a fee selectable. Generating reserves selected fees; another generator cannot bill them again. Removing a draft line or voiding an unpaid bill releases its fee. Cancelled fees cannot be reopened. Time tracked for a fixed-fee matter must be marked non-billable when included in its agreed fee.

## Recurring drafts

Enable recurring drafts is an explicit per-matter choice with timezone, first invoice date, monthly/quarterly frequency and optional end date. Fixed service fees are billed in arrears, optionally with unbilled hourly work/expenses before the invoice date. Pause stops new drafts; resume catches up missed periods, bounded to twelve periods per scheduler pass. Closed/pro bono matters or an inactive/unauthorized billing owner pause processing. Existing billing-cycle fields never enable this schedule. Review every draft before sending. Schedule changes beyond pause/resume and advance billing/proration are not yet exposed.

## Installments

On an invoice, Payment installments records dates/amounts totaling the existing invoice. It never creates another principal charge. Recorded payments allocate oldest-first; the portal pays past/current installments together or the next installment early. Payment plans cannot be rescheduled after payments. Changing draft charges clears the plan; staff must set it again. Staff and portal aging only includes matured unpaid installments. Existing Stripe links must be retired successfully before changing a plan; new links collect the next payable amount. Autocharge is not enabled.

## QuickBooks and manual workflows

All charges use the existing Invoice, InvoiceLineItem and Payment records. Fixed/stage charges use the existing flat_fee service-item mapping. Draft generation does not sync, send, or charge. Explicitly released invoices retain their chosen issue/due dates. Subsequent sync updates the known QBO invoice using its current SyncToken. Manual recording, exports, existing retainer application and portal payments remain on their established paths.

No live QuickBooks company is modified by tests. Payload/ledger tests verify mapped fixed-fee export and repeat sync. Tax/account mappings and provider configuration still belong to the firm's existing integration setup.

## Delivery scope and remaining plan

This PR implements manual/fixed/stage generation, the ready-work list, opt-in recurring drafts and installment records. The approved roadmap also includes formal second-person approval, immutable issued PDF versions, batch send, trust-account/retainer ledger reconciliation and funding requests, collection reminders, statements, credits/refunds, split/multi-matter bills and full LEDES parity. These remain acceptance work before broad parity is claimed; no migration silently reclassifies existing money.


## LawHand subscriptions are separate

Helcim collects LawHand subscription payments from firms. It does not receive matter invoices, client correspondence or QBO credentials. The firm's QuickBooks connection continues to export invoices to its own end clients. Manual invoice generation and payment recording do not require Helcim.

Subscription Billing opens a dedicated billing page. A finance administrator reviews the live Helcim plan price and seat quantity, acknowledges recurring charges, and enters a card inside Helcim's hosted form. The application stores the provider customer/subscription references and sanitized payment history, never card numbers. It supports card updates, status refresh and explicitly acknowledged immediate cancellation. Cancellation ends subscription plan access immediately; refunds and seat changes require LawHand support. Existing application access is not disabled merely by a subscription callback.

Configure the same values for the backend and scheduler before onboarding:

- `PLATFORM_BILLING_PROVIDER=helcim` (default).
- `HELCIM_API_TOKEN`: merchant API token from the deployment secret store.
- `HELCIM_PAYMENT_PLAN_ID`: an active, forever, card-enabled subscription plan without add-ons. Its recurring amount is the per-seat price; the setup fee applies once. Current launch support is USD/CAD card subscriptions, not ACH.
- `HELCIM_WEBHOOK_TOKEN`: Helcim's base64 verifier token. Register the HTTPS endpoint `/api/billing/provider-events`; Helcim does not permit its brand name in webhook URLs.
- The existing token encryption key must be configured for encrypted checkout verification secrets.

Do not put merchant credentials into a firm's QBO settings or into browser build variables. Leave legacy Stripe credentials empty when unused. No paying Stripe customers currently need migration; this code does not transfer payment credentials or cancel live merchant subscriptions. Configure and verify the real merchant plan in a separate deployment before inviting the first paying firm.

The checkout stores an enrollment intent before the potentially charging subscription API call. An uncertain result stays unresolved until a refresh finds exactly one matching provider subscription; it never blindly creates another subscription. Support must investigate an unresolved state in Helcim rather than resetting it to permit another charge. Signed transaction callbacks and hourly scheduler refreshes read the current subscription from Helcim. Old or repeated callbacks cannot replay payment amounts into a local ledger. Callbacks cannot enable Research MCP entitlement by themselves.

MCP usage in Helcim mode is retained with its per-call rate and marked `pending_review`; it is not sent to Stripe. Automated variable-usage invoice creation/collection is not included in this release. Operators must review usage and bill it through Helcim separately until that collection workflow is implemented. Never treat usage estimates as collected payments. Subscription receipts/history do not currently provide downloadable provider invoice PDFs in the application.

Provider contracts: [Recurring API](https://devdocs.helcim.com/docs/recurring-api), [subscription creation](https://devdocs.helcim.com/reference/subscription-create), [checkout proof validation](https://devdocs.helcim.com/docs/validate-helcimpayjs), and [webhook verification](https://devdocs.helcim.com/docs/webhooks).
