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
  relTime,
} from './IntegrationsPanel'
import {
  getAdminPermissions,
  getAdminSettings,
  getSharePointBinding,
  retryCloudInit,
  triggerCloudSync,
  triggerUserSync,
  updateAdminSettings,
} from '../api'

afterEach(cleanup)

vi.mock('../api', () => ({
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
  it('renders a disconnected provider with a Connect action and no granted count', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={disconnected('google')} />)
    expect(screen.getByText('Disconnected')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync now' })).toBeNull()
    expect(screen.getByTestId('scope-tally-granted')).toHaveTextContent('0')
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
    expect(screen.getByText('Missing Scopes')).toBeInTheDocument()
    expect(screen.getByTestId('scope-tally-missing')).toHaveTextContent('1')
    expect(screen.getByText('Read & write Google Drive')).toBeInTheDocument()
    expect(screen.getByTestId('scope-tally-granted')).toHaveTextContent('4')
  })

  it('leads with the remedy and hides the scope tally when the grant is revoked', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={revokedGoogle} />)
    expect(screen.getByText('Reconnect Required')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/re-authorize as an administrator/i)
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

  it('separates the firm-wide connection from per-user connections', () => {
    render(<ProviderCard {...cardProps} name="Google Workspace" provider="google" info={healthyGoogle} />)
    expect(screen.getByText('Firm-wide connection')).toBeInTheDocument()
    const users = screen.getByTestId('user-tokens-google')
    expect(within(users).getByText(/2 of 3 connected/)).toBeInTheDocument()
    expect(within(users).getByText(/1 need to open Calendar and choose Connect Calendar/)).toBeInTheDocument()
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
    expect(screen.getByText(/directory sync not available on this tier/)).toBeInTheDocument()
    expect(screen.getByText('Not on this tier')).toBeInTheDocument()
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
    render(<IntegrationsPanel />)
    expect(await screen.findByText('Integrations: Healthy')).toBeInTheDocument()
    const cards = screen.getAllByTestId(/provider-card-/)
    expect(cards.map((el) => el.dataset.testid)).toEqual(['provider-card-microsoft', 'provider-card-google'])
    const storage = screen.getByTestId('document-storage')
    expect(storage).not.toHaveAttribute('open')
    expect(screen.getByText(/Automatic: OneDrive for Microsoft 365 tenants/)).toBeInTheDocument()
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
      render(<IntegrationsPanel />)
      await screen.findByText('Integrations: Healthy')

      await user.click(screen.getByRole('button', { name: 'Re-authorize' }))
      expect(window.location.href).toBe('https://api.test/api/integrations/google/connect?intent=admin')

      await user.click(screen.getByRole('button', { name: 'Connect' }))
      expect(window.location.href).toBe('https://api.test/api/integrations/microsoft/connect?intent=admin')
    } finally {
      window.location = realLocation
    }
  })

  it('triggers a directory sync and reloads permissions afterwards', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    triggerUserSync.mockResolvedValue({ status: 'ok' })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<IntegrationsPanel />)
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
    render(<IntegrationsPanel />)
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByRole('button', { name: /Sync files \+ email/ }))
    expect(triggerCloudSync).toHaveBeenCalledOnce()
    expect(await screen.findByText('Synced 700 cloud items')).toBeInTheDocument()
  })

  it('retries cloud folder setup from inside document storage', async () => {
    retryCloudInit.mockResolvedValue({ matters_initialized: 2, matters_failed: 0, status: 'ready' })
    const user = userEvent.setup()
    render(<IntegrationsPanel />)
    await screen.findByText('Integrations: Healthy')

    await user.click(screen.getByText('Document storage'))
    await user.click(screen.getByRole('button', { name: /Create missing matter folders/ }))
    expect(retryCloudInit).toHaveBeenCalledOnce()
    expect(await screen.findByText('Cloud folders ready · 2 matters set up')).toBeInTheDocument()
  })

  it('requires confirmation before repointing the primary provider', async () => {
    updateAdminSettings.mockResolvedValue({})
    const user = userEvent.setup()
    render(<IntegrationsPanel />)
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
    expect(await screen.findByText('Saved')).toBeInTheDocument()
    expect(screen.getByText(/Matter documents go to Google Drive/)).toBeInTheDocument()
  })

  it('shows the load error instead of an empty page when permissions fail', async () => {
    getAdminPermissions.mockRejectedValue(new Error('boom'))
    render(<IntegrationsPanel />)
    expect(await screen.findByText('Failed to load permissions.')).toBeInTheDocument()
  })

  it('reports attention needed and the revoked remedy when the tenant grant is dead', async () => {
    getAdminPermissions.mockResolvedValue(permissions({ overall_health: 'attention_needed', google: revokedGoogle }))
    render(<IntegrationsPanel />)
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
    render(<IntegrationsPanel />)
    expect((await screen.findAllByText(/Reconnect Microsoft 365 before saving matter documents to Microsoft OneDrive/)).length).toBe(2)
    await userEvent.setup().click(screen.getByText('Document storage'))
    expect(screen.getByText('Matter document storage is not ready.')).toBeInTheDocument()
  })
})

describe('PrimaryCloudSelector', () => {
  it('reverts the pending choice on cancel without calling onChange', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<PrimaryCloudSelector value="onedrive" saving={false} saved={false} onChange={onChange} />)
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
