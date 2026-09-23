import React, { useCallback, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Plus, RefreshCw, Search, X } from 'lucide-react'
import {
  approvePlatformTenantTrial,
  findPlatformUsers,
  getPlatformTenant,
  getPlatformTenants,
  provisionPlatformTenant,
  updatePlatformTenant,
} from '../../api'
import { SegmentedControl } from '../../components/ui'
import TenantDetailPanel from './TenantDetailPanel'
import { ProvisionTrialTenantForm } from './TenantControls'
import {
  DEBUG_SCOPE,
  Pager,
  TenantExpiry,
  TenantTypeBadge,
  TierBadge,
  apiErrorMessage,
  isScopeDenied,
  isSessionEnded,
  sessionHasScope,
  tenantType,
  useLatest,
} from './shared'

export const TENANT_VIEWS = [
  { value: 'platform', label: 'All firms' },
  { value: 'pending', label: 'Needs approval' },
  { value: 'active', label: 'Active' },
  { value: 'trial', label: 'Trials' },
  { value: 'expiring', label: 'Ending ≤14 days' },
  { value: 'expired', label: 'Expired' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'demo', label: 'Demo' },
]

const PAGE_SIZE = 50

const tenantStatus = (tenant) => {
  if (tenant.signup_status === 'pending') return { label: 'Pending approval', text: 'text-brand-amber', dot: 'bg-brand-amber' }
  if (!tenant.is_active) return { label: 'Inactive', text: 'text-brand-rose', dot: 'bg-brand-rose' }
  if (tenant.expires_at && new Date(tenant.expires_at).getTime() <= Date.now()) {
    return { label: 'Expired', text: 'text-brand-rose', dot: 'bg-brand-rose' }
  }
  return { label: 'Active', text: 'text-brand-accent', dot: 'bg-brand-accent' }
}

// The Details button stays the row's only control: the row keeps native table
// semantics (no role or tabindex), matching every other table in the app.
export function PlatformTenantRow({ tenant: t, expanded, onToggle }) {
  const toggle = () => onToggle?.(t.id)
  const status = tenantStatus(t)

  return (
    <tr className="transition-colors hover:bg-brand-bg">
      <td className="px-4 py-3">{expanded ? <ChevronDown size={14} className="text-brand-ink" /> : <ChevronRight size={14} className="text-brand-muted" />}</td>
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-brand-ink font-sans">{t.name}</p>
        <p className="text-xs text-brand-muted">{t.domain}</p>
        {t.signup_email && <p className="text-xs text-brand-muted">{t.signup_email}</p>}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-1">
          <TierBadge tier={t.billing_tier} />
          {tenantType(t) === 'demo' && <TenantTypeBadge type="demo" />}
          {t.on_trial && tenantType(t) !== 'demo' && (
            <span className="inline-flex items-center rounded border border-brand-amber/20 bg-brand-amber/10 px-2 py-0.5 text-xs font-medium text-brand-amber">Trial</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-center text-sm text-brand-ink-2 font-sans">{t.user_count}</td>
      <td className="px-4 py-3 text-center text-sm text-brand-ink-2 font-sans">{t.requests_30d?.toLocaleString()}</td>
      <td className="px-4 py-3 text-right text-sm text-brand-ink-2 font-mono">${t.cost_usd_30d?.toFixed(2)}</td>
      <td className="px-4 py-3 text-xs text-brand-muted"><TenantExpiry tenant={t} /></td>
      <td className="px-4 py-3 text-center">
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium font-sans ${status.text}`}>
          <span className={`w-2 h-2 rounded-full ${status.dot}`} />
          {status.label}
        </span>
      </td>
      <td className="px-4 py-3 text-center">
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={`tenant-details-${t.id}`}
          onClick={toggle}
          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-sm text-xs text-brand-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent font-sans"
        >
          {expanded ? 'Close' : 'Details'}
        </button>
      </td>
    </tr>
  )
}

function UserSearchResults({ platformKey, query, onOpenTenant, onAuthError }) {
  const [users, setUsers] = useState(null)
  const [message, setMessage] = useState('')
  const callbacks = useLatest({ onAuthError })

  useEffect(() => {
    let active = true
    setUsers(null)
    setMessage('')
    findPlatformUsers(platformKey, query)
      .then((found) => { if (active) setUsers(found) })
      .catch((error) => {
        if (!active) return
        if (isSessionEnded(error)) callbacks.current.onAuthError?.()
        else if (isScopeDenied(error)) setMessage('Finding firms by a user’s address needs the platform:debug scope.')
        else setMessage(apiErrorMessage(error, 'Could not search users.'))
      })
    return () => { active = false }
  }, [platformKey, query, callbacks])

  if (message) return <p className="text-xs text-brand-muted">{message}</p>
  if (!users) return <p className="text-xs text-brand-muted">Searching logins…</p>
  if (users.length === 0) return <p className="text-xs text-brand-muted">No login matches “{query}”.</p>
  return (
    <div className="rounded-xl border border-brand-line bg-brand-surface p-3">
      <p className="text-xs font-semibold text-brand-ink">Logins matching “{query}”</p>
      <ul className="mt-2 divide-y divide-brand-line">
        {users.map((user) => (
          <li key={user.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-xs">
            <span className="min-w-0">
              <span className="font-medium text-brand-ink">{user.email}</span>
              {user.full_name && <span className="text-brand-muted"> · {user.full_name}</span>}
              <span className="text-brand-muted"> · {user.role}{user.is_active ? '' : ' · not active'}</span>
            </span>
            <button type="button" onClick={() => onOpenTenant(user.tenant_id)} className="font-medium text-brand-accent hover:underline">
              Open {user.tenant_name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * The firm directory. Search, lifecycle view, page and the open firm live in
 * the URL (owned by the page), so a refresh or a shared link lands in the same
 * place and every other tab can open a firm here.
 */
export default function TenantsTab({
  platformKey,
  session,
  llmConfig,
  view,
  query,
  page,
  expandedId,
  onNavigate,
  onOpenTenant,
  onOpenLogs,
  onAuthError,
}) {
  const [tenants, setTenants] = useState([])
  const [counts, setCounts] = useState(null)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState(query)
  const [showRegister, setShowRegister] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailState, setDetailState] = useState('idle')
  const callbacks = useLatest({ onAuthError, onNavigate })
  const canDebug = sessionHasScope(session, DEBUG_SCOPE)

  // Follow the URL when it changes elsewhere (a firm opened by id, Clear), but
  // keep what is being typed: the committed query is trimmed, and copying it
  // back would eat the space between two words mid-typing.
  useEffect(() => {
    setDraft((current) => (current.trim() === query ? current : query))
  }, [query])

  // Commit the search box to the URL a moment after typing stops.
  useEffect(() => {
    if (draft.trim() === query) return undefined
    const timer = setTimeout(() => callbacks.current.onNavigate({ q: draft.trim(), page: 1 }, { replace: true }), 300)
    return () => clearTimeout(timer)
  }, [draft, query, callbacks])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { status: view, limit: PAGE_SIZE }
      if (query) params.q = query
      const data = await getPlatformTenants(platformKey, page, params)
      setTenants(data.tenants || [])
      setCounts(data.counts || null)
      setTotal(data.total || 0)
    } catch (loadError) {
      if (isSessionEnded(loadError)) { callbacks.current.onAuthError?.(); return }
      setError(apiErrorMessage(loadError, 'Could not load firms.'))
    } finally {
      setLoading(false)
    }
  }, [platformKey, view, query, page, callbacks])

  useEffect(() => { load() }, [load])

  const loadDetail = useCallback(async (id) => {
    const data = await getPlatformTenant(platformKey, id)
    const merged = { ...data, ...(data.tenant || {}) }
    setDetail(merged)
    setTenants((previous) => previous.map((item) => (item.id === id ? { ...item, ...(data.tenant || {}) } : item)))
    return merged
  }, [platformKey])

  useEffect(() => {
    if (!expandedId) { setDetail(null); setDetailState('idle'); return undefined }
    let active = true
    setDetailState('loading')
    loadDetail(expandedId)
      .then(() => { if (active) setDetailState('ready') })
      .catch((detailError) => {
        if (!active) return
        if (isSessionEnded(detailError)) { callbacks.current.onAuthError?.(); return }
        setDetailState(detailError?.response?.status === 404 ? 'missing' : 'failed')
      })
    return () => { active = false }
  }, [expandedId, loadDetail, callbacks])

  const refreshOpenTenant = async () => {
    if (!expandedId) return
    await loadDetail(expandedId)
    load()
  }

  const patchTenant = async (payload) => {
    const result = await updatePlatformTenant(platformKey, expandedId, payload)
    await refreshOpenTenant()
    return result
  }

  const approveTenant = async (payload) => {
    const approved = await approvePlatformTenantTrial(platformKey, expandedId, payload)
    await refreshOpenTenant()
    return approved
  }

  // Routing profile, plan and Background Automations save through their own
  // requests; fold what they saved into the open detail so the form is clean.
  const mergeDetail = (id, changes) => {
    if (id !== expandedId) return
    setDetail((previous) => {
      if (!previous) return previous
      const next = { ...previous }
      for (const key of ['llm_config', 'assistant_config', 'module_config']) {
        if (changes[key]) next[key] = { ...(previous[key] || {}), ...changes[key] }
      }
      return next
    })
  }

  const provision = async (payload) => {
    const created = await provisionPlatformTenant(platformKey, payload)
    load()
    return created
  }

  const toggle = (id) => onNavigate({ tenant: expandedId === id ? '' : id })
  const expandedInList = tenants.some((item) => item.id === expandedId)
  const looksLikeEmail = query.includes('@')

  const detailPanel = detail && detailState === 'ready' && (
    <TenantDetailPanel
      key={detail.id}
      tenant={detail}
      detail={detail}
      platformKey={platformKey}
      session={session}
      llmConfig={llmConfig}
      onPatch={patchTenant}
      onApprove={approveTenant}
      onUpdate={mergeDetail}
      onDetailChange={setDetail}
      onRefresh={refreshOpenTenant}
      onError={setError}
      onAuthError={onAuthError}
      onOpenLogs={onOpenLogs}
    />
  )

  const detailStatus = detailState === 'loading'
    ? <div className="flex justify-center py-4"><div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-accent border-t-transparent" role="status" aria-label="Loading firm" /></div>
    : detailState === 'missing'
      ? <p className="text-sm text-brand-rose">This firm no longer exists.</p>
      : detailState === 'failed'
        ? <p className="text-sm text-brand-rose">Failed to load this firm.</p>
        : null

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-bold text-brand-ink">Firms</h1>
          <p className="mt-1 text-sm text-brand-muted">Search by firm, domain or tenant ID — or paste a user’s email to find their firm.</p>
        </div>
        <button
          type="button"
          aria-expanded={showRegister}
          onClick={() => setShowRegister((open) => !open)}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-ink px-4 py-2 text-sm font-medium text-white"
        >
          <Plus size={15} aria-hidden="true" /> {showRegister ? 'Hide registration' : 'Register customer'}
        </button>
      </div>

      {showRegister && <ProvisionTrialTenantForm onProvision={provision} />}

      <div className="flex flex-wrap items-center gap-3">
        <label className="relative min-w-0 flex-1 basis-72">
          <span className="sr-only">Search firms</span>
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" aria-hidden="true" />
          <input
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Firm, domain, tenant ID or user email"
            className="w-full rounded-lg border border-brand-line bg-brand-surface py-2 pl-9 pr-9 text-sm font-sans focus:outline-none focus:ring-2 focus:ring-brand-accent"
          />
          {draft && (
            <button type="button" aria-label="Clear search" onClick={() => { setDraft(''); onNavigate({ q: '', page: 1 }, { replace: true }) }} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-brand-muted hover:text-brand-ink">
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </label>
        <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line px-3 py-2 text-xs font-semibold text-brand-ink disabled:opacity-50">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden="true" /> Refresh
        </button>
      </div>

      <SegmentedControl
        label="Firm lifecycle view"
        value={view}
        onChange={(next) => onNavigate({ view: next, page: 1 })}
        items={TENANT_VIEWS.map((item) => ({ ...item, count: counts ? counts[item.value] : null }))}
      />

      {looksLikeEmail && (
        canDebug
          ? <UserSearchResults platformKey={platformKey} query={query} onOpenTenant={onOpenTenant} onAuthError={onAuthError} />
          : <p className="text-xs text-brand-muted">Finding a firm from a user’s address needs the platform:debug scope.</p>
      )}

      {error && <p role="alert" className="rounded-lg border border-brand-rose/20 bg-brand-rose/10 px-4 py-3 text-sm text-brand-rose">{error}</p>}

      {expandedId && !expandedInList && (detailPanel || detailStatus) && (
        <section aria-label="Open firm" id={`tenant-details-${expandedId}`} className="rounded-xl border border-brand-line bg-brand-bg-soft p-4">
          <div className="mb-2 flex justify-end">
            <button type="button" onClick={() => onNavigate({ tenant: '' })} className="text-xs font-medium text-brand-accent hover:underline">Close</button>
          </div>
          {detailPanel || detailStatus}
        </section>
      )}

      <div className="overflow-hidden rounded-xl border border-brand-line bg-brand-surface shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Firms</caption>
            <thead className="border-b border-brand-line bg-brand-bg-soft">
              <tr className="text-xs uppercase tracking-wider text-brand-muted font-sans">
                <th scope="col" className="px-4 py-3 text-left"><span className="sr-only">Expanded</span></th>
                <th scope="col" className="px-4 py-3 text-left">Firm</th>
                <th scope="col" className="px-4 py-3 text-left">Plan</th>
                <th scope="col" className="px-4 py-3 text-center">Users</th>
                <th scope="col" className="px-4 py-3 text-center">Requests (30d)</th>
                <th scope="col" className="px-4 py-3 text-right">Cost (30d)</th>
                <th scope="col" className="px-4 py-3 text-left">Access ends</th>
                <th scope="col" className="px-4 py-3 text-center">Status</th>
                <th scope="col" className="px-4 py-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-line">
              {tenants.map((tenant) => (
                <React.Fragment key={tenant.id}>
                  <PlatformTenantRow tenant={tenant} expanded={expandedId === tenant.id} onToggle={toggle} />
                  {expandedId === tenant.id && (
                    <tr id={`tenant-details-${tenant.id}`}>
                      <td colSpan={9} className="bg-brand-bg-soft px-4 py-4">
                        {detailPanel || detailStatus}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {!loading && tenants.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-5 py-10 text-center text-sm text-brand-muted">
                    {query ? `No firms match “${query}” in this view.` : 'No firms in this view.'}
                  </td>
                </tr>
              )}
              {loading && tenants.length === 0 && (
                <tr><td colSpan={9} className="px-5 py-10 text-center text-sm text-brand-muted">Loading firms…</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager page={page} total={total} limit={PAGE_SIZE} onPage={(next) => onNavigate({ page: next })} label="Firm pages" />
      </div>
    </div>
  )
}
