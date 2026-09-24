import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ConnectedAccountsCard from './ConnectedAccountsCard'
import { connectCalendarIntegration, getCalendarProviders } from '../api'

vi.mock('../api', () => ({
  connectCalendarIntegration: vi.fn(),
  getCalendarProviders: vi.fn(),
}))

afterEach(cleanup)

const notConnected = { connected: false, needs_reconnect: false, reason: 'not_connected', missing_scopes: [] }

describe('ConnectedAccountsCard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers only the suites the firm uses and says what connecting allows', async () => {
    getCalendarProviders.mockResolvedValue({
      providers: [],
      tenant_providers: ['microsoft'],
      provider_status: { microsoft: notConnected, google: notConnected },
    })
    const user = userEvent.setup()
    render(<ConnectedAccountsCard />)

    const microsoft = await screen.findByTestId('connected-account-microsoft')
    expect(screen.queryByTestId('connected-account-google')).toBeNull()
    expect(within(microsoft).getByText('Not connected')).toBeInTheDocument()
    // One consent covers mail, sending, calendar and files, so all four are named.
    expect(within(microsoft).getByText(/file matter correspondence/)).toBeInTheDocument()
    expect(within(microsoft).getByText(/Send client email you approve/)).toBeInTheDocument()
    expect(within(microsoft).getByText(/Outlook calendar/)).toBeInTheDocument()
    expect(within(microsoft).getByText(/OneDrive or SharePoint/)).toBeInTheDocument()

    await user.click(within(microsoft).getByRole('button', { name: 'Connect Microsoft 365' }))
    expect(connectCalendarIntegration).toHaveBeenCalledWith('microsoft')
  })

  it('explains why a connection needs reconnecting', async () => {
    getCalendarProviders.mockResolvedValue({
      providers: [],
      tenant_providers: ['google'],
      provider_status: {
        microsoft: notConnected,
        google: { connected: false, needs_reconnect: true, reason: 'refresh_failed', missing_scopes: [] },
      },
    })
    render(<ConnectedAccountsCard />)
    const google = await screen.findByTestId('connected-account-google')
    expect(within(google).getByText('Needs reconnecting')).toBeInTheDocument()
    expect(within(google).getByText(/sign-in has expired or was revoked/)).toBeInTheDocument()
    expect(within(google).getByRole('button', { name: 'Reconnect Google' })).toBeInTheDocument()
  })

  it('shows a connected account and still lists a personal connection outside the firm suites', async () => {
    getCalendarProviders.mockResolvedValue({
      providers: ['google'],
      tenant_providers: ['microsoft'],
      provider_status: {
        microsoft: { connected: true, needs_reconnect: false, reason: null, missing_scopes: [] },
        google: { connected: true, needs_reconnect: false, reason: null, missing_scopes: [] },
      },
    })
    render(<ConnectedAccountsCard />)
    expect(within(await screen.findByTestId('connected-account-microsoft')).getByText('Connected')).toBeInTheDocument()
    expect(within(screen.getByTestId('connected-account-google')).getByText('Connected')).toBeInTheDocument()
  })

  it('tells people when the firm has not connected a suite yet', async () => {
    getCalendarProviders.mockResolvedValue({
      providers: [],
      tenant_providers: [],
      provider_status: { microsoft: notConnected, google: notConnected },
    })
    render(<ConnectedAccountsCard />)
    expect(await screen.findByText(/firm has not connected Microsoft 365 or Google Workspace yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('reports a load failure instead of an empty card', async () => {
    getCalendarProviders.mockRejectedValue(new Error('boom'))
    render(<ConnectedAccountsCard />)
    expect(await screen.findByRole('status')).toHaveTextContent('Could not load your connected accounts')
  })
})
