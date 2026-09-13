import { describe, expect, it } from 'vitest'
import { formatEventTime, localDateTimeToIso, providerEventDate } from './CalendarPage'

describe('localDateTimeToIso', () => {
  it('does not invent a clock time for a date-only calendar event', () => {
    expect(formatEventTime('2026-09-14')).toBeNull()
    expect(formatEventTime(null)).toBeNull()
    expect(formatEventTime('invalid')).toBeNull()
    const timed = '2026-09-14T14:00:00'
    expect(formatEventTime(timed)).toBe(new Date(timed).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }))
  })
  it('turns the calendar form wall-clock fields into an offset-bearing instant', () => {
    const expected = new Date(2026, 8, 7, 8, 30, 0, 0).toISOString()

    expect(localDateTimeToIso('2026-09-07', '08:30')).toBe(expected)
  })

  it('groups explicit UTC provider timestamps by the browser-local day while preserving all-day dates', () => {
    const timed = '2026-09-08T00:30:00Z'
    const expectedLocalDate = new Date(timed)
    const expected = [
      expectedLocalDate.getFullYear(),
      String(expectedLocalDate.getMonth() + 1).padStart(2, '0'),
      String(expectedLocalDate.getDate()).padStart(2, '0'),
    ].join('-')

    expect(providerEventDate({ start: timed })).toBe(expected)
    expect(providerEventDate({ start: '2026-09-08' })).toBe('2026-09-08')
    expect(providerEventDate({ start: 'malformed-time' })).toBe('malformed-')
  })
})
