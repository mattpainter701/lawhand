import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CloudRetryStatus, ProviderCard } from './IntegrationsPanel'

vi.mock('../api', () => ({
  getAdminPermissions: vi.fn(),
  triggerUserSync: vi.fn(),
  retryCloudInit: vi.fn(),
  getAdminSettings: vi.fn(),
  updateAdminSettings: vi.fn(),
  triggerCloudSync: vi.fn(),
  getIntegrationReadiness: vi.fn(),
  getSharePointBinding: vi.fn(),
  listSharePointSites: vi.fn(),
  listSharePointDrives: vi.fn(),
  saveSharePointBinding: vi.fn(),
  uploadTabs3ImportBundle: vi.fn(),
  getExternalImportTables: vi.fn(),
  reconcileExternalImport: vi.fn(),
  API_BASE_URL: '',
}))

const baseInfo = {
  connected: true,
  health: 'healthy',
  account_label: 'Personal Google (Gmail)',
  account_type: 'personal',
  last_sync_status: 'not_applicable',
  last_sync_error: "Directory sync isn't available on personal Google accounts",
  last_sync_at: null,
  last_refresh_at: null,
  required_scopes: [],
  missing_required: [],
  granted_scopes: [],
  capabilities: {
    directory_sync: { available: false, status: 'unavailable', reason: 'personal account' },
    cloud_storage: { available: true, status: 'ok', reason: 'available' },
  },
}

const props = {
  name: 'Google Workspace',
  provider: 'google',
  scopeLabels: {},
  onReauthorize: vi.fn(),
  relTime: () => 'never',
  onSyncNow: vi.fn(),
  syncing: false,
}

describe('ProviderCard tier status', () => {
  afterEach(cleanup)
  it('shows a neutral not-applicable state for personal accounts', () => {
    render(<ProviderCard {...props} info={baseInfo} />)
    expect(screen.getByText('Personal Google (Gmail)')).toBeTruthy()
    expect(screen.getByText(/directory sync unavailable for this account/)).toBeTruthy()
    expect(screen.getByText('Unavailable for this account')).toBeTruthy()
    expect(screen.getByText(/Directory sync imports organization users. Its availability is separate from document storage/)).toBeTruthy()
    expect(screen.getByText('Cloud file storage').parentElement).toHaveTextContent('Available')
    expect(screen.queryByText(baseInfo.last_sync_error)).toBeNull()
  })

  it.each(['unknown', null])('keeps unknown Microsoft tier (%s) separate from available file storage', (accountType) => {
    const unknownTierInfo = {
      ...baseInfo,
      account_label: 'Microsoft (tier unknown)',
      account_type: accountType,
      last_sync_error: null,
      capabilities: {
        directory_sync: {
          available: false,
          status: 'unavailable',
          reason: 'Account tier not yet detected — reconnect to confirm directory access.',
        },
        cloud_storage: { available: true, status: 'ok', reason: 'Cloud file storage is available.' },
        teams: {
          available: false,
          status: 'unavailable',
          reason: 'Account tier not yet detected — reconnect to confirm Teams access.',
        },
      },
    }

    render(<ProviderCard {...props} name="Microsoft 365" provider="microsoft" info={unknownTierInfo} />)

    expect(screen.getAllByText('Microsoft (tier unknown)')).toHaveLength(1)
    expect(screen.getByText(/directory access not confirmed/)).toBeTruthy()
    expect(screen.getAllByText('Directory / user sync').at(-1).parentElement).toHaveTextContent('Not confirmed')
    expect(screen.getByText('Microsoft Teams').parentElement).toHaveTextContent('Not confirmed')
    expect(screen.getAllByText('Cloud file storage').at(-1).parentElement).toHaveTextContent('Available')
  })

  it('shows genuine sync errors when status is failed', () => {
    render(<ProviderCard {...props} info={{ ...baseInfo, last_sync_status: 'failed' }} />)
    expect(screen.getByText(baseInfo.last_sync_error)).toBeTruthy()
    expect(screen.getByText(/last sync failed/)).toBeTruthy()
  })
})

describe('CloudRetryStatus', () => {
  it('reports a partial retry instead of claiming every matter is ready', () => {
    render(<CloudRetryStatus result={{ matters_initialized: 2, matters_failed: 1, status: 'partial' }} />)
    expect(screen.getByText(/partially ready/)).toBeTruthy()
    expect(screen.getByText(/2 matters set up/)).toBeTruthy()
    expect(screen.getByText(/1 needs retry/)).toBeTruthy()
  })

  it('reports a fully successful retry', () => {
    render(<CloudRetryStatus result={{ matters_initialized: 1, matters_failed: 0, status: 'ready' }} />)
    expect(screen.getByText('Cloud folders ready · 1 matter set up')).toBeTruthy()
  })
})
