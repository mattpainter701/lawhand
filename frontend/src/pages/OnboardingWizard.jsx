import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../App'
import {
  getOnboardingStatus,
  completeOnboarding,
  confirmOnboardingStorage,
  reenterOnboarding,
  skipOnboarding,
  updateOnboardingStep,
  API_BASE_URL,
} from '../api'
import { AgreementAcceptancePanel } from '../components/CompliancePanel'
import WorkflowSynthesisPanel from '../components/workflows/WorkflowSynthesisPanel'

// Step numbers are shared with backend/app/routers/onboarding.py.
export const STEP = {
  WELCOME: 0,
  CONNECT: 1,
  STORAGE: 2,
  SYNC: 3,
  REVIEW: 4,
  COMPLETE: 5,
}

const STEPS = [
  { id: STEP.WELCOME, label: 'Welcome' },
  { id: STEP.CONNECT, label: 'Connect' },
  { id: STEP.STORAGE, label: 'Storage' },
  { id: STEP.SYNC, label: 'Sync Users' },
  { id: STEP.REVIEW, label: 'Review' },
  { id: STEP.COMPLETE, label: 'Complete' },
]

const STORAGE_OPTIONS = [
  {
    id: 'google_drive',
    label: 'Google Drive',
    credential: 'google',
    detail: 'A "claritylegal-records" folder is created in the connected Google account. Every matter gets its own folder inside it.',
  },
  {
    id: 'onedrive',
    label: 'Microsoft OneDrive',
    credential: 'microsoft',
    detail: 'A "claritylegal-records" folder is created in the connected Microsoft account. Every matter gets its own folder inside it.',
  },
]

// Tenants that completed onboarding before the Storage step existed stored
// step 4 as "complete". Map that to the new final step so a revisit shows
// the completed screen rather than the review screen.
export function normalizeStep(status) {
  if (!status) return STEP.WELCOME
  if (status.onboarding_completed && status.onboarding_step >= STEP.REVIEW) return STEP.COMPLETE
  return status.onboarding_step ?? STEP.WELCOME
}

export default function OnboardingWizard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [step, setStep] = useState(STEP.WELCOME)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [agreementStatus, setAgreementStatus] = useState(null)
  const [storageChoice, setStorageChoice] = useState(null)
  const [storageBusy, setStorageBusy] = useState(false)
  const [storageResult, setStorageResult] = useState(null)
  const [googleAccountMode, setGoogleAccountMode] = useState('workspace')

  useEffect(() => {
    loadStatus()
  }, [])

  useEffect(() => {
    const code = searchParams.get('error')
    if (!code) return
    const messages = {
      account_mode_mismatch: 'The selected Google account type did not match the consented account. Choose Google Workspace or Personal Google and try again.',
      identity_verification_failed: 'Google identity verification failed. No connection was saved; try again or contact LawHand support.',
      token_exchange_failed: 'Google authorization could not be completed. No connection was saved; try again.',
    }
    setError(messages[code] || 'The cloud connection could not be completed. No connection was saved; try again.')
    setSearchParams({}, { replace: true })
  }, [searchParams, setSearchParams])

  const loadStatus = async () => {
    try {
      const data = await getOnboardingStatus()
      setStatus(data)
      setStep(normalizeStep(data))
      return data
    } catch (err) {
      setError('Failed to load onboarding status.')
      return null
    } finally {
      setLoading(false)
    }
  }

  const advanceStep = async (newStep) => {
    setStep(newStep)
    try {
      await updateOnboardingStep(newStep)
    } catch {
      // Non-fatal — progress is persisted optimistically
    }
    await loadStatus()
  }

  const handleConnectMicrosoft = () => {
    window.location.href = `${API_BASE_URL}/integrations/microsoft/connect?intent=admin`
  }

  const handleConnectGoogle = () => {
    window.location.href = `${API_BASE_URL}/integrations/google/connect?intent=admin&account_mode=${googleAccountMode}`
  }

  const handleSyncUsers = async () => {
    setSyncing(true)
    try {
      await advanceStep(STEP.SYNC)
      await loadStatus()
      // After integration connect, the backend auto-syncs.
      // If it already happened, advance to review.
      const msConnected = status?.integrations?.microsoft?.connected
      const googleConnected = status?.integrations?.google?.connected
      if (msConnected || googleConnected) {
        await advanceStep(STEP.REVIEW)
      }
    } catch {
      setError('User sync failed. Try again from the Admin panel later.')
    } finally {
      setSyncing(false)
    }
  }

  const handleConfirmStorage = async (provider) => {
    if (!provider) return
    setStorageBusy(true)
    setError(null)
    setStorageResult(null)
    try {
      const result = await confirmOnboardingStorage(provider)
      setStorageResult(result)
      if (result.status === 'ready') {
        // Refresh the saved root so Continue sees it, but stay on this step:
        // the folder's identity is shown here, not assumed.
        try {
          setStatus(await getOnboardingStatus())
        } catch {
          // The confirmation result already carries the root; keep going.
        }
      }
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to set up document storage.')
    } finally {
      setStorageBusy(false)
    }
  }

  const handleComplete = async () => {
    setCompleting(true)
    try {
      await completeOnboarding()
      navigate('/admin', { replace: true })
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          'Failed to complete onboarding. At least one integration must be connected.'
      )
    } finally {
      setCompleting(false)
    }
  }

  const handleSkip = async () => {
    setCompleting(true)
    try {
      await skipOnboarding()
      navigate('/matters', { replace: true })
    } catch {
      setError('Failed to skip.')
    } finally {
      setCompleting(false)
    }
  }

  const handleRestart = async () => {
    setRestarting(true)
    setError(null)
    try {
      await reenterOnboarding()
      await loadStatus()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to restart setup.')
    } finally {
      setRestarting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-brand-bg">
        <div className="text-center">
          <div className="inline-block w-10 h-10 border-4 border-brand-ink border-t-transparent rounded-full animate-spin mb-4" />
          <p className="text-brand-ink font-sans text-sm font-medium">Loading setup...</p>
        </div>
      </div>
    )
  }

  const msConnected = status?.integrations?.microsoft?.connected
  const googleConnected = status?.integrations?.google?.connected
  const hasIntegration = msConnected || googleConnected
  const agreementsConfigured = agreementStatus?.configured ?? status?.agreements_configured
  const agreementReady = agreementStatus !== null && !agreementStatus.blocking && (agreementsConfigured || !agreementStatus.enforced)
  const syncedUsers = status?.synced_users || {}
  const totalSynced = (syncedUsers.microsoft || 0) + (syncedUsers.google || 0)
  const cloudRoot = status?.cloud_root || {}
  const storageOptions = STORAGE_OPTIONS.filter((option) => status?.integrations?.[option.credential]?.connected)
  const selectedProvider = storageChoice || status?.primary_cloud_provider || storageOptions[0]?.id || null
  const existingRoot = selectedProvider ? cloudRoot[selectedProvider] : null
  const storageReady = Boolean(existingRoot?.id)
  const confirmedRoot = storageResult?.status === 'ready' ? storageResult.root : existingRoot
  const setupDeferred = Boolean(status?.setup_deferred)

  return (
    <div className="min-h-screen bg-brand-bg flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-brand-line bg-brand-surface">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <h1 className="text-brand-ink font-sans text-lg font-bold tracking-tight">
            {user?.tenant_name || 'Firm'} Setup
          </h1>
          <button
            onClick={handleSkip}
            className="text-brand-ink-2 hover:text-brand-ink font-sans text-xs transition-colors"
          >
            Set up later
          </button>
        </div>
      </div>

      {/* Step indicator */}
      <div className="px-6 py-4 border-b border-brand-line bg-white">
        <div className="max-w-3xl mx-auto mb-3 flex items-center justify-between text-[11px] font-sans font-semibold uppercase tracking-wider text-brand-muted">
          <span>Step {Math.min(step, STEPS.length - 1) + 1} of {STEPS.length} · {STEPS[Math.min(step, STEPS.length - 1)].label}</span>
          <span aria-hidden="true">{Math.round((Math.min(step, STEPS.length - 1) / (STEPS.length - 1)) * 100)}%</span>
        </div>
        <div className="max-w-3xl mx-auto mb-4 h-1 rounded-full bg-brand-line overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={STEPS.length - 1} aria-valuenow={Math.min(step, STEPS.length - 1)} aria-label="Setup progress">
          <div className="h-full rounded-full bg-brand-ink transition-all duration-500" style={{ width: `${(Math.min(step, STEPS.length - 1) / (STEPS.length - 1)) * 100}%` }} />
        </div>
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          {STEPS.map((s, i) => (
            <React.Fragment key={s.id}>
              <div className="flex items-center gap-2">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                    step > s.id
                      ? 'bg-brand-ink text-white'
                      : step === s.id
                        ? 'bg-brand-ink text-white ring-2 ring-brand-ink/20'
                        : 'bg-brand-bg-soft text-brand-ink-2 border border-brand-line'
                  }`}
                >
                  {step > s.id ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : (
                    s.id + 1
                  )}
                </div>
                <span
                  className={`text-xs font-medium hidden sm:inline ${
                    step >= s.id ? 'text-brand-ink' : 'text-brand-ink-2'
                  }`}
                >
                  {s.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-3 rounded transition-colors ${
                    step > s.id ? 'bg-brand-ink' : 'bg-brand-line'
                  }`}
                />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Step content */}
      <div className="flex-1 flex items-start justify-center px-6 py-10">
        <div className="max-w-lg w-full animate-in fade-in slide-in-from-bottom-2 duration-300" key={step}>
          {setupDeferred && step === STEP.WELCOME && (
            <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900" role="status">
              Setup is deferred. Your core workspace remains available; no cloud connection or team import has been completed.
            </div>
          )}
          {error && (
            <div className="mb-6 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs font-medium">
              {error}
              <button
                onClick={() => setError(null)}
                className="ml-2 underline hover:no-underline"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Step 0: Welcome */}
          {step === STEP.WELCOME && (
            <div className="bg-brand-surface border border-brand-line rounded-2xl p-8 shadow-sm">
              <div className="text-center mb-8">
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand-ink/5 mb-4">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M9 22V12h6v10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h2 className="text-brand-ink font-sans text-xl font-bold mb-2">
                  Welcome, {user?.full_name || user?.email?.split('@')[0]}
                </h2>
                <p className="text-brand-ink-2 font-sans text-sm leading-relaxed">
                  Let's set up your firm in a few quick steps. Connect your Microsoft 365 or
                  Google Workspace, choose where case documents live, and import your team.
                </p>
              </div>

              <div className="space-y-3 mb-8">
                {[
                  { icon: '🔗', text: 'Connect your firm\'s Microsoft 365 or Google Workspace' },
                  { icon: '📁', text: 'Choose where case documents are stored and confirm the folder' },
                  { icon: '👥', text: 'Import your team from the directory' },
                  { icon: '⚙️', text: 'Configure licenses and permissions' },
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 bg-brand-bg rounded-xl">
                    <span className="text-lg">{item.icon}</span>
                    <span className="text-brand-ink font-sans text-sm">{item.text}</span>
                  </div>
                ))}
              </div>

              <button
                onClick={() => advanceStep(STEP.CONNECT)}
                className="w-full py-3 px-6 bg-brand-ink text-white font-sans text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity shadow-sm"
              >
                Get Started
              </button>
            </div>
          )}

          {/* Step 1: Connect Integrations */}
          {step === STEP.CONNECT && (
            <div className="bg-brand-surface border border-brand-line rounded-2xl p-8 shadow-sm">
              <h2 className="text-brand-ink font-sans text-lg font-bold mb-1">Connect Your Firm</h2>
              <p className="text-brand-ink-2 font-sans text-sm mb-8">
                Connect a supported work account to import users and sync email. A
                Google Workspace administrator is required for directory sync; a
                personal Gmail account does not provide a team directory.
              </p>

              <div className="mb-8 rounded-xl border border-brand-line bg-brand-bg-soft p-4">
                <AgreementAcceptancePanel compact onStatusChange={setAgreementStatus} />
                {agreementStatus && !agreementStatus.configured && agreementStatus.enforced && (
                  <p className="mt-3 text-xs leading-relaxed text-amber-800" role="alert">
                    Cloud connections are paused until the required counsel-owned
                    agreements are published and current. You can use the core
                    workspace and choose Set up later.
                  </p>
                )}
                {agreementStatus && !agreementStatus.configured && !agreementStatus.enforced && (
                  <p className="mt-3 text-xs leading-relaxed text-brand-muted" role="status">
                    No required agreements are published yet. Agreement enforcement
                    is in controlled rollout mode, so you may continue; acceptance
                    has not been recorded.
                  </p>
                )}
              </div>

              <div className="space-y-4 mb-8">
                {/* Microsoft */}
                <div className={`p-5 rounded-xl border transition-colors ${msConnected ? 'border-green-300 bg-green-50' : 'border-brand-line bg-brand-bg'}`}>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-brand-ink font-sans text-sm font-semibold">Microsoft 365</span>
                    {msConnected ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-bold">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
                        Connected
                      </span>
                    ) : (
                      <button
                        onClick={handleConnectMicrosoft}
                        disabled={!agreementReady}
                        className="px-4 py-2 bg-brand-ink text-white font-sans text-xs font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Connect
                      </button>
                    )}
                  </div>
                  <p className="text-brand-ink-2 font-sans text-xs leading-relaxed">
                    Required: Read all users, read mail, read files (OneDrive + SharePoint), read/write calendars.
                  </p>
                </div>

                {/* Google */}
                <div className={`p-5 rounded-xl border transition-colors ${googleConnected ? 'border-green-300 bg-green-50' : 'border-brand-line bg-brand-bg'}`}>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-brand-ink font-sans text-sm font-semibold">Google Workspace</span>
                    {googleConnected ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-bold">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
                        Connected
                      </span>
                    ) : (
                      <button
                        onClick={handleConnectGoogle}
                        disabled={!agreementReady}
                        className="px-4 py-2 bg-brand-ink text-white font-sans text-xs font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Connect {googleAccountMode === 'personal' ? 'Personal Google' : 'Workspace'}
                      </button>
                    )}
                  </div>
                  <p className="text-brand-ink-2 font-sans text-xs leading-relaxed">
                    {googleAccountMode === 'personal'
                      ? 'Personal Google / Google One: connects your Gmail, Drive, and Calendar without directory access. Invite teammates from Admin instead.'
                      : 'Google Workspace: administrator consent enables directory sync, Gmail, Drive, and Calendar.'}
                  </p>
                  {!googleConnected && (
                    <div className="mt-3 flex flex-wrap gap-3 text-xs text-brand-ink-2">
                      <label><input type="radio" name="google-account-mode" checked={googleAccountMode === 'workspace'} onChange={() => setGoogleAccountMode('workspace')} /> <span className="ml-1">Google Workspace administrator</span></label>
                      <label><input type="radio" name="google-account-mode" checked={googleAccountMode === 'personal'} onChange={() => setGoogleAccountMode('personal')} /> <span className="ml-1">Personal Google / Google One</span></label>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => advanceStep(STEP.WELCOME)}
                  className="flex-1 py-2.5 px-4 border border-brand-line text-brand-ink font-sans text-sm font-medium rounded-xl hover:bg-brand-bg-soft transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={() => advanceStep(STEP.STORAGE)}
                  disabled={!hasIntegration || !agreementReady}
                  className="flex-1 py-2.5 px-4 bg-brand-ink text-white font-sans text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Choose Storage
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Storage */}
          {step === STEP.STORAGE && (
            <div className="bg-brand-surface border border-brand-line rounded-2xl p-8 shadow-sm">
              <h2 className="text-brand-ink font-sans text-lg font-bold mb-1">Where Should Documents Live?</h2>
              <p className="text-brand-ink-2 font-sans text-sm mb-6">
                Your connected cloud account is the matter-document system of record.
                Confirm its folder before any matter is created; setup will stop if
                the cloud root cannot be verified.
              </p>

              {storageOptions.length === 0 ? (
                <div className="mb-6 px-4 py-3 rounded-xl border border-amber-200 bg-amber-50 text-amber-800 text-xs font-sans">
                  Connect Microsoft 365 or Google Workspace first. Document storage uses the connected account.
                </div>
              ) : (
                <div className="space-y-3 mb-6" role="radiogroup" aria-label="Document storage provider">
                  {storageOptions.map((option) => {
                    const checked = selectedProvider === option.id
                    const rootForOption = cloudRoot[option.id]
                    return (
                      <label
                        key={option.id}
                        className={`block p-4 rounded-xl border cursor-pointer transition-colors ${checked ? 'border-brand-ink bg-brand-bg' : 'border-brand-line bg-brand-surface hover:border-brand-line-2'}`}
                      >
                        <span className="flex items-center gap-3">
                          <input
                            type="radio"
                            name="storage-provider"
                            value={option.id}
                            checked={checked}
                            disabled={storageBusy}
                            onChange={() => { setStorageChoice(option.id); setStorageResult(null) }}
                          />
                          <span className="text-brand-ink font-sans text-sm font-semibold">{option.label}</span>
                          {rootForOption?.id && (
                            <span className="ml-auto inline-flex items-center px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-[11px] font-bold">Folder exists</span>
                          )}
                        </span>
                        <span className="mt-2 block text-brand-ink-2 font-sans text-xs leading-relaxed pl-7">{option.detail}</span>
                      </label>
                    )
                  })}
                </div>
              )}

              {msConnected && (
                <p className="mb-6 text-[11px] text-brand-muted font-sans">
                  Prefer a SharePoint library? Finish setup with OneDrive, then choose the site and library under Admin → Integrations → Cloud → Document storage.
                </p>
              )}

              {storageResult?.status === 'failed' && (
                <div className="mb-6 px-4 py-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-xs font-sans" role="alert">
                  {storageResult.error}
                </div>
              )}
              {storageResult?.status === 'repair_needed' && (
                <div className="mb-6 px-4 py-3 rounded-xl border border-amber-200 bg-amber-50 text-amber-800 text-xs font-sans" role="alert">
                  {storageResult.error}
                </div>
              )}

              {confirmedRoot?.id && (
                <div className="mb-6 px-4 py-3 rounded-xl border border-green-200 bg-green-50 text-xs font-sans" data-testid="storage-root">
                  <p className="text-green-800 font-semibold">
                    {storageResult?.created ? 'Folder created' : 'Folder confirmed'}: {confirmedRoot.folder_name || 'claritylegal-records'}
                  </p>
                  {confirmedRoot.url && (
                    <a href={confirmedRoot.url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-green-800 underline break-all">
                      Open in {STORAGE_OPTIONS.find((o) => o.id === selectedProvider)?.label || 'provider'}
                    </a>
                  )}
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => advanceStep(STEP.CONNECT)}
                  className="flex-1 py-2.5 px-4 border border-brand-line text-brand-ink font-sans text-sm font-medium rounded-xl hover:bg-brand-bg-soft transition-colors"
                >
                  Back
                </button>
                {storageReady || storageResult?.status === 'ready' ? (
                  <button
                    onClick={() => advanceStep(STEP.SYNC)}
                    className="flex-1 py-2.5 px-4 bg-brand-ink text-white font-sans text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity"
                  >
                    Continue
                  </button>
                ) : (
                  <button
                    onClick={() => handleConfirmStorage(selectedProvider)}
                    disabled={!selectedProvider || storageBusy}
                    className="flex-1 py-2.5 px-4 bg-brand-ink text-white font-sans text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {storageBusy ? 'Creating folder...' : storageResult?.status === 'failed' ? 'Try again' : 'Create folder'}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Step 3: Syncing */}
          {step === STEP.SYNC && (
            <div className="bg-brand-surface border border-brand-line rounded-2xl p-8 shadow-sm text-center">
              <h2 className="text-brand-ink font-sans text-lg font-bold mb-2">{status?.integrations?.google?.account_type === 'personal' ? 'Confirm Personal Google Setup' : 'Import Your Team'}</h2>
              <p className="text-brand-ink-2 font-sans text-sm leading-relaxed mb-6">
                {status?.integrations?.google?.account_type === 'personal'
                  ? 'Personal Google accounts do not have a Workspace directory to import. Gmail, Drive, and Calendar are connected; invite users from the Admin panel if needed.'
                  : syncing
                  ? 'Pulling users from your connected directory. This may take a moment.'
                  : 'LawHand imports users from your connected directory. On personal accounts there is no directory to import; you can invite users from the Admin panel instead.'}
              </p>
              {syncing && (
                <div className="inline-block w-12 h-12 border-4 border-brand-ink border-t-transparent rounded-full animate-spin mb-5" />
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => advanceStep(STEP.STORAGE)}
                  className="flex-1 py-2.5 px-4 border border-brand-line text-brand-ink font-sans text-sm font-medium rounded-xl hover:bg-brand-bg-soft transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={() => handleSyncUsers()}
                  disabled={syncing || !hasIntegration}
                  className="flex-1 py-2.5 px-4 bg-brand-ink text-white font-sans text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {syncing ? 'Syncing...' : status?.integrations?.google?.account_type === 'personal' ? 'Continue' : 'Sync Users'}
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Review */}
          {step === STEP.REVIEW && (
            <div className="bg-brand-surface border border-brand-line rounded-2xl p-8 shadow-sm">
              <h2 className="text-brand-ink font-sans text-lg font-bold mb-1">{status?.integrations?.google?.account_type === 'personal' ? 'Review Google Setup' : 'Review Imported Users'}</h2>
              <WorkflowSynthesisPanel user={user} onboarding />
              <p className="text-brand-ink-2 font-sans text-sm mb-6">
                {status?.integrations?.google?.account_type === 'personal'
                  ? 'No team directory sync was performed for this personal Google account.'
                  : totalSynced > 0
                  ? `${totalSynced} users were imported from your directory.`
                  : 'No users were imported yet. You can sync again from the Admin panel later.'}
              </p>

              <div className="space-y-2 mb-6">
                {msConnected && (
                  <div className="flex items-center justify-between px-4 py-3 bg-brand-bg rounded-xl">
                    <span className="text-brand-ink font-sans text-sm">Microsoft 365 users synced</span>
                    <span className="text-brand-ink font-sans text-sm font-bold">{syncedUsers.microsoft || 0}</span>
                  </div>
                )}
                {googleConnected && (
                  <div className="flex items-center justify-between px-4 py-3 bg-brand-bg rounded-xl">
                    <span className="text-brand-ink font-sans text-sm">Google Workspace users synced</span>
                    <span className="text-brand-ink font-sans text-sm font-bold">{syncedUsers.google || 0}</span>
                  </div>
                )}
                {status?.storage_ready ? (
                  <div className="flex items-center justify-between px-4 py-3 bg-brand-bg rounded-xl">
                    <span className="text-brand-ink font-sans text-sm">Document storage</span>
                    <span className="text-green-700 font-sans text-sm font-bold">Confirmed</span>
                  </div>
                ) : (
                  <div className="flex items-center justify-between px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl">
                    <span className="text-amber-800 font-sans text-sm">Document storage not confirmed</span>
                    <button onClick={() => advanceStep(STEP.STORAGE)} className="text-amber-800 font-sans text-sm font-bold underline">Fix</button>
                  </div>
                )}
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => advanceStep(STEP.SYNC)}
                  className="flex-1 py-2.5 px-4 border border-brand-line text-brand-ink font-sans text-sm font-medium rounded-xl hover:bg-brand-bg-soft transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleComplete}
                  disabled={completing || !status?.storage_ready}
                  className="flex-1 py-2.5 px-4 bg-brand-ink text-white font-sans text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40"
                >
                  {completing ? 'Completing...' : 'Complete Setup'}
                </button>
              </div>
            </div>
          )}

          {/* Step 5: Complete (shown briefly before redirect) */}
          {step === STEP.COMPLETE && (
            <div className="bg-brand-surface border border-brand-line rounded-2xl p-8 shadow-sm text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-100 mb-4">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M5 13l4 4L19 7" stroke="#16a34a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <h2 className="text-brand-ink font-sans text-xl font-bold mb-2">Setup Complete!</h2>
              <p className="text-brand-ink-2 font-sans text-sm leading-relaxed mb-6">
                Your firm is ready. You can manage users, licenses, and integrations
                from the Admin panel.
              </p>
              <div className="flex flex-col items-center gap-3">
                <button
                  onClick={() => navigate('/admin', { replace: true })}
                  className="py-3 px-8 bg-brand-ink text-white font-sans text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity"
                >
                  Go to Admin Panel
                </button>
                <button
                  onClick={handleRestart}
                  disabled={restarting}
                  className="text-sm font-medium text-brand-ink underline disabled:opacity-40"
                >
                  {restarting ? 'Restarting setup...' : 'Restart setup'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
