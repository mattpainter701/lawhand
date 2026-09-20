import { describe, expect, it } from 'vitest'
import { fillReview, suggestionConfidenceLabel, suggestionOriginLabel } from './templateFillReview'

const fields = {
  client_name: { name: 'client_name', label: 'Client name' },
  notes: { name: 'notes', label: 'Notes' },
  sig: { name: 'sig', field_type: 'signature', signer_role: 'client' },
}
const names = ['client_name', 'notes', 'sig']

describe('fillReview verification', () => {
  it('counts verified rows among the filled ones and never among the empty', () => {
    const values = { client_name: 'Ada', notes: '' }
    const none = fillReview(names, fields, values, {}, {})
    expect(none.total).toBe(2)
    expect(none.verified).toBe(0)
    expect(none.unverified.map((row) => row.name)).toEqual(['client_name'])
    const some = fillReview(names, fields, values, {}, {}, { client_name: true, notes: true })
    expect(some.verified).toBe(1)
    expect(some.unverified).toEqual([])
    expect(some.rows.find((row) => row.name === 'notes').verified).toBe(false)
  })

  it('leaves the review of suggestions separate from verification', () => {
    const sources = { client_name: { suggested_value: 'Ada', confidence: 0.9 } }
    const review = fillReview(names, fields, { client_name: 'Ada', notes: '' }, sources, {}, { client_name: true })
    expect(review.review.map((row) => row.name)).toEqual(['client_name'])
    expect(review.verified).toBe(1)
  })
})

describe('document evidence labels', () => {
  const source = { source_type: 'document_evidence', suggested_value: 'Ada', confidence: 0.6, source_field: 'scan.pdf#ocr:1:3', provenance: { source_document_id: 'd', source_filename: 'scan.pdf', ocr_confidence: 0.82 } }
  it('names the document and the OCR confidence', () => {
    expect(suggestionOriginLabel(source)).toBe("From scan.pdf in this matter's documents · check it against the page")
    expect(suggestionConfidenceLabel({ source, confidence: 60 })).toBe('Read from a document · 82% OCR confidence')
    expect(suggestionConfidenceLabel({ source: { ...source, provenance: {} }, confidence: 60 })).toBe('Read from a document')
  })
  it('keeps the record wording for other sources', () => {
    expect(suggestionOriginLabel({ source_type: 'contact', suggested_value: 'Ada', provenance: { binding_label: 'Client name' } })).toBe('From Client name · verify current accuracy')
    expect(suggestionOriginLabel({ suggested_value: null })).toBe('Missing: review or enter a value')
  })
})
