import { useState } from 'react'
import { Search } from 'lucide-react'
import { findPlatformUsers, getPlatformErrorDetail, resolvePlatformError, tracePlatformRequest } from '../../api'
import { ErrorDetailCard } from './ErrorDetail'
import SupportQueue from './SupportQueue'
import {
  CopyButton,
  DEBUG_SCOPE,
  ScopeNotice,
  apiErrorMessage,
  formatDateTime,
  isScopeDenied,
  isSessionEnded,
  sessionHasScope,
} from './shared'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HEX_TOKEN_PATTERN = /^[0-9a-f]{16,100}$/i

/**
 * What a pasted value most likely is. Error ids and request ids are both
 * UUIDs, so a UUID is looked up as both at once.
 */
export const lookupKind = (value, mode = 'auto') => {
  const text = String(value || '').trim()
  if (!text) return null
  if (mode !== 'auto') return mode
  if (text.includes('@')) return 'email'
  if (UUID_PATTERN.test(text)) return 'id'
  if (HEX_TOKEN_PATTERN.test(text)) return 'request'
  return 'email'
}

function UserMatches({ users, query, onOpenTenant }) {
  if (users.length === 0) {
    return <p className="text-sm text-brand-muted">No LawHand login contains “{query}”.</p>
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-brand-line bg-brand-surface">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Users matching {query}</caption>
        <thead className="border-b border-brand-line bg-brand-bg-soft text-xs uppercase tracking-wider text-brand-muted">
          <tr>
            <th scope="col" className="px-4 py-2">User</th>
            <th scope="col" className="px-4 py-2">Role</th>
            <th scope="col" className="px-4 py-2">Login</th>
            <th scope="col" className="px-4 py-2">Firm</th>
            <th scope="col" className="px-4 py-2">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-brand-line">
          {users.map((user) => (
            <tr key={user.id}>
              <td className="px-4 py-2.5">
                <p className="font-medium text-brand-ink">{user.full_name || '—'}</p>
                <p className="text-xs text-brand-muted">{user.email}</p>
              </td>
              <td className="px-4 py-2.5 text-xs text-brand-ink-2">{user.role || '—'}</td>
              <td className="px-4 py-2.5 text-xs">
                <span className={user.is_active ? 'text-brand-accent' : 'text-brand-rose'}>
                  {user.is_active ? 'Active' : 'Inactive or invite not accepted'}
                </span>
              </td>
              <td className="px-4 py-2.5 text-xs">
                <button type="button" onClick={() => onOpenTenant(user.tenant_id)} className="font-medium text-brand-accent hover:underline">
                  {user.tenant_name}
                </button>
              </td>
              <td className="px-4 py-2.5 text-xs text-brand-muted">{formatDateTime(user.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TraceTimeline({ trace, onOpenTenant, onResolveError }) {
  const events = [
    ...trace.access_entries.map((entry) => ({ kind: 'access', at: entry.created_at, entry })),
    ...trace.errors.map((entry) => ({ kind: 'error', at: entry.created_at, entry })),
  ].sort((a, b) => new Date(a.at) - new Date(b.at))

  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-1 text-sm text-brand-ink-2">
        Request <span className="font-mono text-xs">{trace.request_id}</span>
        <CopyButton value={trace.request_id} label="request ID" />
        — {trace.access_entries.length} request log {trace.access_entries.length === 1 ? 'entry' : 'entries'}, {trace.errors.length} {trace.errors.length === 1 ? 'error' : 'errors'}.
        {trace.tenant_ids.map((tenantId) => (
          <button key={tenantId} type="button" onClick={() => onOpenTenant(tenantId)} className="ml-1 text-brand-accent hover:underline">Open firm</button>
        ))}
      </p>
      <ol className="space-y-2">
        {events.map(({ kind, entry }) => (
          <li key={`${kind}-${entry.id}`}>
            {kind === 'error' ? (
              <ErrorDetailCard error={entry} onOpenTenant={onOpenTenant} onResolve={(payload) => onResolveError(entry, payload)} />
            ) : (
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-brand-line bg-brand-surface px-4 py-2 text-xs">
                <span className="text-brand-muted">{formatDateTime(entry.created_at)}</span>
                <span className="font-mono text-brand-ink">{entry.method} {entry.endpoint}</span>
                <span className={`font-mono ${entry.status_code >= 500 ? 'text-brand-rose' : entry.status_code >= 400 ? 'text-brand-amber' : 'text-brand-accent'}`}>{entry.status_code}</span>
                {entry.latency_ms != null && <span className="text-brand-muted">{Math.round(entry.latency_ms)} ms</span>}
                <span className="text-brand-muted">{entry.tenant_name}</span>
                {entry.user_id && <span className="font-mono text-brand-muted">user {entry.user_id}</span>}
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}

/** One box for whatever the customer sent: an email, an error id or a request id. */
export function SupportLookup({ platformKey, onOpenTenant, onAuthError }) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('auto')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [scopeDenied, setScopeDenied] = useState(false)

  const fail = (lookupError, fallback) => {
    if (isSessionEnded(lookupError)) { onAuthError?.(); return }
    if (isScopeDenied(lookupError)) { setScopeDenied(true); return }
    setError(apiErrorMessage(lookupError, fallback))
  }

  const run = async (event) => {
    event.preventDefault()
    const text = query.trim()
    const kind = lookupKind(text, mode)
    if (!kind) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      if (kind === 'email') {
        if (text.length < 3) {
          setError('Enter at least three characters of the address.')
          return
        }
        setResult({ kind, query: text, users: await findPlatformUsers(platformKey, text) })
        return
      }
      const [detail, trace] = await Promise.allSettled([
        kind === 'request' ? Promise.resolve(null) : getPlatformErrorDetail(platformKey, text),
        kind === 'error' ? Promise.resolve(null) : tracePlatformRequest(platformKey, text),
      ])
      const rejected = [detail, trace].find((outcome) => (
        outcome.status === 'rejected' && outcome.reason?.response?.status !== 404
      ))
      if (rejected) {
        fail(rejected.reason, 'The lookup failed.')
        return
      }
      const errorRecord = detail.status === 'fulfilled' ? detail.value : null
      const traceRecord = trace.status === 'fulfilled' ? trace.value : null
      const traceHasEntries = Boolean(traceRecord && (traceRecord.errors.length || traceRecord.access_entries.length))
      setResult({ kind, query: text, error: errorRecord, trace: traceHasEntries ? traceRecord : null })
    } catch (lookupError) {
      fail(lookupError, 'The lookup failed.')
    } finally {
      setBusy(false)
    }
  }

  const resolveError = async (record, payload) => {
    const updated = await resolvePlatformError(platformKey, record.id, payload, record.tenant_id)
    setResult((current) => {
      if (!current) return current
      const swap = (item) => (item?.id === updated.id ? { ...item, ...updated } : item)
      return {
        ...current,
        error: swap(current.error),
        trace: current.trace ? { ...current.trace, errors: current.trace.errors.map(swap) } : current.trace,
      }
    })
  }

  if (scopeDenied) {
    return <ScopeNotice>Looking up users, errors and requests shows client addresses and stack traces, so it needs a credential with the</ScopeNotice>
  }

  const nothingFound = result && result.kind !== 'email' && !result.error && !result.trace

  return (
    <section aria-labelledby="support-lookup" className="rounded-xl border border-brand-line bg-brand-surface p-5 shadow-sm">
      <h2 id="support-lookup" className="font-serif text-xl font-bold text-brand-ink">Look up a customer issue</h2>
      <p className="mt-1 text-sm text-brand-muted">
        Paste what the customer sent: their email address, the <span className="font-mono text-xs">error_id</span> from an error message, or the <span className="font-mono text-xs">X-Request-ID</span> of a failed request.
      </p>
      <form onSubmit={run} className="mt-4 flex flex-wrap items-end gap-2">
        <label className="min-w-0 flex-1">
          <span className="sr-only">Email, error ID or request ID</span>
          <span className="relative block">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="name@firm.com, error ID or request ID"
              className="w-full rounded-lg border border-brand-line bg-brand-surface py-2 pl-9 pr-3 text-sm"
            />
          </span>
        </label>
        <label className="flex items-center gap-2 text-xs text-brand-muted">
          Look up as
          <select value={mode} onChange={(event) => setMode(event.target.value)} className="rounded-lg border border-brand-line bg-brand-surface px-2 py-2 text-xs text-brand-ink">
            <option value="auto">Detect</option>
            <option value="email">Email</option>
            <option value="error">Error ID</option>
            <option value="request">Request ID</option>
          </select>
        </label>
        <button type="submit" disabled={busy || !query.trim()} className="rounded-lg bg-brand-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? 'Looking up…' : 'Look up'}
        </button>
      </form>

      {error && <p role="alert" className="mt-3 text-sm text-brand-rose">{error}</p>}
      <div className="mt-4 space-y-4" aria-live="polite">
        {result?.kind === 'email' && <UserMatches users={result.users} query={result.query} onOpenTenant={onOpenTenant} />}
        {result?.error && (
          <ErrorDetailCard error={result.error} onOpenTenant={onOpenTenant} onResolve={(payload) => resolveError(result.error, payload)} />
        )}
        {result?.trace && <TraceTimeline trace={result.trace} onOpenTenant={onOpenTenant} onResolveError={resolveError} />}
        {nothingFound && (
          <p className="text-sm text-brand-muted">
            Nothing recorded for “{result.query}”. Errors are kept for 90 days and request logs for 30 by default, so an older reference returns nothing.
          </p>
        )}
      </div>
    </section>
  )
}

export default function SupportDeskTab({ platformKey, session, onOpenTenant, onAuthError, onCountsChange }) {
  const canDebug = sessionHasScope(session, DEBUG_SCOPE)
  return (
    <div className="space-y-8">
      {canDebug ? (
        <SupportLookup platformKey={platformKey} onOpenTenant={onOpenTenant} onAuthError={onAuthError} />
      ) : (
        <ScopeNotice>Looking up users, errors and requests needs a credential with the</ScopeNotice>
      )}
      <SupportQueue
        platformKey={platformKey}
        onOpenTenant={onOpenTenant}
        onAuthError={onAuthError}
        onCountsChange={onCountsChange}
      />
    </div>
  )
}
