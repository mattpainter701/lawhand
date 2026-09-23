const IDENTITY_KEYS = ['pdf_field_name', 'pdf_source_key']

const stableIdentity = (field, key) => {
  const value = field?.[key]
  return typeof value === 'string' && value.trim() ? value.trim() : ''
}

const identityIndexes = (fields, key) => {
  const grouped = new Map()
  fields.forEach((field, index) => {
    const identity = stableIdentity(field, key)
    if (!identity) return
    const indexes = grouped.get(identity) || []
    indexes.push(index)
    grouped.set(identity, indexes)
  })
  return grouped
}

/**
 * Carry only advisory labels and matter bindings from a shared PDF sample onto
 * a fresh upload analysis. The freshly analyzed source remains authoritative
 * for field names, geometry, type, options, page data, and review state.
 */
export function applyLibrarySampleMetadata(analysis, sample) {
  const sourceAnalysis = analysis || {}
  const schema = sourceAnalysis.suggested_variable_schema || {}
  const freshFields = Array.isArray(schema.fields) ? schema.fields : []
  const catalogFields = Array.isArray(sample?.variable_schema?.fields) ? sample.variable_schema.fields : []
  const catalogIndexes = Object.fromEntries(IDENTITY_KEYS.map(key => [key, identityIndexes(catalogFields, key)]))

  const candidateSets = freshFields.map((field) => {
    const candidates = new Set()
    IDENTITY_KEYS.forEach((key) => {
      const identity = stableIdentity(field, key)
      if (!identity) return
      const catalogCandidates = catalogIndexes[key].get(identity) || []
      catalogCandidates.forEach(catalogIndex => candidates.add(catalogIndex))
    })
    return candidates
  })
  const claimsByCatalogIndex = new Map()
  candidateSets.forEach((candidates) => {
    candidates.forEach((catalogIndex) => {
      claimsByCatalogIndex.set(catalogIndex, (claimsByCatalogIndex.get(catalogIndex) || 0) + 1)
    })
  })

  const matchedCatalogIndexes = new Set()
  const enrichedFields = freshFields.map((field, index) => {
    const candidates = candidateSets[index]
    if (candidates.size !== 1) return { ...field, review_required: true }
    const [catalogIndex] = candidates
    if (claimsByCatalogIndex.get(catalogIndex) !== 1) return { ...field, review_required: true }
    const catalogField = catalogFields[catalogIndex]
    matchedCatalogIndexes.add(catalogIndex)
    const enriched = { ...field, review_required: true }
    if (typeof catalogField.label === 'string' && catalogField.label.trim()) enriched.label = catalogField.label
    if (typeof catalogField.binding === 'string' && catalogField.binding.trim()) enriched.binding = catalogField.binding
    return enriched
  })

  const unmappedBindingCount = catalogFields.reduce((count, field, index) => (
    typeof field?.binding === 'string' && field.binding.trim() && !matchedCatalogIndexes.has(index)
      ? count + 1
      : count
  ), 0)
  const warnings = Array.isArray(sourceAnalysis.warnings) ? [...sourceAnalysis.warnings] : []
  if (unmappedBindingCount) {
    const noun = unmappedBindingCount === 1 ? 'binding' : 'bindings'
    const warning = `${unmappedBindingCount} shared-library ${noun} could not be matched to the fresh PDF analysis. Review and bind those fields in Studio.`
    if (!warnings.includes(warning)) warnings.push(warning)
  }

  const freshSchema = { ...schema }
  delete freshSchema.pdf_source_review
  return {
    ...sourceAnalysis,
    title: sample?.title || sourceAnalysis.title,
    suggested_variable_schema: {
      ...freshSchema,
      fields: enrichedFields,
      library_reference: {
        id: sample?.id ?? null,
        slug: sample?.slug ?? null,
        title: sample?.title ?? null,
        source_sha256: sample?.source_sha256 ?? null,
        category: sample?.category ?? null,
        jurisdictions: sample?.jurisdictions ?? null,
        provenance: sample?.provenance ?? null,
      },
    },
    warnings,
  }
}
