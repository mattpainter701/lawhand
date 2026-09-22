import { describe, expect, it } from 'vitest'
import { fillReview, interviewReview, suggestionConfidenceLabel, suggestionOriginLabel } from './templateFillReview'

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

describe('interviewReview', () => {
  const questions = [
    { key: 'defendant.full_name', label: 'Defendant', value_kind: 'text', required: true, appears_in: [{ template_id: 'a' }, { template_id: 'b' }], suggested_value: 'Ada', provenance: { source_type: 'matter_party', confidence: 0.8 }, review_required: true },
    { key: 'manual:a:note', label: 'Note', value_kind: 'text', required: false, appears_in: [{ template_id: 'a' }] },
  ]
  it('reviews a packet the way one document is reviewed', () => {
    const review = interviewReview(questions, { 'defendant.full_name': 'Ada' }, {}, {})
    expect(review.total).toBe(2)
    expect(review.completed).toBe(1)
    expect(review.rows[0]).toMatchObject({ present: true, needsReview: true, confidence: 80, documents: 2, required: true })
    expect(review.review.map((row) => row.name)).toEqual(['defendant.full_name'])
    expect(review.remaining.map((row) => row.name)).toEqual(['manual:a:note'])
    expect(review.verified).toBe(0)
    const confirmed = interviewReview(questions, { 'defendant.full_name': 'Ada' }, { 'defendant.full_name': 'Ada' }, { 'defendant.full_name': true })
    expect(confirmed.review).toEqual([])
    expect(confirmed.verified).toBe(1)
    // A typed value that differs from the suggestion is not a suggestion any more.
    expect(interviewReview(questions, { 'defendant.full_name': 'Grace' }).rows[0].source).toBeNull()
  })

  it('requires review again when a suggestion changes after confirmation', () => {
    const confirmed = { 'defendant.full_name': 'Ada' }
    const changed = interviewReview(
      [{ ...questions[0], suggested_value: 'Grace' }],
      { 'defendant.full_name': 'Grace' },
      confirmed,
      { 'defendant.full_name': true },
    )
    expect(changed.rows[0]).toMatchObject({ present: true, needsReview: true, verified: true })
  })
})
