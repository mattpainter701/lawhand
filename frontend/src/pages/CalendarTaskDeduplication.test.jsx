// Issue #484: "The calendar then showed both the LawHand task and its synced
// copy as separate entries", and clicking either did not reach the same task.
//
// We stamp clarity_task_id on every task event we push, which is what makes
// the push an upsert. The read path now surfaces it, so the synced copy can be
// collapsed into the task rather than rendered beside it.
import { describe, expect, it } from 'vitest'
import { mapProviderEvents, mergeCalendarEvents } from './CalendarPage'

const TASK_ID = '11111111-1111-4111-8111-111111111111'

const lawhandTask = (overrides = {}) => ({
  id: `task-${TASK_ID}`,
  task_id: TASK_ID,
  title: 'File response brief',
  date: '2026-09-18',
  event_type: 'task_due',
  url: `/tasks/${TASK_ID}`,
  ...overrides,
})

const providerRow = (overrides = {}) => ({
  id: 'AAMkAGI2',
  subject: 'File response brief',
  start: '2026-09-18T14:30:00Z',
  end: '2026-09-18T15:00:00Z',
  task_id: TASK_ID,
  ...overrides,
})

describe('a task and its synced copy are one entry', () => {
  it('drops the provider copy of a task already on the calendar', () => {
    const provider = mapProviderEvents('microsoft', [providerRow()])
    const merged = mergeCalendarEvents([lawhandTask()], provider)

    expect(merged).toHaveLength(1)
    expect(merged[0].event_type).toBe('task_due')
  })

  it('keeps the LawHand task, which is the entry that can be acted on', () => {
    const provider = mapProviderEvents('google', [providerRow({ id: 'g-1' })])
    const merged = mergeCalendarEvents([lawhandTask()], provider)

    expect(merged[0].id).toBe(`task-${TASK_ID}`)
    expect(merged[0].url).toBe(`/tasks/${TASK_ID}`)
  })

  it('collapses the copy on a repeat sync rather than accumulating entries', () => {
    const provider = mapProviderEvents('microsoft', [providerRow()])
    const first = mergeCalendarEvents([lawhandTask()], provider)
    const second = mergeCalendarEvents([lawhandTask()], provider)

    expect(first).toHaveLength(1)
    expect(second).toHaveLength(1)
  })

  it('keeps an ordinary meeting that is not a task copy', () => {
    const provider = mapProviderEvents('microsoft', [
      providerRow({ id: 'meeting-1', subject: 'Client call', task_id: null }),
    ])
    const merged = mergeCalendarEvents([lawhandTask()], provider)

    expect(merged).toHaveLength(2)
    expect(merged.map((e) => e.title)).toContain('Client call')
  })

  it('keeps a synced copy whose task is outside the range being shown', () => {
    // The task is not in internalEvents, so its copy is the only record of the
    // deadline on screen. Dropping it would lose the entry entirely.
    const provider = mapProviderEvents('microsoft', [providerRow()])
    const merged = mergeCalendarEvents([], provider)

    expect(merged).toHaveLength(1)
    expect(merged[0].event_type).toBe('external_calendar')
  })

  it('gives a surviving synced copy somewhere to go', () => {
    // Provider entries used to carry url: null, so clicking one did nothing.
    const [copy] = mapProviderEvents('microsoft', [providerRow()])
    expect(copy.url).toBe(`/tasks/${TASK_ID}`)
  })

  it('leaves an unrelated provider event without a task link', () => {
    const [meeting] = mapProviderEvents('microsoft', [
      providerRow({ task_id: null }),
    ])
    expect(meeting.url).toBeNull()
    expect(meeting.task_id).toBeNull()
  })

  it('matches ids across string and uuid representations', () => {
    const provider = mapProviderEvents('microsoft', [providerRow()])
    const merged = mergeCalendarEvents(
      [lawhandTask({ task_id: TASK_ID.toUpperCase() })],
      provider,
    )
    // Same task, different casing from the provider round-trip: still one entry.
    expect(merged.filter((e) => e.event_type === 'external_calendar')).toHaveLength(0)
    expect(merged).toHaveLength(1)
  })

  it('still de-duplicates identical ids as it did before', () => {
    const merged = mergeCalendarEvents(
      [lawhandTask(), lawhandTask()],
      [],
    )
    expect(merged).toHaveLength(1)
  })
})
