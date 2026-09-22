import { describe, expect, it } from 'vitest'
import { rangeLabel, viewRange } from './CalendarPage'

describe('calendar list heading matches the loaded range (S1.08)', () => {
  it('labels the list with the same two-month span the view loads', () => {
    const pivot = new Date(2026, 8, 15)

    const [start, end] = viewRange('list', pivot)
    expect([start.getFullYear(), start.getMonth(), start.getDate()]).toEqual([2026, 8, 1])
    expect([end.getFullYear(), end.getMonth()]).toEqual([2026, 9])

    expect(rangeLabel('list', pivot)).toBe('September 2026 – October 2026')
  })

  it('names both months when the span crosses a year boundary', () => {
    const pivot = new Date(2026, 11, 10)

    const [start, end] = viewRange('list', pivot)
    expect([start.getFullYear(), start.getMonth()]).toEqual([2026, 11])
    expect([end.getFullYear(), end.getMonth()]).toEqual([2027, 0])

    expect(rangeLabel('list', pivot)).toBe('December 2026 – January 2027')
  })

  it('leaves the day, week and month headings unchanged', () => {
    const pivot = new Date(2026, 8, 15)

    expect(rangeLabel('day', pivot)).toContain('September')
    expect(rangeLabel('month', pivot)).toBe('September 2026')
  })
})
