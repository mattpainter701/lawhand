import React, { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, Globe, Zap } from 'lucide-react'
import {
  getPlatformAccessLogs,
  getPlatformAccessLogsSummary,
  getPlatformLogs,
  getPlatformLogsSummary,
  getPlatformTenantLogsSummary,
  getPlatformTenants,
} from '../../api'
import { ErrorDetailLoader, errorSeverityClass } from './ErrorDetail'
import {
  DEBUG_SCOPE,
  Pager,
  StatCard,
  apiErrorMessage,
  formatDateTime,
  isSessionEnded,
  sessionHasScope,
  useLatest,
} from './shared'

const PAGE_SIZE = 50

/** Group exact status codes ("200", "404", …) into 2xx/3xx/4xx/5xx totals. */
export const statusClassTotals = (byStatus = {}) => Object.entries(byStatus).reduce((totals, [code, count]) => {
  const bucket = `${String(code).charAt(0)}xx`
  totals[bucket] = (totals[bucket] || 0) + (Number(count) || 0)
  return totals
}, {})

const statusColor = (code) => {
  if (code >= 500) return 'text-brand-rose'
  if (code >= 400) return 'text-brand-amber'
  if (code >= 200) return 'text-brand-accent'
  return 'text-brand-muted'
}

/** Firms that appear in a summary, plus the selected one if it has no rows. */
function tenantOptions(byTenant = [], selectedId, selectedName) {
  const options = byTenant
    .filter((item) => item.tenant_id && item.tenant_id !== 'None')
    .map((item) => ({ id: item.tenant_id, label: `${item.tenant_name} (${item.count})` }))
  if (selectedId && !options.some((option) => option.id === selectedId)) {
    options.unshift({ id: selectedId, label: selectedName || 'Selected firm' })
  }
  return options
}

function ErrorsView({ platformKey, canDebug, tenantId, tenantName, onTenantChange, onOpenTenant, onAuthError }) {
  const [days, setDays] = useState(7)
  const [severity, setSeverity] = useState('')
  const [errorType, setErrorType] = useState('')
  const [unresolved, setUnresolved] = useState(false)
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState(null)
  const [tenantSummary, setTenantSummary] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const callbacks = useLatest({ onAuthError })

  // Any filter change starts again from the first page.
  const filter = (setter) => (value) => { setter(value); setPage(1) }

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { page, limit: PAGE_SIZE, days }
      if (severity) params.severity = severity
      if (errorType) params.error_type = errorType
      if (tenantId) params.tenant_id = tenantId
      if (unresolved) params.unresolved_only = true
      const [list, overall, scoped] = await Promise.all([
        getPlatformLogs(platformKey, params),
        getPlatformLogsSummary(platformKey, { days }),
        tenantId ? getPlatformTenantLogsSummary(platformKey, tenantId, { days }) : Promise.resolve(null),
      ])
      setRows(list.errors || [])
      setTotal(list.total || 0)
      setSummary(overall)
      setTenantSummary(scoped)
    } catch (loadError) {
      if (isSessionEnded(loadError)) { callbacks.current.onAuthError?.(); return }
      setError(apiErrorMessage(loadError, 'Could not load error logs.'))
    } finally {
      setLoading(false)
    }
  }, [platformKey, page, days, severity, errorType, tenantId, unresolved, callbacks])

  useEffect(() => { load() }, [load])

  const shown = tenantSummary || summary
  const types = Object.keys(summary?.by_type || {}).sort()
  const selectedTenantName = tenantName || rows.find((row) => row.tenant_id === tenantId)?.tenant_name

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <select aria-label="Error window" value={days} onChange={(event) => filter(setDays)(Number(event.target.value))} className="border border-brand-line rounded-lg px-3 py-1.5 text-xs font-sans bg-brand-surface">
          <option value={1}>24h</option>
          <option value={3}>3d</option>
          <option value={7}>7d</option>
          <option value={30}>30d</option>
          <option value={90}>90d</option>
        </select>
        <select aria-label="Firm" value={tenantId || ''} onChange={(event) => { onTenantChange(event.target.value); setPage(1) }} className="max-w-[240px] border border-brand-line rounded-lg px-3 py-1.5 text-xs font-sans bg-brand-surface">
          <option value="">All firms</option>
          {tenantOptions(summary?.by_tenant, tenantId, selectedTenantName).map((option) => (
            <option key={option.id} value={option.id}>{option.label}</option>
          ))}
        </select>
        <select aria-label="Severity" value={severity} onChange={(event) => filter(setSeverity)(event.target.value)} className="border border-brand-line rounded-lg px-3 py-1.5 text-xs font-sans bg-brand-surface">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select aria-label="Error type" value={errorType} onChange={(event) => filter(setErrorType)(event.target.value)} className="max-w-[200px] border border-brand-line rounded-lg px-3 py-1.5 text-xs font-sans bg-brand-surface">
          <option value="">All types</option>
          {types.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-brand-muted font-sans cursor-pointer">
          <input type="checkbox" checked={unresolved} onChange={(event) => filter(setUnresolved)(event.target.checked)} className="rounded" />
          Unresolved only
        </label>
        {tenantId && onOpenTenant && (
          <button type="button" onClick={() => onOpenTenant(tenantId)} className="text-xs font-medium text-brand-accent hover:underline">Open firm</button>
        )}
      </div>

      {error && <p role="alert" className="rounded-lg border border-brand-rose/20 bg-brand-rose/10 px-4 py-3 text-sm text-brand-rose">{error}</p>}

      {shown && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label={tenantId ? 'Firm errors' : 'Total errors'} value={shown.total_errors} icon={AlertTriangle} />
          <StatCard label="Unresolved" value={shown.unresolved} sub={shown.total_errors > 0 ? `${((shown.unresolved / shown.total_errors) * 100).toFixed(0)}%` : null} icon={AlertTriangle} />
          <StatCard label="Critical" value={shown.by_severity?.critical || 0} icon={AlertTriangle} />
          <StatCard label="Error" value={shown.by_severity?.error || 0} icon={AlertTriangle} />
        </div>
      )}

      <div className="bg-brand-surface border border-brand-line rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Error log</caption>
            <thead className="bg-brand-bg-soft border-b border-brand-line">
              <tr className="text-xs text-brand-muted uppercase tracking-wider font-sans">
                {!tenantId && <th scope="col" className="text-left px-4 py-2">Firm</th>}
                <th scope="col" className="text-left px-4 py-2">Type</th>
                <th scope="col" className="text-left px-4 py-2">Severity</th>
                <th scope="col" className="text-left px-4 py-2">Message</th>
                {tenantId && <th scope="col" className="text-left px-4 py-2">User</th>}
                <th scope="col" className="text-left px-4 py-2">Endpoint</th>
                <th scope="col" className="text-right px-4 py-2">Status</th>
                <th scope="col" className="text-right px-4 py-2">When</th>
                <th scope="col" className="text-right px-4 py-2"><span className="sr-only">Details</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-line">
              {rows.map((row) => (
                <React.Fragment key={row.id}>
                  <tr className="hover:bg-brand-bg transition-colors">
                    {!tenantId && <td className="px-4 py-2.5 text-xs text-brand-ink font-sans max-w-[140px] truncate" title={row.tenant_name}>{row.tenant_name}</td>}
                    <td className="px-4 py-2.5 text-xs text-brand-muted font-mono">{row.error_type}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium border ${errorSeverityClass(row.severity)}`}>{row.severity}</span>
                      {row.is_resolved && <span className="ml-1 text-[10px] font-medium text-brand-accent">resolved</span>}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-brand-ink-2 font-sans max-w-[300px] truncate" title={row.message}>{row.message}</td>
                    {tenantId && <td className="px-4 py-2.5 text-xs text-brand-muted font-mono">{row.user_id || 'system'}</td>}
                    <td className="px-4 py-2.5 text-xs text-brand-muted font-mono max-w-[150px] truncate" title={row.endpoint || ''}>{row.endpoint || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-brand-muted text-right font-sans">{row.status_code || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-brand-muted text-right font-sans whitespace-nowrap">{formatDateTime(row.created_at)}</td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        type="button"
                        aria-expanded={openId === row.id}
                        onClick={() => setOpenId(openId === row.id ? null : row.id)}
                        className="text-xs font-medium text-brand-accent hover:underline"
                      >
                        {openId === row.id ? 'Hide' : 'Details'}
                      </button>
                    </td>
                  </tr>
                  {openId === row.id && (
                    <tr>
                      <td colSpan={8} className="bg-brand-bg-soft px-4 py-3">
                        {canDebug ? (
                          <ErrorDetailLoader
                            platformKey={platformKey}
                            errorId={row.id}
                            tenantId={row.tenant_id !== 'None' ? row.tenant_id : undefined}
                            onOpenTenant={onOpenTenant}
                            onAuthError={onAuthError}
                            onResolved={(updated) => setRows((current) => current.map((item) => (
                              item.id === updated.id ? { ...item, is_resolved: updated.is_resolved, resolution_notes: updated.resolution_notes } : item
                            )))}
                          />
                        ) : (
                          <p className="text-xs text-brand-muted">Stack traces, request IDs and resolving an error need the {DEBUG_SCOPE} scope.</p>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={8} className="px-5 py-8 text-sm text-brand-muted text-center font-sans">{loading ? 'Loading…' : 'No errors found'}</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager page={page} total={total} limit={PAGE_SIZE} onPage={setPage} label="Error log pages" />
      </div>
    </div>
  )
}

function TrafficView({ platformKey, tenantId, tenantName, onTenantChange, onAuthError }) {
  const [hours, setHours] = useState(24)
  const [endpoint, setEndpoint] = useState('')
  const [endpointFilter, setEndpointFilter] = useState('')
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const callbacks = useLatest({ onAuthError })

  // Filter by endpoint a moment after typing stops rather than per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => { setEndpointFilter(endpoint.trim()); setPage(1) }, 300)
    return () => clearTimeout(timer)
  }, [endpoint])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { page, limit: PAGE_SIZE, hours }
      if (tenantId) params.tenant_id = tenantId
      if (endpointFilter) params.endpoint = endpointFilter
      const summaryParams = { hours }
      if (tenantId) summaryParams.tenant_id = tenantId
      const [list, nextSummary] = await Promise.all([
        getPlatformAccessLogs(platformKey, params),
        getPlatformAccessLogsSummary(platformKey, summaryParams),
      ])
      setRows(list.entries || [])
      setTotal(list.total || 0)
      setSummary(nextSummary)
    } catch (loadError) {
      if (isSessionEnded(loadError)) { callbacks.current.onAuthError?.(); return }
      setError(apiErrorMessage(loadError, 'Could not load API traffic.'))
    } finally {
      setLoading(false)
    }
  }, [platformKey, page, hours, tenantId, endpointFilter, callbacks])

  useEffect(() => { load() }, [load])

  const buckets = statusClassTotals(summary?.by_status)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <select aria-label="Traffic window" value={hours} onChange={(event) => { setHours(Number(event.target.value)); setPage(1) }} className="border border-brand-line rounded-lg px-3 py-1.5 text-xs font-sans bg-brand-surface">
          <option value={1}>1h</option>
          <option value={6}>6h</option>
          <option value={24}>24h</option>
          <option value={72}>3d</option>
          <option value={168}>7d</option>
        </select>
        <select aria-label="Firm" value={tenantId || ''} onChange={(event) => { onTenantChange(event.target.value); setPage(1) }} className="max-w-[240px] border border-brand-line rounded-lg px-3 py-1.5 text-xs font-sans bg-brand-surface">
          <option value="">All firms</option>
          {tenantOptions(summary?.by_tenant, tenantId, tenantName).map((option) => (
            <option key={option.id} value={option.id}>{option.label}</option>
          ))}
        </select>
        <input type="text" aria-label="Filter endpoint" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="Filter endpoint…" className="border border-brand-line rounded-lg px-3 py-1.5 text-xs font-sans bg-brand-surface w-48" />
      </div>

      {error && <p role="alert" className="rounded-lg border border-brand-rose/20 bg-brand-rose/10 px-4 py-3 text-sm text-brand-rose">{error}</p>}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard label="Requests" value={summary.total_requests?.toLocaleString()} sub={`${hours}h window`} icon={Globe} />
          <StatCard label="2xx" value={(buckets['2xx'] || 0).toLocaleString()} icon={Activity} />
          <StatCard label="4xx" value={(buckets['4xx'] || 0).toLocaleString()} icon={AlertTriangle} />
          <StatCard label="5xx" value={(buckets['5xx'] || 0).toLocaleString()} icon={AlertTriangle} />
          <StatCard label="Avg latency" value={summary.avg_latency_ms ? `${summary.avg_latency_ms}ms` : '—'} icon={Zap} />
        </div>
      )}

      <div className="bg-brand-surface border border-brand-line rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">API traffic</caption>
            <thead className="bg-brand-bg-soft border-b border-brand-line">
              <tr className="text-xs text-brand-muted uppercase tracking-wider font-sans">
                <th scope="col" className="text-left px-4 py-2">Firm</th>
                <th scope="col" className="text-left px-4 py-2">Method</th>
                <th scope="col" className="text-left px-4 py-2">Endpoint</th>
                <th scope="col" className="text-right px-4 py-2">Status</th>
                <th scope="col" className="text-right px-4 py-2">Latency</th>
                <th scope="col" className="text-right px-4 py-2">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-line">
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-brand-bg transition-colors">
                  <td className="px-4 py-2.5 text-xs text-brand-ink font-sans max-w-[140px] truncate" title={row.tenant_name}>{row.tenant_name}</td>
                  <td className="px-4 py-2.5 text-xs text-brand-muted font-mono">{row.method}</td>
                  <td className="px-4 py-2.5 text-xs text-brand-ink-2 font-mono max-w-[250px] truncate" title={row.endpoint}>{row.endpoint}</td>
                  <td className={`px-4 py-2.5 text-xs text-right font-mono ${statusColor(row.status_code)}`}>{row.status_code}</td>
                  <td className="px-4 py-2.5 text-xs text-brand-muted text-right font-sans">{row.latency_ms != null ? `${Math.round(row.latency_ms)}ms` : '—'}</td>
                  <td className="px-4 py-2.5 text-xs text-brand-muted text-right font-sans whitespace-nowrap">{formatDateTime(row.created_at)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={6} className="px-5 py-8 text-sm text-brand-muted text-center font-sans">{loading ? 'Loading…' : 'No traffic recorded'}</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager page={page} total={total} limit={PAGE_SIZE} onPage={setPage} label="API traffic pages" />
      </div>
    </div>
  )
}

/**
 * Error and API traffic logs. The firm filter is owned by the page (URL), so
 * "Error logs" in a firm's panel lands here already filtered to that firm.
 */
export default function LogsTab({ platformKey, session, tenantId, onTenantChange, onOpenTenant, onAuthError }) {
  const [subtab, setSubtab] = useState('errors')
  const [tenantName, setTenantName] = useState('')
  const canDebug = sessionHasScope(session, DEBUG_SCOPE)

  // A firm opened from a link may have no rows in the window, so its name
  // cannot come from the summaries; look it up once by id.
  useEffect(() => {
    if (!tenantId) { setTenantName(''); return undefined }
    let active = true
    getPlatformTenants(platformKey, 1, { q: tenantId, limit: 1 })
      .then((data) => { if (active) setTenantName(data?.tenants?.[0]?.name || '') })
      .catch(() => { /* the select falls back to a generic label */ })
    return () => { active = false }
  }, [platformKey, tenantId])

  return (
    <div>
      <div role="tablist" aria-label="Log type" className="flex gap-1 mb-6 border-b border-brand-line pb-0">
        {[
          { id: 'errors', label: 'Errors', icon: AlertTriangle },
          { id: 'traffic', label: 'API traffic', icon: Globe },
        ].map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={subtab === item.id}
            onClick={() => setSubtab(item.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-sans font-medium border-b-2 transition-colors -mb-px ${subtab === item.id ? 'border-brand-ink text-brand-ink' : 'border-transparent text-brand-muted hover:text-brand-ink-2'}`}
          >
            <item.icon size={14} aria-hidden="true" />
            {item.label}
          </button>
        ))}
      </div>
      {subtab === 'errors' ? (
        <ErrorsView
          platformKey={platformKey}
          canDebug={canDebug}
          tenantId={tenantId}
          tenantName={tenantName}
          onTenantChange={onTenantChange}
          onOpenTenant={onOpenTenant}
          onAuthError={onAuthError}
        />
      ) : (
        <TrafficView
          platformKey={platformKey}
          tenantId={tenantId}
          tenantName={tenantName}
          onTenantChange={onTenantChange}
          onAuthError={onAuthError}
        />
      )}
    </div>
  )
}
