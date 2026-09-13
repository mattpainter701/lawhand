import { useEffect, useState } from 'react'
import { createBillingFee, getBillingFees, updateBillingFee } from '../api'

export default function BillingFees({ matterId, onChange }) {
  const [fees, setFees] = useState([])
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [serviceDate, setServiceDate] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let current = true
    getBillingFees(matterId).then(data => { if (current) setFees(data.items) }).catch(() => { if (current) setError('Fees could not be loaded.') })
    return () => { current = false }
  }, [matterId])
  async function change(action) {
    setBusy(true)
    setError('')
    try {
      await action()
      const data = await getBillingFees(matterId)
      setFees(data.items)
      onChange()
    } catch (e) {
      setError(e?.response?.data?.detail || 'Fee could not be saved. Refresh and try again.')
    } finally { setBusy(false) }
  }
  return <fieldset className="mt-4 rounded-xl border border-brand-line p-4">
    <legend className="px-2 font-semibold">Agreed stage fees</legend>
    <p className="text-sm text-brand-muted">Record agreed fees here, then mark each ready when that stage is billable. This does not send an invoice or charge the client.</p>
    {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
    <ul className="mt-3 divide-y divide-brand-line">
      {fees.map(fee => <li key={fee.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
        <span className="flex-1">{fee.description} · {fee.amount} · {fee.service_date} · {fee.status}</span>
        {fee.status === 'pending' && <button type="button" className="btn-secondary" disabled={busy} onClick={() => change(() => updateBillingFee(fee.id, 'ready'))}>Mark ready</button>}
        {['pending', 'ready'].includes(fee.status) && <button type="button" className="btn-secondary" disabled={busy} onClick={() => change(() => updateBillingFee(fee.id, 'cancelled'))}>Cancel fee</button>}
      </li>)}
    </ul>
    <div className="mt-3 grid gap-3 sm:grid-cols-3">
      <label className="text-sm">Stage description<input className="min-h-11 rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-accent w-full" maxLength={4000} value={description} onChange={e => setDescription(e.target.value)} /></label>
      <label className="text-sm">Agreed amount<input className="min-h-11 rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-accent w-full" type="number" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /></label>
      <label className="text-sm">Stage billing date<input className="min-h-11 rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-accent w-full" type="date" value={serviceDate} onChange={e => setServiceDate(e.target.value)} /></label>
    </div>
    <button type="button" className="btn-secondary mt-3" disabled={busy || !description.trim() || amount === '' || Number(amount) < 0 || !serviceDate} onClick={() => change(async () => {
      await createBillingFee({ matter_id: matterId, description, amount, service_date: serviceDate })
      setDescription(''); setAmount(''); setServiceDate('')
    })}>Add stage fee</button>
  </fieldset>
}
