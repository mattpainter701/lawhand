// A populated value is separate from a reviewed value. Confidence describes
// the suggestion that actually supplied this value, never a manual override.
export const fillValue = value => value == null ? '' : String(value)
export const isSigningField = field => ['signature', 'initials'].includes(field?.field_type) || (field?.field_type === 'date' && Boolean(String(field.signer_role || '').trim()))

export function suggestionConfidenceLabel(review) {
  if (review.source?.source_type === 'firm_profile') return 'Saved firm profile value'
  if (review.source?.source_type === 'document_evidence') {
    const ocr = review.source?.provenance?.ocr_confidence
    return typeof ocr === 'number' ? `Read from a document · ${Math.round(ocr * 100)}% OCR confidence` : 'Read from a document'
  }
  return review.confidence == null ? 'Confidence unavailable' : `${review.confidence}% match confidence`
}

// The one-line origin shown above a filled field.
export function suggestionOriginLabel(source) {
  if (!source) return ''
  if (source.suggested_value == null) return 'Missing: review or enter a value'
  if (source.source_type === 'document_evidence') {
    const filename = source.provenance?.source_filename || source.source_field?.split('#')[0]
    return `From ${filename || 'a document'} in this matter's documents · check it against the page`
  }
  return `From ${source.provenance?.binding_label || source.source_type || 'record'} · verify current accuracy`
}

export function initialFillValues(names, fields) {
  return Object.fromEntries(names.map(name => [name, fields[name]?.field_type === 'checkbox' ? 'false' : '']))
}

export function discoverySuggestions(response) {
  const raw = response?.variables ?? response?.values ?? response?.field_values ?? {}
  const entries = Array.isArray(raw)
    ? raw.map(item => [item?.variable || item?.name || item?.key, item])
    : Object.entries(raw)
  return Object.fromEntries(entries.filter(([name]) => name).map(([name, item]) => [name,
    item && typeof item === 'object'
      ? { ...item, suggested_value: item.suggested_value ?? item.value ?? item.text ?? null }
      : { suggested_value: item },
  ]))
}

// `verified` is the set of names the preparer has checked, by hand or by
// typing the value. It is advisory: nothing waits on it, and a verified row
// stays verified until its value changes.
export function fillReview(names, fields, values, sources, reviewed, verified = {}) {
  const rows = names.filter(name => !isSigningField(fields[name]) && !fields[name]?.value_from).map(name => {
    const field = fields[name] || {}
    const value = fillValue(values[name])
    const present = field.field_type === 'checkbox'
      ? (field.required ? value === 'true' : ['true', 'false'].includes(value))
      : Boolean(value.trim())
    const source = sources[name]
    const fromSource = source?.suggested_value != null && fillValue(source.suggested_value) === value
    const rawConfidence = fromSource ? source.confidence : null
    const confidence = typeof rawConfidence === 'number' && Number.isFinite(rawConfidence) && rawConfidence >= 0 && rawConfidence <= 1 ? Math.round(rawConfidence * 100) : null
    const needsReview = present && fromSource && reviewed[name] !== value
    const isVerified = present && Boolean(verified[name])
    return { name, present, confidence, needsReview, verified: isVerified, source: fromSource ? source : null }
  })
  const completed = rows.filter(row => row.present).length
  const unverified = rows.filter(row => row.present && !row.verified)
  return { rows, completed, total: rows.length, percent: rows.length ? Math.round(completed / rows.length * 100) : 100,
    remaining: rows.filter(row => !row.present), review: rows.filter(row => row.needsReview),
    verified: completed - unverified.length, unverified }
}

export function applyFillSuggestions(names, fields, values, sources, suggestions) {
  const nextValues = { ...values }
  const nextSources = { ...sources }
  for (const name of names) {
    if (isSigningField(fields[name])) continue
    const suggestion = suggestions[name]
    if (suggestion?.suggested_value == null) continue
    // Unchecked checkboxes are real choices, not empty strings to overwrite.
    if (fillValue(values[name]).trim()) continue
    const value = fillValue(suggestion.suggested_value)
    if (fields[name]?.field_type === 'checkbox' && !['true', 'false'].includes(value)) continue
    nextValues[name] = value
    nextSources[name] = suggestion
  }
  return { values: nextValues, sources: nextSources }
}
