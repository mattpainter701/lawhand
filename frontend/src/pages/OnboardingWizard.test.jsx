import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import OnboardingWizard, { STEP, normalizeStep } from './OnboardingWizard'
import {
  completeOnboarding,
  confirmOnboardingStorage,
  getOnboardingStatus,
  reenterOnboarding,
  updateOnboardingStep,
} from '../api'

vi.mock('../App', () => ({
  useAuth: () => ({ user: { role: 'admin' } }),
}))

vi.mock('../components/CompliancePanel', async () => {
  const { useEffect } = await import('react')
  return {
    AgreementAcceptancePanel: ({ onStatusChange }) => {
      // Report once after mount; reporting during render would re-render the
      // wizard forever.
      useEffect(() => { onStatusChange?.({ blocking: false, configured: true }) }, [onStatusChange])
      return null
    },
  }
})

vi.mock('../components/workflows/WorkflowSynthesisPanel', () => ({
  default: () => null,
}))

vi.mock('../api', () => ({
  getOnboardingStatus: vi.fn(),
  completeOnboarding: vi.fn(),
  confirmOnboardingStorage: vi.fn(),
  reenterOnboarding: vi.fn(),
  skipOnboarding: vi.fn(),
  updateOnboardingStep: vi.fn(),
  API_BASE_URL: '',
}))

afterEach(cleanup)

const googleConnected = { google: { connected: true }, microsoft: { connected: false } }

function statusAt(step, extra = {}) {
  return {
    onboarding_completed: false,
    onboarding_step: step,
    integrations: googleConnected,
    synced_users: { google: 0, microsoft: 0 },
    total_users: 1,
    primary_cloud_provider: null,
    cloud_root: null,
    storage_ready: false,
    ...extra,
  }
}

describe('OnboardingWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    updateOnboardingStep.mockResolvedValue({ status: 'ok' })
  })

  it('reenters completed setup at step one after the server preserves integrations', async () => {
    getOnboardingStatus
      .mockResolvedValueOnce({ onboarding_completed: true, onboarding_step: STEP.COMPLETE, integrations: googleConnected })
      .mockResolvedValueOnce({ onboarding_completed: true, onboarding_step: STEP.CONNECT, integrations: googleConnected })
    reenterOnboarding.mockResolvedValue({ onboarding_step: STEP.CONNECT })
    const user = userEvent.setup()

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Setup Complete!')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Restart setup' }))

    expect(reenterOnboarding).toHaveBeenCalledOnce()
    expect(await screen.findByText('Connect Your Firm')).toBeInTheDocument()
    expect(getOnboardingStatus).toHaveBeenCalledTimes(2)
  })

  it('surfaces a safe OAuth failure returned by the provider', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.CONNECT))
    render(<MemoryRouter initialEntries={['/onboarding?error=account_mode_mismatch&provider=google']}><OnboardingWizard /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent(/selected Google account type did not match/i)
  })

  it.each([
    [
      '?error=token_exchange_failed&provider=microsoft',
      'Microsoft 365 authorization could not be completed. No connection was saved; try again.',
    ],
    [
      '?error=consent_required&provider=microsoft',
      'Microsoft 365 needs an administrator to approve LawHand before this account can connect. Sign in with an administrator account, or ask your administrator to approve LawHand.',
    ],
    [
      '?error=access_denied&provider=google',
      'The Google sign-in was cancelled, so nothing was connected. Try again when you are ready.',
    ],
    [
      '?error=identity_verification_failed&provider=google',
      'Google identity verification failed. No connection was saved; try again or contact LawHand support.',
    ],
    [
      '?error=something_new',
      'The cloud connection could not be completed. No connection was saved; try again.',
    ],
    [
      '?error=token_exchange_failed&provider=%3Cb%3Eevil%3C%2Fb%3E',
      'The cloud provider authorization could not be completed. No connection was saved; try again.',
    ],
  ])('names the provider in the OAuth failure for %s', async (query, message) => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.CONNECT))
    render(<MemoryRouter initialEntries={[`/onboarding${query}`]}><OnboardingWizard /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByText(/evil/)).not.toBeInTheDocument()
  })

  it('shows no OAuth error when the callback returned none', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.CONNECT))
    render(<MemoryRouter initialEntries={['/onboarding?provider=microsoft']}><OnboardingWizard /></MemoryRouter>)
    expect(await screen.findByText('Connect Your Firm')).toBeInTheDocument()
    expect(screen.queryByText(/could not be completed/)).not.toBeInTheDocument()
  })

  it('treats a tenant completed before the storage step existed as complete', () => {
    expect(normalizeStep({ onboarding_completed: true, onboarding_step: 4 })).toBe(STEP.COMPLETE)
    expect(normalizeStep({ onboarding_completed: true, onboarding_step: 5 })).toBe(STEP.COMPLETE)
    expect(normalizeStep({ onboarding_completed: true, onboarding_step: 1 })).toBe(STEP.CONNECT)
    expect(normalizeStep({ onboarding_completed: true, onboarding_step: 4, setup_reentry_active: true })).toBe(STEP.REVIEW)
    expect(normalizeStep({ onboarding_completed: false, onboarding_step: 4 })).toBe(STEP.REVIEW)
  })

  it('shows the storage step between connect and sync and lists only connected providers', async () => {
    getOnboardingStatus
      .mockResolvedValueOnce(statusAt(STEP.CONNECT))
      .mockResolvedValue(statusAt(STEP.STORAGE))
    const user = userEvent.setup()

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Connect Your Firm')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Choose Storage' }))
    expect(updateOnboardingStep).toHaveBeenCalledWith(STEP.STORAGE)
    expect(await screen.findByText('Where Should Documents Live?')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Google Drive/ })).toBeChecked()
    expect(screen.queryByRole('radio', { name: /OneDrive/ })).toBeNull()
    expect(screen.getByText(/A "lawhand-records" folder is created/)).toBeInTheDocument()
    expect(screen.queryByText(/claritylegal-records/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create folder' })).toBeEnabled()
  })

  it('warns when the bound storage root is tied to one person', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.STORAGE, {
      cloud_root: { google_drive: { id: 'root-1', folder_name: 'lawhand-records' } },
      storage_ready: true,
      root_ownership: {
        status: 'at_risk',
        org_owned: false,
        at_risk_providers: ['Google Drive'],
        providers: {},
      },
    }))

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Where Should Documents Live?')).toBeInTheDocument()
    const callout = screen.getByTestId('root-ownership')
    expect(callout).toHaveTextContent(/tied to one person's account/i)
    expect(callout).toHaveTextContent(/Google Drive live in a personal drive/i)
  })

  it('confirms organisation-owned storage', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.STORAGE, {
      cloud_root: { google_drive: { id: 'root-1', folder_name: 'lawhand-records' } },
      storage_ready: true,
      root_ownership: { status: 'durable', org_owned: true, at_risk_providers: [], providers: {} },
    }))

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Where Should Documents Live?')).toBeInTheDocument()
    expect(screen.getByTestId('root-ownership')).toHaveTextContent(/Organisation-owned storage/i)
  })

  it('creates the root folder, shows where it is, and only then allows continuing', async () => {
    getOnboardingStatus
      .mockResolvedValueOnce(statusAt(STEP.STORAGE))
      .mockResolvedValue(statusAt(STEP.SYNC, {
        primary_cloud_provider: 'google_drive',
        cloud_root: { google_drive: { id: 'root-1', folder_name: 'lawhand-records', url: 'https://drive.google.com/x' } },
        storage_ready: true,
      }))
    confirmOnboardingStorage.mockResolvedValue({
      status: 'ready',
      provider: 'google_drive',
      created: true,
      root: { id: 'root-1', folder_name: 'lawhand-records', url: 'https://drive.google.com/x' },
    })
    const user = userEvent.setup()

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Where Should Documents Live?')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Create folder' }))
    expect(confirmOnboardingStorage).toHaveBeenCalledWith('google_drive')
    expect(await screen.findByText('Folder created: lawhand-records')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open in Google Drive' })).toHaveAttribute('href', 'https://drive.google.com/x')

    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(updateOnboardingStep).toHaveBeenCalledWith(STEP.SYNC)
    expect(await screen.findByText('Import Your Team')).toBeInTheDocument()
  })

  it('reports a failed folder creation and offers to try again', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.STORAGE))
    confirmOnboardingStorage.mockResolvedValue({ status: 'failed', provider: 'google_drive', error: 'LawHand could not create the root folder in Google Drive.' })
    const user = userEvent.setup()

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)
    await screen.findByText('Where Should Documents Live?')

    await user.click(screen.getByRole('button', { name: 'Create folder' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('could not create the root folder')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()
  })

  it('keeps an existing folder on re-entry instead of creating it again', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.STORAGE, {
      onboarding_completed: true,
      primary_cloud_provider: 'google_drive',
      cloud_root: { google_drive: { id: 'root-1', folder_name: 'lawhand-records', url: 'https://drive.google.com/x' } },
      storage_ready: true,
    }))

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Folder confirmed: lawhand-records')).toBeInTheDocument()
    expect(screen.getByText('Folder exists')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create folder' })).toBeNull()
    expect(confirmOnboardingStorage).not.toHaveBeenCalled()
  })

  it('blocks completion until storage is confirmed and surfaces the server reason', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.REVIEW))

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Review Imported Users')).toBeInTheDocument()
    expect(screen.getByText('Document storage not confirmed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Complete Setup' })).toBeDisabled()
    expect(completeOnboarding).not.toHaveBeenCalled()
  })

  it('completes once storage is confirmed', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.REVIEW, {
      storage_ready: true,
      cloud_root: { google_drive: { id: 'root-1' } },
    }))
    completeOnboarding.mockResolvedValue({ status: 'ok' })
    const user = userEvent.setup()

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    await screen.findByText('Review Imported Users')
    expect(screen.getByText('Confirmed')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Complete Setup' }))
    expect(completeOnboarding).toHaveBeenCalledOnce()
  })

  it('describes a personal Google connection without claiming a Workspace directory sync', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.REVIEW, {
      integrations: {
        google: { connected: true, account_type: 'personal' },
        microsoft: { connected: false },
      },
      synced_users: { google: 1, microsoft: 0 },
      storage_ready: true,
      cloud_root: { google_drive: { id: 'root-1' } },
    }))

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Review Google Setup')).toBeInTheDocument()
    expect(screen.getByText('Personal Google account')).toBeInTheDocument()
    expect(screen.getByText('Connected')).toBeInTheDocument()
    expect(screen.queryByText('Google Workspace users synced')).toBeNull()
  })

  it('labels an existing personal Google connection correctly on the connect step', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.CONNECT, {
      integrations: {
        google: { connected: true, account_type: 'personal' },
        microsoft: { connected: false },
      },
    }))

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    expect(await screen.findByText('Personal Google / Google One')).toBeInTheDocument()
    expect(screen.getByText(/connects your Gmail, Drive, and Calendar without directory access/i)).toBeInTheDocument()
    expect(screen.queryByText(/^Google Workspace$/)).toBeNull()
  })

  it('lists send and file-write access before an administrator connects (D81)', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.CONNECT, {
      integrations: { google: { connected: false }, microsoft: { connected: false } },
    }))

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    const microsoft = await screen.findByRole('list', { name: 'Microsoft 365 permissions' })
    const msItems = within(microsoft).getAllByRole('listitem').map((item) => item.textContent)
    expect(msItems).toEqual([
      'Read staff profiles in your organization (for user sync)',
      "Read mail in the connected account's mailbox",
      'Send email as the connected account',
      'Read and write every file the connected account can open (OneDrive + SharePoint)',
      'Read every SharePoint site the connected account can open',
      "Read and write the connected account's calendars",
    ])
    // The old copy said "read mail, read files" and never mentioned sending.
    expect(screen.queryByText(/read mail, read files/i)).toBeNull()

    const google = screen.getByRole('list', { name: 'Google permissions' })
    const googleItems = within(google).getAllByRole('listitem').map((item) => item.textContent)
    expect(googleItems).toContain('Send email as the connected account')
    expect(googleItems).toContain('Read your Workspace user directory (for user sync)')
    expect(googleItems).toContain('Read and write every Google Drive file the connected account can open')
  })

  it('drops the directory permission from the personal Google list', async () => {
    getOnboardingStatus.mockResolvedValue(statusAt(STEP.CONNECT, {
      integrations: { google: { connected: false }, microsoft: { connected: false } },
    }))
    const user = userEvent.setup()

    render(<MemoryRouter><OnboardingWizard /></MemoryRouter>)

    await user.click(await screen.findByLabelText('Personal Google / Google One'))

    const google = screen.getByRole('list', { name: 'Google permissions' })
    const googleItems = within(google).getAllByRole('listitem').map((item) => item.textContent)
    expect(googleItems).toContain('Send email as the connected account')
    expect(googleItems).not.toContain('Read your Workspace user directory (for user sync)')
  })
})
