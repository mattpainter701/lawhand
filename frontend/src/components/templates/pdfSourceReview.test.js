import { describe, expect, it } from 'vitest'

import { fieldNeedsReview, fieldsNeedingReview } from './pdfSourceReview'

// Kept in step with backend/app/services/pdf_source_review.py, whose own tests
// pin the same cases. A disagreement means the editor says a template is ready
// and publish refuses it.
describe('which scanned fields a person must check', () => {
  it('flags a field the scan scored low', () => {
    expect(fieldNeedsReview({ confidence: 0.4 })).toBe(true)
    expect(fieldNeedsReview({ confidence: 0.99 })).toBe(false)
  })

  it('flags a field read off pixels however confident the scan was', () => {
    expect(fieldNeedsReview({ confidence: 1, pdf_overlays: [{ source_kind: 'ocr' }] })).toBe(true)
    expect(fieldNeedsReview({ confidence: 1, pdf_overlays: [{ source_kind: 'acroform' }] })).toBe(false)
  })

  it('does not treat an unreadable confidence as a confident one', () => {
    expect(fieldNeedsReview({ confidence: 'high' })).toBe(true)
  })

  it('treats an OCR scan as uncertain as a whole', () => {
    const fields = [{ name: 'a', confidence: 1 }, { name: 'b', confidence: 1 }]
    expect(fieldsNeedingReview(fields, { detection: { method: 'ocr_fallback' } })).toHaveLength(2)
    expect(fieldsNeedingReview(fields, { detection: { method: 'acroform' } })).toHaveLength(0)
  })

  it('leaves out fields nobody is generating', () => {
    expect(fieldsNeedingReview([{ name: 'a', confidence: 0.1, included: false }])).toHaveLength(0)
  })
})
