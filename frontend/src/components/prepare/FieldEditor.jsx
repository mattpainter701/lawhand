import { suggestionConfidenceLabel } from '../templates/templateFillReview'

// The one per-field editor of the Prepare flows: a single document and a
// packet of documents both render their answers through it, in the field
// list, the Questions view and the guided bar on the page.
//
// It owns the review controls every answer shares (required state, the
// suggestion's confidence and Confirm, Verify) and the input for the field's
// type. Callers add what only they know through slots: provenance notes,
// "now suggests", "Also fills", or a read-only explanation in place of the
// input for fields that are not typed here (signatures, linked fields).
export const fieldInputClass = 'w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent'

const optionParts = (option) => (typeof option === 'object' && option !== null
  ? { value: option.value ?? option.name ?? option.label ?? '', label: option.label ?? option.name ?? option.value ?? '' }
  : { value: option, label: option })

export default function FieldEditor({
  inputId,
  label,
  required = false,
  fieldType = 'text',
  multiline = false,
  options = [],
  value = '',
  disabled = false,
  inputDisabled = disabled,
  review = null,
  onChange,
  onConfirm,
  onToggleVerified,
  onEnter,
  onFocus,
  labelNote = null,
  notes = null,
  afterReview = null,
  readOnly = null,
  asHeading = false,
  verifiable = true,
  verifyId,
  choicePlaceholder,
  footer = null,
  className = '',
}) {
  const choices = (options || []).map(optionParts)
  const text = value ?? ''
  const enterAdvances = (event) => {
    if (event.key !== 'Enter' || !onEnter || !String(text).trim()) return
    event.preventDefault()
    onEnter()
  }
  let input
  if (readOnly) {
    input = readOnly
  } else if (fieldType === 'checkbox') {
    input = (
      <label className="inline-flex items-center gap-2 text-sm text-brand-ink py-1">
        <input
          id={inputId}
          type="checkbox"
          checked={text === 'true'}
          onChange={(event) => onChange(event.target.checked ? 'true' : 'false')}
          disabled={inputDisabled}
          className="h-4 w-4 rounded border-brand-line text-brand-accent focus:ring-brand-accent"
        />
        Checked
      </label>
    )
  } else if ((fieldType === 'choice' || fieldType === 'radio') && choices.length > 0) {
    input = (
      <select id={inputId} value={text} onChange={(event) => onChange(event.target.value)} onKeyDown={enterAdvances} disabled={inputDisabled} className={fieldInputClass}>
        <option value="">{choicePlaceholder || `Select ${label}`}</option>
        {choices.map((option) => <option key={String(option.value)} value={option.value}>{option.label}</option>)}
      </select>
    )
  } else if (fieldType === 'multiline' || multiline) {
    input = <textarea id={inputId} rows={3} value={text} onChange={(event) => onChange(event.target.value)} disabled={inputDisabled} className={fieldInputClass} placeholder={`Enter ${label}`} />
  } else {
    input = <input id={inputId} type="text" value={text} onChange={(event) => onChange(event.target.value)} onKeyDown={enterAdvances} disabled={inputDisabled} className={fieldInputClass} placeholder={`Enter ${label}`} />
  }

  return (
    <div onFocus={onFocus} className={className}>
      {asHeading
        ? <p className="block text-xs font-medium text-brand-muted mb-0.5">{label}</p>
        : <label htmlFor={inputId} className="block text-xs font-medium text-brand-muted mb-0.5">{label}{required ? ' *' : ''}{labelNote}</label>}
      {review && !review.present && <p className={`mb-1 text-xs font-semibold ${required ? 'text-brand-rose' : 'text-brand-amber'}`}>{required ? 'Required — missing' : 'Optional — not filled'}</p>}
      {notes}
      {review?.source && (
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          <span>{suggestionConfidenceLabel(review)}</span>
          {review.needsReview
            ? <button type="button" disabled={disabled} className="rounded border border-brand-line px-2 py-1" onClick={onConfirm}>Confirm {label}</button>
            : <span className="text-brand-green">Reviewed</span>}
        </div>
      )}
      {afterReview}
      {input}
      {review?.present && verifiable && !readOnly && (
        <label className={`mt-1 inline-flex items-center gap-2 text-xs ${review.verified ? 'text-brand-green' : 'text-brand-muted'}`}>
          <input
            id={verifyId}
            type="checkbox"
            aria-label={`Verified: ${label}`}
            checked={Boolean(review.verified)}
            onChange={onToggleVerified}
            onKeyDown={(event) => { if (event.key === 'Enter' && onEnter) { event.preventDefault(); onEnter() } }}
            disabled={disabled}
            className="h-3.5 w-3.5 rounded border-brand-line text-brand-green focus:ring-brand-green"
          />
          {review.verified ? 'Verified' : 'Verify'}
        </label>
      )}
      {footer}
    </div>
  )
}
