import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
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

  it('treats a tenant completed before the storage step existed as complete', () => {
    expect(normalizeStep({ onboarding_completed: true, onboarding_step: 4 })).toBe(STEP.COMPLETE)
    expect(normalizeStep({ onboarding_completed: true, onboarding_step: 5 })).toBe(STEP.COMPLETE)
    expect(normalizeStep({ onboarding_completed: true, onboarding_step: 1 })).toBe(STEP.CONNECT)
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
})
