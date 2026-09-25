import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, Download, Eye, FileCheck2, Loader2, Save, Wand2, X } from 'lucide-react'
import { getSampleTemplateSource, previewSampleTemplateSmartFill, renderSampleTemplateFile, saveSampleTemplateToMatter, updateMatterDocument } from '../../api'
import MatterPicker from '../prepare/MatterPicker'
import FillOnDocument, { hasFillValue as hasValue, isFieldRequired as isRequired } from './FillOnDocument'
import GeneratedPdfPreview from './GeneratedPdfPreview'
import { placementsFor } from './pdfFieldGeometry'
import { readFillViewPreference, writeFillViewPreference } from './fillViewPreference'

// Fill a shared sample form with ad-hoc values and download the flattened PDF.
// The sample library is read-only shared content: filling never saves a copy to
// the tenant's own template library, it only produces a one-off PDF.
//
// Opened from a matter (`fixedMatterId`), the dialog fills from that matter on
// open and files the reviewed PDF on it, then offers to share it with the
// client. That keeps a one-off court form from having to be imported, tested
// and published as a firm template before it can be used.
//
// Answers are typed on the original document by default (Document view). The
// Questions view lists the same answers as a form for people who prefer it, and
// Final PDF shows the server-flattened result that will be downloaded.
const inputClass = 'w-full rounded-lg border border-brand-line bg-brand-bg px-3 py-2 text-sm text-brand-ink'
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

const VIEWS = [
  { id: 'document', label: 'Document' },
  { id: 'questions', label: 'Questions' },
]

export default function SampleFillDialog({ sample, onClose, fixedMatterId = '', folderId = null, onSaved }) {
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
  const [sourceUnavailable, setSourceUnavailable] = useState(false)
  const [filledPreview, setFilledPreview] = useState(null)
  const [fieldFilter, setFieldFilter] = useState('all')
  // The original document is the default: people recognise a form by its
  // pages, not by a list of its field names. Questions stays one click away.
  const [view, setView] = useState(readFillViewPreference)
  const [editView, setEditView] = useState(readFillViewPreference)
  const [suggestedNames, setSuggestedNames] = useState(() => new Set())
  // Matter search stays folded away until asked for, so the document gets the
  // screen. Once a matter is chosen the picker collapses to a one-line summary.
  const [matterOpen, setMatterOpen] = useState(false)
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
  const [saving, setSaving] = useState(false)
  const [savedDocument, setSavedDocument] = useState(null)
  const [sharing, setSharing] = useState(false)
  const [shareError, setShareError] = useState('')
  const matterMode = Boolean(fixedMatterId)
  useEffect(() => {
    let active = true
    getSampleTemplateSource(sample.id)
      .then(blob => { if (active) setSourcePreview(blob) })
      .catch(() => { if (active) setSourceUnavailable(true) })
    return () => { active = false }
  }, [sample.id])
  const savingRef = useRef(false)
  const requestClose = () => { if (!savingRef.current) onClose() }
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape' && !savingRef.current) onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const hasPlacedFields = useMemo(() => fields.some((field) => placementsFor(field).length), [fields])
  const documentAvailable = hasPlacedFields && !sourceUnavailable
  const showView = (next) => {
    setView(next)
    if (next !== 'final') {
      setEditView(next)
      writeFillViewPreference(next)
    }
  }
  // A final PDF is only meaningful for the answers it was rendered from; once
  // it is cleared the Final tab goes away and editing resumes where it was.
  const activeView = view === 'final' && !filledPreview
    ? editView
    : (view === 'document' && !documentAvailable ? 'questions' : view)

  const invalidateFinal = () => {
    renderRevision.current += 1
    setFilledPreview(null)
    setBusy(false)
  }
  const setValue = (name, value) => {
    if (savedDocument) return
    manualFields.current.add(name)
    invalidateFinal()
    setSuggestedNames((current) => {
      if (!current.has(name)) return current
      const next = new Set(current)
      next.delete(name)
      return next
    })
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
    invalidateFinal()
    setMatterId(nextMatterId)
    setSmartFill(null)
    if (!sameMatter) {
      manualFields.current = new Set()
      setSuggestedNames(new Set())
    }
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
      setSuggestedNames(new Set(Object.keys(suggested).filter((name) => !manual.has(name))))
      setSmartFill({ suggestions })
    } catch (err) {
      if (mounted.current && request === matterRequest.current) setError(err?.response?.data?.detail || 'The matter could not be used for Smart Fill.')
    } finally {
      if (mounted.current && request === matterRequest.current) setSmartFillBusy(false)
    }
  }

  // From a matter the destination is already known, so fill from it at once.
  useEffect(() => {
    if (fixedMatterId && fields.length) chooseMatter(fixedMatterId)
  }, [fixedMatterId, sample.id])

  const renderPreview = async () => {
    const revision = ++renderRevision.current
    setBusy(true)
    setError('')
    try {
      const result = await renderSampleTemplateFile(sample.id, { variables: values })
      if (mounted.current && revision === renderRevision.current) {
        setFilledPreview(result)
        setView('final')
      }
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

  const saveToMatter = async () => {
    if (!filledPreview || busy || smartFillBusy || saving || savedDocument) return
    savingRef.current = true
    setSaving(true)
    setError('')
    try {
      const result = await saveSampleTemplateToMatter(sample.id, {
        matter_id: fixedMatterId,
        // Saving requires an explicit answer for every field; blank is an answer.
        variables: Object.fromEntries(fields.map((field) => [field.name, values[field.name] ?? ''])),
        ...(folderId ? { folder_id: folderId } : {}),
      })
      if (!mounted.current) return
      setSavedDocument(result.matter_document || { id: result.matter_document_id, filename: result.output_filename, portal_visible: false })
      await onSaved?.(result)
    } catch (err) {
      if (mounted.current) setError(err?.response?.data?.detail || err?.message || 'The document could not be saved to the matter. Try again.')
    } finally {
      savingRef.current = false
      if (mounted.current) setSaving(false)
    }
  }

  const shareWithClient = async () => {
    if (!savedDocument || sharing) return
    setSharing(true)
    setShareError('')
    try {
      const updated = await updateMatterDocument(fixedMatterId, savedDocument.id, { portal_visible: true })
      if (mounted.current) setSavedDocument((current) => ({ ...current, ...updated, portal_visible: true }))
    } catch (err) {
      if (mounted.current) setShareError(err?.response?.data?.detail || 'The document was saved but could not be shared. Share it from the Documents list.')
    } finally {
      if (mounted.current) setSharing(false)
    }
  }

  const requiredMissing = smartFillCounts.requiredMissing > 0
  const submit = (event) => {
    event.preventDefault()
    if (matterMode && filledPreview) saveToMatter()
    else renderPreview()
  }
  const renderInput = (field, value, onChange) => <FieldInput field={field} value={value} onChange={onChange} />
  const views = [
    ...VIEWS.filter((item) => item.id !== 'document' || documentAvailable),
    ...(filledPreview ? [{ id: 'final', label: 'Final PDF' }] : []),
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/40 sm:p-3" role="presentation" onClick={requestClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sample-fill-title"
        className="flex h-full w-full max-w-[1400px] flex-col overflow-hidden bg-brand-surface-2 shadow-xl sm:rounded-xl sm:border sm:border-brand-line"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="shrink-0 border-b border-brand-line px-3 pb-2 pt-3 sm:px-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h3 id="sample-fill-title" className="truncate text-base font-semibold text-brand-ink sm:text-lg">{matterMode ? `Fill “${sample.title}” for this matter` : `Fill “${sample.title}”`}</h3>
              <details className="text-xs text-brand-muted">
                <summary className="cursor-pointer">About this sample</summary>
                <p className="mt-1 leading-5">
                  {sample.jurisdictions?.length ? sample.jurisdictions.join(', ') : 'General'}
                  {sourceContext ? ` · Source: ${sourceContext}` : ' · Source details were not recorded'}
                </p>
                {sample.description && <p className="mt-2 text-xs leading-5 text-brand-muted">{sample.description}</p>}
                <p className="mt-1">{matterMode
                  ? 'Saving files the filled PDF on this matter. Nothing is added to your firm’s template library.'
                  : 'Downloading does not save a copy to the matter or template library.'}</p>
              </details>
            </div>
            <button type="button" onClick={requestClose} disabled={saving} aria-label="Close fill dialog" className="rounded-lg p-1 text-brand-muted hover:bg-brand-bg hover:text-brand-ink">
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          {!matterMode && (matterOpen || matterId) && (
            <div className="mt-2 flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <MatterPicker matters={[]} selectedMatterId={matterId} onSelect={chooseMatter} loading={false} disabled={smartFillBusy || busy} />
              </div>
              {!matterId && <button type="button" onClick={() => setMatterOpen(false)} className="shrink-0 rounded-lg border border-brand-line px-2 py-1 text-xs text-brand-muted hover:bg-brand-bg hover:text-brand-ink">Hide</button>}
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
            <div role="tablist" aria-label="Fill view" className="inline-flex rounded-lg border border-brand-line bg-brand-bg p-0.5">
              {views.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={activeView === item.id}
                  onClick={() => showView(item.id)}
                  className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${activeView === item.id ? 'bg-brand-surface text-brand-ink shadow-sm' : 'text-brand-muted hover:text-brand-ink'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {!matterMode && !matterOpen && !matterId && (
              <button type="button" onClick={() => setMatterOpen(true)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line bg-brand-surface px-3 py-1.5 text-sm font-semibold text-brand-ink hover:bg-brand-bg">
                <Wand2 size={15} aria-hidden="true" /> Fill from a matter
              </button>
            )}
            <p className="text-xs text-brand-muted" aria-live="polite">
              {smartFillBusy ? 'Filling from the matter…' : `${smartFillCounts.filled} filled · ${smartFillCounts.requiredMissing} required answers missing · ${smartFillCounts.optionalUnfilled} optional unanswered.`}
              {smartFill && !smartFillBusy && (matterMode ? ' Filled from this matter — review every value before saving.' : ' Review every value before downloading.')}
            </p>
          </div>
        </header>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col px-3 pt-3 sm:px-4">
          {activeView === 'document' && (
            <FillOnDocument
              source={sourcePreview || null}
              fields={fields}
              values={values}
              suggestedNames={suggestedNames}
              onChange={setValue}
              renderInput={renderInput}
              onUnavailable={() => setSourceUnavailable(true)}
            />
          )}
          {activeView === 'questions' && (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto max-w-2xl space-y-3 pb-3">
                <div className="sticky top-0 z-10 flex items-center gap-2 bg-brand-surface-2 pb-2 text-xs">
                  <span className="font-semibold text-brand-muted">Show</span>
                  {['all', 'missing', 'optional', 'filled'].map((filter) => <button key={filter} type="button" onClick={() => setFieldFilter(filter)} className={`rounded border px-2 py-1 ${fieldFilter === filter ? 'border-brand-accent bg-brand-accent/10 font-semibold' : 'border-brand-line'}`}>{filter[0].toUpperCase() + filter.slice(1)}</button>)}
                </div>
                {!documentAvailable && sourceUnavailable && <p className="rounded border border-brand-line bg-brand-bg px-3 py-2 text-xs text-brand-muted">The original document could not be opened here, so answers are listed as questions. Preview the final PDF to check placement.</p>}
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
            </div>
          )}
          {activeView === 'final' && filledPreview && (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <GeneratedPdfPreview key={filledPreview.filename} source={filledPreview.blob} title={`Filled: ${sample.title}`} />
            </div>
          )}
          {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
          {savedDocument ? (
            <div role="status" className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-brand-line py-3">
              <p className="flex min-w-0 items-center gap-2 text-sm text-brand-ink">
                <CheckCircle2 size={18} className="shrink-0 text-brand-green" aria-hidden="true" />
                <span className="min-w-0">Saved to this matter’s documents{savedDocument.filename ? <> as <strong className="break-all">{savedDocument.filename}</strong></> : ''}.{savedDocument.portal_visible ? ' Shared with the client.' : ''}</span>
              </p>
              {shareError && <p role="alert" className="w-full text-sm text-red-700">{shareError}</p>}
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={downloadPreview} className="inline-flex items-center gap-2 rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-bg"><Download size={16} aria-hidden="true" /> Download</button>
                {!savedDocument.portal_visible && <button type="button" disabled={sharing} onClick={shareWithClient} className="inline-flex items-center gap-2 rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-bg disabled:opacity-50">
                  {sharing ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />} {sharing ? 'Sharing…' : 'Share with client'}
                </button>}
                <button type="button" onClick={onClose} className="rounded-lg bg-brand-ink px-4 py-2 text-sm font-semibold text-white">Done</button>
              </div>
            </div>
          ) : matterMode ? (
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-brand-line py-3">
              {requiredMissing && <p className="mr-auto text-xs text-brand-muted">Answer the required questions to finish.</p>}
              <button type="button" onClick={requestClose} disabled={saving} className="rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-bg disabled:opacity-50">
                Cancel
              </button>
              {filledPreview ? (
                <button type="submit" disabled={busy || smartFillBusy || saving || requiredMissing} className="inline-flex items-center gap-2 rounded-lg bg-brand-ink px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
                  {saving ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Save size={16} aria-hidden="true" />}
                  {saving ? 'Saving to matter…' : 'Save to matter'}
                </button>
              ) : (
                <button type="submit" disabled={busy || smartFillBusy || !fields.length} className="inline-flex items-center gap-2 rounded-lg bg-brand-ink px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
                  {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <FileCheck2 size={16} aria-hidden="true" />}
                  {busy ? 'Preparing final PDF…' : 'Review final PDF'}
                </button>
              )}
            </div>
          ) : (
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-brand-line py-3">
            <button type="button" onClick={onClose} className="rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand-bg">
              Cancel
            </button>
            {filledPreview && <button type="button" disabled={busy || smartFillBusy} onClick={downloadPreview} className="inline-flex items-center gap-2 rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink disabled:cursor-not-allowed disabled:opacity-50"> <Download size={16} aria-hidden="true" /> Download filled PDF</button>}
            <button type="submit" disabled={busy || smartFillBusy || !fields.length} className="inline-flex items-center gap-2 rounded-lg bg-brand-ink px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
              {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <FileCheck2 size={16} aria-hidden="true" />}
              {busy ? 'Preparing preview…' : 'Preview filled PDF'}
            </button>
          </div>
          )}
        </form>
      </div>
    </div>
  )
}
