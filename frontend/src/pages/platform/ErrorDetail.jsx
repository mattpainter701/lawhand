import { useCallback, useEffect, useState } from 'react'
import { CheckCircle, RotateCcw } from 'lucide-react'
import { getPlatformErrorDetail, resolvePlatformError } from '../../api'
import {
  CopyButton,
  ScopeNotice,
  apiErrorMessage,
  formatDateTime,
  formatRelative,
  isScopeDenied,
  isSessionEnded,
  useLatest,
} from './shared'

export const errorSeverityClass = (severity) => {
  if (severity === 'critical') return 'text-brand-rose bg-brand-rose/10 border-brand-rose/20'
  if (severity === 'error') return 'text-red-700 bg-red-50 border-red-200'
  if (severity === 'warning') return 'text-brand-amber bg-brand-amber/10 border-brand-amber/20'
  return 'text-brand-muted bg-brand-muted/10 border-brand-muted/20'
}

function Field({ label, children, mono = false }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-bold uppercase tracking-wider text-brand-muted">{label}</dt>
      <dd className={`mt-0.5 flex items-center gap-1 break-all text-xs text-brand-ink ${mono ? 'font-mono' : ''}`}>{children}</dd>
    </div>
  )
}

/**
 * One error record as support needs it: what failed, for whom, how to
 * correlate it, and a place to record that it was handled.
 */
export function ErrorDetailCard({ error, onResolve, onOpenTenant }) {
  const [notes, setNotes] = useState(error.resolution_notes || '')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  useEffect(() => { setNotes(error.resolution_notes || '') }, [error.id, error.resolution_notes])

  const submit = async (isResolved) => {
    setSaving(true)
    setSaveError('')
    try {
      await onResolve({ is_resolved: isResolved, resolution_notes: notes.trim() || null })
    } catch (resolveError) {
      setSaveError(apiErrorMessage(resolveError, 'Could not update this error.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <article className="rounded-xl border border-brand-line bg-brand-surface p-5 shadow-sm" aria-label={`Error ${error.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${errorSeverityClass(error.severity)}`}>{error.severity}</span>
        <span className="font-mono text-xs text-brand-muted">{error.error_type}</span>
        {error.status_code && <span className="font-mono text-xs text-brand-muted">HTTP {error.status_code}</span>}
        <span className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold ${error.is_resolved ? 'bg-brand-accent/10 text-brand-accent' : 'bg-brand-amber/10 text-brand-amber'}`}>
          {error.is_resolved ? 'Resolved' : 'Unresolved'}
        </span>
      </div>
      <p className="mt-3 text-sm font-medium text-brand-ink">{error.message}</p>
      <p className="mt-1 text-xs text-brand-muted">{formatDateTime(error.created_at)} · {formatRelative(error.created_at)}</p>

      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Firm">
          <span>{error.tenant_name || (error.tenant_id ? error.tenant_id : 'System')}</span>
          {error.tenant_id && onOpenTenant && (
            <button type="button" onClick={() => onOpenTenant(error.tenant_id)} className="ml-1 text-brand-accent underline-offset-2 hover:underline">Open firm</button>
          )}
        </Field>
        <Field label="User" mono>{error.user_id || '—'}</Field>
        <Field label="Endpoint" mono>{[error.method, error.endpoint].filter(Boolean).join(' ') || '—'}</Field>
        <Field label="Error ID" mono>{error.id}<CopyButton value={error.id} label="error ID" /></Field>
        <Field label="Request ID" mono>
          {error.request_id || '—'}
          {error.request_id && <CopyButton value={error.request_id} label="request ID" />}
        </Field>
        <Field label="Client" mono>{error.ip_address || '—'}</Field>
      </dl>
      {error.user_agent && <p className="mt-3 break-all text-[11px] text-brand-muted">{error.user_agent}</p>}

      {error.stack_trace && (
        <details className="mt-4 rounded-lg border border-brand-line bg-brand-bg">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-brand-ink">Stack trace</summary>
          <pre className="max-h-72 overflow-auto border-t border-brand-line px-3 py-2 text-[11px] leading-5 text-brand-ink-2">{error.stack_trace}</pre>
        </details>
      )}
      {error.query_text && (
        <details className="mt-2 rounded-lg border border-brand-line bg-brand-bg">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-brand-ink">Retained query text (may contain client content)</summary>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap border-t border-brand-line px-3 py-2 text-[11px] text-brand-ink-2">{error.query_text}</pre>
        </details>
      )}

      {onResolve && (
        <div className="mt-4 border-t border-brand-line pt-4">
          <label className="block">
            <span className="text-xs font-medium text-brand-muted">Resolution notes (operator-only)</span>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={2}
              maxLength={2000}
              placeholder="What caused it and what was done"
              className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm"
            />
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {error.is_resolved ? (
              <>
                <button type="button" disabled={saving} onClick={() => submit(true)} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink disabled:opacity-50">Update notes</button>
                <button type="button" disabled={saving} onClick={() => submit(false)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-amber/30 px-3 py-2 text-xs font-medium text-brand-amber disabled:opacity-50">
                  <RotateCcw size={13} aria-hidden="true" /> Reopen
                </button>
              </>
            ) : (
              <button type="button" disabled={saving} onClick={() => submit(true)} className="inline-flex items-center gap-1.5 rounded-lg bg-brand-ink px-3 py-2 text-xs font-medium text-white disabled:opacity-50">
                <CheckCircle size={13} aria-hidden="true" /> {saving ? 'Saving…' : 'Mark resolved'}
              </button>
            )}
            {error.resolved_at && <span className="text-xs text-brand-muted">Resolved {formatDateTime(error.resolved_at)}</span>}
          </div>
          {saveError && <p role="alert" className="mt-2 text-xs text-brand-rose">{saveError}</p>}
        </div>
      )}
    </article>
  )
}

/** Loads one error by id (platform:debug) and lets the operator resolve it. */
export function ErrorDetailLoader({ platformKey, errorId, tenantId, onOpenTenant, onAuthError, onResolved }) {
  const [error, setError] = useState(null)
  const [state, setState] = useState('loading')
  const [message, setMessage] = useState('')
  const callbacks = useLatest({ onAuthError, onResolved })

  const load = useCallback(async () => {
    setState('loading')
    try {
      setError(await getPlatformErrorDetail(platformKey, errorId, tenantId))
      setState('ready')
    } catch (loadError) {
      if (isSessionEnded(loadError)) { callbacks.current.onAuthError?.(); return }
      if (isScopeDenied(loadError)) { setState('scope'); return }
      setMessage(loadError?.response?.status === 404
        ? 'No error with that ID. Error records are kept for 90 days by default.'
        : apiErrorMessage(loadError, 'Could not load this error.'))
      setState('failed')
    }
  }, [platformKey, errorId, tenantId, callbacks])

  useEffect(() => { load() }, [load])

  const resolve = async (payload) => {
    const updated = await resolvePlatformError(platformKey, errorId, payload, tenantId)
    setError(updated)
    callbacks.current.onResolved?.(updated)
  }

  if (state === 'loading') return <p className="px-1 py-3 text-sm text-brand-muted">Loading error…</p>
  if (state === 'scope') return <ScopeNotice>Error details show stack traces and client addresses, so they need a credential with the</ScopeNotice>
  if (state === 'failed') return <p role="alert" className="px-1 py-3 text-sm text-brand-rose">{message}</p>
  return <ErrorDetailCard error={error} onResolve={resolve} onOpenTenant={onOpenTenant} />
}
