import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { getPlatformOperatorAudit } from '../../api'
import {
  Pager,
  ScopeNotice,
  apiErrorMessage,
  formatDateTime,
  isScopeDenied,
  isSessionEnded,
  useLatest,
} from './shared'

const ACTION_LABELS = {
  'tenant.provisioned': 'Customer registered',
  'tenant.trial_approved': 'Registration approved',
  'tenant.updated': 'Firm settings changed',
  'trial.revoked': 'Trial revoked and login released',
  'support.acknowledged': 'Support request acknowledged',
  'support.mitigated': 'Support request mitigated',
  'support.resolved': 'Support request resolved',
  'platform.error.resolved': 'Error marked handled',
  'platform.session.issued': 'Console sign-in',
  'platform.request': 'API request',
  'documents.reindex.queued': 'Document reindex queued',
  'documents.reindex.previewed': 'Document reindex previewed',
}

const PAGE_SIZE = 25

const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/

const formatValue = (value) => {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '(none)'
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'string' && ISO_TIMESTAMP.test(value)) return formatDateTime(value)
  return String(value)
}

/** One line per change, readable without opening raw JSON. */
export const summarizeAuditMetadata = (entry) => {
  const metadata = entry?.metadata || {}
  if (metadata.changes && typeof metadata.changes === 'object') {
    return Object.entries(metadata.changes).map(([field, change]) => (
      change && typeof change === 'object' && ('from' in change || 'to' in change)
        ? `${field}: ${formatValue(change.from)} → ${formatValue(change.to)}`
        : `${field}: ${formatValue(change)}`
    ))
  }
  return Object.entries(metadata)
    .filter(([key]) => !['tenant_id', 'tenant_name', 'token_jti'].includes(key))
    .slice(0, 6)
    .map(([key, value]) => `${key}: ${formatValue(value)}`)
}

/**
 * What operators did, newest first. With `tenantId` it is that firm's history,
 * including support and error actions recorded against their own resources.
 */
export default function OperatorAuditLog({ platformKey, tenantId, canDebug, onAuthError }) {
  const [days, setDays] = useState(tenantId ? 90 : 7)
  const [actionsOnly, setActionsOnly] = useState(true)
  const [actor, setActor] = useState('')
  const [actorDraft, setActorDraft] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(Boolean(canDebug))
  const [error, setError] = useState('')
  const [scopeDenied, setScopeDenied] = useState(false)
  const callbacks = useLatest({ onAuthError })

  const load = useCallback(async () => {
    if (!canDebug) return
    setLoading(true)
    setError('')
    try {
      const params = { page, limit: PAGE_SIZE, days, exclude_requests: actionsOnly }
      if (tenantId) params.tenant_id = tenantId
      if (actor.trim()) params.actor_id = actor.trim()
      setData(await getPlatformOperatorAudit(platformKey, params))
    } catch (loadError) {
      if (isSessionEnded(loadError)) { callbacks.current.onAuthError?.(); return }
      if (isScopeDenied(loadError)) { setScopeDenied(true); return }
      setError(apiErrorMessage(loadError, 'Could not load the audit trail.'))
    } finally {
      setLoading(false)
    }
  }, [platformKey, tenantId, canDebug, page, days, actionsOnly, actor, callbacks])

  useEffect(() => { load() }, [load])

  if (!canDebug || scopeDenied) {
    return <ScopeNotice>The operator audit trail needs a credential with the</ScopeNotice>
  }

  const entries = data?.entries || []
  const applyActor = () => {
    if (actorDraft.trim() === actor) return
    setActor(actorDraft.trim())
    setPage(1)
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-brand-muted">
          Period
          <select value={days} onChange={(event) => { setDays(Number(event.target.value)); setPage(1) }} className="rounded-lg border border-brand-line bg-brand-surface px-2 py-1.5 text-xs text-brand-ink">
            {[7, 30, 90, 365].map((value) => <option key={value} value={value}>Last {value} days</option>)}
          </select>
        </label>
        {!tenantId && (
          <form onSubmit={(event) => { event.preventDefault(); applyActor() }}>
            <label className="flex items-center gap-2 text-xs text-brand-muted">
              Operator
              <input value={actorDraft} onChange={(event) => setActorDraft(event.target.value)} onBlur={applyActor} placeholder="operator id, then Enter" className="w-44 rounded-lg border border-brand-line bg-brand-surface px-2 py-1.5 text-xs text-brand-ink" />
            </label>
          </form>
        )}
        <label className="flex items-center gap-1.5 text-xs text-brand-muted">
          <input type="checkbox" checked={!actionsOnly} onChange={(event) => { setActionsOnly(!event.target.checked); setPage(1) }} />
          Include every API request
        </label>
        <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink disabled:opacity-50">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden="true" /> Refresh
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-brand-rose">{error}</p>}
      <div className="overflow-hidden rounded-xl border border-brand-line bg-brand-surface">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">{tenantId ? 'Operator history for this firm' : 'Operator audit trail'}</caption>
            <thead className="border-b border-brand-line bg-brand-bg-soft uppercase tracking-wider text-brand-muted">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">When</th>
                <th scope="col" className="px-4 py-2 font-medium">Action</th>
                <th scope="col" className="px-4 py-2 font-medium">Operator</th>
                {!tenantId && <th scope="col" className="px-4 py-2 font-medium">Target</th>}
                <th scope="col" className="px-4 py-2 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-line">
              {entries.map((entry) => (
                <tr key={entry.id} className="align-top">
                  <td className="whitespace-nowrap px-4 py-2.5 text-brand-muted">{formatDateTime(entry.created_at)}</td>
                  <td className="px-4 py-2.5">
                    <p className="font-medium text-brand-ink">{ACTION_LABELS[entry.action] || entry.action}</p>
                    <p className="font-mono text-[10px] text-brand-muted">{entry.action}</p>
                  </td>
                  <td className="px-4 py-2.5 text-brand-ink-2">
                    <p>{entry.actor_id || '—'}</p>
                    <p className="text-[10px] text-brand-muted">{entry.actor_type}</p>
                  </td>
                  {!tenantId && (
                    <td className="max-w-[220px] px-4 py-2.5 text-brand-muted">
                      <p className="truncate font-mono" title={entry.resource_id || ''}>{entry.resource_id || '—'}</p>
                      <p className="text-[10px]">{entry.resource_type}</p>
                    </td>
                  )}
                  <td className="px-4 py-2.5 text-brand-ink-2">
                    <ul className="space-y-0.5">
                      {summarizeAuditMetadata(entry).map((line) => <li key={line} className="break-words">{line}</li>)}
                    </ul>
                  </td>
                </tr>
              ))}
              {!loading && entries.length === 0 && (
                <tr><td colSpan={tenantId ? 4 : 5} className="px-4 py-8 text-center text-sm text-brand-muted">No operator actions in this period.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager page={page} total={data?.total || 0} limit={PAGE_SIZE} onPage={setPage} label="Audit trail pages" />
      </div>
    </div>
  )
}
