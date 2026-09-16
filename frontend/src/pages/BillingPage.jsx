import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getBillingStatus, createCheckoutSession, createPortalSession } from '../api'
import { useAuth } from '../App'
import PlatformSubscription from '../components/PlatformSubscription'

// Anything that is not recognised used to read "Pay-as-you-go", which would
// label a firm on a free trial as a paying pay-as-you-go customer on the very
// page it is sent to in order to subscribe.
const TIER_LABELS = {
  flat: { text: 'Flat-seat subscription', className: 'bg-green-100 text-green-800' },
  trial: { text: 'Free trial', className: 'bg-blue-100 text-blue-800' },
  intake_trial: { text: 'Free trial', className: 'bg-blue-100 text-blue-800' },
  demo: { text: 'Demo workspace', className: 'bg-gray-100 text-gray-800' },
  payg: { text: 'Pay-as-you-go', className: 'bg-yellow-100 text-yellow-800' },
}

export function tierBadgeLabel(tier) {
  return TIER_LABELS[tier] || { text: tier || 'Unknown', className: 'bg-gray-100 text-gray-800' }
}

function TierBadge({ tier }) {
  const label = tierBadgeLabel(tier)
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${label.className}`}
    >
      {label.text}
    </span>
  )
}

export default function BillingPage({ embedded = false }) {
  useAuth()
  const [searchParams] = useSearchParams()

  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(null)
  const [error, setError] = useState(null)

  // Stripe reports a live subscription while the stored tier says
  // pay-as-you-go: a reconciliation problem, not a plan the firm chose. Never
  // upsell in this state — the firm is already paying for what we'd be selling.
  const subscriptionDisagrees = Boolean(
    status?.billing_tier === 'payg'
    && status?.subscription_status
    && !['canceled', 'cancelled', 'term_ended', 'none', 'incomplete_expired', ''].includes(
      String(status.subscription_status).toLowerCase()
    )
  )
  const [successMsg, setSuccessMsg] = useState(null)

  useEffect(() => {
    if (searchParams.get('success') === '1') {
      setSuccessMsg('Subscription activated! Your billing tier will update momentarily via webhook.')
    }
    getBillingStatus()
      .then(setStatus)
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load billing info'))
      .finally(() => setLoading(false))
  }, [])

  const handleUpgrade = async () => {
    setActionLoading('checkout')
    setError(null)
    try {
      const { checkout_url } = await createCheckoutSession()
      window.location.href = checkout_url
    } catch (e) {
      setError(e?.response?.data?.detail || 'Stripe checkout unavailable')
      setActionLoading(null)
    }
  }

  const handlePortal = async () => {
    setActionLoading('portal')
    setError(null)
    try {
      const { portal_url } = await createPortalSession()
      window.location.href = portal_url
    } catch (e) {
      setError(e?.response?.data?.detail || 'Stripe portal unavailable')
      setActionLoading(null)
    }
  }

  if (loading) {
    return (
      <div className={`flex items-center justify-center bg-brand-bg ${embedded ? 'py-16' : 'h-screen'}`}>
        <div className="w-6 h-6 border-2 border-brand-accent border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="">
      <div className={`${embedded ? 'max-w-3xl' : 'max-w-2xl mx-auto px-4 py-12'}`}>
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-brand-ink font-serif">Subscription Billing</h1>
            <p className="text-sm text-brand-muted mt-1 font-sans">
              Manage the firm's LawHand subscription and payment method.
            </p>
          </div>
          {!embedded && (
            <button
              onClick={() => window.location.assign('/admin?tab=billing')}
              className="text-sm text-brand-muted hover:text-brand-ink font-sans"
            >
              ← Back
            </button>
          )}
        </div>

        {successMsg && (
          <div className="mb-6 bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-700 font-sans">
            {successMsg}
          </div>
        )}

        {error && (
          <div className="mb-6 bg-brand-rose/10 border border-brand-rose/20 rounded-lg px-4 py-3 text-sm text-brand-rose font-sans">
            {error}
          </div>
        )}

        {/* An ended trial is sent here by the route guard, because the API
            refuses every other route. Say why, rather than leaving the firm to
            infer it from a page that simply looks empty. */}
        {searchParams.get('reason') === 'trial_expired' && (
          <div
            role="status"
            className="mb-6 rounded-lg border border-brand-rose/30 bg-brand-rose/10 px-4 py-4 font-sans"
          >
            <p className="text-sm font-semibold text-brand-ink">Your free trial has ended</p>
            <p className="mt-1 text-sm text-brand-ink-2">
              Subscribe below to get your firm working again. Your matters, documents and
              settings are all still here, and premium AI becomes available once the
              subscription is active.
            </p>
          </div>
        )}

        {/* Current plan card */}
        <div className="bg-brand-surface rounded-xl border border-brand-line shadow-sm p-6 mb-6">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-brand-muted uppercase tracking-wider font-sans mb-1">
                Current Plan
              </p>
              <div className="flex items-center gap-3">
                <span className="text-xl font-bold text-brand-ink font-serif capitalize">
                  {status?.billing_tier ?? '—'}
                </span>
                {status?.billing_tier && <TierBadge tier={status.billing_tier} />}
              </div>
              {status?.flat_seat_count > 0 && (
                <p className="text-sm text-brand-muted mt-1 font-sans">
                  {status.flat_seat_count} seat{status.flat_seat_count !== 1 ? 's' : ''}
                </p>
              )}
            </div>
          </div>

          {subscriptionDisagrees && (
            <div className="mt-4 pt-4 border-t border-brand-line">
              <p className="text-sm font-semibold text-brand-rose font-sans">
                This plan does not match the subscription on file.
              </p>
              <p className="text-sm text-brand-ink-2 font-sans mt-1">
                {status?.provider === 'helcim' ? 'Helcim' : 'Stripe'} reports this firm&rsquo;s subscription as
                {' '}<span className="font-semibold">{status.subscription_status}</span>, but the plan
                above is pay-as-you-go. Do not purchase again — contact support so billing can be
                reconciled, otherwise you may be charged twice.
              </p>
            </div>
          )}

          {status?.provider === 'stripe' && status?.billing_tier === 'payg' && !subscriptionDisagrees && (
            <div className="mt-4 pt-4 border-t border-brand-line">
              <p className="text-sm text-brand-ink-2 font-sans mb-3">
                On pay-as-you-go, usage is billed at a 10× markup on model cost.
                Upgrade to a flat-seat plan for predictable monthly pricing and
                significantly lower per-query costs.
              </p>
              <button
                onClick={handleUpgrade}
                disabled={actionLoading === 'checkout'}
                className="inline-flex items-center gap-2 bg-brand-accent text-white px-4 py-2 rounded-lg text-sm font-medium font-sans hover:bg-brand-accent-2 disabled:opacity-60 transition-colors"
              >
                {actionLoading === 'checkout' ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Redirecting to Stripe…
                  </>
                ) : (
                  'Upgrade to Flat-seat Plan'
                )}
              </button>
            </div>
          )}
        </div>

        {status?.provider === 'helcim' && <PlatformSubscription subscription={status.subscription} embedded={embedded} onChanged={async () => setStatus(await getBillingStatus())} />}

        {status?.mcp_usage && (
          <div className="bg-brand-surface rounded-xl border border-brand-line shadow-sm p-6 mb-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-brand-ink font-sans mb-1">
                  MCP usage
                </p>
                <p className="text-sm text-brand-muted font-sans">
                  {status.mcp_usage.collection_status === 'pending_review' ? 'Usage charges are reviewed and invoiced separately through Helcim. These estimates are not payments collected.' : 'Product-key calls are metered separately from subscription seats and model usage.'}
                </p>
              </div>
              <span className="inline-flex items-center rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800">
                PAYG line
              </span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <div className="rounded-lg border border-brand-line bg-brand-bg px-3 py-2">
                <p className="text-xs uppercase tracking-wider text-brand-muted font-sans">30-day calls</p>
                <p className="mt-1 text-xl font-bold text-brand-ink font-serif">
                  {(status.mcp_usage.successful_calls_30d || 0).toLocaleString()}
                </p>
                <p className="mt-1 text-xs text-brand-muted">Successful · billable</p>
              </div>
              <div className="rounded-lg border border-brand-line bg-brand-bg px-3 py-2">
                <p className="text-xs uppercase tracking-wider text-brand-muted font-sans">Failed calls</p>
                <p className="mt-1 text-xl font-bold text-brand-ink font-serif">{(status.mcp_usage.failed_calls_30d || 0).toLocaleString()}</p>
                <p className="mt-1 text-xs text-brand-muted">Visible · not billed</p>
              </div>
              <div className="rounded-lg border border-brand-line bg-brand-bg px-3 py-2">
                <p className="text-xs uppercase tracking-wider text-brand-muted font-sans">Estimated charges</p>
                <p className="mt-1 text-xl font-bold text-brand-ink font-serif">${Number(status.mcp_usage.estimated_charges_usd_30d || 0).toFixed(2)}</p>
                <p className="mt-1 text-xs text-brand-muted">{status.provider === 'helcim' ? 'Rates recorded when usage occurred' : `$${Number(status.mcp_usage.unit_price_usd || 0.45).toFixed(2)} per successful call`}</p>
              </div>
              <div className="rounded-lg border border-brand-line bg-brand-bg px-3 py-2">
                <p className="text-xs uppercase tracking-wider text-brand-muted font-sans">Returned results</p>
                <p className="mt-1 text-xl font-bold text-brand-ink font-serif">
                  {(status.mcp_usage.results_30d || 0).toLocaleString()}
                </p>
              </div>
            </div>
            <p className="mt-3 text-xs text-brand-muted font-mono">
              {status.mcp_usage.line_item || 'MCP usage'} / {status.mcp_usage.meter || 'mcp_product_key_calls'}
            </p>
          </div>
        )}

        {/* Manage subscription */}
        {status?.provider === 'stripe' && status?.stripe_customer_id && (
          <div className="bg-brand-surface rounded-xl border border-brand-line shadow-sm p-6 mb-6">
            <p className="text-sm font-semibold text-brand-ink font-sans mb-1">
              Manage Subscription
            </p>
            <p className="text-sm text-brand-muted font-sans mb-4">
              Update your payment method, download invoices, or cancel via the
              Stripe customer portal.
            </p>
            <button
              onClick={handlePortal}
              disabled={actionLoading === 'portal'}
              className="inline-flex items-center gap-2 border border-brand-accent text-brand-accent px-4 py-2 rounded-lg text-sm font-medium font-sans hover:bg-brand-accent hover:text-white disabled:opacity-60 transition-colors"
            >
              {actionLoading === 'portal' ? (
                <>
                  <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  Opening portal…
                </>
              ) : (
                'Open Billing Portal →'
              )}
            </button>
          </div>
        )}

        {/* Pricing reference */}
        <div className="bg-brand-surface rounded-xl border border-brand-line shadow-sm p-6">
          <p className="text-sm font-semibold text-brand-ink font-sans mb-3">Pricing reference</p>
          <div className="overflow-x-auto">
          <table className="w-full min-w-[400px] text-sm font-sans">
            <thead>
              <tr className="text-xs text-brand-muted uppercase">
                <th className="text-left pb-2">Model</th>
                <th className="text-right pb-2">PAYG (10×)</th>
                <th className="text-right pb-2">Flat-seat</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-line">
              <tr className="py-2">
                <td className="py-2 text-brand-ink-2">Standard</td>
                <td className="py-2 text-right text-brand-muted">$2.70 / 1M input</td>
                <td className="py-2 text-right text-brand-muted">$0.27 / 1M input</td>
              </tr>
              <tr>
                <td className="py-2 text-brand-ink-2">Premium</td>
                <td className="py-2 text-right text-brand-muted">$30 / 1M input</td>
                <td className="py-2 text-right text-brand-muted">$3 / 1M input</td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
  )
}
