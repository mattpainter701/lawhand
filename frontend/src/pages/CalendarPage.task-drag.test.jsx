import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CalendarPage, { addMinutesToTimeInput, eventIsMovable, localDateTimeToIso } from './CalendarPage'

const api = vi.hoisted(() => ({
  browserTimezone: vi.fn(() => 'America/Chicago'),
  connectCalendarIntegration: vi.fn(),
  connectZoomIntegration: vi.fn(),
  createScheduledEvent: vi.fn(),
  deleteScheduledEvent: vi.fn(),
  getCalendarEvents: vi.fn(),
  getCalendarProviders: vi.fn(),
  getMattersV2: vi.fn(),
  getZoomStatus: vi.fn(),
  syncCalendarDeadlines: vi.fn(),
  updateScheduledEvent: vi.fn(),
  updateTask: vi.fn(),
}))

vi.mock('../api', () => api)
vi.mock('../utils/reportError', () => ({ reportError: vi.fn() }))

const taskEvent = {
  id: 'task-task-1',
  title: 'File the motion',
  date: '2026-09-10',
  event_type: 'task_due',
  task_id: 'task-1',
  task_version: 4,
  matter_id: 'matter-1',
  url: '/tasks',
  is_completed: false,
}

// A drop payload the month grid would produce. The grid spills into the
// neighbouring months, so a day number can appear twice — take the first,
// which is always the one inside the month being shown for these fixtures.
function dropOn(dayLabel, eventId = taskEvent.id) {
  const cell = screen.getAllByRole('button', { name: dayLabel })[0].parentElement
  fireEvent.drop(cell, {
    dataTransfer: { getData: (key) => (key === 'text/calendar-event-id' ? eventId : '') },
  })
}

async function renderCalendarOn(pivot) {
  vi.setSystemTime(new Date(pivot))
  render(<MemoryRouter><CalendarPage /></MemoryRouter>)
  await screen.findAllByText('File the motion')
}

describe('dragging a task on the calendar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] })
    window.localStorage.setItem('calendar-view', 'month')
    api.getCalendarEvents.mockResolvedValue({ events: [taskEvent] })
    api.getCalendarProviders.mockResolvedValue({ providers: [], provider_status: {}, tenant_providers: [] })
    api.getZoomStatus.mockResolvedValue({ connected: false, configured: false })
    api.getMattersV2.mockResolvedValue({ items: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
    window.localStorage.clear()
    cleanup()
  })

  it('only offers the drag gesture for open task deadlines and firm events', () => {
    expect(eventIsMovable(taskEvent)).toBe(true)
    expect(eventIsMovable({ ...taskEvent, is_completed: true })).toBe(false)
    expect(eventIsMovable({ ...taskEvent, task_id: null })).toBe(false)
    expect(eventIsMovable({ event_type: 'scheduled_event' })).toBe(true)
    expect(eventIsMovable({ event_type: 'external_calendar' })).toBe(false)
    expect(eventIsMovable({ event_type: 'matter_key_date' })).toBe(false)
  })

  it('moves the due date and reports that the alert follows the new date', async () => {
    api.updateTask.mockResolvedValue({ id: 'task-1' })
    await renderCalendarOn('2026-09-10T12:00:00')

    dropOn('17')
    fireEvent.click(await screen.findByRole('button', { name: 'Move due date' }))

    await waitFor(() => expect(api.updateTask).toHaveBeenCalledWith('task-1', {
      due_date: '2026-09-17',
      due_time: null,
      expected_version: 4,
    }))
    expect(api.createScheduledEvent).not.toHaveBeenCalled()
    expect(await screen.findByText(/is now due .*Sep 17, 2026.*reminder and connected-calendar copy follow the new date/)).toBeInTheDocument()
  })

  it('blocks working time without touching the due date', async () => {
    api.createScheduledEvent.mockResolvedValue({ id: 'event-9' })
    await renderCalendarOn('2026-09-10T12:00:00')

    dropOn('17')
    fireEvent.click(await screen.findByRole('radio', { name: /Block time to work on it/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Block the time' }))

    await waitFor(() => expect(api.createScheduledEvent).toHaveBeenCalledWith({
      title: 'Work block: File the motion',
      description: 'Time blocked in LawHand to work on “File the motion”.',
      start_at: localDateTimeToIso('2026-09-17', '09:00'),
      end_at: localDateTimeToIso('2026-09-17', '10:00'),
      timezone: 'America/Chicago',
      task_id: 'task-1',
      matter_id: 'matter-1',
      calendar_provider: null,
      meeting_provider: 'none',
    }))
    expect(api.updateTask).not.toHaveBeenCalled()
    expect(await screen.findByText(/Blocked .* to work on “File the motion”\. Its due date is unchanged\./)).toBeInTheDocument()
  })

  it('surfaces the conflict message when the task changed after the calendar loaded', async () => {
    api.updateTask.mockRejectedValue({
      response: { data: { detail: { message: 'This task changed after it was loaded.' } } },
    })
    await renderCalendarOn('2026-09-10T12:00:00')

    dropOn('17')
    fireEvent.click(await screen.findByRole('button', { name: 'Move due date' }))

    expect(await screen.findByText('This task changed after it was loaded.')).toBeInTheDocument()
    // The prompt stays open so the drop can be retried after a refresh.
    expect(screen.getByRole('button', { name: 'Move due date' })).toBeInTheDocument()
  })

  it('ignores a drop back onto the day the task is already due', async () => {
    await renderCalendarOn('2026-09-10T12:00:00')

    dropOn('10')

    expect(screen.queryByRole('button', { name: 'Move due date' })).not.toBeInTheDocument()
    expect(api.updateTask).not.toHaveBeenCalled()
  })

  it('takes the due time from the hour column the deadline was dropped into', async () => {
    api.updateTask.mockResolvedValue({ id: 'task-1' })
    window.localStorage.setItem('calendar-view', 'week')
    vi.setSystemTime(new Date('2026-09-10T12:00:00'))
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)
    await screen.findAllByText('File the motion')

    // Week of Sep 6–12: the Friday column, 14:00 row.
    const columns = document.querySelectorAll('.grid.relative > div')
    const fridayHours = columns[6].querySelectorAll('div.h-16')
    fireEvent.drop(fridayHours[14], {
      dataTransfer: { getData: (key) => (key === 'text/calendar-event-id' ? taskEvent.id : '') },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Move due date' }))

    await waitFor(() => expect(api.updateTask).toHaveBeenCalledWith('task-1', {
      due_date: '2026-09-11',
      due_time: '14:00',
      expected_version: 4,
    }))
  })

  it('closes the prompt on Escape so a misdropped chip changes nothing', async () => {
    await renderCalendarOn('2026-09-10T12:00:00')

    dropOn('17')
    expect(await screen.findByRole('button', { name: 'Move due date' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Move due date' })).not.toBeInTheDocument())
    expect(api.updateTask).not.toHaveBeenCalled()
    expect(api.createScheduledEvent).not.toHaveBeenCalled()
  })

  it('labels a work block so it is not read as the deadline itself', async () => {
    api.getCalendarEvents.mockResolvedValue({
      events: [{
        id: 'scheduled-event-9',
        title: 'Work block: File the motion',
        date: '2026-09-11',
        event_type: 'scheduled_event',
        task_id: 'task-1',
        start: '2026-09-11T09:00:00',
        end: '2026-09-11T10:00:00',
      }],
    })
    window.localStorage.setItem('calendar-view', 'list')
    vi.setSystemTime(new Date('2026-09-10T12:00:00'))
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)

    expect(await screen.findByText('Work Block')).toBeInTheDocument()
  })
})

describe('addMinutesToTimeInput', () => {
  it('advances a wall-clock time input and never rolls past the end of the day', () => {
    expect(addMinutesToTimeInput('09:00', 60)).toBe('10:00')
    expect(addMinutesToTimeInput('09:45', 30)).toBe('10:15')
    expect(addMinutesToTimeInput('23:30', 60)).toBe('23:59')
  })
})
