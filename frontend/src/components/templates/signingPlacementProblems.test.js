import { describe, expect, it } from 'vitest'
import {
  placementBlockMessage,
  placementBlocked,
  placementProblemLines,
  placementReviewPossible,
} from './signingPlacementProblems'

const problem = (overrides = {}) => ({
  code: 'missing_signer_role',
  detail: "Signing field 'client_sig' requires a signer role before it can be positioned",
  field: 'client_sig',
  role: '',
  remedy: 'Open the template, select this field, and set its signer role.',
  ...overrides,
})

describe('placementReviewPossible', () => {
  it('offers the review for a PDF that simply has nothing placed yet', () => {
    expect(placementReviewPossible({ signing_placement_problems: [problem()] })).toBe(true)
  })

  it('withholds it for a Word document, which the review cannot open', () => {
    const document = { signing_placement_problems: [problem({ code: 'no_pdf_output' })] }
    expect(placementReviewPossible(document)).toBe(false)
  })

  it('offers it when the server recorded nothing, as on older documents', () => {
    expect(placementReviewPossible({ signing_placement_required: true })).toBe(true)
    expect(placementReviewPossible(undefined)).toBe(true)
  })

  it('withholds it when one of several problems is the Word one', () => {
    const document = {
      signing_placement_problems: [problem(), problem({ code: 'no_pdf_output' })],
    }
    expect(placementReviewPossible(document)).toBe(false)
  })
})

describe('placementProblemLines', () => {
  it('reads each problem as its reason followed by its remedy', () => {
    const [line] = placementProblemLines({ signing_placement_problems: [problem()] })
    expect(line).toContain('client_sig')
    expect(line).toContain('set its signer role')
  })

  it('states a repeated page-level fault once', () => {
    const rotated = problem({
      code: 'unsupported_pdf_page',
      detail: 'Rotated or scaled PDF pages are not supported (page 1)',
      remedy: 'Rebuild the template from an unrotated PDF.',
    })
    expect(placementProblemLines({ signing_placement_problems: [rotated, rotated] }))
      .toHaveLength(1)
  })

  it('drops a problem carrying no text rather than rendering a blank row', () => {
    const document = {
      signing_placement_problems: [problem(), { code: 'x' }, null, undefined],
    }
    expect(placementProblemLines(document)).toHaveLength(1)
  })

  it('survives a malformed column', () => {
    expect(placementProblemLines({ signing_placement_problems: 'nonsense' })).toEqual([])
    expect(placementProblemLines({})).toEqual([])
    expect(placementProblemLines(null)).toEqual([])
  })

  it('reads a reason that has no remedy', () => {
    const [line] = placementProblemLines({
      signing_placement_problems: [problem({ remedy: '' })],
    })
    expect(line).toContain('client_sig')
  })
})

describe('placementBlockMessage', () => {
  it('names the field so the template can be fixed', () => {
    expect(placementBlockMessage({ signing_placement_problems: [problem()] }))
      .toContain('client_sig')
  })

  it('falls back to the generic instruction for a document with no reasons', () => {
    expect(placementBlockMessage({ signing_placement_required: true }))
      .toMatch(/Review signing positions on the final PDF/)
  })

  it('tells a Word document to be regenerated as a PDF', () => {
    const document = {
      signing_placement_problems: [
        problem({
          code: 'no_pdf_output',
          detail: 'This document was generated as DOCX, which has no PDF page to position signing fields on',
          remedy: 'Regenerate this document with Word-to-PDF conversion enabled.',
          field: '',
        }),
      ],
    }
    expect(placementBlockMessage(document)).toContain('Word-to-PDF conversion')
  })
})

describe('placementBlocked', () => {
  it('is true only when review is required and nothing is placed', () => {
    expect(placementBlocked({ signing_placement_required: true, positioned_fields: [] })).toBe(true)
    expect(placementBlocked({ signing_placement_required: true, positioned_fields: [{}] })).toBe(false)
    expect(placementBlocked({ signing_placement_required: false })).toBe(false)
    expect(placementBlocked(undefined)).toBe(false)
  })
})
