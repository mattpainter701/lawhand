import React, { useEffect, useState } from 'react'
import { getPlatformAgreementDefinitions, publishPlatformAgreementDefinition } from '../api'

const TERMS_DEFAULTS = {
  kind: 'terms_of_use',
  title: 'LawHand Terms of Use',
  version: '2026-07-27',
  effective_at: '2026-07-27T00:00:00.000Z',
  document_url: `${window.location.origin}/terms`,
  required_for_onboarding: true,
}

async function fetchTermsHash() {
  const response = await fetch('/terms', { cache: 'no-store' })
  if (!response.ok) throw new Error('Could not fetch the served Terms page.')
  const bytes = await response.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export default function PlatformAgreementsPanel({ platformKey }) {
  const [agreements, setAgreements] = useState([])
  const [draft, setDraft] = useState(null)
  const [approval, setApproval] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = async () => {
    setError('')
    try { setAgreements((await getPlatformAgreementDefinitions(platformKey)).agreements || []) }
    catch (err) { setError(err?.response?.data?.detail || 'Could not load agreement definitions.') }
  }
  useEffect(() => { load() }, [platformKey])

  const prepare = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      const content_hash = await fetchTermsHash()
      setDraft({ ...TERMS_DEFAULTS, content_hash })
      setApproval(false)
    } catch (err) { setError(err.message || 'Could not hash the served Terms page.') }
    finally { setBusy(false) }
  }

  const publish = async () => {
    if (!draft || !approval) return
    setBusy(true); setError(''); setNotice('')
    try {
      const content_hash = await fetchTermsHash()
      if (content_hash !== draft.content_hash) {
        throw new Error('The Terms page changed since it was loaded. Reload and review the new hash before publishing.')
      }
      await publishPlatformAgreementDefinition(platformKey, draft)
      setDraft(null); setApproval(false); setNotice('Terms published. Each tenant administrator must still accept the current version.')
      await load()
    } catch (err) { setError(err?.response?.data?.detail || err.message || 'Could not publish agreement definition.') }
    finally { setBusy(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-xl font-bold text-brand-ink">Agreements</h2>
        <p className="mt-1 text-sm text-brand-muted">Publish immutable counsel-owned definitions. This panel never invents or auto-publishes agreement text.</p>
      </div>
      {error && <div role="alert" className="rounded-lg border border-brand-rose/30 bg-brand-rose/10 px-4 py-3 text-sm text-brand-rose">{error}</div>}
      {notice && <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</div>}
      <div className="rounded-xl border border-brand-line bg-brand-surface p-5">
        <h3 className="font-semibold text-brand-ink">Published definitions</h3>
        {agreements.length === 0 ? <p className="mt-3 text-sm text-brand-muted">No agreement definitions published.</p> : (
          <div className="mt-3 space-y-2">{agreements.map((agreement) => <div key={agreement.id} className="rounded-lg bg-brand-bg p-3 text-sm"><div className="flex justify-between"><span className="font-medium">{agreement.title}</span><span className="font-mono text-xs">{agreement.version}</span></div><p className="mt-1 break-all font-mono text-xs text-brand-muted">{agreement.content_hash}</p></div>)}</div>
        )}
      </div>
      <div className="rounded-xl border border-brand-line bg-brand-surface p-5">
        <h3 className="font-semibold text-brand-ink">Load current LawHand Terms</h3>
        <p className="mt-1 text-sm text-brand-muted">Fetches the same-origin served bytes with no-store and computes SHA-256 in your browser. Review with counsel before publishing.</p>
        {!draft ? <button type="button" onClick={prepare} disabled={busy} className="mt-4 rounded-lg bg-brand-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{busy ? 'Loading…' : 'Load current LawHand Terms'}</button> : (
          <div className="mt-4 space-y-3">
            <dl className="grid gap-2 text-sm sm:grid-cols-2"><div><dt className="text-brand-muted">Kind</dt><dd className="font-mono">{draft.kind}</dd></div><div><dt className="text-brand-muted">Version</dt><dd>{draft.version}</dd></div><div><dt className="text-brand-muted">Effective</dt><dd>{draft.effective_at}</dd></div><div><dt className="text-brand-muted">URL</dt><dd className="break-all">{draft.document_url}</dd></div></dl>
            <div><p className="text-xs text-brand-muted">SHA-256</p><p className="break-all font-mono text-xs">{draft.content_hash}</p></div>
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={approval} onChange={(event) => setApproval(event.target.checked)} /><span>I confirm counsel approved publishing these exact served Terms bytes.</span></label>
            <div className="flex gap-2"><button type="button" onClick={publish} disabled={busy || !approval} className="rounded-lg bg-brand-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{busy ? 'Publishing…' : 'Re-fetch, verify, and publish'}</button><button type="button" onClick={() => setDraft(null)} disabled={busy} className="rounded-lg border border-brand-line px-4 py-2 text-sm">Cancel</button></div>
          </div>
        )}
      </div>
    </div>
  )
}

export { fetchTermsHash, TERMS_DEFAULTS }
