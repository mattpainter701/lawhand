import { describe, expect, it } from 'vitest'
import { needsAction } from './MatterPortfolioPage'

const daysAgo = (days) => new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString()

describe('needsAction predicate (S3.04 needs-attention view)', () => {
  it('flags threatened matters', () => {
    expect(needsAction({ status: 'threatened' })).toBe(true)
  })

  it('flags overdue and due-today matters', () => {
    expect(needsAction({ status: 'open', overdue_deadline_label: '3 days overdue' })).toBe(true)
    expect(needsAction({ status: 'open', overdue_deadline_label: 'Due today' })).toBe(true)
  })

  it('flags open/active matters untouched for more than two weeks', () => {
    expect(needsAction({ status: 'open', updated_at: daysAgo(20) })).toBe(true)
    expect(needsAction({ status: 'active', updated_at: daysAgo(20) })).toBe(true)
  })

  it('does not flag recent, closed, or on-track matters', () => {
    expect(needsAction({ status: 'open', updated_at: daysAgo(2) })).toBe(false)
    expect(needsAction({ status: 'closed', updated_at: daysAgo(60) })).toBe(false)
    expect(needsAction({ status: 'open', overdue_deadline_label: 'Due in 6 days', updated_at: daysAgo(2) })).toBe(false)
  })
})
