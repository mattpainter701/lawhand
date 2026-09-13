import { useEffect, useState } from 'react'
import { getReadyToBill } from '../api'

export default function ReadyToBill({ cutoff, onSelect }) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let active = true
    setData(null)
    const timer = setTimeout(() => getReadyToBill({ q: query, page, date_to: cutoff }).then(result => {
      if (active) { setData(result); setError('') }
    }).catch(() => { if (active) setError('Unbilled work could not be loaded.') }), 200)
    return () => { active = false; clearTimeout(timer) }
  }, [query, page, cutoff, refresh])
  return <section className="mb-6 rounded-2xl border border-brand-line bg-brand-surface p-4" aria-label="Ready to bill">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-lg font-semibold">Ready to bill</h2>
      <label className="text-sm">Find matter<input className="min-h-11 rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-accent ml-2" value={query} onChange={e => { setQuery(e.target.value); setPage(1) }} /></label>
      <button type="button" className="btn-secondary" onClick={() => setRefresh(v => v + 1)}>Refresh unbilled work</button>
    </div>
    <p className="mt-2 text-sm text-brand-muted">Unbilled work through {cutoff}. Older work stays visible until billed. Fixed-fee-only invoices can also be created with Generate invoice.</p>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">Loading unbilled work…</p>}
    {data && <>
      <p className="my-3 text-sm">{data.total} matters · {data.total_amount} unbilled before tax</p>
      <ul className="divide-y divide-brand-line">
        {data.items.map(row => <li key={row.matter_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div><strong>{row.matter_name}</strong>{row.closed && <span> · Closed</span>}<p className="text-sm text-brand-muted">{row.count} items · oldest {row.oldest} · {row.amount}</p></div>
          <button type="button" className="btn-secondary" onClick={() => onSelect(row)}>Review work</button>
        </li>)}
      </ul>
      <div className="mt-3 flex items-center gap-3"><button type="button" className="btn-secondary" disabled={page === 1} onClick={() => setPage(v => v - 1)}>Previous</button><span>Page {page}</span><button type="button" className="btn-secondary" disabled={page * 25 >= data.total} onClick={() => setPage(v => v + 1)}>Next</button></div>
    </>}
  </section>
}
