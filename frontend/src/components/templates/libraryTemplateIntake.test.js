import { describe, expect, it } from 'vitest'
import { applyLibrarySampleMetadata } from './libraryTemplateIntake'

const analysisFor = (fields, extra = {}) => ({
  title: 'Analyzer title',
  body: 'Fresh analyzed body',
  analysis_token: 'analysis-token',
  warnings: ['Existing warning'],
  suggested_variable_schema: {
    detection: { method: 'acroform' },
    pages: [{ page: 1, width: 612, height: 792 }],
    fields,
  },
  ...extra,
})

const sampleWith = (fields, extra = {}) => ({
  id: 'sample-1',
  slug: 'sample-form',
  title: 'Shared Sample',
  source_sha256: 'sample-sha',
  category: 'court_form',
  jurisdictions: ['ND'],
  provenance: { edition: 'Rev. 2025' },
  variable_schema: { fields },
  ...extra,
})

describe('applyLibrarySampleMetadata', () => {
  it('copies only label and binding for an exact unique stable identity', () => {
    const fresh = analysisFor([{
      name: 'fresh_name', label: 'Analyzer label', pdf_field_name: 'CLIENT',
      pdf_source_key: 'acro:CLIENT', pdf_overlay: { page: 1, rect: [1, 2, 3, 4] },
      field_type: 'checkbox', options: ['A'], required: true, default_value: 'fresh',
    }])
    const result = applyLibrarySampleMetadata(fresh, sampleWith([{
      name: 'catalog_name', label: 'Catalog label', binding: 'client.full_name',
      pdf_field_name: 'CLIENT', pdf_source_key: 'acro:CLIENT',
      field_type: 'text', required: false, default_value: 'catalog',
    }]))

    const field = result.suggested_variable_schema.fields[0]
    expect(field).toMatchObject({
      name: 'fresh_name', label: 'Catalog label', binding: 'client.full_name',
      pdf_field_name: 'CLIENT', pdf_source_key: 'acro:CLIENT',
      pdf_overlay: { page: 1, rect: [1, 2, 3, 4] },
      field_type: 'checkbox', options: ['A'], required: true,
      default_value: 'fresh', review_required: true,
    })
    expect(field).not.toHaveProperty('default')
    expect(result.title).toBe('Shared Sample')
    expect(result.body).toBe('Fresh analyzed body')
    expect(result.analysis_token).toBe('analysis-token')
    expect(result.suggested_variable_schema.detection).toEqual({ method: 'acroform' })
    expect(result.suggested_variable_schema.pages).toEqual([{ page: 1, width: 612, height: 792 }])
  })

  it('does not guess from names or labels when stable identities differ', () => {
    const result = applyLibrarySampleMetadata(analysisFor([
      { name: 'client', label: 'Client name' },
    ]), sampleWith([
      { name: 'client', label: 'Catalog client', binding: 'client.full_name' },
    ]))

    expect(result.suggested_variable_schema.fields[0]).toMatchObject({
      name: 'client', label: 'Client name', review_required: true,
    })
    expect(result.suggested_variable_schema.fields[0]).not.toHaveProperty('binding')
    expect(result.warnings).toEqual(expect.arrayContaining([
      expect.stringContaining('1 shared-library binding could not be matched'),
    ]))
  })

  it('does not merge duplicate stable identity candidates', () => {
    const result = applyLibrarySampleMetadata(analysisFor([
      { name: 'fresh', pdf_field_name: 'CLIENT', pdf_source_key: 'acro:CLIENT' },
    ]), sampleWith([
      { name: 'catalog-a', pdf_field_name: 'CLIENT', binding: 'party.one' },
      { name: 'catalog-b', pdf_field_name: 'CLIENT', binding: 'party.two' },
    ]))

    expect(result.suggested_variable_schema.fields[0]).not.toHaveProperty('binding')
    expect(result.warnings).toEqual(expect.arrayContaining([
      expect.stringContaining('2 shared-library bindings could not be matched'),
    ]))
  })

  it('does not merge when alternate stable identities conflict or a candidate is shared', () => {
    const result = applyLibrarySampleMetadata(analysisFor([
      { name: 'ambiguous', pdf_field_name: 'CLIENT', pdf_source_key: 'acro:OTHER' },
      { name: 'other', pdf_field_name: 'OTHER', pdf_source_key: 'acro:OTHER' },
    ]), sampleWith([
      { name: 'catalog-client', pdf_field_name: 'CLIENT', binding: 'party.client' },
      { name: 'catalog-other', pdf_source_key: 'acro:OTHER', binding: 'party.other' },
    ]))

    expect(result.suggested_variable_schema.fields.map(field => field.binding)).toEqual([undefined, undefined])
    expect(result.warnings).toEqual(expect.arrayContaining([
      expect.stringContaining('2 shared-library bindings could not be matched'),
    ]))
  })

  it('adds no warning when there are no catalog bindings to map', () => {
    const result = applyLibrarySampleMetadata(analysisFor([
      { name: 'fresh', pdf_field_name: 'CLIENT' },
    ]), sampleWith([
      { name: 'catalog', pdf_field_name: 'CLIENT', label: 'Client' },
    ]))

    expect(result.warnings).toEqual(['Existing warning'])
    expect(result.suggested_variable_schema.fields[0]).toMatchObject({ label: 'Client', review_required: true })
  })

  it('marks every field for review and never copies a library source-review attestation', () => {
    const fresh = analysisFor([
      { name: 'one', pdf_field_name: 'ONE', review_required: false },
      { name: 'two', pdf_field_name: 'TWO', review_required: false },
    ])
    fresh.suggested_variable_schema.pdf_source_review = { confirmed: true, confirmed_digest: 'old-digest' }
    const sample = sampleWith([
      { name: 'one', pdf_field_name: 'ONE', label: 'One', binding: 'party.one', review_required: false },
      { name: 'two', pdf_field_name: 'TWO', label: 'Two', binding: 'party.two', review_required: false },
    ])
    sample.variable_schema.pdf_source_review = { confirmed: true, confirmed_digest: 'catalog-digest' }

    const result = applyLibrarySampleMetadata(fresh, sample)
    expect(result.suggested_variable_schema.fields.every(field => field.review_required)).toBe(true)
    expect(result.suggested_variable_schema).not.toHaveProperty('pdf_source_review')
  })

  it('records advisory catalog reference metadata inside the submitted schema', () => {
    const result = applyLibrarySampleMetadata(analysisFor([]), sampleWith([]))

    expect(result.suggested_variable_schema.library_reference).toEqual({
      id: 'sample-1', slug: 'sample-form', title: 'Shared Sample', source_sha256: 'sample-sha',
      category: 'court_form', jurisdictions: ['ND'], provenance: { edition: 'Rev. 2025' },
    })
    expect(result).not.toHaveProperty('library_reference')
    expect(result).not.toHaveProperty('source_provenance')
  })
})
