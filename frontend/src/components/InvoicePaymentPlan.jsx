import { useState } from 'react'
import { setInvoicePaymentPlan } from '../api'

export default function InvoicePaymentPlan({ invoice, onSaved }) {
  const [rows, setRows] = useState(invoice.billing_details?.installments || [])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const editable = ['draft', 'sent'].includes(invoice.status) && Number(invoice.amount_paid) === 0
  return <section className="my-4 rounded-xl border border-brand-line p-4" aria-label="Payment plan">
    <h2 className="font-semibold">Payment installments</h2>
    <p className="text-sm text-brand-muted">Divide this invoice total into dated payments. This does not create new charges or enable automatic collection. Changing draft charges clears the plan.</p>
    {error && <p role="alert">{error}</p>}
    {rows.map((row, index) => <div key={index} className="mt-2 flex flex-wrap gap-3">
      <label className="text-sm">Installment date {index + 1}<input className="input block" type="date" min={invoice.issue_date} disabled={!editable || busy} value={row.due_date} onChange={e => setRows(all => all.map((r, i) => i === index ? { ...r, due_date: e.target.value } : r))} /></label>
      <label className="text-sm">Installment amount {index + 1}<input className="input block" type="number" min="0.01" step="0.01" disabled={!editable || busy} value={row.amount} onChange={e => setRows(all => all.map((r, i) => i === index ? { ...r, amount: e.target.value } : r))} /></label>
      {editable && <button className="btn-secondary self-end" type="button" disabled={busy} onClick={() => setRows(all => all.filter((_, i) => i !== index))}>Remove installment {index + 1}</button>}
    </div>)}
    {editable && <div className="mt-3 flex gap-3">
      <button className="btn-secondary" type="button" disabled={busy || rows.length >= 60} onClick={() => setRows(all => [...all, { due_date: '', amount: '' }])}>Add installment</button>
      <button className="btn-primary" type="button" disabled={busy || !rows.length || rows.some(row => !row.due_date || Number(row.amount) <= 0)} onClick={async () => {
        setBusy(true); setError('')
        try { onSaved(await setInvoicePaymentPlan(invoice.id, rows)) } catch (e) { setError(e?.response?.data?.detail || 'Payment plan could not be saved.') }
        finally { setBusy(false) }
      }}>Save payment plan</button>
    </div>}
  </section>
}
