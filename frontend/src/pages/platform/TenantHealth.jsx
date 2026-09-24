import { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, FileText, RefreshCw, Users } from 'lucide-react'
import { getPlatformTenantDiagnostics, getPlatformTenantLogs } from '../../api'
import { ErrorDetailLoader, errorSeverityClass } from './ErrorDetail'
import {
  ScopeNotice,
  StatCard,
  apiErrorMessage,
  formatDateTime,
  formatRelative,
  isScopeDenied,
  isSessionEnded,
  useLatest,
} from './shared'

const WINDOWS = [
  { hours: 24, label: 'Last 24 hours' },
  { hours: 168, label: 'Last 7 days' },
  { hours: 720, label: 'Last 30 days' },
]

function Panel({ title, children, empty }) {
  return (
    <section className="rounded-xl border border-brand-line bg-brand-surface">
      <h5 className="border-b border-brand-line px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-brand-ink">{title}</h5>
      {children || <p className="px-4 py-4 text-xs text-brand-muted">{empty}</p>}
    </section>
  )
}

/**
 * "Is this firm healthy?" in one place: failure rate, what is failing, broken
 * integrations and work that never finished — the checks the troubleshooting
 * runbook does by hand with curl.
 */
export default function TenantHealth({ platformKey, tenantId, canDebug, onAuthError, onOpenLogs }) {
  const [hours, setHours] = useState(24)
  const [data, setData] = useState(null)
  const [errors, setErrors] = useState([])
  const [openError, setOpenError] = useState(null)
  const [loading, setLoading] = useState(Boolean(canDebug))
  const [failure, setFailure] = useState('')
  const [scopeDenied, setScopeDenied] = useState(false)
  const callbacks = useLatest({ onAuthError })

  const load = useCallback(async () => {
    if (!canDebug) return
    setLoading(true)
    setFailure('')
    try {
      const days = Math.max(1, Math.round(hours / 24))
      const [diagnostics, recent] = await Promise.all([
        getPlatformTenantDiagnostics(platformKey, tenantId, hours),
        getPlatformTenantLogs(platformKey, tenantId, { unresolved_only: true, days, limit: 10 }),
      ])
      setData(diagnostics)
      setErrors(recent?.errors || [])
    } catch (error) {
      if (isSessionEnded(error)) { callbacks.current.onAuthError?.(); return }
      if (isScopeDenied(error)) { setScopeDenied(true); return }
      setFailure(apiErrorMessage(error, 'Could not load diagnostics.'))
    } finally {
      setLoading(false)
    }
  }, [platformKey, tenantId, hours, canDebug, callbacks])

  useEffect(() => { load() }, [load])

  if (!canDebug || scopeDenied) {
    return <ScopeNotice>Tenant health shows failing endpoints, stuck jobs and error details, so it needs a credential with the</ScopeNotice>
  }

  const bySeverity = data?.errors_by_severity || {}
  const errorCount = Object.values(bySeverity).reduce((sum, count) => sum + count, 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-xs text-brand-muted">
          Window
          <select value={hours} onChange={(event) => setHours(Number(event.target.value))} className="rounded-lg border border-brand-line bg-brand-surface px-2 py-1.5 text-xs text-brand-ink">
            {WINDOWS.map((window) => <option key={window.hours} value={window.hours}>{window.label}</option>)}
          </select>
        </label>
        <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink disabled:opacity-50">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden="true" /> Refresh
        </button>
        {onOpenLogs && (
          <button type="button" onClick={() => onOpenLogs(tenantId)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink">
            <FileText size={13} aria-hidden="true" /> All error logs
          </button>
        )}
      </div>

      {failure && <p role="alert" className="text-sm text-brand-rose">{failure}</p>}
      {loading && !data && <p className="text-sm text-brand-muted">Loading diagnostics…</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Requests" value={data.requests.toLocaleString()} sub={WINDOWS.find((w) => w.hours === data.window_hours)?.label} icon={Activity} />
            <StatCard label="Server errors" value={`${(data.error_rate * 100).toFixed(1)}%`} sub="of requests returned 5xx" icon={AlertTriangle} />
            <StatCard label="Unresolved errors" value={data.unresolved_errors} sub={`${errorCount} logged in window`} icon={AlertTriangle} />
            <StatCard
              label="Active users"
              value={data.active_users}
              sub={data.last_activity_at ? `Last request ${formatRelative(data.last_activity_at)}` : 'No requests in the log retention window'}
              icon={Users}
            />
          </div>
          {!data.is_active && (
            <p className="rounded-lg border border-brand-rose/20 bg-brand-rose/5 px-3 py-2 text-xs text-brand-ink-2">
              The firm is deactivated, so every request its users make is refused.
            </p>
          )}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Panel title="Failing endpoints (4xx and 5xx)" empty="Nothing failing in this window.">
              {data.top_failing_endpoints.length > 0 && (
                <table className="w-full text-xs">
                  <caption className="sr-only">Failing endpoints</caption>
                  <thead className="text-left text-brand-muted">
                    <tr><th scope="col" className="px-4 py-2 font-medium">Endpoint</th><th scope="col" className="px-4 py-2 text-right font-medium">Status</th><th scope="col" className="px-4 py-2 text-right font-medium">Count</th></tr>
                  </thead>
                  <tbody className="divide-y divide-brand-line">
                    {data.top_failing_endpoints.map((row) => (
                      <tr key={`${row.endpoint}-${row.status_code}`}>
                        <td className="max-w-[280px] truncate px-4 py-2 font-mono text-brand-ink-2" title={row.endpoint}>{row.endpoint}</td>
                        <td className={`px-4 py-2 text-right font-mono ${row.status_code >= 500 ? 'text-brand-rose' : 'text-brand-amber'}`}>{row.status_code}</td>
                        <td className="px-4 py-2 text-right text-brand-ink">{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>

            <Panel title="Failed integration syncs" empty="No failed syncs in this window.">
              {data.failed_sync_runs.length > 0 && (
                <ul className="divide-y divide-brand-line">
                  {data.failed_sync_runs.map((run) => (
                    <li key={run.id} className="px-4 py-2.5 text-xs">
                      <p className="font-medium text-brand-ink">{run.provider} · {run.job_type} · <span className="text-brand-rose">{run.status}</span></p>
                      <p className="text-brand-muted">{formatDateTime(run.started_at)} · {run.items_ok ?? 0} ok, {run.items_failed ?? 0} failed</p>
                      {run.error_summary && <p className="mt-1 break-words text-brand-ink-2">{run.error_summary}</p>}
                      {/invalid_grant/i.test(run.error_summary || '') && (
                        <p className="mt-1 text-brand-amber">The firm needs to reconnect this integration (its grant was revoked or expired).</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <Panel title="Stuck background work (untouched 15+ minutes)" empty="No stuck jobs.">
            {data.stuck_jobs.length > 0 && (
              <ul className="divide-y divide-brand-line">
                {data.stuck_jobs.map((job) => (
                  <li key={job.id} className="px-4 py-2.5 text-xs">
                    <p className="font-medium text-brand-ink">{job.kind} · {job.status} · attempt {job.attempts}/{job.max_attempts}</p>
                    <p className="text-brand-muted">Last updated {formatRelative(job.updated_at)}</p>
                    {job.last_error && <p className="mt-1 break-words text-brand-ink-2">{job.last_error}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Unresolved errors" empty="No unresolved errors in this window.">
            {errors.length > 0 && (
              <ul className="divide-y divide-brand-line">
                {errors.map((error) => (
                  <li key={error.id} className="px-4 py-2.5 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${errorSeverityClass(error.severity)}`}>{error.severity}</span>
                      <span className="min-w-0 flex-1 truncate text-brand-ink" title={error.message}>{error.message}</span>
                      <span className="text-brand-muted">{formatRelative(error.created_at)}</span>
                      <button
                        type="button"
                        aria-expanded={openError === error.id}
                        onClick={() => setOpenError(openError === error.id ? null : error.id)}
                        className="font-medium text-brand-accent hover:underline"
                      >
                        {openError === error.id ? 'Hide' : 'Details'}
                      </button>
                    </div>
                    {error.endpoint && <p className="mt-0.5 font-mono text-brand-muted">{error.method} {error.endpoint}</p>}
                    {openError === error.id && (
                      <div className="mt-2">
                        <ErrorDetailLoader
                          platformKey={platformKey}
                          errorId={error.id}
                          tenantId={tenantId}
                          onAuthError={onAuthError}
                          onResolved={(updated) => { if (updated.is_resolved) { setOpenError(null); load() } }}
                        />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
