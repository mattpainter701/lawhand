import { useEffect, useRef, useState } from 'react'
import api from '../api'

let scriptPromise
function loadCheckout() {
  if (window.appendHelcimPayIframe) return Promise.resolve()
  if (!scriptPromise) scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://secure.helcim.app/helcim-pay/services/start.js'
    script.onload = resolve
    script.onerror = () => { script.remove(); scriptPromise = null; reject(new Error('Unable to load secure checkout')) }
    document.head.appendChild(script)
  })
  return scriptPromise
}

export default function PlatformSubscription({ subscription, embedded, onChanged }) {
  const [offer, setOffer] = useState(null)
  const [consent, setConsent] = useState(false)
  const [cancelConsent, setCancelConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const checkoutCleanup = useRef(null)
  useEffect(() => () => checkoutCleanup.current?.(), [])
  const act = async (fn) => {
    setBusy(true); setError('')
    try { await fn() } catch (e) { setError(e?.response?.data?.detail || e.message || 'Billing action failed') }
    finally { setBusy(false) }
  }
  const checkout = async (updateMethod) => {
    await loadCheckout()
    const { data: result } = await api.post('/billing/subscription/checkout', { fingerprint: offer?.fingerprint || '', update_method: updateMethod })
    await new Promise((resolve, reject) => {
      let processing = false
      const cleanup = () => { window.removeEventListener('message', receive); document.getElementById('helcimPayIframe')?.remove(); checkoutCleanup.current = null }
      const receive = async (event) => {
        if (event.origin !== 'https://secure.helcim.app' || event.data?.eventName !== `helcim-pay-js-${result.checkout_token}` || processing) return
        if (['ABORTED', 'HIDE'].includes(event.data.eventStatus)) { cleanup(); resolve(); return }
        if (event.data.eventStatus !== 'SUCCESS') return
        processing = true
        try {
          const message = typeof event.data.eventMessage === 'string' ? JSON.parse(event.data.eventMessage) : event.data.eventMessage
          const proof = message?.hash ? message : message?.data
          if (!proof?.hash || !proof?.data) throw new Error('Checkout response could not be verified. Refresh billing status.')
          await api.post('/billing/subscription/complete', { checkout_token: result.checkout_token, data: proof.data, signature: proof.hash })
          await onChanged()
          cleanup(); resolve()
        } catch (e) { cleanup(); reject(e) }
      }
      window.addEventListener('message', receive)
      checkoutCleanup.current = () => { cleanup(); resolve() }
      try { window.appendHelcimPayIframe(result.checkout_token, true) } catch (e) { cleanup(); reject(e) }
    })
  }
  const exists = subscription?.has_subscription && !['cancelled', 'term_ended'].includes(subscription.subscription_status)
  return <section className="bg-brand-surface rounded-xl border border-brand-line p-6 mb-6" aria-label="LawHand subscription">
    <h2 className="font-semibold">LawHand subscription · Helcim</h2>
    <p className="text-sm text-brand-muted mt-2">Manage your firm’s LawHand plan and card. Your client invoices remain in matter billing and QuickBooks Online.</p>
    {error && <p role="alert" className="mt-3 text-brand-rose">{error}</p>}
    {embedded ? <a className="btn-primary inline-block mt-3" href="/billing">Open subscription billing</a> : <>
      <p className="mt-3">Status: {subscription?.subscription_status || 'No subscription'}</p>
      {['enrolling', 'needs_review'].includes(subscription?.phase) && <p role="status">Enrollment is awaiting reconciliation. Refresh status before making another change.</p>}
      <div className="flex flex-wrap gap-3 mt-3">
        <button className="btn-secondary" disabled={busy} onClick={() => act(async () => { await api.post('/billing/subscription/refresh'); await onChanged() })}>Refresh billing status</button>
        {!exists && <button className="btn-primary" disabled={busy || ['enrolling', 'needs_review'].includes(subscription?.phase)} onClick={() => act(async () => { setOffer((await api.get('/billing/subscription/offer')).data); setConsent(false) })}>Review subscription price</button>}
        {subscription?.has_customer && <button className="btn-secondary" disabled={busy} onClick={() => act(() => checkout(true))}>Update card</button>}
      </div>
      {offer && !exists && <div className="mt-4 border-t border-brand-line pt-4">
        <h3 className="font-semibold">{offer.name}</h3>
        <p>{offer.currency} {offer.recurring_amount} every {offer.billing_period_increments} {offer.billing_period} billing period(s) for {offer.seats} seat(s).</p>
        <p>Setup fee: {offer.currency} {offer.setup_amount}. Trial: {offer.trial_days} days. Billing day: {offer.billing_day}.</p>
        <p className="text-sm">Applicable taxes are calculated by Helcim. Proration: {offer.proration}. Card details are collected securely by Helcim.</p>
        <label className="block mt-3"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={busy} /> I authorize these recurring charges and any setup fee using the card I provide, until I cancel.</label>
        <button className="btn-primary mt-3" disabled={busy || !consent} onClick={() => act(() => checkout(false))}>Verify card and subscribe</button>
      </div>}
      {exists && <div className="mt-4 border-t border-brand-line pt-4">
        <p>Next billing date: {subscription.details?.next_billing_date || 'Awaiting confirmation'}</p>
        <label className="block mt-3"><input type="checkbox" checked={cancelConsent} onChange={e => setCancelConsent(e.target.checked)} disabled={busy} /> Cancel immediately and end this subscription’s paid plan access. Existing charges are not refunded automatically.</label>
        <button className="btn-secondary mt-3" disabled={busy || !cancelConsent} onClick={() => act(async () => { await api.post('/billing/subscription/cancel'); setCancelConsent(false); await onChanged() })}>Cancel subscription immediately</button>
      </div>}
      {!!subscription?.details?.payments?.length && <div className="mt-4 overflow-x-auto"><h3 className="font-semibold">Subscription payment history</h3><table className="w-full text-sm"><thead><tr><th className="text-left">Due</th><th className="text-left">Amount</th><th className="text-left">Status</th></tr></thead><tbody>{subscription.details.payments.map(payment => <tr key={payment.id}><td>{payment.dateDue}</td><td>{subscription.offer?.currency} {payment.amount}</td><td>{payment.status}</td></tr>)}</tbody></table></div>}
    </>}
  </section>
}
