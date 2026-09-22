import { useEffect, useState } from 'react'
import { getStorageReadiness } from '../../api'

// Advisory only: the save request remains authoritative and may discover a
// folder permission or expired grant after this inexpensive connection check.
export default function StorageReadinessNotice({ enabled = true }) {
  const [result, setResult] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const [checking, setChecking] = useState(false)
  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    setChecking(true)
    ;(async () => {
      try {
        const value = await getStorageReadiness()
        if (active) setResult(value)
      } catch {
        if (active) setResult({ status: 'unknown', message: 'We couldn’t check the document storage connection.' })
      } finally {
        if (active) setChecking(false)
      }
    })()
    return () => { active = false }
  }, [enabled, attempt])
  if (!enabled || !result || result.ready) return null
  return <div role="status" className="rounded border border-brand-amber/40 bg-brand-amber/10 p-3 text-sm">
    <p className="font-semibold">{result.status === 'unknown' ? 'Storage check unavailable' : 'Document storage needs attention'}</p>
    <p className="mt-1">{result.message}</p>
    {result.status !== 'unknown' && <p className="mt-1 text-xs">Your workspace administrator can repair the connection in Cloud settings. You can continue preparing and previewing this document.</p>}
    <button type="button" disabled={checking} onClick={() => setAttempt(value => value + 1)} className="mt-2 underline disabled:opacity-50">{checking ? 'Checking connection…' : 'Check connection again'}</button>
  </div>
}
