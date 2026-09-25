import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Link2 } from 'lucide-react'
import { PdfPageCanvas, useTemplatePdfDocument } from './PdfDocumentCanvas'
import { overlayToCanvasRect, placementsFor } from './pdfFieldGeometry'

// Fill a PDF where the answers will print: every page of the original document
// is drawn, and each form field becomes an input sitting on its own box. A
// guided bar underneath always shows the active question at a readable size,
// so a small screen or a tiny form box never decides whether you can type.
//
// Shared by the sample Fill dialog, the matter Prepare/Generate flow and the
// packet Prepare flow (which also marks answers shared across documents and
// walks "Next required" across its documents). Hosts
// supply the bar's editor (`renderInput`) and, optionally, their own field
// status so review state (needs review, verified) shows on the page too.

const TRUE_VALUES = ['true', 'on', 'yes', '1']
export const isChecked = (value) => TRUE_VALUES.includes(String(value || '').toLowerCase())
export const hasFillValue = (value, field) => {
  if (field?.field_type === 'checkbox') return isChecked(value)
  return value !== undefined && value !== null && !(typeof value === 'string' && value.trim() === '')
}
export const isFieldRequired = (field) => field.required === true || (field.required === undefined && field.source_required === true)
export const fieldLabel = (field) => field.label || String(field.name || '').replace(/_/g, ' ')

const optionParts = (option) => (typeof option === 'object'
  ? { value: option.value ?? option.name ?? option.label ?? '', label: option.label ?? option.name ?? option.value ?? '' }
  : { value: option, label: option })

/** Reading order: page, then top to bottom, then left to right. Unplaced fields follow. */
export function orderFieldsForDocument(fields) {
  const keyed = fields.map((field, index) => {
    const placement = placementsFor(field)[0]
    const rect = placement?.overlay?.rect
    return {
      field,
      index,
      placed: Boolean(placement),
      page: Number(placement?.overlay?.page || field.page) || Number.MAX_SAFE_INTEGER,
      // PDF space has a bottom-left origin, so a higher top edge reads first.
      top: rect ? -Number(rect[3]) : 0,
      left: rect ? Number(rect[0]) : 0,
    }
  })
  keyed.sort((a, b) => (
    Number(b.placed) - Number(a.placed)
    || a.page - b.page
    // Treat boxes within a few points of each other as one line of the form.
    || (Math.abs(a.top - b.top) > 4 ? a.top - b.top : 0)
    || a.left - b.left
    || a.index - b.index
  ))
  return keyed.map((item) => item.field)
}

// One colour language for every fill surface. The legend shows only the
// states a host uses.
export const FILL_TONES = {
  missing: { box: 'border-brand-amber bg-amber-100/70 hover:bg-amber-100', swatch: 'border-brand-amber bg-amber-100', label: 'Required, unanswered' },
  review: { box: 'border-violet-400 bg-violet-50/90 hover:bg-violet-50', swatch: 'border-violet-400 bg-violet-50', label: 'Suggested, check it' },
  suggested: { box: 'border-brand-accent/40 bg-blue-50/80 hover:bg-blue-50', swatch: 'border-brand-accent/40 bg-blue-50', label: 'Filled from the matter' },
  verified: { box: 'border-brand-green/60 bg-green-50/80 hover:bg-green-50', swatch: 'border-brand-green/60 bg-green-50', label: 'Verified' },
  filled: { box: 'border-brand-line-2/70 bg-white/70 hover:bg-white', swatch: 'border-brand-line-2 bg-white', label: 'Answered' },
  open: { box: 'border-brand-accent/30 bg-blue-100/40 hover:bg-blue-100/70', swatch: 'border-brand-accent/30 bg-blue-100/60', label: 'Open field' },
}
const DEFAULT_LEGEND = ['missing', 'suggested', 'open']

const defaultStatus = (field, value, suggestedNames) => {
  const filled = hasFillValue(value, field)
  if (!filled) return isFieldRequired(field) ? 'missing' : 'open'
  return suggestedNames.has(field.name) ? 'suggested' : 'filled'
}
const defaultMarker = (field) => (field.field_type === 'signature' ? 'Signed later' : null)

function FieldOverlay({ field, placementIndex, rect, zoom, value, active, status, marker, shared, checkbox, disabled, onChange, onFocus }) {
  const label = fieldLabel(field)
  const type = field.field_type || 'text'
  const fontSize = Math.max(7, Math.min(rect.height * 0.68, 13 * zoom))
  const style = { left: rect.x, top: rect.y, width: rect.width, height: rect.height, fontSize }
  const tone = active ? 'border-brand-accent bg-white ring-2 ring-brand-accent/50' : (FILL_TONES[status] || FILL_TONES.open).box
  const common = {
    'data-fill-field': field.name,
    'data-fill-placement': placementIndex,
    title: `${label}${isFieldRequired(field) ? ' (required)' : ''}${shared ? ' · also fills other documents' : ''}`,
    onFocus: () => onFocus(field.name),
    style,
  }
  const base = `absolute rounded-[2px] border text-brand-ink outline-none transition-colors disabled:cursor-not-allowed ${tone}`

  if (marker) {
    return (
      <div {...common} tabIndex={0} role="note" aria-label={`${label}: ${marker}`} className={`${base} flex items-center justify-center overflow-hidden border-dashed italic text-brand-muted`}>
        {marker}
      </div>
    )
  }
  if (type === 'checkbox') {
    const checked = isChecked(value)
    return (
      <button
        {...common}
        type="button"
        role="checkbox"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => { onFocus(field.name); onChange(checked ? checkbox.off : checkbox.on) }}
        className={`${base} flex items-center justify-center p-0 font-bold leading-none`}
      >
        {checked ? '✓' : ''}
      </button>
    )
  }
  if ((type === 'choice' || type === 'radio') && Array.isArray(field.options) && field.options.length) {
    return (
      <select {...common} aria-label={label} disabled={disabled} value={value ?? ''} onChange={(event) => onChange(event.target.value)} className={`${base} px-0.5 py-0`}>
        <option value="">—</option>
        {field.options.map((option) => {
          const { value: optionValue, label: optionLabel } = optionParts(option)
          return <option key={String(optionValue)} value={optionValue}>{optionLabel}</option>
        })}
      </select>
    )
  }
  if (field.multiline || type === 'multiline') {
    return <textarea {...common} aria-label={label} disabled={disabled} value={value ?? ''} onChange={(event) => onChange(event.target.value)} className={`${base} resize-none px-1 py-0.5 leading-tight`} />
  }
  return <input {...common} type="text" aria-label={label} disabled={disabled} value={value ?? ''} onChange={(event) => onChange(event.target.value)} className={`${base} px-1 py-0`} />
}

function DocumentPage({ document, page, zoom, placements, values, activeName, statusOf, markerFor, isShared, checkbox, disabled, onChange, onFocus, onError }) {
  const [wrapper, setWrapper] = useState(null)
  const [visible, setVisible] = useState(page.page === 1)
  const [viewport, setViewport] = useState(null)
  const onViewport = useCallback((value) => setViewport(value), [])

  useEffect(() => {
    if (visible || !wrapper) return undefined
    if (typeof IntersectionObserver === 'undefined') { setVisible(true); return undefined }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setVisible(true)
    }, { rootMargin: '900px 0px' })
    observer.observe(wrapper)
    return () => observer.disconnect()
  }, [visible, wrapper])

  const rotated = Math.abs((page.rotation || 0) % 180) === 90
  const width = (rotated ? page.height : page.width) * zoom
  const height = (rotated ? page.width : page.height) * zoom

  return (
    <div
      ref={setWrapper}
      data-fill-page={page.page}
      aria-label={`Page ${page.page}`}
      role="group"
      className="relative mx-auto bg-white shadow-md ring-1 ring-black/5"
      style={{ width, height }}
    >
      {visible
        ? <PdfPageCanvas document={document} pageNumber={page.page} zoom={zoom} onViewport={onViewport} onError={onError} />
        : <span className="absolute inset-0 flex items-center justify-center text-xs text-brand-muted">Page {page.page}</span>}
      {placements.map(({ field, placementIndex, overlay }) => {
        const rect = overlayToCanvasRect(overlay, page, viewport, zoom)
        const shared = Boolean(isShared?.(field))
        return (
          <Fragment key={`${field.name}:${placementIndex}`}>
            <FieldOverlay
              field={field}
              placementIndex={placementIndex}
              rect={rect}
              zoom={zoom}
              value={values[field.name]}
              active={activeName === field.name}
              status={statusOf(field)}
              marker={markerFor(field)}
              shared={shared}
              checkbox={checkbox}
              disabled={disabled}
              onChange={(value) => onChange(field.name, value)}
              onFocus={onFocus}
            />
            {/* One answer fills this box in other documents too. */}
            {shared && (
              <span
                aria-hidden="true"
                data-fill-shared={field.name}
                className="pointer-events-none absolute z-10 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-brand-accent/50 bg-white text-brand-accent shadow-sm"
                style={{ left: rect.x + rect.width - 7, top: rect.y - 7 }}
              >
                <Link2 size={9} strokeWidth={2.5} />
              </span>
            )}
          </Fragment>
        )
      })}
    </div>
  )
}

/**
 * The large, always-readable editor for the active field, with guided
 * navigation. Exported so document views without field geometry (Word and
 * text templates) can pair it with their own page reference.
 */
export function GuidedFieldBar({ field, position, total, onPrevious, onNext, onNextRequired, requiredMissing, placed = true, children }) {
  if (!field) return null
  return (
    <div className="shrink-0 border-t border-brand-line bg-brand-surface px-3 py-2 shadow-[0_-4px_12px_rgba(0,0,0,0.05)]" role="region" aria-label="Current field">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-brand-muted">
        <span className="font-semibold text-brand-ink">Field {position} of {total}</span>
        {isFieldRequired(field) && <span className="rounded bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-900">Required</span>}
        {!placed && <span>Not placed on the page — the answer still prints where the form expects it.</span>}
        {field.page && <span>Page {field.page}</span>}
      </div>
      <div className="mt-1.5 flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="max-h-[40vh] min-w-0 flex-1 overflow-y-auto">{children}</div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button type="button" onClick={onPrevious} aria-label="Previous field" className="rounded-lg border border-brand-line p-2 text-brand-ink hover:bg-brand-bg"><ChevronLeft size={16} aria-hidden="true" /></button>
          <button type="button" onClick={onNext} aria-label="Next field" className="rounded-lg border border-brand-line p-2 text-brand-ink hover:bg-brand-bg"><ChevronRight size={16} aria-hidden="true" /></button>
          <button type="button" disabled={!requiredMissing} onClick={onNextRequired} className="rounded-lg border border-brand-amber/60 px-3 py-2 text-xs font-semibold text-brand-ink hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-40">
            {requiredMissing ? `Next required (${requiredMissing})` : 'All required answered'}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Guided navigation state over an ordered field list. Controlled when the host
 * passes `activeName`/`onActiveChange`, so its own "next field" actions and
 * the page stay on the same field.
 */
export function useGuidedFields(ordered, { values, activeName, onActiveChange, isMissing }) {
  const [innerActive, setInnerActive] = useState(() => ordered[0]?.name || '')
  const controlled = activeName !== undefined && activeName !== null && activeName !== ''
  const active = controlled ? activeName : innerActive
  const setActive = useCallback((name) => {
    if (onActiveChange) onActiveChange(name)
    if (!controlled || !onActiveChange) setInnerActive(name)
  }, [controlled, onActiveChange])
  const missing = ordered.filter((field) => (isMissing ? isMissing(field) : isFieldRequired(field) && !hasFillValue(values[field.name], field)))
  const foundIndex = ordered.findIndex((field) => field.name === active)
  const index = Math.max(0, foundIndex)
  const step = (delta) => {
    if (!ordered.length) return
    setActive(ordered[(index + delta + ordered.length) % ordered.length].name)
  }
  const nextRequired = () => {
    if (!missing.length) return
    const after = missing.find((field) => ordered.indexOf(field) > index)
    setActive((after || missing[0]).name)
  }
  return { active: ordered[index]?.name || '', activeField: ordered[index], index, missing, setActive, step, nextRequired }
}

const ZOOM_OPTIONS = [['fit', 'Fit width'], ['0.75', '75%'], ['1', '100%'], ['1.25', '125%'], ['1.5', '150%'], ['2', '200%']]

export default function FillOnDocument({
  source,
  fields,
  values,
  suggestedNames = new Set(),
  onChange,
  renderInput,
  onUnavailable,
  activeName,
  onActiveChange,
  statusFor,
  isMissing,
  markerFor = defaultMarker,
  legend = DEFAULT_LEGEND,
  checkboxValues = { on: 'Yes', off: '' },
  disabled = false,
  isShared,
  onNextRequired,
  requiredMissing,
  scrollToActiveOnOpen = false,
}) {
  const { document, pages, error } = useTemplatePdfDocument(source)
  const [container, setContainer] = useState(null)
  const [width, setWidth] = useState(720)
  const [zoomMode, setZoomMode] = useState('fit')
  const [renderError, setRenderError] = useState('')
  const ordered = useMemo(() => orderFieldsForDocument(fields), [fields])
  const guided = useGuidedFields(ordered, { values, activeName, onActiveChange, isMissing })
  // A host that opens the document on a chosen field (a packet walking to
  // its next document) asks for that field to be brought into view.
  const lastActive = useRef(scrollToActiveOnOpen ? '' : guided.active)
  const focusedFromPage = useRef('')
  const pendingScroll = useRef('')
  const onError = useCallback(() => setRenderError('A page could not be drawn. Switch to Questions to keep answering, or check the preview.'), [])
  const statusOf = (field) => (statusFor ? statusFor(field, values[field.name]) : defaultStatus(field, values[field.name], suggestedNames))

  useEffect(() => {
    if (!container || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, entry.contentRect.width - 32)))
    observer.observe(container)
    return () => observer.disconnect()
  }, [container])

  useEffect(() => { if (error) onUnavailable?.(error) }, [error, onUnavailable])

  const widest = pages.reduce((max, page) => Math.max(max, Math.abs((page.rotation || 0) % 180) === 90 ? page.height : page.width), 0) || 612
  const zoom = zoomMode === 'fit' ? Math.min(2, width / widest) : Number(zoomMode)

  const byPage = useMemo(() => {
    const map = new Map()
    fields.forEach((field) => {
      placementsFor(field).forEach(({ overlay, index }) => {
        const pageNumber = Number(overlay?.page || field.page) || 1
        if (!map.has(pageNumber)) map.set(pageNumber, [])
        map.get(pageNumber).push({ field, placementIndex: index, overlay })
      })
    })
    return map
  }, [fields])
  const placedNames = useMemo(() => new Set(fields.filter((field) => placementsFor(field).length).map((field) => field.name)), [fields])
  const unplacedCount = fields.length - placedNames.size

  const scrollToField = useCallback((name) => {
    const escaped = globalThis.CSS?.escape ? globalThis.CSS.escape(name) : String(name).replace(/["\\]/g, '\\$&')
    const target = container?.querySelector(`[data-fill-field="${escaped}"]`)
    target?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
    return Boolean(target)
  }, [container])

  // Bring the page to a field chosen from the bar or by the host. A field the
  // user just clicked on the page is already in view, and the opening field
  // stays put so the document starts at its top.
  useEffect(() => {
    const name = guided.active
    if (!name || name === lastActive.current) return
    lastActive.current = name
    if (focusedFromPage.current === name) { focusedFromPage.current = ''; return }
    pendingScroll.current = name
    if (scrollToField(name)) pendingScroll.current = ''
  }, [guided.active, scrollToField])

  useEffect(() => {
    if (!pendingScroll.current || !pages.length) return
    if (scrollToField(pendingScroll.current)) pendingScroll.current = ''
  }, [pages, zoom, scrollToField])

  const focusFromPage = (name) => {
    focusedFromPage.current = name
    guided.setActive(name)
  }

  const loading = !error && (!document || !pages.length)
  const activeField = guided.activeField

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-brand-line bg-brand-bg-soft" data-testid="fill-on-document-surface">
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-brand-line bg-brand-surface-2 px-3 py-1.5 text-xs text-brand-muted">
        {legend.map((key) => (
          <span key={key} className="hidden items-center gap-1.5 sm:inline-flex"><span className={`h-3 w-4 rounded-sm border ${FILL_TONES[key].swatch}`} aria-hidden="true" />{FILL_TONES[key].label}</span>
        ))}
        {unplacedCount > 0 && <span>{unplacedCount} {unplacedCount === 1 ? 'field has' : 'fields have'} no box on the page; reach {unplacedCount === 1 ? 'it' : 'them'} with Next or in Questions.</span>}
        <label className="ml-auto flex items-center gap-2 text-brand-ink">Zoom
          <select aria-label="Document zoom" value={zoomMode} onChange={(event) => setZoomMode(event.target.value)} className="rounded border border-brand-line bg-brand-surface px-1.5 py-1">
            {ZOOM_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>
      <div ref={setContainer} className="min-h-0 flex-1 overflow-auto p-4" aria-busy={loading}>
        {error ? (
          <p role="alert" className="mx-auto max-w-lg rounded border border-brand-line bg-brand-surface p-4 text-sm text-brand-ink">The original document could not be opened here. Switch to Questions to keep answering; the preview still works.</p>
        ) : loading ? (
          <p role="status" className="p-6 text-center text-sm text-brand-muted">Opening the original document…</p>
        ) : (
          <div className="flex flex-col gap-4">
            {renderError && <p role="alert" className="mx-auto max-w-lg text-sm text-brand-rose">{renderError}</p>}
            {pages.map((page) => (
              <DocumentPage
                key={page.page}
                document={document}
                page={page}
                zoom={zoom}
                placements={byPage.get(page.page) || []}
                values={values}
                activeName={guided.active}
                statusOf={statusOf}
                markerFor={markerFor}
                isShared={isShared}
                checkbox={checkboxValues}
                disabled={disabled}
                onChange={onChange}
                onFocus={focusFromPage}
                onError={onError}
              />
            ))}
          </div>
        )}
      </div>
      <GuidedFieldBar
        field={activeField}
        position={guided.index + 1}
        total={ordered.length}
        onPrevious={() => guided.step(-1)}
        onNext={() => guided.step(1)}
        onNextRequired={onNextRequired || guided.nextRequired}
        requiredMissing={requiredMissing ?? guided.missing.length}
        placed={activeField ? placedNames.has(activeField.name) : true}
      >
        {activeField && renderInput(activeField, values[activeField.name], (value) => onChange(activeField.name, value))}
      </GuidedFieldBar>
    </div>
  )
}
