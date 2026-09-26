import { useCallback, useEffect, useState } from 'react'
import { connectCalendarIntegration, getCalendarProviders } from '../api'

// A personal connection is one consent covering mail, calendar and files, so
// it is described here in full rather than behind a "Connect Calendar" label.
const PROVIDERS = {
  microsoft: {
    name: 'Microsoft 365',
    allows: [
      'Read mail in your mailbox so LawHand can file matter correspondence',
      'Send client email you approve, from your own address',
      'Add and update your matter tasks and deadlines on your Outlook calendar',
      'Search and open (read only) any file you can open in OneDrive or SharePoint',
    ],
  },
  google: {
    name: 'Google',
    allows: [
      'Read mail in your Gmail so LawHand can file matter correspondence',
      'Send client email you approve, from your own address',
      'Add and update your matter tasks and deadlines on your Google Calendar',
      'Search, open and save any Google Drive file you can open',
    ],
  },
}

const REASON_TEXT = {
  missing_scopes: 'Some permissions were not granted. Reconnect and approve every permission.',
  refresh_failed: 'Your sign-in has expired or was revoked. Reconnect to restore it.',
}

const FEATURE_LABELS = {
  mail_read: 'reading mail',
  mail_send: 'sending mail',
  calendar: 'calendar updates',
  files: 'file access',
}

function statusFor(state) {
  if (state?.connected && state?.missing_features?.length) {
    return { tone: 'bg-amber-100 text-amber-800', label: 'Limited access' }
  }
  if (state?.connected) return { tone: 'bg-green-100 text-green-700', label: 'Connected' }
  if (state?.needs_reconnect) return { tone: 'bg-amber-100 text-amber-800', label: 'Needs reconnecting' }
  return { tone: 'bg-gray-100 text-gray-600', label: 'Not connected' }
}

export default function ConnectedAccountsCard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      setData(await getCalendarProviders())
    } catch {
      setError('Could not load your connected accounts. Refresh the page to try again.')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const statusByProvider = data?.provider_status || {}
  // Offer the suites the firm uses, plus any the person already connected.
  const shown = ['microsoft', 'google'].filter((provider) =>
    (data?.tenant_providers || []).includes(provider) ||
    statusByProvider[provider]?.connected ||
    statusByProvider[provider]?.needs_reconnect)

  return (
    <section className="bg-brand-surface border border-brand-line rounded-xl p-6" aria-labelledby="connected-accounts-heading" data-testid="connected-accounts">
      <h2 id="connected-accounts-heading" className="text-base font-bold text-brand-ink font-sans">Connected accounts</h2>
      <p className="mt-1 text-xs text-brand-ink-2 font-sans max-w-2xl">
        Connect your own work account so LawHand can act as you: file matter email, send client email you approve, and keep your tasks on your calendar. Only you can connect your account.
      </p>
      {error && <p role="status" className="mt-3 text-xs text-red-700 font-sans">{error}</p>}
      {!data && !error && <p className="mt-3 text-xs text-brand-muted font-sans">Loading…</p>}
      {data && shown.length === 0 && (
        <p className="mt-3 rounded-lg bg-brand-bg px-4 py-3 text-xs text-brand-ink-2 font-sans">
          Your firm has not connected Microsoft 365 or Google Workspace yet. A firm administrator sets this up under Administration → Integrations.
        </p>
      )}
      <div className="mt-4 space-y-3">
        {shown.map((provider) => {
          const meta = PROVIDERS[provider]
          const state = statusByProvider[provider]
          const status = statusFor(state)
          const action = state?.connected ? 'Reconnect' : state?.needs_reconnect ? 'Reconnect' : 'Connect'
          return (
            <article key={provider} className="rounded-xl border border-brand-line bg-brand-bg px-4 py-4" data-testid={`connected-account-${provider}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-brand-ink font-sans">{meta.name}</h3>
                  <span className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${status.tone}`}>{status.label}</span>
                  {!state?.connected && state?.needs_reconnect && REASON_TEXT[state.reason] && (
                    <p className="mt-2 text-xs text-amber-800 font-sans">{REASON_TEXT[state.reason]}</p>
                  )}
                  {state?.connected && state?.missing_features?.length > 0 && (
                    <p className="mt-2 text-xs text-amber-800 font-sans">
                      Permissions missing for {state.missing_features.map((feature) => FEATURE_LABELS[feature] || feature).join(', ')}. Reconnect and approve every permission to use these features.
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => connectCalendarIntegration(provider)}
                  aria-label={`${action} ${meta.name}`}
                  className={`px-4 py-2 font-sans text-xs font-medium rounded-lg transition-colors ${
                    state?.connected
                      ? 'border border-brand-line text-brand-ink hover:bg-brand-bg-soft'
                      : 'bg-brand-ink text-white hover:bg-brand-ink/90'
                  }`}
                >
                  {action}
                </button>
              </div>
              <details className="group mt-3">
                <summary className="cursor-pointer list-none text-xs font-bold text-brand-ink font-sans marker:hidden [&::-webkit-details-marker]:hidden">
                  What connecting allows <span className="inline-block text-brand-muted transition-transform group-open:rotate-180" aria-hidden="true">⌄</span>
                </summary>
                <ul className="mt-2 space-y-1">
                  {meta.allows.map((line) => (
                    <li key={line} className="flex gap-2 text-xs text-brand-ink-2 font-sans">
                      <span className="text-brand-muted" aria-hidden="true">•</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] text-brand-muted font-sans">To remove this connection, ask a firm administrator.</p>
              </details>
            </article>
          )
        })}
      </div>
    </section>
  )
}
