import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { getMatterDocumentPrefill } from '../../api'

// The matter page's answer to "what is already filled in?". An unattended
// Smart Fill run records, per published template, how many fields the matter
// supplies. This shows the ready ones and opens each straight into the
// existing review, where the values are computed live; nothing here is a
// saved document, and nothing is sent anywhere.
export function summarize(readiness) {
  const templates = (readiness?.templates || []).filter((t) => t.status === 'ready')
  if (!templates.length) return null
  const percent = Math.round(templates.reduce((sum, t) => sum + (t.percent || 0), 0) / templates.length)
  return { templates, percent }
}

export default function PreparedDocumentsBanner({ matterId, version = 0, onOpen }) {
  const [readiness, setReadiness] = useState(null)
  const [expanded, setExpanded] = useState(false)
  useEffect(() => {
    if (!matterId) return undefined
    let active = true
    getMatterDocumentPrefill(matterId)
      .then((value) => { if (active) setReadiness(value) })
      .catch(() => { if (active) setReadiness(null) })
    return () => { active = false }
  }, [matterId, version])

  const summary = summarize(readiness)
  if (!summary) return null
  const { templates, percent } = summary
  const shown = expanded ? templates : templates.slice(0, 3)
  return (
    <section aria-label="Prepared documents" className="rounded-xl border border-brand-accent/30 bg-brand-accent/5 px-4 py-3 text-[13px] font-sans">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium text-brand-ink">
          <Sparkles size={16} className="text-brand-accent" />
          {templates.length} document{templates.length === 1 ? '' : 's'} ready to review, {percent}% filled from this matter
          {readiness.stale && <span className="text-brand-muted font-normal"> · matter details changed since; values refresh when you open one</span>}
        </p>
        {templates.length > 3 && (
          <button type="button" onClick={() => setExpanded((v) => !v)} className="text-brand-accent underline">
            {expanded ? 'Show fewer' : `Show all ${templates.length}`}
          </button>
        )}
      </div>
      <ul className="mt-2 divide-y divide-brand-line/60">
        {shown.map((t) => (
          <li key={t.template_id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
            <div>
              <strong className="font-medium">{t.title}</strong>
              <span className="ml-2 text-brand-muted">
                {t.filled} of {t.fields} fields
                {t.missing_required ? ` · ${t.missing_required} required still blank` : ''}
                {t.review ? ` · ${t.review} to confirm` : ''}
                {t.verified ? ` · ${t.verified} verified` : ''}
              </span>
            </div>
            <button type="button" onClick={() => onOpen(t.template_id)} className="rounded border border-brand-line px-3 py-1 text-brand-ink hover:border-brand-ink">
              Review and save
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
