import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import CalendarPage from './CalendarPage'

const api = vi.hoisted(() => ({
  connectCalendarIntegration: vi.fn(),
  getCalendarEvents: vi.fn(),
  getCalendarProviders: vi.fn(),
  getMattersV2: vi.fn(),
  getZoomStatus: vi.fn(),
}))

vi.mock('../api', () => ({
  ...api,
  browserTimezone: vi.fn(() => 'UTC'),
  connectZoomIntegration: vi.fn(),
  createScheduledEvent: vi.fn(),
  deleteScheduledEvent: vi.fn(),
  syncCalendarDeadlines: vi.fn(),
  updateScheduledEvent: vi.fn(),
  updateTask: vi.fn(),
}))
vi.mock('../utils/reportError', () => ({ reportError: vi.fn() }))

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-search">{location.search}</output>
}

function renderCalendar(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CalendarPage />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('calendar OAuth callback handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.setItem('calendar-view', 'month')
    api.getCalendarEvents.mockResolvedValue({ events: [] })
    api.getMattersV2.mockResolvedValue({ items: [] })
    api.getZoomStatus.mockResolvedValue({ connected: false, configured: false })
  })

  afterEach(() => {
    cleanup()
    window.localStorage.clear()
  })

  it('shows success only after the returned provider is confirmed usable and clears callback fields', async () => {
    api.getCalendarProviders.mockResolvedValue({
      providers: ['microsoft'],
      provider_status: { microsoft: { connected: true } },
      tenant_providers: ['microsoft'],
    })
    renderCalendar('/calendar?connected=microsoft&keep=1')

    expect(await screen.findByText('Microsoft Calendar connected successfully.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?keep=1'))
  })

  it('prefers the callback provider when both providers are usable', async () => {
    api.getCalendarProviders.mockResolvedValue({ providers: ['microsoft', 'google'], provider_status: {}, tenant_providers: [] })
    renderCalendar('/calendar?connected=google')

    expect(await screen.findByText('Google Calendar connected successfully.')).toBeInTheDocument()
  })

  it('does not claim success for an unavailable or unrecognized provider', async () => {
    api.getCalendarProviders.mockResolvedValue({ providers: ['microsoft'], provider_status: {}, tenant_providers: [] })
    renderCalendar('/calendar?connected=google')

    expect(await screen.findByText('Calendar connection could not be confirmed. Please try again.')).toBeInTheDocument()
    expect(screen.queryByText('Google Calendar connected successfully.')).not.toBeInTheDocument()
  })

  it('does not claim success for an unknown callback provider', async () => {
    api.getCalendarProviders.mockResolvedValue({ providers: ['microsoft'], provider_status: {}, tenant_providers: [] })
    renderCalendar('/calendar?connected=dropbox')

    expect(await screen.findByText('Calendar connection could not be confirmed. Please try again.')).toBeInTheDocument()
    expect(screen.queryByText(/Dropbox Calendar connected successfully/)).not.toBeInTheDocument()
  })

  it('shows a friendly retry message for cancellation and keeps unrelated query state', async () => {
    api.getCalendarProviders.mockResolvedValue({ providers: ['microsoft'], provider_status: {}, tenant_providers: ['microsoft', 'google'] })
    renderCalendar('/calendar?error=access_denied&provider=google&keep=1')

    expect(await screen.findByText('Calendar connection was cancelled. You can try again when ready.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sync Calendar' })).toBeInTheDocument()
    screen.getByRole('button', { name: 'Reconnect Google Calendar' }).click()
    expect(api.connectCalendarIntegration).toHaveBeenCalledWith('google')
    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?keep=1'))
  })

  it('clears callback fields and shows a safe message when provider lookup fails', async () => {
    api.getCalendarProviders.mockRejectedValue(new Error('provider details leaked'))
    renderCalendar('/calendar?error=provider_error&provider=microsoft&keep=1')

    expect(await screen.findByText('Calendar connection could not be confirmed. Please try again.')).toBeInTheDocument()
    expect(screen.queryByText(/provider details leaked/)).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?keep=1'))
  })
})
