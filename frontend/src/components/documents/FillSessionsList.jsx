import { useEffect, useState } from 'react'
import { abandonFillSession, getMatterFillSessions } from '../../api'
import { buildPrepareTarget } from '../prepare/prepareRouting'

const memberSummary = (session) => {
  const members = session.members || []
  if (!members.length) return ''
  const saved = members.filter((m) => m.status === 'saved').length
  return ` · ${saved} of ${members.length} saved`
}

// The matter's packets still in progress: the caller's own fill sessions,
// resumable on the Prepare route, or abandoned here. Answers never appear in
// this list; the session that owns them decrypts them on resume.
export default function FillSessionsList({ matterId, version = 0, onResume }) {
  const [sessions, setSessions] = useState([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!matterId) return undefined
    let active = true
    getMatterFillSessions(matterId)
      .then((value) => { if (active) setSessions(Array.isArray(value?.items) ? value.items : []) })
      .catch(() => { if (active) setSessions([]) })
    return () => { active = false }
  }, [matterId, version])
  if (!sessions.length) return null
  const resume = (session) => onResume(buildPrepareTarget({ templateId: session.template_id, setId: session.set_id, matterId, sessionId: session.id, returnTo: `/matters/${matterId}?tab=documents` }).url)
  const drop = async (session) => {
    setBusy(session.id)
    setError('')
    try { await abandonFillSession(session.id); setSessions((prev) => prev.filter((item) => item.id !== session.id)) }
    catch { setError('The document in progress could not be discarded. Try again.') }
    finally { setBusy('') }
  }
  return (
    <section aria-label="Documents in progress" className="rounded-xl border border-brand-line bg-brand-surface-2 px-4 py-3 text-[13px] font-sans">
      <p className="font-medium text-brand-ink">{sessions.length} document{sessions.length === 1 ? '' : 's'} in progress</p>
      <ul className="mt-2 divide-y divide-brand-line/60">
        {sessions.map((session) => (
          <li key={session.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
            <span><strong className="font-medium">{session.title || (session.set_id ? 'Packet' : 'Document')}</strong><span className="ml-2 text-brand-muted">{session.status === 'saving' ? 'Saving in the background…' : session.status === 'failed' ? (session.last_error || 'Needs attention') : 'In progress'}{memberSummary(session)}</span></span>
            <span className="flex gap-2">
              <button type="button" onClick={() => resume(session)} className="rounded border border-brand-line px-3 py-1 text-brand-ink hover:border-brand-ink">Resume</button>
              <button type="button" onClick={() => drop(session)} disabled={busy === session.id} className="rounded border border-brand-line px-3 py-1 text-brand-rose disabled:opacity-50">Discard</button>
            </span>
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="mt-2 text-xs text-brand-rose">{error}</p>}
    </section>
  )
}
