import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CalendarPage from './CalendarPage'

const api = vi.hoisted(() => ({
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
}))

vi.mock('../api', () => api)
vi.mock('../utils/reportError', () => ({ reportError: vi.fn() }))

async function openCreateModal() {
  render(<MemoryRouter><CalendarPage /></MemoryRouter>)
  const newEvent = await screen.findByRole('button', { name: /New Event/ })
  fireEvent.click(newEvent)
  await screen.findByRole('heading', { name: 'Create event' })
}

async function submitTitledEvent(title = 'Deposition prep') {
  fireEvent.change(screen.getByPlaceholderText('Event title'), { target: { value: title } })
  fireEvent.click(screen.getByRole('button', { name: 'Create event' }))
}

describe('calendar create-event save vs external sync truthfulness (S1.09)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getCalendarEvents.mockResolvedValue({ events: [] })
    api.getCalendarProviders.mockResolvedValue({ providers: [], provider_status: {}, tenant_providers: [] })
    api.getZoomStatus.mockResolvedValue({ connected: false, configured: false })
    api.getMattersV2.mockResolvedValue({ items: [] })
  })

  afterEach(cleanup)

  it('reports a saved event with a failed external sync and offers to reconnect', async () => {
    api.getCalendarProviders.mockResolvedValue({
      providers: [],
      provider_status: { microsoft: { connected: true } },
      tenant_providers: [],
    })
    api.createScheduledEvent.mockResolvedValue({
      id: 'event-1',
      sync_status: 'error',
      sync_error: 'token expired',
      calendar_provider: 'microsoft',
    })

    await openCreateModal()
    await submitTitledEvent()

    expect(await screen.findByText('Saved in LawHand, but the connected calendar could not be updated.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reconnect/ })).toBeInTheDocument()
  })

  it('does not claim an external sync for a local-only save', async () => {
    api.createScheduledEvent.mockResolvedValue({ id: 'event-2', sync_status: 'local', calendar_provider: null })

    await openCreateModal()
    await submitTitledEvent()

    expect(await screen.findByText('Event created in LawHand.')).toBeInTheDocument()
    expect(screen.queryByText(/synced to your connected calendar/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reconnect/ })).not.toBeInTheDocument()
  })

  it('says when an event was created and synced', async () => {
    api.createScheduledEvent.mockResolvedValue({ id: 'event-3', sync_status: 'synced', calendar_provider: 'google' })

    await openCreateModal()
    await submitTitledEvent()

    expect(await screen.findByText('Event created and synced to your connected calendar.')).toBeInTheDocument()
  })
})
