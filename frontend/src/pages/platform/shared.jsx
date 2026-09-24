import { useEffect, useRef, useState } from 'react'
import { Check, Copy, ShieldAlert } from 'lucide-react'

/** Primitives shared by the operator console tabs. */

/**
 * Keeps the newest callback without making it a load dependency, so a parent
 * that passes an inline handler cannot turn a data load into a refetch loop.
 */
export function useLatest(value) {
  const ref = useRef(value)
  useEffect(() => { ref.current = value })
  return ref
}

export const apiErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (typeof detail?.message === 'string') return detail.message
  return error?.message || fallback
}

// Every platform 403 used to sign the operator out. A token that is valid but
// lacks a scope (platform:debug, for instance) should say so and stay signed
// in; only an expired or invalid token ends the session.
export const isScopeDenied = (error) => (
  error?.response?.status === 403
  && /scope denied/i.test(String(error?.response?.data?.detail || ''))
)

export const isSessionEnded = (error) => error?.response?.status === 403 && !isScopeDenied(error)

export const DEBUG_SCOPE = 'platform:debug'

/** True unless the session is known to lack the scope. */
export const sessionHasScope = (session, scope) => (
  !Array.isArray(session?.scopes) || session.scopes.includes(scope)
)

export function StatCard({ label, value, sub, icon: Icon }) {
  return (
    <div className="bg-brand-surface border border-brand-line rounded-xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-brand-muted font-sans uppercase tracking-wider">{label}</p>
        {Icon && <Icon size={16} className="text-brand-muted" />}
      </div>
      <p className="text-2xl font-bold text-brand-ink font-serif">{value ?? '—'}</p>
      {sub && <p className="text-xs text-brand-muted mt-1 font-sans">{sub}</p>}
    </div>
  )
}

export function TierBadge({ tier }) {
  const colors = {
    flat: 'bg-brand-accent/10 text-brand-accent border-brand-accent/20',
    payg: 'bg-brand-amber/10 text-brand-amber border-brand-amber/20',
    demo: 'bg-brand-ink/10 text-brand-ink border-brand-ink/20',
  }
  const labels = { flat: 'Flat-seat', payg: 'PAYG', demo: 'Demo' }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colors[tier] || colors.payg}`}>
      {labels[tier] || tier}
    </span>
  )
}

export function TenantTypeBadge({ type }) {
  const isDemo = type === 'demo'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${isDemo ? 'bg-brand-ink/10 text-brand-ink border-brand-ink/20' : 'bg-brand-accent/10 text-brand-accent border-brand-accent/20'}`}>
      {isDemo ? 'Demo' : 'Platform'}
    </span>
  )
}

export const tenantType = (tenant) => tenant.tenant_type || (tenant.billing_tier === 'demo' ? 'demo' : 'platform')

export function TenantExpiry({ tenant }) {
  if (!tenant.expires_at) {
    return <span className="text-brand-muted">No expiration</span>
  }
  const expiresAt = new Date(tenant.expires_at)
  const expired = expiresAt.getTime() <= Date.now()
  return (
    <time dateTime={tenant.expires_at} className={expired ? 'text-brand-rose' : 'text-brand-ink-2'}>
      {expired ? 'Expired ' : ''}{expiresAt.toLocaleString()}
    </time>
  )
}

export const formatDateTime = (value) => {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString()
}

/** "in 23 min", "2 h ago", "3 days ago" — coarse on purpose. */
export const formatRelative = (value, now = Date.now()) => {
  if (!value) return ''
  const target = new Date(value).getTime()
  if (Number.isNaN(target)) return ''
  const minutes = Math.round((target - now) / 60000)
  const size = Math.abs(minutes)
  let text
  if (size < 1) text = 'less than a minute'
  else if (size < 60) text = `${size} min`
  else if (size < 48 * 60) text = `${Math.round(size / 60)} h`
  else text = `${Math.round(size / 1440)} days`
  return minutes >= 0 ? `in ${text}` : `${text} ago`
}

export function ScopeNotice({ scope = DEBUG_SCOPE, children }) {
  return (
    <div role="status" className="flex items-start gap-3 rounded-lg border border-brand-amber/30 bg-brand-amber/5 px-4 py-3 text-sm text-brand-ink-2">
      <ShieldAlert size={16} className="mt-0.5 shrink-0 text-brand-amber" aria-hidden="true" />
      <p>
        {children || 'This needs a platform credential with the'}{' '}
        <code className="rounded bg-brand-bg-soft px-1 font-mono text-xs">{scope}</code> scope.
        Sign in with a credential that carries it to use this view.
      </p>
    </div>
  )
}

/** Copies an identifier support will paste elsewhere (tenant, request, error). */
export function CopyButton({ value, label }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? `${label} copied` : `Copy ${label}`}
      title={copied ? 'Copied' : `Copy ${label}`}
      className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-brand-muted hover:bg-brand-bg-soft hover:text-brand-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
    >
      {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
    </button>
  )
}

export function Pager({ page, total, limit, onPage, label }) {
  if (!total || total <= limit) return null
  const pages = Math.ceil(total / limit)
  return (
    <nav aria-label={label || 'Pagination'} className="flex items-center justify-between px-5 py-3 border-t border-brand-line">
      <button type="button" onClick={() => onPage(Math.max(1, page - 1))} disabled={page <= 1} className="text-sm text-brand-muted hover:text-brand-ink disabled:opacity-40 font-sans">← Prev</button>
      <span className="text-xs text-brand-muted font-sans">Page {page} of {pages} ({total} total)</span>
      <button type="button" onClick={() => onPage(Math.min(pages, page + 1))} disabled={page >= pages} className="text-sm text-brand-muted hover:text-brand-ink disabled:opacity-40 font-sans">Next →</button>
    </nav>
  )
}
