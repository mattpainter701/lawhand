import { useEffect, useMemo, useRef, useState } from 'react'
import { Download, Loader2, X } from 'lucide-react'
import { getSampleTemplateSource, previewSampleTemplateSmartFill, renderSampleTemplateFile } from '../../api'
import MatterPicker from '../prepare/MatterPicker'
import GeneratedPdfPreview from './GeneratedPdfPreview'

// Fill a shared sample form with ad-hoc values and download the flattened PDF.
// The sample library is read-only shared content: filling never saves a copy to
// the tenant's own template library, it only produces a one-off PDF download.
const inputClass = 'w-full rounded-lg border border-brand-line bg-brand-bg px-3 py-2 text-sm text-brand-ink'
const hasValue = (value, field) => {
  if (field?.field_type === 'checkbox') return ['true', 'on', 'yes', '1'].includes(String(value || '').toLowerCase())
  return value !== undefined && value !== null && !(typeof value === 'string' && value.trim() === '')
}
const isRequired = (field) => field.required === true || (field.required === undefined && field.source_required === true)
const isPlaceholderSourceLabel = (value) => /^(undefined|null|unknown|none)(?:[_ -]\d+)?$/i.test(String(value || '').trim())

export function FieldInput({ field, value, onChange }) {
  const label = field.label || String(field.name || '').replace(/_/g, ' ')
  const type = field.field_type || 'text'
  const inputId = `sample-field-${field.name}`

  if (type === 'radio' && Array.isArray(field.options) && field.options.length) {
    return (
      <fieldset className="space-y-1.5">
        <legend className="block text-sm font-medium text-brand-ink">{label}{isRequired(field) ? ' *' : ''}</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {field.options.map((option) => {
            const optionValue = typeof option === 'object' ? option.value : option
            const optionLabel = typeof option === 'object' ? (option.label || option.value) : option
            return (
              <label key={optionValue} htmlFor={`${inputId}-${optionValue}`} className="flex items-center gap-2 text-sm text-brand-ink">
                <input
                  id={`${inputId}-${optionValue}`}
                  name={inputId}
                  type="radio"
                  checked={value === optionValue}
                  onChange={() => onChange(optionValue)}
                  className="h-4 w-4 border-brand-line"
                />
                <span>{optionLabel}</span>
              </label>
            )
          })}
        </div>
      </fieldset>
    )
  }

  if (type === 'checkbox') {
    return (
      <label htmlFor={inputId} className="flex items-center gap-2 text-sm text-brand-ink">
        <input
          id={inputId}
          type="checkbox"
          checked={['true', 'on', 'yes', '1'].includes(String(value || '').toLowerCase())}
          onChange={(event) => onChange(event.target.checked ? 'Yes' : '')}
          className="h-4 w-4 rounded border-brand-line"
        />
        <span>{label}{isRequired(field) ? ' *' : ''}</span>
      </label>
    )
  }

  if (type === 'choice' && Array.isArray(field.options) && field.options.length) {
    return (
      <label htmlFor={inputId} className="block text-sm text-brand-ink">
        <span className="mb-1 block font-medium">{label}{isRequired(field) ? ' *' : ''}</span>
        <select
          id={inputId}
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value)}
          className={inputClass}
        >
          <option value="">—</option>
          {field.options.map((option) => {
            const optionValue = typeof option === 'object' ? option.value : option
            const optionLabel = typeof option === 'object' ? (option.label || option.value) : option
            return <option key={optionValue} value={optionValue}>{optionLabel}</option>
          })}
        </select>
      </label>
    )
  }

  return (
    <label htmlFor={inputId} className="block text-sm text-brand-ink">
      <span className="mb-1 block font-medium">{label}{isRequired(field) ? ' *' : ''}</span>
      <input
        id={inputId}
        type="text"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
        className={inputClass}
      />
    </label>
  )
}

export default function SampleFillDialog({ sample, onClose }) {
  const fields = useMemo(
    () => (sample.variable_schema?.fields || []).filter((field) => field?.name),
    [sample],
  )
  const [values, setValues] = useState(() => Object.fromEntries(
    fields.filter((field) => field.default !== undefined && field.default !== '')
      .map((field) => [field.name, field.default]),
  ))
  const [matterId, setMatterId] = useState('')
  const [smartFill, setSmartFill] = useState(null)
  const [smartFillBusy, setSmartFillBusy] = useState(false)
  const [sourcePreview, setSourcePreview] = useState('')
  const [filledPreview, setFilledPreview] = useState(null)
  const [fieldFilter, setFieldFilter] = useState('all')
  const manualFields = useRef(new Set())
  const matterRequest = useRef(0)
  const renderRevision = useRef(0)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    getSampleTemplateSource(sample.id)
      .then(blob => { if (active) setSourcePreview(blob) })
      .catch(() => { /* The visible source button lets the user retry. */ })
    return () => { active = false }
  }, [sample.id])

  const setValue = (name, value) => {
    manualFields.current.add(name)
    renderRevision.current += 1
    setFilledPreview(null)
    setBusy(false)
    setValues((current) => ({ ...current, [name]: value }))
  }
  const groups = useMemo(() => {
    const byPage = new Map()
    fields.forEach((field) => {
      const key = field.page ? `Page ${field.page}` : 'Source fields'
      if (!byPage.has(key)) byPage.set(key, [])
      byPage.get(key).push(field)
    })
    return [...byPage.entries()]
  }, [fields])
  const filteredFields = useMemo(() => fields.filter((field) => (
    fieldFilter === 'all'
      || (fieldFilter === 'missing' ? isRequired(field) && !hasValue(values[field.name], field) : false)
      || (fieldFilter === 'optional' ? !isRequired(field) && !hasValue(values[field.name], field) : false)
      || (fieldFilter === 'filled' ? hasValue(values[field.name], field) : false)
  )), [fields, fieldFilter, values])
  const smartFillCounts = useMemo(() => ({
    filled: fields.filter((field) => hasValue(values[field.name], field)).length,
    requiredMissing: fields.filter((field) => isRequired(field) && !hasValue(values[field.name], field)).length,
    optionalUnfilled: fields.filter((field) => !isRequired(field) && !hasValue(values[field.name], field)).length,
  }), [fields, values])

  const provenance = sample.provenance || {}
  const sourceContext = [provenance.source_name, provenance.edition].filter(Boolean).join(' · ')

  const chooseMatter = async (nextMatterId) => {
    const request = ++matterRequest.current
    const sameMatter = Boolean(nextMatterId && nextMatterId === matterId)
    renderRevision.current += 1
    setFilledPreview(null)
    setBusy(false)
    setMatterId(nextMatterId)
    setSmartFill(null)
    if (!sameMatter) manualFields.current = new Set()
    if (!nextMatterId) {
      setSmartFillBusy(false)
      setError('')
      setValues(Object.fromEntries(fields.map((field) => [field.name, field.default || ''])))
      return
    }
    if (!sameMatter) setValues(Object.fromEntries(fields.map((field) => [field.name, field.default || ''])))
    setSmartFillBusy(true)
    setError('')
    try {
      const result = await previewSampleTemplateSmartFill(sample.id, {
        matter_id: nextMatterId,
        variables: fields.map((field) => field.name),
      })
      if (!mounted.current || request !== matterRequest.current) return
      const suggestions = result.variables || []
      const suggested = Object.fromEntries(suggestions.filter((item) => item.suggested_value != null && item.suggested_value !== '').map((item) => [item.variable, item.suggested_value]))
      const manual = manualFields.current
      setValues((current) => Object.fromEntries(fields.map((field) => [
        field.name,
        manual.has(field.name) ? current[field.name] : (suggested[field.name] ?? field.default ?? ''),
      ])))
      setSmartFill({ suggestions })
    } catch (err) {
      if (mounted.current && request === matterRequest.current) setError(err?.response?.data?.detail || 'The matter could not be used for Smart Fill.')
    } finally {
      if (mounted.current && request === matterRequest.current) setSmartFillBusy(false)
    }
  }

  const previewSource = async () => {
    try {
      const blob = await getSampleTemplateSource(sample.id)
      setSourcePreview(blob)
    } catch {
      setError('The source preview could not be opened.')
    }
  }

  const renderPreview = async () => {
    const revision = ++renderRevision.current
    setBusy(true)
    setError('')
    try {
      const result = await renderSampleTemplateFile(sample.id, { variables: values })
      if (mounted.current && revision === renderRevision.current) setFilledPreview(result)
    } catch (err) {
      if (mounted.current && revision === renderRevision.current) setError(err?.message || 'The sample could not be previewed. Please try again.')
    } finally {
      if (mounted.current && revision === renderRevision.current) setBusy(false)
    }
  }

  const downloadPreview = () => {
    if (!filledPreview || busy || smartFillBusy) return
    const url = URL.createObjectURL(filledPreview.blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filledPreview.filename
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const submit = (event) => { event.preventDefault(); renderPreview() }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sample-fill-title"
        className="flex h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-brand-line bg-brand-surface-2 p-4 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 id="sample-fill-title" className="text-lg font-semibold text-brand-ink">Fill “{sample.title}”</h3>
            <p className="mt-1 text-sm text-brand-muted">
              Choose a matter, check the answers, then preview your PDF.
            </p>
            <details className="mt-1 text-xs text-brand-muted">
            <summary className="cursor-pointer">About this sample</summary>
            <p className="mt-1 leading-5">
              {sample.jurisdictions?.length ? sample.jurisdictions.join(', ') : 'General'}
              {sourceContext ? ` · Source: ${sourceContext}` : ' · Source details were not recorded'}
            </p>
            {sample.description && <p className="mt-2 text-xs leading-5 text-brand-muted">{sample.description}</p>}
            <p className="mt-1">Downloading does not save a copy to the matter or template library.</p>
            </details>
            <div className="mt-2">
              <MatterPicker matters={[]} selectedMatterId={matterId} onSelect={chooseMatter} loading={false} disabled={smartFillBusy || busy} />
            </div>
            {smartFill && <p className="mt-2 rounded border border-brand-line bg-brand-bg px-3 py-2 text-xs text-brand-muted">{smartFillCounts.filled} filled · {smartFillCounts.requiredMissing} required answers missing · {smartFillCounts.optionalUnfilled} optional unanswered. Review every value before downloading.</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close fill dialog" className="rounded-lg p-1 text-brand-muted hover:bg-brand-bg hover:text-brand-ink">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {!sourcePreview && <div className="mt-2 flex shrink-0 items-center gap-2">
          <button type="button" onClick={previewSource} className="rounded-lg border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand-bg">Preview source here</button>
        </div>}
        <form onSubmit={submit} className="mt-3 flex min-h-0 flex-1 flex-col">
          <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:overflow-hidden">
          <div className="space-y-3 lg:overflow-y-auto lg:pr-2">
          <div className="sticky top-0 z-10 flex items-center gap-2 bg-brand-surface-2 pb-2 text-xs">
            <span className="font-semibold text-brand-muted">Show</span>
            {['all', 'missing', 'optional', 'filled'].map((filter) => <button key={filter} type="button" onClick={() => setFieldFilter(filter)} className={`rounded border px-2 py-1 ${fieldFilter === filter ? 'border-brand-accent bg-brand-accent/10 font-semibold' : 'border-brand-line'}`}>{filter[0].toUpperCase() + filter.slice(1)}</button>)}
          </div>
          {groups.filter(([, groupFields]) => groupFields.some(field => filteredFields.includes(field))).map(([group, groupFields]) => (
            <fieldset key={group} className="space-y-3 rounded-lg border border-brand-line p-3">
              <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-brand-muted">{group}</legend>
              {groupFields.filter((field) => filteredFields.includes(field)).map((field) => (
                <div key={field.name}>
                  <FieldInput
                    field={field}
                    value={values[field.name]}
                    onChange={(value) => setValue(field.name, value)}
                  />
                  {field.source_label && !isPlaceholderSourceLabel(field.source_label) && field.source_label !== field.label && (
                    <p className="mt-1 text-[11px] text-brand-muted">Source label: {field.source_label}</p>
                  )}
                  {field.source_label && isPlaceholderSourceLabel(field.source_label) && field.label_source !== 'curated' && (
                    <p className="mt-1 text-[11px] text-brand-muted">Source label unavailable; check this field in the source PDF before filling.</p>
                  )}
                </div>
              ))}
            </fieldset>
          ))}
          {!filteredFields.length && <p className="rounded border border-dashed border-brand-line p-3 text-sm text-brand-muted">No fields match this filter.</p>}
          </div>
          <div className="min-w-0 lg:overflow-y-auto">
            {filledPreview ? <GeneratedPdfPreview key={filledPreview.filename} source={filledPreview.blob} title={`Filled: ${sample.title}`} /> : sourcePreview ? <GeneratedPdfPreview key="source-preview" source={sourcePreview} title={`Source: ${sample.title}`} /> : <p className="rounded border border-dashed border-brand-line p-6 text-sm text-brand-muted">Preview the source or filled PDF here.</p>}
          </div>
          </div>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="mt-3 flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-brand-line pt-3">
            <button type="button" onClick={onClose} className="rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-bg">
              Cancel
            </button>
            {filledPreview && <button type="button" disabled={busy || smartFillBusy} onClick={downloadPreview} className="inline-flex items-center gap-2 rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink disabled:cursor-not-allowed disabled:opacity-50"> <Download size={16} aria-hidden="true" /> Download filled PDF</button>}
            <button type="submit" disabled={busy || smartFillBusy || !fields.length} className="inline-flex items-center gap-2 rounded-lg bg-brand-ink px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
              {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Download size={16} aria-hidden="true" />}
              {busy ? 'Preparing preview…' : 'Preview filled PDF'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
