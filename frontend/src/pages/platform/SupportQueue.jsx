import { useCallback, useEffect, useState } from 'react'
import { LifeBuoy, RefreshCw } from 'lucide-react'
import { getPlatformSupportQueue, getPublicSupportPolicy, updatePlatformSupportRequest } from '../../api'
import { SegmentedControl } from '../../components/ui'
import {
  ScopeNotice,
  apiErrorMessage,
  formatDateTime,
  formatRelative,
  isScopeDenied,
  isSessionEnded,
  useLatest,
} from './shared'

const STATUS_VIEWS = [
  { value: 'active', label: 'Needs work' },
  { value: 'open', label: 'Open' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'mitigated', label: 'Mitigated' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
]

const SEVERITY_CLASS = {
  S1: 'bg-brand-rose text-white',
  S2: 'bg-brand-amber text-white',
  S3: 'bg-brand-ink/10 text-brand-ink',
  S4: 'bg-brand-bg-soft text-brand-muted border border-brand-line',
}

const STATUS_CLASS = {
  open: 'border-brand-amber/30 bg-brand-amber/10 text-brand-amber',
  acknowledged: 'border-blue-200 bg-blue-50 text-blue-800',
  mitigated: 'border-indigo-200 bg-indigo-50 text-indigo-800',
  resolved: 'border-brand-accent/20 bg-brand-accent/10 text-brand-accent',
}

const countFor = (counts, view) => {
  if (!counts) return null
  if (view === 'active') return (counts.open || 0) + (counts.acknowledged || 0) + (counts.mitigated || 0)
  if (view === 'all') return ['open', 'acknowledged', 'mitigated', 'resolved'].reduce((sum, key) => sum + (counts[key] || 0), 0)
  return counts[view] ?? null
}

export const isSupportOverdue = (item, now = Date.now()) => (
  item.status === 'open'
  && (Boolean(item.overdue) || new Date(item.acknowledgement_due_at).getTime() <= now)
)

function SupportClock({ item, now }) {
  if (item.status === 'resolved') {
    return <span>Resolved {formatDateTime(item.resolved_at)}</span>
  }
  if (item.status !== 'open') {
    return <span>Acknowledged {formatRelative(item.acknowledged_at, now)}</span>
  }
  if (isSupportOverdue(item, now)) {
    return (
      <span className="font-semibold text-brand-rose">
        Acknowledgement overdue · was due {formatRelative(item.acknowledgement_due_at, now)}
      </span>
    )
  }
  return <span>Acknowledge {formatRelative(item.acknowledgement_due_at, now)}</span>
}

// Status moves only forward: open → acknowledged → (mitigated) → resolved.
// The API also records the escalation level with each move, so the current
// level is always sent to avoid silently resetting it to zero.
function SupportActions({ item, onUpdate }) {
  const [escalation, setEscalation] = useState(item.escalation_level || 0)
  const [resolving, setResolving] = useState(false)
  const [summary, setSummary] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { setEscalation(item.escalation_level || 0) }, [item.escalation_level])

  if (item.status === 'resolved') return null

  const move = async (status) => {
    setBusy(true)
    setError('')
    try {
      await onUpdate(item, {
        status,
        escalation_level: Number(escalation),
        ...(status === 'resolved' ? { resolution_summary: summary.trim() || null } : {}),
      })
      setResolving(false)
      setSummary('')
    } catch (updateError) {
      setError(apiErrorMessage(updateError, 'Could not update this request.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {item.status === 'open' && (
          <button type="button" disabled={busy} onClick={() => move('acknowledged')} className="rounded-lg bg-brand-ink px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
            Acknowledge
          </button>
        )}
        {item.status === 'acknowledged' && (
          <button type="button" disabled={busy} onClick={() => move('mitigated')} className="rounded-lg border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink disabled:opacity-50">
            Mark mitigated
          </button>
        )}
        {item.status !== 'open' && !resolving && (
          <button type="button" disabled={busy} onClick={() => setResolving(true)} className="rounded-lg border border-brand-accent/30 px-3 py-1.5 text-xs font-semibold text-brand-accent disabled:opacity-50">
            Resolve…
          </button>
        )}
        <label className="flex items-center gap-1.5 text-xs text-brand-muted">
          Escalation
          <select
            value={escalation}
            onChange={(event) => setEscalation(event.target.value)}
            className="rounded border border-brand-line bg-brand-surface px-1.5 py-1 text-xs text-brand-ink"
          >
            {[0, 1, 2, 3, 4].map((level) => <option key={level} value={level}>{level}</option>)}
          </select>
        </label>
        <span className="text-[11px] text-brand-muted">Saved with the next status change.</span>
      </div>
      {resolving && (
        <form
          onSubmit={(event) => { event.preventDefault(); move('resolved') }}
          className="rounded-lg border border-brand-line bg-brand-bg p-3"
        >
          <label className="block">
            <span className="text-xs font-medium text-brand-muted">Resolution summary — the firm&apos;s administrators see this</span>
            <textarea
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              rows={2}
              maxLength={4000}
              className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm"
            />
          </label>
          <div className="mt-2 flex gap-2">
            <button type="submit" disabled={busy} className="rounded-lg bg-brand-ink px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
              {busy ? 'Resolving…' : 'Resolve request'}
            </button>
            <button type="button" onClick={() => setResolving(false)} className="rounded-lg border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink">Cancel</button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="text-xs text-brand-rose">{error}</p>}
    </div>
  )
}

/**
 * Support requests firm administrators file from Admin > Support. With a
 * `tenantId` it becomes that firm's history inside the tenant panel.
 */
export default function SupportQueue({ platformKey, tenantId, onOpenTenant, onAuthError, onCountsChange }) {
  const [view, setView] = useState(tenantId ? 'all' : 'active')
  const [severity, setSeverity] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [scopeDenied, setScopeDenied] = useState(false)
  const [policy, setPolicy] = useState({})
  const [now, setNow] = useState(() => Date.now())
  const callbacks = useLatest({ onAuthError, onCountsChange })

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    let active = true
    getPublicSupportPolicy()
      .then((next) => {
        if (!active) return
        setPolicy(Object.fromEntries((next?.severities || []).map((item) => [item.severity, item])))
      })
      .catch(() => { /* escalation guidance is optional */ })
    return () => { active = false }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { status: view, limit: 100 }
      if (severity) params.severity = severity
      if (tenantId) params.tenant_id = tenantId
      const next = await getPlatformSupportQueue(platformKey, params)
      setData(next)
      setNow(Date.now())
      if (!tenantId) callbacks.current.onCountsChange?.(next.counts)
    } catch (loadError) {
      if (isSessionEnded(loadError)) { callbacks.current.onAuthError?.(); return }
      if (isScopeDenied(loadError)) { setScopeDenied(true); return }
      setError(apiErrorMessage(loadError, 'Could not load support requests.'))
    } finally {
      setLoading(false)
    }
  }, [platformKey, view, severity, tenantId, callbacks])

  useEffect(() => { load() }, [load])

  const update = async (item, payload) => {
    try {
      await updatePlatformSupportRequest(platformKey, item.tenant_id, item.id, payload)
    } catch (updateError) {
      if (isSessionEnded(updateError)) callbacks.current.onAuthError?.()
      throw updateError
    }
    await load()
  }

  if (scopeDenied) return <ScopeNotice scope="platform:read">The support queue needs a credential with the</ScopeNotice>

  const items = data?.items || []
  const counts = data?.counts

  return (
    <section aria-labelledby={tenantId ? `support-${tenantId}` : 'support-queue'} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={tenantId ? `support-${tenantId}` : 'support-queue'} className={tenantId ? 'text-xs font-bold uppercase tracking-wider text-brand-ink' : 'font-serif text-xl font-bold text-brand-ink'}>
            {tenantId ? 'Support requests' : 'Customer support queue'}
          </h2>
          {!tenantId && (
            <p className="mt-1 max-w-3xl text-sm text-brand-muted">
              Requests firm administrators file from Admin → Support. The acknowledgement clock runs from filing — continuously for S1, covered hours for S2–S4.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {data?.checked_at && <span className="text-xs text-brand-muted">Updated {formatRelative(data.checked_at, now)}</span>}
          <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink disabled:opacity-50">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden="true" /> Refresh
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Support request status"
          value={view}
          onChange={setView}
          items={STATUS_VIEWS.map((item) => ({ ...item, count: countFor(counts, item.value) }))}
        />
        <label className="flex items-center gap-2 text-xs text-brand-muted">
          Severity
          <select value={severity} onChange={(event) => setSeverity(event.target.value)} className="rounded-lg border border-brand-line bg-brand-surface px-2 py-1.5 text-xs text-brand-ink">
            <option value="">All</option>
            {['S1', 'S2', 'S3', 'S4'].map((level) => <option key={level} value={level}>{level}</option>)}
          </select>
        </label>
        {counts?.overdue > 0 && (
          <span className="rounded-full bg-brand-rose/10 px-2.5 py-1 text-xs font-semibold text-brand-rose">
            {counts.overdue} overdue
          </span>
        )}
      </div>

      {error && <p role="alert" className="rounded-lg border border-brand-rose/20 bg-brand-rose/10 px-4 py-3 text-sm text-brand-rose">{error}</p>}

      {!loading && items.length === 0 && !error && (
        <div className="rounded-xl border border-brand-line bg-brand-surface p-8 text-center">
          <LifeBuoy size={24} className="mx-auto text-brand-muted" aria-hidden="true" />
          <p className="mt-2 text-sm text-brand-muted">
            {view === 'active' ? 'No open support requests.' : 'No support requests match this view.'}
          </p>
        </div>
      )}

      <ul className="space-y-3">
        {items.map((item) => {
          const overdue = isSupportOverdue(item, now)
          const guidance = policy[item.severity]
          return (
            <li key={item.id} className={`rounded-xl border bg-brand-surface p-4 shadow-sm ${overdue ? 'border-brand-rose/40' : 'border-brand-line'}`}>
              <div className="flex flex-wrap items-start gap-2">
                <span className={`inline-flex rounded px-1.5 py-0.5 text-[11px] font-bold ${SEVERITY_CLASS[item.severity] || SEVERITY_CLASS.S4}`} title={guidance?.definition}>{item.severity}</span>
                <h3 className="min-w-0 flex-1 text-sm font-semibold text-brand-ink">{item.subject}</h3>
                <span className={`rounded border px-2 py-0.5 text-[11px] font-medium ${STATUS_CLASS[item.status] || STATUS_CLASS.open}`}>{item.status}</span>
              </div>
              <p className="mt-1 text-xs text-brand-muted">
                {!tenantId && (
                  <>
                    {onOpenTenant ? (
                      <button type="button" onClick={() => onOpenTenant(item.tenant_id)} className="font-medium text-brand-accent hover:underline">{item.tenant_name}</button>
                    ) : item.tenant_name}
                    {' · '}
                  </>
                )}
                <a href={`mailto:${item.requested_by_email}`} className="hover:underline">{item.requested_by_email}</a>
                {' · filed '}{formatDateTime(item.created_at)}
                {item.channel ? ` · via ${item.channel}` : ''}
                {item.escalation_level ? ` · escalation ${item.escalation_level}` : ''}
              </p>
              <p className="mt-1 text-xs"><SupportClock item={item} now={now} /></p>
              <p className="mt-2 whitespace-pre-line text-sm text-brand-ink-2">{item.safe_summary}</p>
              {overdue && guidance?.escalation && (
                <p className="mt-2 rounded-lg bg-brand-rose/5 px-3 py-2 text-xs text-brand-ink-2">
                  <span className="font-semibold">Policy:</span> {guidance.escalation}
                </p>
              )}
              {item.status === 'resolved' && item.resolution_summary && (
                <p className="mt-2 rounded-lg bg-brand-accent/5 px-3 py-2 text-xs text-brand-ink-2">
                  <span className="font-semibold">Resolution:</span> {item.resolution_summary}
                </p>
              )}
              {item.operator_actor_id && <p className="mt-1 text-[11px] text-brand-muted">Last handled by {item.operator_actor_id}</p>}
              <SupportActions item={item} onUpdate={update} />
            </li>
          )
        })}
      </ul>
      {data && data.total > items.length && (
        <p className="text-xs text-brand-muted">Showing {items.length} of {data.total}. Narrow the view to see the rest.</p>
      )}
    </section>
  )
}
