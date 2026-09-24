/**
 * Characterization tests for the cloud accounts panel.
 *
 * IntegrationsPanel owns the Google and Microsoft admin connect flows and
 * had no test file while ZoomPanel and TeamsPanel did. These pin the states
 * the panel can be in from /api/admin/permissions and the requests each
 * action fires, so the panel can be restructured safely.
 */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import IntegrationsPanel, {
  CloudRetryStatus,
  PrimaryCloudSelector,
  ProviderCard,
  describeProviderError,
  readConnectReturn,
  relTime,
  syncJobLabel,
} from './IntegrationsPanel'
import { ConfirmProvider } from './dialog/ConfirmProvider'
import {
  disconnectCloudProvider,
  getAdminPermissions,
  getAdminSettings,
  getSharePointBinding,
  retryCloudInit,
  triggerCloudSync,
  triggerUserSync,
  updateAdminSettings,
} from '../api'

afterEach(cleanup)

const renderPanel = () => render(<ConfirmProvider><IntegrationsPanel /></ConfirmProvider>)

vi.mock('../api', () => ({
  disconnectCloudProvider: vi.fn(),
  getAdminPermissions: vi.fn(),
  triggerUserSync: vi.fn(),
  retryCloudInit: vi.fn(),
  getAdminSettings: vi.fn(),
  updateAdminSettings: vi.fn(),
  triggerCloudSync: vi.fn(),
  getSharePointBinding: vi.fn(),
  listSharePointSites: vi.fn(),
  listSharePointDrives: vi.fn(),
  saveSharePointBinding: vi.fn(),
  API_BASE_URL: 'https://api.test/api',
}))

const GOOGLE_REQUIRED = [
  'openid',
  'email',
  'https://www.googleapis.com/auth/admin.directory.user.readonly',
  'https://www.googleapis.com/auth/gmail.readonly',
  'https://www.googleapis.com/auth/drive',
]

const disconnected = (provider) => ({
  connected: false,
  health: 'disconnected',
  required_scopes: GOOGLE_REQUIRED,
  granted_scopes: [],
  missing_required: GOOGLE_REQUIRED,
  extra_scopes: [],
  user_count: 0,
  capabilities: {},
  user_tokens: { total: 0, healthy: 0, needs_reauth: 0 },
  provider,
})

const healthyGoogle = {
  connected: true,
  health: 'healthy',
  account_label: 'Google Workspace',
  service_account_email: 'admin@firm.test',
  required_scopes: GOOGLE_REQUIRED,
  granted_scopes: [...GOOGLE_REQUIRED, 'https://www.googleapis.com/auth/calendar'],
  missing_required: [],
  extra_scopes: ['https://www.googleapis.com/auth/calendar'],
  user_count: 12,
  last_sync_status: 'ok',
  last_sync_at: new Date(Date.now() - 2 * 3600e3).toISOString(),
  last_refresh_at: new Date(Date.now() - 30 * 60e3).toISOString(),
  last_refresh_error: null,
  recent_sync_runs: [
    { job_type: 'cloud_sync', status: 'completed', started_at: new Date().toISOString(), items_ok: 700, items_failed: 0 },
  ],
  capabilities: {
    directory_sync: { available: true, status: 'ok', reason: 'ok' },
    cloud_storage: { available: true, status: 'ok', reason: 'ok' },
  },
  user_tokens: { total: 3, healthy: 2, needs_reauth: 1 },
}

const revokedGoogle = {
  ...healthyGoogle,
  health: 'revoked',
  reconnect_required: true,
  last_refresh_at: new Date(Date.now() - 62 * 86400e3).toISOString(),
  last_refresh_error: '400 invalid_grant Token has been expired or revoked.',
}

// A connected Microsoft tenant the panel reports without per-user counts.
const connectedMicrosoft = {
  connected: true,
  health: 'healthy',
  account_type: 'business',
  service_account_email: 'admin@firm.test',
  required_scopes: ['User.Read.All', 'Mail.Read'],
  granted_scopes: ['User.Read.All', 'Mail.Read'],
  missing_required: [],
  extra_scopes: [],
  user_count: 4,
  last_sync_status: 'ok',
  capabilities: {},
}

function permissions(overrides = {}) {
  return {
    overall_health: 'healthy',
    microsoft: disconnected('microsoft'),
    google: healthyGoogle,
    ...overrides,
  }
}

const cardProps = {
  scopeLabels: {},
  onReauthorize: vi.fn(),
  relTime,
  onSyncNow: vi.fn(),
  syncing: false,
}

describe('ProviderCard states', () => {
  it('renders a never-connected provider as a starting point, not a wall of failures', () => {
    const labels = {
      'https://www.googleapis.com/auth/drive': 'Read and write Drive',
      'https://www.googleapis.com/auth/gmail.readonly': 'Read Gmail',
    }
    render(<ProviderCard {...cardProps} scopeLabels={labels} name="Google Workspace" provider="google" info={disconnected('google')} />)
    expect(screen.getByText('Not connected')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync now' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Disconnect' })).toBeNull()
    // No red scope tally: the card explains what will be asked and who signs in.
    expect(screen.queryByTestId('scope-tally-missing')).toBeNull()
    expect(screen.queryByText('Missing')).toBeNull()
    expect(screen.getByText(/Google Workspace administrator account/)).toBeInTheDocument()
    const asks = screen.getByTestId('connect-asks-google')
    expect(within(asks).getByText('Read and write Drive')).toBeInTheDocument()
    // Sign-in plumbing is not presented as a feature to weigh.
    expect(within(asks).queryByText('openid')).toBeNull()
  })

  it('keeps the unused suite compact when the firm already runs on the other one', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={disconnected('google')} otherConnected />)
    expect(screen.getByText('Only needed if your firm also uses Google Workspace.')).toBeInTheDocument()
    expect(screen.getByText(/What Google Workspace will be asked to allow/).closest('details')).not.toHaveAttribute('open')
  })

  it('lists what will be asked from the missing list when no required list is sent', () => {
    const info = {
      ...disconnected('google'),
      required_scopes: [],
      missing_required: ['openid', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/tasks'],
    }
    render(<ProviderCard {...cardProps} scopeLabels={{ 'https://www.googleapis.com/auth/drive': 'Read and write Drive' }} name="Google Workspace" provider="google" info={info} />)
    const asks = screen.getByTestId('connect-asks-google')
    expect(within(asks).getAllByRole('listitem')).toHaveLength(2)
    expect(within(asks).getByText('Read and write Drive')).toBeInTheDocument()
    expect(within(asks).getByText('https://www.googleapis.com/auth/tasks')).toBeInTheDocument()
    expect(within(asks).queryByText('openid')).toBeNull()
  })

  it('still offers Connect, without an empty permission list, when no scopes are sent at all', () => {
    const { required_scopes: _required, missing_required: _missing, ...info } = disconnected('google')
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={info} />)
    expect(screen.getByText('Not connected')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect' })).toBeInTheDocument()
    expect(screen.queryByTestId('connect-asks-google')).toBeNull()
    expect(screen.queryByText(/will be asked to allow/)).toBeNull()
  })

  it('renders a healthy provider with granted scopes, extra scopes and sync actions', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={healthyGoogle} />)
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    expect(screen.getByText('Granted by admin@firm.test')).toBeInTheDocument()
    expect(screen.getByText(/12 users synced/)).toBeInTheDocument()
    expect(screen.getByTestId('scope-tally-granted')).toHaveTextContent('5')
    expect(screen.getByText('Additional granted scopes')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-authorize' })).toBeInTheDocument()
    expect(screen.getByText(/Last successful token refresh 30m ago/)).toBeInTheDocument()
    expect(screen.getByText(/700 ok/)).toBeInTheDocument()
  })

  it('reports missing scopes against the required list', () => {
    const info = {
      ...healthyGoogle,
      health: 'missing_scopes',
      missing_required: ['https://www.googleapis.com/auth/drive'],
      granted_scopes: GOOGLE_REQUIRED.slice(0, -1),
    }
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={info} scopeLabels={{ 'https://www.googleapis.com/auth/drive': 'Read & write Google Drive' }} />)
    expect(screen.getByText('Missing permissions')).toBeInTheDocument()
    expect(screen.getByTestId('scope-tally-missing')).toHaveTextContent('1')
    expect(screen.getByText('Read & write Google Drive')).toBeInTheDocument()
    expect(screen.getByTestId('scope-tally-granted')).toHaveTextContent('4')
  })

  it('names the declined permission, leads with Re-authorize and downgrades the feature it powers', () => {
    const info = {
      ...healthyGoogle,
      health: 'missing_scopes',
      missing_required: ['https://www.googleapis.com/auth/drive'],
      granted_scopes: GOOGLE_REQUIRED.slice(0, -1),
    }
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={info} scopeLabels={{ 'https://www.googleapis.com/auth/drive': 'Read & write Google Drive' }} />)
    const banner = screen.getByTestId('missing-scopes-google')
    expect(banner).toHaveTextContent('Some permissions were not granted')
    expect(banner).toHaveTextContent('Not granted: Read & write Google Drive.')
    expect(screen.getByRole('button', { name: 'Re-authorize' }).className).toContain('bg-brand-ink')
    // The backend still reports storage as available; the declined Drive scope wins.
    const storage = screen.getByTestId('capability-cloud_storage')
    expect(within(storage).getByText('Reconnect needed')).toBeInTheDocument()
    expect(within(storage).getByText('Not granted: Read & write Google Drive.')).toBeInTheDocument()
    expect(within(screen.getByTestId('capability-directory_sync')).getByText('Available')).toBeInTheDocument()
  })

  it('names a declined permission it has no label for by its scope', () => {
    const drive = 'https://www.googleapis.com/auth/drive'
    const info = {
      ...healthyGoogle,
      health: 'missing_scopes',
      missing_required: [drive],
      granted_scopes: GOOGLE_REQUIRED.slice(0, -1),
    }
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={info} />)
    expect(screen.getByTestId('missing-scopes-google')).toHaveTextContent(`Not granted: ${drive}.`)
    const storage = screen.getByTestId('capability-cloud_storage')
    expect(within(storage).getByText('Reconnect needed')).toBeInTheDocument()
    expect(within(storage).getByText(`Not granted: ${drive}.`)).toBeInTheDocument()
  })

  it('leads with the remedy and hides the scope tally when the grant is revoked', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={revokedGoogle} />)
    expect(screen.getByText('Reconnect Required')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/re-authorize as an administrator/i)
    // Plain language first; the raw provider text stays available for support.
    const refreshError = screen.getByTestId('refresh-error-google')
    expect(refreshError).toHaveTextContent(/no longer accepts the saved sign-in/)
    expect(refreshError).not.toHaveAttribute('open')
    expect(screen.getByText('400 invalid_grant Token has been expired or revoked.')).toBeInTheDocument()
    expect(screen.getByText(/Last token refresh attempt 62d ago failed/)).toBeInTheDocument()
    // The scope tally is behind a disclosure and never claims a full green grant.
    expect(screen.getByText('Scope detail for support')).toBeInTheDocument()
    expect(screen.getByTestId('scope-tally-granted')).toHaveTextContent('0')
    expect(screen.getAllByText('Unusable').length).toBe(GOOGLE_REQUIRED.length)
    expect(screen.queryByText('Features on this account')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Sync now' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Re-authorize' })).toBeInTheDocument()
  })

  it('treats refresh_failed the same way as revoked', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={{ ...revokedGoogle, health: 'refresh_failed', last_refresh_error: '503 upstream' }} />)
    expect(screen.getByText('Refresh Failed')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/could not refresh/i)
    expect(screen.getByTestId('scope-tally-granted')).toHaveTextContent('0')
  })

  it('separates the firm connection from per-user connections and says whose account it acts as', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={healthyGoogle} />)
    expect(screen.getByText('Firm connection')).toBeInTheDocument()
    expect(screen.getByText(/features that use this connection act as admin@firm\.test/)).toBeInTheDocument()
    const users = screen.getByTestId('user-tokens-google')
    expect(within(users).getByText(/2 of 3 connected/)).toBeInTheDocument()
    expect(within(users).getByText(/1 need to reconnect from Profile → Connected accounts/)).toBeInTheDocument()
  })

  it('labels sync runs in plain language', () => {
    const info = {
      ...healthyGoogle,
      recent_sync_runs: [
        { job_type: 'correspondence-capture', status: 'failed', started_at: new Date().toISOString(), items_ok: 0, items_failed: 1 },
      ],
    }
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={info} />)
    expect(screen.getByText('Email filing')).toBeInTheDocument()
    expect(screen.getByText(/Failed · just now/)).toBeInTheDocument()
    expect(screen.queryByText('correspondence-capture')).toBeNull()
  })

  it('renders directory sync as a tier statement, not a failure, and hides Sync now', () => {
    const info = {
      ...healthyGoogle,
      account_label: 'Personal Google (Gmail)',
      last_sync_status: 'not_applicable',
      last_sync_error: "Directory sync isn't available on personal Google accounts",
      capabilities: { directory_sync: { available: false, status: 'unavailable', reason: 'personal' } },
    }
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={info} />)
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    expect(screen.getByText(/directory sync unavailable for this account/)).toBeInTheDocument()
    expect(screen.getByText('Unavailable for this account')).toBeInTheDocument()
    expect(screen.getByText(/Directory sync imports organization users. Its availability is separate from document storage/)).toBeInTheDocument()
    expect(screen.queryByText(info.last_sync_error)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Sync now' })).toBeNull()
  })
})

describe('IntegrationsPanel actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAdminPermissions.mockResolvedValue(permissions())
    getAdminSettings.mockResolvedValue({ primary_cloud_provider: null })
    getSharePointBinding.mockResolvedValue({ binding: null })
  })

  it('shows provider status first and keeps storage settings collapsed', async () => {
    renderPanel()
    expect(await screen.findByText('Integrations: Healthy')).toBeInTheDocument()
    const cards = screen.getAllByTestId(/provider-card-/)
    expect(cards.map((el) => el.dataset.testid)).toEqual(['provider-card-microsoft', 'provider-card-google'])
    const storage = screen.getByTestId('document-storage')
    expect(storage).not.toHaveAttribute('open')
    expect(screen.getByText(/Automatic provider: Google Drive .* matter folder access is checked when saving/)).toBeInTheDocument()
    // Operator tooling no longer renders inside the firm-admin panel.
    expect(screen.queryByText('Storage migration')).toBeNull()
    expect(screen.queryByText('Tabs3 Import')).toBeNull()
    expect(screen.queryByText('Cloud Integration Readiness')).toBeNull()
  })

  it('re-authorizes and connects at admin intent by navigating to the connect endpoint', async () => {
    // jsdom does not implement cross-origin navigation; stub the location so
    // the assigned href can be read back.
    const realLocation = window.location
    delete window.location
    window.location = { href: 'http://localhost/admin' }
    try {
      const user = userEvent.setup()
      renderPanel()
      await screen.findByText('Integrations: Healthy')

      await user.click(screen.getByRole('button', { name: 'Re-authorize' }))
      expect(window.location.href).toBe('https://api.test/api/integrations/google/connect?intent=admin&return_to=integrations')

      await user.click(screen.getByRole('button', { name: 'Connect' }))
      expect(window.location.href).toBe('https://api.test/api/integrations/microsoft/connect?intent=admin&return_to=integrations')
    } finally {
      window.location = realLocation
    }
  })

  it('triggers a directory sync and reloads permissions afterwards', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    triggerUserSync.mockResolvedValue({ status: 'ok' })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderPanel()
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByRole('button', { name: 'Sync now' }))
    expect(triggerUserSync).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Syncing…' })).toBeDisabled()
    await vi.advanceTimersByTimeAsync(4000)
    await waitFor(() => expect(getAdminPermissions).toHaveBeenCalledTimes(2))
    vi.useRealTimers()
  })

  it('runs the cloud file and email sync and reports the count', async () => {
    triggerCloudSync.mockResolvedValue({ total: 700 })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByRole('button', { name: /Sync files \+ email/ }))
    expect(triggerCloudSync).toHaveBeenCalledOnce()
    expect(await screen.findByText('Synced 700 cloud items')).toBeInTheDocument()
  })

  it('retries cloud folder setup from inside document storage', async () => {
    retryCloudInit.mockResolvedValue({ matters_initialized: 2, matters_failed: 0, status: 'ready' })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByText('Document storage'))
    await user.click(screen.getByRole('button', { name: /Create missing matter folders/ }))
    expect(retryCloudInit).toHaveBeenCalledOnce()
    expect(await screen.findByText('Cloud folders ready · 2 matters set up')).toBeInTheDocument()
  })

  it('requires confirmation before repointing the primary provider', async () => {
    updateAdminSettings.mockResolvedValue({})
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByText('Document storage'))
    await user.selectOptions(screen.getByLabelText('Primary cloud provider'), 'google_drive')
    expect(updateAdminSettings).not.toHaveBeenCalled()
    expect(screen.getByText(/Switch new matter documents to Google Drive\?/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(updateAdminSettings).not.toHaveBeenCalled()

    await user.selectOptions(screen.getByLabelText('Primary cloud provider'), 'google_drive')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))
    expect(updateAdminSettings).toHaveBeenCalledWith({ primary_cloud_provider: 'google_drive' })
    expect(await screen.findByText('Preference saved')).toBeInTheDocument()
    expect(screen.getByText(/Connection available: Google Drive/)).toBeInTheDocument()
    expect(screen.getByText(/matter folder access is checked when saving/)).toBeInTheDocument()
  })

  it('shows the load error instead of an empty page when permissions fail', async () => {
    getAdminPermissions.mockRejectedValue(new Error('boom'))
    renderPanel()
    expect(await screen.findByText('Failed to load permissions.')).toBeInTheDocument()
  })

  it('reports attention needed and the revoked remedy when the tenant grant is dead', async () => {
    getAdminPermissions.mockResolvedValue(permissions({ overall_health: 'attention_needed', google: revokedGoogle }))
    renderPanel()
    expect(await screen.findByText('Integrations: Needs Attention')).toBeInTheDocument()
    expect(screen.getByText('Reconnect Required')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/re-authorize/i)
  })

  it('does not report configured OneDrive as ready when Microsoft needs reconnection', async () => {
    getAdminPermissions.mockResolvedValue(permissions({
      microsoft: {
        ...disconnected('microsoft'),
        connected: true,
        health: 'refresh_failed',
        missing_required: [],
      },
    }))
    getAdminSettings.mockResolvedValue({ primary_cloud_provider: 'onedrive' })
    renderPanel()
    expect((await screen.findAllByText(/Reconnect Microsoft 365 before saving matter documents to Microsoft OneDrive/)).length).toBe(2)
    await userEvent.setup().click(screen.getByText('Document storage'))
    expect(screen.getByText('Matter document storage is not ready.')).toBeInTheDocument()
  })
})

describe('IntegrationsPanel account modes and disconnect', () => {
  let realLocation
  beforeEach(() => {
    vi.clearAllMocks()
    getAdminSettings.mockResolvedValue({ primary_cloud_provider: null })
    getSharePointBinding.mockResolvedValue({ binding: null })
    realLocation = window.location
    delete window.location
    window.location = { href: 'http://localhost/admin' }
  })
  afterEach(() => {
    window.location = realLocation
  })

  it('re-authorizes a personal Gmail firm in personal mode so the callback accepts it', async () => {
    getAdminPermissions.mockResolvedValue(permissions({
      google: { ...healthyGoogle, account_type: 'personal', account_label: 'Personal Google (Gmail)' },
    }))
    const user = userEvent.setup()
    renderPanel()
    expect(await screen.findByText('Google (personal Gmail)')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Re-authorize' }))
    expect(window.location.href).toBe('https://api.test/api/integrations/google/connect?intent=admin&return_to=integrations&account_mode=personal')
  })

  it('offers a personal Gmail connect for a solo practice that has not connected Google yet', async () => {
    getAdminPermissions.mockResolvedValue(permissions({
      overall_health: 'disconnected',
      google: disconnected('google'),
    }))
    const user = userEvent.setup()
    renderPanel()
    const google = await screen.findByTestId('provider-card-google')
    // The plain Connect stays in Workspace mode; only the solo link asks for personal.
    await user.click(within(google).getByRole('button', { name: 'Connect' }))
    expect(window.location.href).toBe('https://api.test/api/integrations/google/connect?intent=admin&return_to=integrations')
    await user.click(within(google).getByRole('button', { name: /Solo practice on personal Gmail/ }))
    expect(window.location.href).toBe('https://api.test/api/integrations/google/connect?intent=admin&return_to=integrations&account_mode=personal')
  })

  it('names a personal Microsoft account and never adds the Gmail account mode to its link', async () => {
    getAdminPermissions.mockResolvedValue(permissions({
      microsoft: { ...connectedMicrosoft, account_type: 'consumer' },
      google: { ...healthyGoogle, account_type: 'personal', account_label: 'Personal Google (Gmail)' },
    }))
    const user = userEvent.setup()
    renderPanel()
    const microsoft = await screen.findByTestId('provider-card-microsoft')
    expect(within(microsoft).getByRole('heading', { name: 'Microsoft (personal account)' })).toBeInTheDocument()
    expect(within(microsoft).queryByRole('heading', { name: 'Microsoft 365' })).toBeNull()

    await user.click(within(microsoft).getByRole('button', { name: 'Re-authorize' }))
    expect(window.location.href).toBe('https://api.test/api/integrations/microsoft/connect?intent=admin&return_to=integrations')

    await user.click(within(screen.getByTestId('provider-card-google')).getByRole('button', { name: 'Re-authorize' }))
    expect(window.location.href).toBe('https://api.test/api/integrations/google/connect?intent=admin&return_to=integrations&account_mode=personal')
  })

  it('disconnects only after the administrator types the firm-wide acknowledgement', async () => {
    getAdminPermissions.mockResolvedValueOnce(permissions())
      .mockResolvedValueOnce(permissions({ overall_health: 'disconnected', google: disconnected('google') }))
    disconnectCloudProvider.mockResolvedValue({ status: 'disconnected', provider: 'google' })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByRole('button', { name: 'Disconnect' }))
    let dialog = screen.getByRole('alertdialog', { name: 'Disconnect Google for the whole firm?' })
    const details = within(dialog).getByTestId('confirm-details')
    expect(details).toHaveTextContent(/Files already there stay where they are/)
    // healthyGoogle has three personal connections; the dialog names the count.
    expect(details).toHaveTextContent(/3 staff members’ personal Google connections are removed as well/)
    expect(details).toHaveTextContent(/revokes its access at Google/)
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(disconnectCloudProvider).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Disconnect' }))
    dialog = screen.getByRole('alertdialog')
    const confirmButton = within(dialog).getByRole('button', { name: 'Disconnect Google' })
    expect(confirmButton).toBeDisabled()
    const phrase = within(dialog).getByLabelText(/to confirm/)
    await user.type(phrase, 'disconnect')
    expect(confirmButton).toBeDisabled()
    await user.type(phrase, ' GOOGLE ')
    expect(confirmButton).toBeEnabled()
    await user.click(confirmButton)
    expect(disconnectCloudProvider).toHaveBeenCalledOnce()
    expect(disconnectCloudProvider).toHaveBeenCalledWith('google')
    expect(await screen.findByText('Integrations: No integrations connected')).toBeInTheDocument()
  })

  it('disconnects Microsoft 365 with its own phrase and consequences, and never on Escape or a wrong phrase', async () => {
    getAdminPermissions.mockResolvedValueOnce(permissions({ microsoft: connectedMicrosoft, google: disconnected('google') }))
      .mockResolvedValueOnce(permissions({ overall_health: 'disconnected', google: disconnected('google') }))
    disconnectCloudProvider.mockResolvedValue({ status: 'disconnected', provider: 'microsoft' })
    const user = userEvent.setup()
    renderPanel()
    const microsoft = await screen.findByTestId('provider-card-microsoft')
    expect(within(microsoft).getByRole('heading', { name: 'Microsoft 365' })).toBeInTheDocument()

    await user.click(within(microsoft).getByRole('button', { name: 'Disconnect' }))
    expect(screen.getByRole('alertdialog', { name: 'Disconnect Microsoft 365 for the whole firm?' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(disconnectCloudProvider).not.toHaveBeenCalled()

    await user.click(within(microsoft).getByRole('button', { name: 'Disconnect' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Disconnect Microsoft 365 for the whole firm?' })
    const details = within(dialog).getByTestId('confirm-details')
    expect(details).toHaveTextContent('Saving matter documents to OneDrive or SharePoint stops. Files already there stay where they are.')
    // No per-user counts reported, so the dialog does not invent a number.
    expect(details).toHaveTextContent("Any staff member's personal Microsoft 365 connection is removed as well.")
    expect(details).toHaveTextContent(/remove it under Enterprise applications in Microsoft Entra/)
    expect(details).not.toHaveTextContent(/revokes its access at Google/)

    const phrase = within(dialog).getByLabelText('Type disconnect Microsoft 365 to confirm')
    const confirmButton = within(dialog).getByRole('button', { name: 'Disconnect Microsoft 365' })
    // The other provider's phrase does not unlock this one, by click or by Enter.
    await user.type(phrase, 'disconnect Google{Enter}')
    expect(confirmButton).toBeDisabled()
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(disconnectCloudProvider).not.toHaveBeenCalled()

    await user.clear(phrase)
    await user.type(phrase, 'disconnect microsoft 365')
    expect(confirmButton).toBeEnabled()
    await user.click(confirmButton)
    expect(disconnectCloudProvider).toHaveBeenCalledOnce()
    expect(disconnectCloudProvider).toHaveBeenCalledWith('microsoft')
    expect(await screen.findByText('Integrations: No integrations connected')).toBeInTheDocument()
    expect(getAdminPermissions).toHaveBeenCalledTimes(2)
  })

  it('keeps the card and says what to do when the disconnect request fails', async () => {
    getAdminPermissions.mockResolvedValue(permissions({
      google: { ...healthyGoogle, user_tokens: { total: 1, healthy: 1, needs_reauth: 0 } },
    }))
    let failDisconnect
    disconnectCloudProvider.mockReturnValue(new Promise((_resolve, reject) => { failDisconnect = reject }))
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByRole('button', { name: 'Disconnect' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Disconnect Google for the whole firm?' })
    expect(within(dialog).getByTestId('confirm-details')).toHaveTextContent('1 staff member’s personal Google connection is removed as well.')
    await user.type(within(dialog).getByLabelText(/to confirm/), 'disconnect google')
    await user.click(within(dialog).getByRole('button', { name: 'Disconnect Google' }))

    expect(disconnectCloudProvider).toHaveBeenCalledOnce()
    expect(disconnectCloudProvider).toHaveBeenCalledWith('google')
    expect(screen.getByRole('button', { name: 'Disconnecting…' })).toBeDisabled()

    failDisconnect(new Error('boom'))
    expect(await screen.findByText('Failed to disconnect Google. Reload this page to check its status, then try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Disconnect' })).toBeEnabled()
    expect(screen.getByText('Integrations: Healthy')).toBeInTheDocument()
    expect(getAdminPermissions).toHaveBeenCalledOnce()
  })

  it('confirms a completed connect above the cards and lets the administrator dismiss it', async () => {
    window.location.search = '?tab=integrations&integration=cloud&connected=google'
    getAdminPermissions.mockResolvedValue(permissions())
    const user = userEvent.setup()
    renderPanel()
    const notice = await screen.findByTestId('connect-return')
    expect(notice).toHaveAttribute('role', 'status')
    expect(notice).toHaveTextContent('Google connected. Check the card below: anything that was not granted is listed there.')

    await user.click(within(notice).getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByTestId('connect-return')).toBeNull()
    expect(screen.getByText('Integrations: Healthy')).toBeInTheDocument()
  })

  it('reports a failed connect as an alert for the provider the callback named', async () => {
    window.location.search = '?error=consent_required&provider=microsoft'
    getAdminPermissions.mockResolvedValue(permissions())
    renderPanel()
    const notice = await screen.findByRole('alert')
    expect(notice).toHaveAttribute('data-testid', 'connect-return')
    expect(notice).toHaveTextContent('Microsoft 365 needs an administrator to approve LawHand before this account can connect.')
  })

  it('falls back to a generic failure message for an error code it does not know', async () => {
    window.location.search = '?error=server_error&provider=google'
    getAdminPermissions.mockResolvedValue(permissions())
    renderPanel()
    const notice = await screen.findByRole('alert')
    expect(notice).toHaveTextContent('The Google connection could not be completed. No connection was saved; try again.')
    expect(notice).not.toHaveTextContent('server_error')
  })

  it('opens document storage on its own when a connected firm cannot save yet', async () => {
    getAdminPermissions.mockResolvedValue(permissions({
      microsoft: { ...disconnected('microsoft'), connected: true, health: 'refresh_failed', missing_required: [] },
      google: disconnected('google'),
      overall_health: 'attention_needed',
    }))
    getAdminSettings.mockResolvedValue({ primary_cloud_provider: 'onedrive' })
    renderPanel()
    await screen.findByText('Integrations: Needs Attention')
    expect(screen.getByTestId('document-storage')).toHaveAttribute('open')
  })
})

describe('readConnectReturn', () => {
  it('confirms a completed connect and explains a failed one with the right provider', () => {
    expect(readConnectReturn('?tab=integrations&integration=cloud&connected=microsoft')).toEqual({
      tone: 'ok',
      text: 'Microsoft 365 connected. Check the card below: anything that was not granted is listed there.',
    })
    expect(readConnectReturn('?error=access_denied&provider=google')).toEqual({
      tone: 'error',
      text: 'The Google sign-in was cancelled, so nothing was connected. Try again when you are ready.',
    })
  })

  it('ignores other integrations and missing parameters', () => {
    expect(readConnectReturn('?connected=zoom')).toBeNull()
    expect(readConnectReturn('')).toBeNull()
    expect(readConnectReturn(undefined)).toBeNull()
  })

  it('uses a generic message for unknown codes and never echoes the code from the URL', () => {
    expect(readConnectReturn('?error=Call%20support%20at%20555&provider=microsoft')).toEqual({
      tone: 'error',
      text: 'The Microsoft 365 connection could not be completed. No connection was saved; try again.',
    })
  })

  it('never reports success when the callback carried an error without a known provider', () => {
    expect(readConnectReturn('?error=access_denied&connected=google')).toBeNull()
    expect(readConnectReturn('?error=access_denied&provider=zoom')).toBeNull()
    expect(readConnectReturn('?error=access_denied')).toBeNull()
  })
})

describe('plain-language helpers', () => {
  it('names sync jobs for people, whatever separator the backend uses', () => {
    expect(syncJobLabel('user-sync')).toBe('Directory sync')
    expect(syncJobLabel('cloud_sync')).toBe('File & email index')
    expect(syncJobLabel('correspondence-capture')).toBe('Email filing')
    expect(syncJobLabel('calendar-push')).toBe('Calendar push')
    expect(syncJobLabel(null)).toBe('Sync')
  })

  it('explains common provider errors before showing raw text', () => {
    expect(describeProviderError('400 invalid_grant Token has been expired or revoked.')).toMatch(/no longer accepts the saved sign-in/)
    expect(describeProviderError('503 upstream')).toMatch(/did not respond/)
    expect(describeProviderError('403 Forbidden')).toMatch(/refused access/)
    expect(describeProviderError('something odd')).toBe('The provider returned an error.')
  })

  it('falls back to the generic line when the provider sent no error text', () => {
    expect(describeProviderError(null)).toBe('The provider returned an error.')
    expect(describeProviderError(undefined)).toBe('The provider returned an error.')
    expect(describeProviderError('')).toBe('The provider returned an error.')
  })
})

describe('PrimaryCloudSelector', () => {
  it('reverts the pending choice on cancel without calling onChange', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<PrimaryCloudSelector value="onedrive" saving={false} saved={false} onChange={onChange} />)
    expect(screen.getByText(/Saving this preference does not verify an individual matter folder/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Primary cloud provider'), 'sharepoint')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Primary cloud provider')).toHaveValue('onedrive')
  })
})

describe('CloudRetryStatus', () => {
  it('reports a partial retry instead of claiming every matter is ready', () => {
    render(<CloudRetryStatus result={{ matters_initialized: 2, matters_failed: 1, status: 'partial' }} />)
    expect(screen.getByText(/partially ready/)).toBeInTheDocument()
  })
})

describe('relTime', () => {
  it('formats relative times', () => {
    const now = Date.UTC(2026, 8, 13, 12, 0, 0)
    expect(relTime(null, now)).toBe('never')
    expect(relTime(new Date(now - 10e3).toISOString(), now)).toBe('just now')
    expect(relTime(new Date(now - 5 * 60e3).toISOString(), now)).toBe('5m ago')
    expect(relTime(new Date(now - 3 * 3600e3).toISOString(), now)).toBe('3h ago')
    expect(relTime(new Date(now - 62 * 86400e3).toISOString(), now)).toBe('62d ago')
  })
})
