import { describe, expect, it } from 'vitest'
import { fillReview } from './templateFillReview'

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
