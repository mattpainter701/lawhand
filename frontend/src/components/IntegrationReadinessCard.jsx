import { useEffect, useState } from 'react'
import { getIntegrationReadiness } from '../api'

const CORE_READINESS_ENV_KEYS = new Set([
  'FRONTEND_URL',
  'BACKEND_URL',
  'MICROSOFT_CLIENT_ID',
  'MICROSOFT_CLIENT_SECRET',
  'MICROSOFT_TENANT_ID',
  'GOOGLE_CLIENT_ID',
  'GOOGLE_CLIENT_SECRET',
  'TEAMS_APP_ID',
])

/**
 * Operator view of provider app configuration: which server-side OAuth
 * settings are present and which redirect URIs the provider consoles must
 * carry. Redacted, but it names environment variables and infrastructure —
 * nothing a firm administrator can act on — so it lives under Advanced.
 */
export function ReadinessCard({ readiness }) {
  if (!readiness) return null
  const envEntries = Object.entries(readiness.env || {})
    .filter(([key]) => CORE_READINESS_ENV_KEYS.has(key))
  const redirects = Object.fromEntries(
    Object.entries(readiness.expected_redirect_uris || {})
      .filter(([provider]) => !['zoom', 'zoom_phone'].includes(provider))
  )

  return (
    <div className="bg-brand-surface border border-brand-line rounded-xl p-6">
      <h3 className="text-brand-ink font-sans text-base font-bold mb-1">Cloud Integration Readiness</h3>
      <p className="text-brand-ink-2 font-sans text-xs mb-4">
        Redacted setup status for Microsoft, Google, Teams, and cloud document callbacks.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <h4 className="text-xs font-bold uppercase tracking-widest text-brand-muted mb-2">Environment</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {envEntries.map(([key, value]) => (
              <div key={key} className="flex items-center justify-between gap-3 bg-brand-bg rounded-lg px-3 py-2">
                <span className="text-xs font-mono text-brand-ink truncate">{key}</span>
                <span className={`text-[10px] font-bold uppercase ${value.configured ? 'text-green-700' : 'text-red-600'}`}>
                  {value.configured ? 'Set' : 'Missing'}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h4 className="text-xs font-bold uppercase tracking-widest text-brand-muted mb-2">Expected Redirect URIs</h4>
          <div className="space-y-2">
            {Object.entries(redirects).map(([provider, uris]) => (
              <div key={provider} className="bg-brand-bg rounded-lg px-3 py-2">
                <div className="text-xs font-bold text-brand-ink capitalize mb-1">{provider}</div>
                {(uris || []).map((uri) => (
                  <div key={uri} className="text-[11px] font-mono text-brand-muted break-all">{uri}</div>
                ))}
              </div>
            ))}
          </div>
          {readiness.entra_verification_command && (
            <div className="mt-3 text-[11px] font-mono text-brand-muted bg-brand-bg px-3 py-2 rounded-lg break-all">
              {readiness.entra_verification_command}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function IntegrationReadinessCard() {
  const [readiness, setReadiness] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    getIntegrationReadiness()
      .then((data) => { if (active) setReadiness(data) })
      .catch(() => { if (active) setError('Readiness information is unavailable.') })
    return () => { active = false }
  }, [])

  if (error) {
    return <p className="text-xs text-brand-muted font-sans">{error}</p>
  }
  return <ReadinessCard readiness={readiness} />
}
