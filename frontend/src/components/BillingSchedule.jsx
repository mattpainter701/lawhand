import { useEffect, useState } from 'react'
import { createBillingSchedule, getBillingSchedules, pauseBillingSchedule } from '../api'

export default function BillingSchedule({ matterId }) {
  const [schedule, setSchedule] = useState(null)
  const [firstDate, setFirstDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [months, setMonths] = useState('1')
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('0')
  const [includeWork, setIncludeWork] = useState(true)
  const [zone, setZone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let current = true
    getBillingSchedules(matterId).then(data => { if (current) { setSchedule(data.items[0] || null); setLoading(false) } }).catch(() => { if (current) setError('Schedule could not be loaded.') })
    return () => { current = false }
  }, [matterId])
  async function save(action) {
    setBusy(true); setError('')
    try { setSchedule(await action()) } catch (e) { setError(e?.response?.data?.detail || 'Schedule could not be saved.') }
    finally { setBusy(false) }
  }
  return <fieldset className="mt-4 rounded-xl border border-brand-line p-4">
    <legend className="px-2 font-semibold">Recurring drafts (optional)</legend>
    <p className="text-sm text-brand-muted">Prepare drafts for review, billed in arrears. No automatic sending or charging. Work before each invoice date is included only if selected below.</p>
    {error && <p role="alert">{error}</p>}
    {schedule ? <div className="mt-3 text-sm">
      <p>Next invoice: {schedule.next_date} · {schedule.paused ? 'Paused' : 'Active'} · {schedule.config.timezone}</p>
      {schedule.last_error && <p role="alert">{schedule.last_error}</p>}
      <button type="button" className="btn-secondary mt-2" disabled={busy} onClick={() => save(() => pauseBillingSchedule(schedule.id, !schedule.paused))}>{schedule.paused ? 'Resume recurring drafts' : 'Pause recurring drafts'}</button>
    </div> : !loading && <>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <label className="text-sm">First recurring invoice date<input type="date" className="input w-full" value={firstDate} onChange={e => setFirstDate(e.target.value)} /></label>
        <label className="text-sm">End date (optional)<input type="date" className="input w-full" min={firstDate} value={endDate} onChange={e => setEndDate(e.target.value)} /></label>
        <label className="text-sm">Frequency<select className="input w-full" value={months} onChange={e => setMonths(e.target.value)}><option value="1">Monthly</option><option value="3">Quarterly</option></select></label>
        <label className="text-sm">Timezone<input className="input w-full" value={zone} onChange={e => setZone(e.target.value)} /></label>
        <label className="text-sm">Recurring fee description<input className="input w-full" value={description} onChange={e => setDescription(e.target.value)} /></label>
        <label className="text-sm">Recurring fixed amount<input type="number" className="input w-full" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /></label>
      </div>
      <label className="mt-3 flex gap-2 text-sm"><input type="checkbox" checked={includeWork} onChange={e => setIncludeWork(e.target.checked)} />Include unbilled hourly work and expenses in addition to the fixed fee</label>
      <button type="button" className="btn-secondary mt-3" disabled={busy || !firstDate || !zone || (!includeWork && Number(amount) <= 0) || (Number(amount) > 0 && !description.trim())} onClick={() => save(() => createBillingSchedule({ matter_id: matterId, first_invoice_date: firstDate, end_date: endDate || null, timezone: zone, interval_months: Number(months), fixed_description: description, fixed_amount: amount || '0', include_unbilled_work: includeWork }))}>Enable recurring drafts</button>
    </>}
  </fieldset>
}
