import { useState } from 'react'
import { Link } from 'react-router-dom'
import { confirmMatterCsvImport, getMatterCsvTemplate, previewMatterCsvImport } from '../api'

const inputClass = 'border border-brand-line rounded-lg px-3 py-2 w-full bg-white text-brand-ink'
const button = 'min-h-11 rounded-lg bg-brand-ink px-4 text-[13px] font-semibold text-white disabled:opacity-50'
const detail = (error) => (typeof error?.response?.data?.detail === 'string'
  ? error.response.data.detail
  : typeof error?.response?.data?.detail?.message === 'string'
    ? error.response.data.detail.message
    : 'The CSV could not be processed. Check the file and try again.')

const ENGAGEMENT_TEXT = {
  existing: 'Existing engagement',
  review: 'Transfer / review required',
  required: 'Fresh intake required',
}

// Bulk matter creation from the firm's CSV template: download the template,
// upload the filled sheet, review how every row resolves (which client it
// reuses or creates, which attorney, what is wrong), exclude rows, then
// create. Files come afterwards, per matter, through the existing importers.
export default function MatterCsvImport({ onComplete }) {
  const [run, setRun] = useState(null)
  const [excluded, setExcluded] = useState(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function downloadTemplate() {
    setError('')
    try {
      const blob = await getMatterCsvTemplate()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'matters-template.csv'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (caught) {
      setError(detail(caught))
    }
  }

  async function preview(file) {
    if (!file) return
    setBusy(true); setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const next = await previewMatterCsvImport(form)
      setRun(next)
      setExcluded(new Set())
    } catch (caught) { setError(detail(caught)) } finally { setBusy(false) }
  }

  async function confirm() {
    setBusy(true); setError('')
    try {
      const include = run.rows.filter(row => !excluded.has(row.row)).map(row => row.row)
      const next = await confirmMatterCsvImport(run.id, { confirm: true, include_rows: include })
      setRun(next)
      onComplete?.(next)
    } catch (caught) { setError(detail(caught)) } finally { setBusy(false) }
  }

  function toggle(rowNumber) {
    setExcluded(previous => {
      const next = new Set(previous)
      if (next.has(rowNumber)) next.delete(rowNumber)
      else next.add(rowNumber)
      return next
    })
  }

  const included = run?.rows?.filter(row => !excluded.has(row.row)) || []
  const blocking = included.filter(row => row.errors?.length).length
  const complete = run?.status === 'complete'

  return (
    <section className="space-y-4 p-4" aria-label="Bulk create matters from CSV">
      <h3 className="font-bold text-lg">Bulk create matters from CSV</h3>
      <p className="text-sm">
        Fill in one row per matter. A client is reused when its client number, email or contact ID matches; otherwise a new client is created. Nothing is sent to any client. Files and signed fee agreements are added afterwards from each matter.
      </p>
      <p className="text-sm text-brand-muted">Up to 500 rows and 1 MiB per file. Dates are YYYY-MM-DD.</p>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={inputClass} onClick={downloadTemplate} disabled={busy}>Download template</button>
        <label className="block flex-1">Choose CSV<input disabled={busy} className={inputClass} type="file" accept=".csv,text/csv" onChange={e => preview(e.target.files?.[0])} /></label>
      </div>

      {run && !complete && (
        <>
          <p role="status" className="text-sm">
            {run.summary.total} rows · {run.summary.valid} ready · {run.summary.invalid} with problems · {run.summary.contacts_matched} existing clients · {run.summary.contacts_to_create} new clients
          </p>
          <div className="max-h-96 overflow-auto rounded-lg border border-brand-line">
            <table className="min-w-full text-left text-[12px]">
              <thead className="bg-brand-bg-soft/60 text-[11px] uppercase tracking-wider text-brand-muted">
                <tr>
                  <th className="px-2 py-2">Include</th>
                  <th className="px-2 py-2">Row</th>
                  <th className="px-2 py-2">Matter</th>
                  <th className="px-2 py-2">Client</th>
                  <th className="px-2 py-2">Attorney</th>
                  <th className="px-2 py-2">Opened</th>
                  <th className="px-2 py-2">Engagement</th>
                  <th className="px-2 py-2">Problems</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-line/70">
                {run.rows.map(row => (
                  <tr key={row.row} className={excluded.has(row.row) ? 'opacity-50' : ''}>
                    <td className="px-2 py-2"><input type="checkbox" aria-label={`Include row ${row.row}`} checked={!excluded.has(row.row)} onChange={() => toggle(row.row)} /></td>
                    <td className="px-2 py-2">{row.row}</td>
                    <td className="px-2 py-2 font-semibold">{row.values.matter_name || '—'}</td>
                    <td className="px-2 py-2">
                      {row.contact?.display_name || '—'}
                      {row.contact && (
                        <span className={`ml-1 rounded px-1 py-0.5 text-[10px] font-semibold uppercase ${row.contact.action === 'match' ? 'bg-brand-green/10 text-brand-green' : 'bg-brand-amber/10 text-brand-amber'}`}>
                          {row.contact.action === 'match' ? 'existing client' : 'new client'}
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2">{row.attorney?.name || '—'}</td>
                    <td className="px-2 py-2">{row.values.opened_on || 'today'}</td>
                    <td className="px-2 py-2">
                      {ENGAGEMENT_TEXT[row.values.engagement] || row.values.engagement}
                      {row.values.agreement && <span className="block text-brand-muted">{row.values.agreement.replaceAll('_', ' ')}</span>}
                    </td>
                    <td className="px-2 py-2 text-brand-rose">{(row.errors || []).join('; ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {blocking > 0 && <p className="text-sm text-brand-rose">{blocking} included row{blocking === 1 ? ' has' : 's have'} problems. Fix the CSV and upload it again, or exclude those rows.</p>}
          <button type="button" className={button} disabled={busy || included.length === 0 || blocking > 0} onClick={confirm}>
            Create {included.length} matter{included.length === 1 ? '' : 's'}
          </button>
        </>
      )}

      {complete && (
        <>
          <p role="status" className="text-sm font-semibold">Created {run.results.length} matter{run.results.length === 1 ? '' : 's'}.</p>
          <ul className="max-h-60 space-y-1 overflow-auto text-sm">
            {run.results.map(result => (
              <li key={result.matter_id}>
                <Link className="text-brand-accent underline" to={`/matters/${result.matter_id}`}>{result.matter_number ? `${result.matter_number} · ` : ''}{result.matter_name}</Link>
                <span className="text-brand-muted"> — {result.contact_created ? 'new client' : 'existing client'}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-brand-muted">
            Next: open each matter → Documents → Import files &amp; emails, or use New Matter → Import existing matters and choose these matters as destinations. To file a signed fee agreement, open the matter and choose Add signed copy on its paperwork card.
          </p>
        </>
      )}

      {busy && <p role="status">Working…</p>}
      {error && <p role="alert" className="text-red-700">{error}</p>}
    </section>
  )
}
