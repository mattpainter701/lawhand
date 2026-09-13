import BillingSchedule from '../components/BillingSchedule'
import ReadyToBill from '../components/ReadyToBill'
import BillingFees from '../components/BillingFees'
import { useCallback, useEffect, useRef, useState } from 'react'
import { reportError } from '../utils/reportError'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Receipt, RefreshCw } from 'lucide-react'
import { generateInvoice, getInvoicePreview, getInvoices, getMattersV2 } from '../api'
import {
  AlertBanner,
  EmptyState,
  FilterToolbar,
  MetricStrip,
  SegmentedControl,
  Spinner,
  WorkspacePage,
  WorkspacePageHeader,
} from '../components/ui'

const STATUS_STYLES = {
  draft: 'border-brand-line bg-brand-bg-soft text-brand-ink-2',
  sent: 'border-brand-accent/20 bg-brand-accent/10 text-brand-accent-2',
  invoiced: 'border-brand-accent/20 bg-brand-accent/10 text-brand-accent-2',
  paid: 'border-brand-green/20 bg-brand-green/10 text-brand-green',
  partially_paid: 'border-brand-amber/20 bg-brand-amber/10 text-brand-amber',
  overdue: 'border-brand-rose/20 bg-brand-rose/10 text-brand-rose',
  void: 'border-brand-line bg-brand-bg-soft text-brand-muted',
  written_off: 'border-brand-line bg-brand-bg-soft text-brand-muted',
}

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'draft', label: 'Draft' },
  { value: 'sent', label: 'Sent' },
  { value: 'partially_paid', label: 'Part paid' },
  { value: 'paid', label: 'Paid' },
  { value: 'overdue', label: 'Overdue' },
]

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function InvoiceStatus({ status }) {
  const normalized = status || 'draft'
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${
      STATUS_STYLES[normalized] || STATUS_STYLES.draft
    }`}>
      {normalized.replaceAll('_', ' ')}
    </span>
  )
}

function QboStatus({ invoice }) {
  const synced = invoice.qbo_sync_status === 'synced'
  return (
    <span
      title={synced
        ? `Synced to QuickBooks${invoice.qbo_invoice_id ? ` (${invoice.qbo_invoice_id})` : ''}`
        : `QuickBooks ${invoice.qbo_sync_status || 'not synced'}`}
      className={`inline-flex items-center gap-1.5 text-xs ${synced ? 'text-brand-green' : 'text-brand-muted'}`}
    >
      <span className={`h-2 w-2 rounded-full ${synced ? 'bg-brand-green' : 'bg-brand-line-2'}`} />
      <span className="hidden xl:inline">{synced ? 'Synced' : 'Not synced'}</span>
    </span>
  )
}

function localDate() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

export default function InvoicesPage() {
  const navigate = useNavigate()
  const [invoices, setInvoices] = useState([])
  const [matters, setMatters] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [filter, setFilter] = useState('all')
  const [showGenerate, setShowGenerate] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generateForm, setGenerateForm] = useState({
    matter_id: '',
    date_from: '',
    date_to: localDate(),
    issue_date: localDate(),
    due_date_days: 30,
    payment_terms: 'Net 30',
    tax_rate: '',
    notes: '',
  })
  const [manualCharges, setManualCharges] = useState([])
  const generationKey = useRef(null)
  const generationPayload = useRef(null)
  const cutoffEdited = useRef(false)
  const selectionScope = useRef('')
  const [generateError, setGenerateError] = useState(null)
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(null)
  const [selectedTimeIds, setSelectedTimeIds] = useState(new Set())
  const [selectedExpenseIds, setSelectedExpenseIds] = useState(new Set())
  const [selectedFeeIds, setSelectedFeeIds] = useState(new Set())
  const [previewVersion, setPreviewVersion] = useState(0)
  const defaultsMatterRef = useRef(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const params = {}
      if (filter === 'overdue') params.overdue_only = true
      else if (filter !== 'all') params.status = filter
      const [invoiceData, matterData] = await Promise.all([
        getInvoices(params),
        getMattersV2({ page_size: 200 }),
      ])
      setInvoices(invoiceData.items || invoiceData || [])
      setMatters(matterData.items || matterData || [])
    } catch (error) {
      reportError('Failed to load invoices', error)
      setLoadError(error?.response?.data?.detail || 'Invoices could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    if (!showGenerate || !generateForm.matter_id) {
      setPreview(null)
      return
    }
    let cancelled = false
    setPreviewLoading(true)
    setPreviewError(null)
    getInvoicePreview({
      matter_id: generateForm.matter_id,
      date_from: generateForm.date_from || undefined,
      date_to: generateForm.date_to || undefined,
    }).then((data) => {
      if (cancelled) return
      setPreview(data)
      const scope = `${generateForm.matter_id}|${generateForm.date_from}|${generateForm.date_to}`
      if (selectionScope.current !== scope) {
        setSelectedTimeIds(new Set((data.time_entries || []).map((entry) => entry.id)))
        setSelectedExpenseIds(new Set((data.expenses || []).map((expense) => expense.id)))
        setSelectedFeeIds(new Set((data.fees || []).map(fee => fee.id)))
        selectionScope.current = scope
      }
      if (defaultsMatterRef.current !== data.matter_id) {
        defaultsMatterRef.current = data.matter_id
        setGenerateForm((current) => ({
          ...current,
          due_date_days: data.default_due_date_days ?? current.due_date_days,
          payment_terms: data.default_payment_terms || current.payment_terms,
          tax_rate: data.default_tax_rate != null ? String(Number(data.default_tax_rate) * 100) : current.tax_rate,
          notes: data.default_notes || current.notes,
        }))
      }
    }).catch((error) => {
      if (!cancelled) setPreviewError(error?.response?.data?.detail || 'The billing preview could not be loaded.')
    }).finally(() => {
      if (!cancelled) setPreviewLoading(false)
    })
    return () => { cancelled = true }
  }, [showGenerate, generateForm.matter_id, generateForm.date_from, generateForm.date_to, previewVersion])

  const handleGenerate = async (event) => {
    event.preventDefault()
    setGenerateError(null)
    setGenerating(true)
    try {
      if (!generateForm.matter_id) return
      const payload = {
        manual_charges: manualCharges.map(({ description, quantity, unit_price }) => ({ description, quantity, unit_price })),
        ...generateForm,
        date_from: generateForm.date_from || undefined,
        date_to: generateForm.date_to || undefined,
        due_date_days: generateForm.due_date_days === '' ? undefined : Number(generateForm.due_date_days),
        tax_rate: generateForm.tax_rate === '' ? undefined : Number(generateForm.tax_rate) / 100,
        time_entry_ids: [...selectedTimeIds],
        expense_ids: [...selectedExpenseIds],
        fee_ids: [...selectedFeeIds],
      }
      const signature = JSON.stringify(payload)
      if (generationPayload.current !== signature) {
        generationKey.current = crypto.randomUUID()
        generationPayload.current = signature
      }
      const invoice = await generateInvoice({ ...payload, generation_key: generationKey.current })
      setShowGenerate(false)
      setManualCharges([])
      cutoffEdited.current = false
      selectionScope.current = ''
      defaultsMatterRef.current = null
      setGenerateForm({ matter_id: '', date_from: '', date_to: localDate(), issue_date: localDate(), due_date_days: 30, payment_terms: 'Net 30', tax_rate: '', notes: '' })
      navigate(`/invoices/${invoice.id}`)
    } catch (error) {
      const detail = error?.response?.data?.detail
      setGenerateError(
        typeof detail === 'string'
          ? detail
          : 'The draft could not be generated. Check that the matter has unbilled time entries.',
      )
    } finally {
      setGenerating(false)
    }
  }

  const totalOutstanding = invoices
    .filter((invoice) => ['sent', 'partially_paid'].includes(invoice.status) || invoice.is_overdue)
    .reduce((sum, invoice) => sum + Number(invoice.balance_due ?? invoice.total ?? 0), 0)
  const overdueCount = invoices.filter((invoice) => invoice.is_overdue).length
  const draftCount = invoices.filter((invoice) => invoice.status === 'draft').length
  const selectedTime = (preview?.time_entries || []).filter((entry) => selectedTimeIds.has(entry.id))
  const selectedExpenses = (preview?.expenses || []).filter((expense) => selectedExpenseIds.has(expense.id))
  const selectedFees = (preview?.fees || []).filter(fee => selectedFeeIds.has(fee.id))
  const selectedHours = selectedTime.reduce((sum, entry) => sum + Number(entry.hours || 0), 0)
  const selectedSubtotal = [...selectedTime, ...selectedExpenses, ...selectedFees]
    .reduce((sum, item) => sum + Number(item.amount || 0), 0) + manualCharges.reduce((sum, item) => sum + Math.round(Number(item.quantity) * Number(item.unit_price) * 100) / 100, 0)
  const selectedTax = selectedSubtotal * (Number(generateForm.tax_rate || 0) / 100)
  const selectedTotal = selectedSubtotal + selectedTax
  const selectedCount = selectedTime.length + selectedExpenses.length + manualCharges.length + selectedFees.length

  return (
    <WorkspacePage width="wide">
      <WorkspacePageHeader
        eyebrow="Billing"
        icon={Receipt}
        title="Invoices"
        description="Generate drafts from unbilled work, review balances, and track payment status."
        meta={<span>{invoices.length} invoice{invoices.length !== 1 ? 's' : ''} in this view</span>}
        actions={
          <>
            <button
              type="button"
              onClick={loadData}
              disabled={loading}
              className="btn-secondary inline-flex items-center gap-2"
            >
              <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => {
                setShowGenerate((open) => !open)
                setGenerateError(null)
                defaultsMatterRef.current = null
              }}
              aria-expanded={showGenerate}
              className="btn-primary inline-flex items-center gap-2"
            >
              <Plus size={16} /> Generate invoice
            </button>
          </>
        }
      />

      <MetricStrip
        className="mb-6"
        items={[
          { label: 'Outstanding', value: money.format(totalOutstanding) },
          {
            label: 'Overdue',
            value: overdueCount,
            className: overdueCount ? 'text-brand-rose' : 'text-brand-ink',
          },
          { label: 'Drafts to review', value: draftCount },
        ]}
      />

      <ReadyToBill cutoff={generateForm.date_to || localDate()} onSelect={row => {
        setMatters(current => current.some(m => m.id === row.matter_id) ? current : [...current, { id: row.matter_id, matter_name: row.matter_name }])
        setGenerateForm(current => ({ ...current, matter_id: row.matter_id }))
        setManualCharges([])
        setShowGenerate(true)
      }} />
      {showGenerate && (
        <form
          onSubmit={handleGenerate}
          className="mb-6 rounded-2xl border border-brand-line bg-brand-surface p-4 shadow-sm sm:p-5"
        >
          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-brand-ink">Generate a draft invoice</h2>
              <p className="mt-1 text-sm text-brand-muted">
                Choose work through a date, add any fixed fees, and save a draft for review. Saving does not send the invoice.
              </p>
            </div>
          </div>
          {generateError && (
            <AlertBanner type="error" title="Draft was not generated" className="mt-4">
              {generateError}
            </AlertBanner>
          )}
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label htmlFor="invoicespage-matter" className="mb-1.5 block text-xs font-semibold text-brand-ink">
                Matter
              </label>
              <select
                id="invoicespage-matter"
                value={generateForm.matter_id}
                onChange={(event) => {
                  defaultsMatterRef.current = null
                  setGenerateForm((current) => ({ ...current, matter_id: event.target.value }))
                }}
                required
                className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-accent"
              >
                <option value="">Select a matter</option>
                {matters.map((matter) => (
                  <option key={matter.id} value={matter.id}>{matter.matter_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="invoicespage-date-from" className="mb-1.5 block text-xs font-semibold text-brand-ink">Work from (optional)</label>
              <input id="invoicespage-date-from" type="date" max={generateForm.date_to || undefined} value={generateForm.date_from} onChange={(event) => setGenerateForm((current) => ({ ...current, date_from: event.target.value }))} className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink" />
            </div>
            <div>
              <label htmlFor="invoicespage-date-to" className="mb-1.5 block text-xs font-semibold text-brand-ink">Work through</label>
              <input id="invoicespage-date-to" type="date" min={generateForm.date_from || undefined} value={generateForm.date_to} onChange={(event) => { cutoffEdited.current = true; setGenerateForm((current) => ({ ...current, date_to: event.target.value })) }} className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink" />
            </div>
            <div>
              <label htmlFor="invoicespage-issue-date" className="mb-1.5 block text-xs font-semibold text-brand-ink">Issue date</label>
              <input id="invoicespage-issue-date" type="date" value={generateForm.issue_date} onChange={(event) => setGenerateForm((current) => ({ ...current, issue_date: event.target.value, date_to: cutoffEdited.current ? current.date_to : event.target.value }))} required className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink" />
            </div>
            <div>
              <label htmlFor="invoicespage-terms" className="mb-1.5 block text-xs font-semibold text-brand-ink">Payment terms</label>
              <input id="invoicespage-terms" value={generateForm.payment_terms} onChange={(event) => setGenerateForm((current) => ({ ...current, payment_terms: event.target.value }))} className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink" />
            </div>
            <div>
              <label htmlFor="invoicespage-due-days" className="mb-1.5 block text-xs font-semibold text-brand-ink">Due in (days)</label>
              <input id="invoicespage-due-days" type="number" min="0" value={generateForm.due_date_days} onChange={(event) => setGenerateForm((current) => ({ ...current, due_date_days: event.target.value }))} className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink" />
            </div>
            <div>
              <label htmlFor="invoicespage-tax" className="mb-1.5 block text-xs font-semibold text-brand-ink">Sales tax rate (%)</label>
              <input id="invoicespage-tax" type="number" min="0" max="100" step="0.01" value={generateForm.tax_rate} onChange={(event) => setGenerateForm((current) => ({ ...current, tax_rate: event.target.value }))} placeholder="0" className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink" />
              <p className="mt-1 text-xs text-brand-ink-2">Use 0 for non-taxable services. QuickBooks will receive the same taxable status.</p>
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="invoicespage-notes" className="mb-1.5 block text-xs font-semibold text-brand-ink">Invoice notes</label>
              <input id="invoicespage-notes" value={generateForm.notes} onChange={(event) => setGenerateForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Optional note for the client" className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-surface px-3 text-sm text-brand-ink" />
            </div>
            <button
              type="submit"
              disabled={generating || previewLoading || !!previewError || !preview || selectedCount === 0}
              className="btn-primary self-end inline-flex min-h-11 items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {generating && <RefreshCw size={15} className="animate-spin" />}
              {generating ? 'Generating draft' : 'Generate draft'}
            </button>
          </div>
          {previewError && <AlertBanner type="error" title="Preview unavailable" className="mt-4">{previewError}</AlertBanner>}
          <fieldset className="mt-4 rounded-xl border border-brand-line p-4">
            <legend className="px-2 text-sm font-semibold text-brand-ink">Fixed fees</legend>
            <p className="text-sm text-brand-muted">Create a fee-only invoice or add charges to the selected work. All older unbilled work remains eligible unless you set a start date.</p>
            {manualCharges.map((charge, index) => (
              <div key={charge.id} className="mt-3 grid gap-3 sm:grid-cols-4">
                <label className="text-sm">Fee description {index + 1}<input required maxLength={4000} value={charge.description} onChange={e => setManualCharges(rows => rows.map(row => row.id === charge.id ? { ...row, description: e.target.value } : row))} className="input w-full" /></label>
                <label className="text-sm">Quantity {index + 1}<input required type="number" min="0.01" step="0.01" value={charge.quantity} onChange={e => setManualCharges(rows => rows.map(row => row.id === charge.id ? { ...row, quantity: e.target.value } : row))} className="input w-full" /></label>
                <label className="text-sm">Unit price {index + 1}<input required type="number" min="0" step="0.01" value={charge.unit_price} onChange={e => setManualCharges(rows => rows.map(row => row.id === charge.id ? { ...row, unit_price: e.target.value } : row))} className="input w-full" /></label>
                <button type="button" className="btn-secondary self-end" onClick={() => setManualCharges(rows => rows.filter(row => row.id !== charge.id))}>Remove fee {index + 1}</button>
              </div>
            ))}
            <button type="button" className="btn-secondary mt-3" disabled={manualCharges.length >= 100} onClick={() => setManualCharges(rows => [...rows, { id: crypto.randomUUID(), description: '', quantity: '1', unit_price: '' }])}>Add fixed fee</button>
          </fieldset>
          {previewLoading && <div className="mt-5"><Spinner /></div>}
          {preview && !previewLoading && selectedCount === 0 && (
            <AlertBanner type="warning" title="Select work to invoice" className="mt-4">
              This billing period has no selected time or expenses. Adjust the dates or include at least one row.
            </AlertBanner>
          )}
          {preview && !previewLoading && (
            <div className="mt-5 rounded-xl border border-brand-line bg-brand-bg-soft/40 p-4">
              <h3 className="text-sm font-semibold text-brand-ink">Review billable work{preview.matter_name ? ` · ${preview.matter_name}` : ''}</h3>
              <div className="mt-3 overflow-x-auto">
                <table className="min-w-full text-left text-xs">
                  <thead><tr className="border-b border-brand-line text-[10px] uppercase tracking-wide text-brand-muted"><th className="px-2 py-2">Include</th><th className="px-2 py-2">Date</th><th className="px-2 py-2">Description</th><th className="px-2 py-2 text-right">Hours / Amount</th></tr></thead>
                  <tbody className="divide-y divide-brand-line/60">
                    {[...(preview.time_entries || []).map((entry) => ({ ...entry, kind: 'time' })), ...(preview.expenses || []).map((expense) => ({ ...expense, kind: 'expense' })), ...(preview.fees || []).map(fee => ({ ...fee, date: fee.service_date, kind: 'fee' }))].map((item) => {
                      const selected = (item.kind === 'time' ? selectedTimeIds : item.kind === 'fee' ? selectedFeeIds : selectedExpenseIds).has(item.id)
                      return (
                        <tr key={`${item.kind}-${item.id}`}>
                          <td className="px-2 py-2">
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => (item.kind === 'time' ? setSelectedTimeIds : item.kind === 'fee' ? setSelectedFeeIds : setSelectedExpenseIds)((current) => {
                                const next = new Set(current)
                                selected ? next.delete(item.id) : next.add(item.id)
                                return next
                              })}
                              aria-label={`Include ${item.description}`}
                            />
                          </td>
                          <td className="px-2 py-2 text-brand-muted">{item.date || '—'}</td>
                          <td className="max-w-md px-2 py-2 text-brand-ink">{item.description}</td>
                          <td className="px-2 py-2 text-right font-mono">
                            {item.kind === 'time'
                              ? `${item.hours}h · ${money.format(Number(item.amount || 0))}`
                              : (
                                <>
                                  {money.format(Number(item.amount || 0))}
                                  {item.cost_amount != null && Number(item.cost_amount) !== Number(item.amount) && (
                                    <span className="block text-[10px] text-brand-muted">
                                      firm cost {money.format(Number(item.cost_amount))}
                                    </span>
                                  )}
                                </>
                              )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <dl className="mt-4 grid gap-3 border-t border-brand-line pt-3 text-sm sm:grid-cols-4">
                <div><dt className="text-xs text-brand-muted">Selected work</dt><dd className="mt-1 font-semibold text-brand-ink">{selectedCount} item{selectedCount === 1 ? '' : 's'} · {selectedHours.toFixed(2)}h</dd></div>
                <div><dt className="text-xs text-brand-muted">Subtotal</dt><dd className="mt-1 font-semibold text-brand-ink">{money.format(selectedSubtotal)}</dd></div>
                <div><dt className="text-xs text-brand-muted">Tax</dt><dd className="mt-1 font-semibold text-brand-ink">{money.format(selectedTax)}</dd></div>
                <div><dt className="text-xs text-brand-muted">Draft total</dt><dd className="mt-1 font-serif text-lg font-bold text-brand-ink">{money.format(selectedTotal)}</dd></div>
              </dl>
            </div>
          )}
          {generateForm.matter_id && <BillingFees key={generateForm.matter_id} matterId={generateForm.matter_id} onChange={() => { selectionScope.current = ''; setPreviewVersion(value => value + 1) }} />}
          {generateForm.matter_id && <BillingSchedule key={`schedule-${generateForm.matter_id}`} matterId={generateForm.matter_id} />}
        </form>
      )}

      <FilterToolbar ariaLabel="Invoice status filters">
        <SegmentedControl
          items={FILTERS}
          value={filter}
          onChange={setFilter}
          label="Filter invoices by status"
        />
      </FilterToolbar>

      {loadError ? (
        <AlertBanner
          type="error"
          title="Invoices could not be loaded"
          actionLabel="Retry"
          onAction={loadData}
        >
          {loadError}
        </AlertBanner>
      ) : loading ? (
        <Spinner />
      ) : invoices.length === 0 ? (
        <EmptyState
          icon={Receipt}
          title={filter === 'all' ? 'No invoices yet' : `No ${FILTERS.find((item) => item.value === filter)?.label.toLowerCase()} invoices`}
          actionLabel="Generate invoice"
          onAction={() => setShowGenerate(true)}
          secondaryActionLabel={filter !== 'all' ? 'Show all invoices' : undefined}
          onSecondaryAction={() => setFilter('all')}
        >
          {filter === 'all'
            ? 'Generate a draft from a matter with unbilled time or expenses.'
            : 'Choose another status or return to all invoices.'}
        </EmptyState>
      ) : (
        <>
          <div className="space-y-3 md:hidden">
            {invoices.map((invoice) => {
              const displayStatus = invoice.is_overdue ? 'overdue' : invoice.status
              return (
                <Link
                  key={invoice.id}
                  to={`/invoices/${invoice.id}`}
                  className="block rounded-2xl border border-brand-line bg-brand-surface p-4 shadow-sm hover:border-brand-line-2"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-brand-accent-2">{invoice.invoice_number}</p>
                      <p className="mt-1 truncate text-sm font-semibold text-brand-ink">
                        {invoice.matter_name || 'Matter unavailable'}
                      </p>
                    </div>
                    <InvoiceStatus status={displayStatus} />
                  </div>
                  <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-brand-line pt-3">
                    <div>
                      <dt className="text-[10px] font-bold uppercase tracking-wide text-brand-muted">Balance</dt>
                      <dd className={`mt-1 text-sm font-semibold ${Number(invoice.balance_due) > 0 ? 'text-brand-rose' : 'text-brand-green'}`}>
                        {money.format(Number(invoice.balance_due ?? invoice.total ?? 0))}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[10px] font-bold uppercase tracking-wide text-brand-muted">Due</dt>
                      <dd className={`mt-1 text-sm ${invoice.is_overdue ? 'font-semibold text-brand-rose' : 'text-brand-ink'}`}>
                        {invoice.due_date || 'Not set'}
                      </dd>
                    </div>
                  </dl>
                </Link>
              )
            })}
          </div>

          <div className="hidden overflow-hidden rounded-2xl border border-brand-line bg-brand-surface shadow-sm md:block">
            <div className="overflow-x-auto">
              <table className="min-w-[860px] w-full border-collapse text-left text-sm">
                <thead className="border-b border-brand-line bg-brand-bg-soft/60">
                  <tr>
                    {['Invoice', 'Matter', 'Issued', 'Due', 'Total', 'Balance', 'Status', 'QuickBooks'].map((heading) => (
                      <th key={heading} scope="col" className="px-4 py-3 text-[10px] font-bold uppercase tracking-[0.12em] text-brand-muted">
                        {heading}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-brand-line">
                  {invoices.map((invoice) => {
                    const displayStatus = invoice.is_overdue ? 'overdue' : invoice.status
                    return (
                      <tr key={invoice.id} className="hover:bg-brand-bg-soft/50">
                        <td className="px-4 py-3">
                          <Link
                            to={`/invoices/${invoice.id}`}
                            className="inline-flex min-h-10 items-center font-semibold text-brand-accent-2 hover:underline"
                          >
                            {invoice.invoice_number}
                          </Link>
                        </td>
                        <td className="max-w-64 truncate px-4 py-3 text-brand-ink" title={invoice.matter_name || ''}>
                          {invoice.matter_name || '—'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-brand-muted">{invoice.issue_date || '—'}</td>
                        <td className={`whitespace-nowrap px-4 py-3 ${invoice.is_overdue ? 'font-semibold text-brand-rose' : 'text-brand-muted'}`}>
                          {invoice.due_date || '—'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 font-semibold text-brand-ink">
                          {money.format(Number(invoice.total || 0))}
                        </td>
                        <td className={`whitespace-nowrap px-4 py-3 font-semibold ${Number(invoice.balance_due) > 0 ? 'text-brand-rose' : 'text-brand-green'}`}>
                          {money.format(Number(invoice.balance_due ?? invoice.total ?? 0))}
                        </td>
                        <td className="px-4 py-3"><InvoiceStatus status={displayStatus} /></td>
                        <td className="px-4 py-3"><QboStatus invoice={invoice} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </WorkspacePage>
  )
}
