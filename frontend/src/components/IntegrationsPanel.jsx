import { useEffect, useState } from 'react'
import {
  API_BASE_URL,
  disconnectCloudProvider,
  getAdminPermissions,
  triggerUserSync,
  retryCloudInit,
  getAdminSettings,
  updateAdminSettings,
  triggerCloudSync,
  getSharePointBinding,
  listSharePointSites,
  listSharePointDrives,
  saveSharePointBinding,
} from '../api'
import { useConfirm } from './dialog/ConfirmProvider'
import { Disclosure } from './ui'
import { oauthErrorMessage, oauthProviderLabel } from '../utils/oauthErrors'
import { deriveStorageReadiness, STORAGE_PROVIDER_LABELS } from './storageReadiness'

// Firm connections are delegated grants: every call acts as the account that
// connected, so the labels say "the connected account" rather than implying
// organization-wide mailbox access.
const SCOPE_LABELS_MS = {
  offline_access: 'Stay connected without signing in again',
  'User.Read.All': 'Read staff profiles in your organization (for user sync)',
  'Mail.Read': "Read mail in the connected account's mailbox",
  'Mail.Send': 'Send email as the connected account',
  'Files.Read.All': 'Read every file the connected account can open (OneDrive + SharePoint)',
  'Files.ReadWrite.All': 'Read and write every file the connected account can open (OneDrive + SharePoint)',
  'Sites.Read.All': 'Read every SharePoint site the connected account can open',
  'Calendars.ReadWrite': "Read and write the connected account's calendars",
  openid: 'Confirm who signed in',
  email: 'Email address',
  profile: 'Profile info',
}

const SCOPE_LABELS_GOOGLE = {
  'openid': 'Confirm who signed in',
  'email': 'Email address',
  'profile': 'Profile info',
  'https://www.googleapis.com/auth/userinfo.email': 'Email address',
  'https://www.googleapis.com/auth/userinfo.profile': 'Profile info',
  'https://www.googleapis.com/auth/admin.directory.user.readonly': 'Read your Workspace user directory (for user sync)',
  'https://www.googleapis.com/auth/gmail.readonly': "Read mail in the connected account's Gmail",
  'https://www.googleapis.com/auth/gmail.send': 'Send email as the connected account',
  'https://www.googleapis.com/auth/drive.readonly': 'Read every Google Drive file the connected account can open',
  'https://www.googleapis.com/auth/drive': 'Read and write every Google Drive file the connected account can open',
  'https://www.googleapis.com/auth/calendar': "Read and write the connected account's Google Calendars",
}

// Sign-in plumbing scopes are listed for support but are not a feature a
// firm administrator needs to weigh before connecting.
const PLUMBING_SCOPES = new Set([
  'openid',
  'email',
  'profile',
  'offline_access',
  'https://www.googleapis.com/auth/userinfo.email',
  'https://www.googleapis.com/auth/userinfo.profile',
])

// The capability matrix reports mail, calendar and storage as available from
// the account tier alone; a scope the administrator declined still disables
// the feature, so the card downgrades it from the audited missing list.
const SCOPE_CAPABILITY = {
  'User.Read.All': 'directory_sync',
  'Mail.Read': 'email',
  'Mail.Send': 'email',
  'Files.ReadWrite.All': 'cloud_storage',
  'Sites.Read.All': 'cloud_storage',
  'Calendars.ReadWrite': 'calendar',
  'https://www.googleapis.com/auth/admin.directory.user.readonly': 'directory_sync',
  'https://www.googleapis.com/auth/gmail.readonly': 'email',
  'https://www.googleapis.com/auth/gmail.send': 'email',
  'https://www.googleapis.com/auth/drive': 'cloud_storage',
  'https://www.googleapis.com/auth/calendar': 'calendar',
}

const JOB_LABELS = {
  'user-sync': 'Directory sync',
  'cloud-sync': 'File & email index',
  'correspondence-capture': 'Email filing',
}

export function syncJobLabel(jobType) {
  const key = String(jobType || '').replace(/_/g, '-')
  if (JOB_LABELS[key]) return JOB_LABELS[key]
  const words = key.replace(/-/g, ' ').trim()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : 'Sync'
}

// Plain-language first line for a provider error; the raw text stays one
// click away for support.
export function describeProviderError(raw) {
  const text = String(raw || '')
  if (/invalid_grant|revoked|expired/i.test(text)) {
    return 'The provider no longer accepts the saved sign-in (it was revoked, expired, or blocked by an admin policy). Re-authorize to fix it.'
  }
  if (/\b(429|5\d\d)\b|timeout|timed out|temporar/i.test(text)) {
    return 'The provider did not respond. LawHand retries automatically.'
  }
  if (/\b(401|403)\b|access.?denied|forbidden/i.test(text)) {
    return 'The provider refused access. Re-authorize and approve every requested permission.'
  }
  return 'The provider returned an error.'
}

const CONNECT_WHO = {
  microsoft: 'Sign in with an administrator account for your Microsoft 365 organization. Microsoft shows its own consent screen before anything is shared.',
  google: 'Sign in with a Google Workspace administrator account, or with your Gmail account for a solo practice. Google shows its own consent screen before anything is shared.',
}

const CAPABILITY_LABELS = {
  directory_sync: 'Directory / user sync',
  cloud_storage: 'Cloud file storage',
  email: 'Email',
  calendar: 'Calendar',
  teams: 'Microsoft Teams',
}
const CAP_BADGE = {
  ok: { text: 'Available', cls: 'bg-green-100 text-green-700' },
  needs_reauth: { text: 'Reconnect needed', cls: 'bg-amber-100 text-amber-700' },
  error: { text: 'Error', cls: 'bg-red-100 text-red-700' },
  unavailable: { text: 'Not on this tier', cls: 'bg-gray-100 text-gray-500' },
}

// The backend emits an explicit unknown/null account type before it can
// confirm these account-dependent features. Missing legacy fields stay unchanged.
const isCapabilityUnconfirmed = (info, key, capability) =>
  ['directory_sync', 'teams'].includes(key) &&
  capability?.status === 'unavailable' &&
  Object.prototype.hasOwnProperty.call(info, 'account_type') &&
  (info.account_type === 'unknown' || info.account_type === null)

export const PRIMARY_CLOUD_LABELS = STORAGE_PROVIDER_LABELS

// A credential in one of these states cannot be used, whatever its stored
// scope string says. The card leads with the remedy and hides the scope
// tally, which describes what was once consented, not whether it works now.
const UNUSABLE_HEALTH = new Set(['revoked', 'refresh_failed'])

export function relTime(iso, now = Date.now()) {
  if (!iso) return 'never'
  const diffMs = now - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// The connect callback lands here with ?connected=<provider> or
// ?error=<code>&provider=<provider>; say what happened next to the card.
export function readConnectReturn(search = globalThis.window?.location?.search) {
  const params = new URLSearchParams(search || '')
  const error = params.get('error')
  const provider = error ? params.get('provider') : params.get('connected')
  if (!['microsoft', 'google'].includes(provider)) return null
  if (error) return { tone: 'error', text: oauthErrorMessage(error, provider) }
  return { tone: 'ok', text: `${oauthProviderLabel(provider)} connected. Check the card below: anything that was not granted is listed there.` }
}

export default function IntegrationsPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryResult, setRetryResult] = useState(null)
  const [primaryCloud, setPrimaryCloud] = useState(null)
  const [cloudSaving, setCloudSaving] = useState(false)
  const [cloudSaved, setCloudSaved] = useState(false)
  const [contentSyncing, setContentSyncing] = useState(false)
  const [contentSyncResult, setContentSyncResult] = useState(null)
  const [sharePointBinding, setSharePointBinding] = useState(null)
  const [sharePointFlash, setSharePointFlash] = useState(null)
  const [disconnecting, setDisconnecting] = useState(null)
  const [returnNotice, setReturnNotice] = useState(() => readConnectReturn())
  const confirmAction = useConfirm()

  const handleRetryCloudInit = async () => {
    setRetrying(true)
    setRetryResult(null)
    try {
      const result = await retryCloudInit()
      setRetryResult(result)
    } catch {
      setRetryResult({ error: 'Cloud setup failed. Check that Google or Microsoft is connected.' })
    } finally {
      setRetrying(false)
    }
  }

  const handleSyncNow = async () => {
    setSyncing(true)
    try {
      await triggerUserSync()
      setTimeout(() => {
        getAdminPermissions().then(setData).catch(() => {})
        setSyncing(false)
      }, 4000)
    } catch {
      setError('Failed to trigger sync.')
      setSyncing(false)
    }
  }

  const handlePrimaryCloudChange = async (value) => {
    const previous = primaryCloud
    const next = value === '' ? null : value
    setPrimaryCloud(next)
    setCloudSaving(true)
    setCloudSaved(false)
    try {
      await updateAdminSettings({ primary_cloud_provider: next })
      setCloudSaved(true)
    } catch {
      setPrimaryCloud(previous)
      setError('Failed to save primary cloud provider.')
    } finally {
      setCloudSaving(false)
    }
  }

  useEffect(() => {
    Promise.all([
      getAdminPermissions(),
      getAdminSettings(),
      getSharePointBinding().catch(() => ({ binding: null })),
    ])
      .then(([perms, settings, bindingData]) => {
        setData(perms)
        setPrimaryCloud(settings.primary_cloud_provider ?? null)
        setSharePointBinding(bindingData?.binding || null)
      })
      .catch(() => setError('Failed to load permissions.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex justify-center py-12" role="status" aria-label="Loading integrations">
        <div className="w-8 h-8 border-4 border-brand-ink border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!data) {
    return error ? (
      <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs font-medium">{error}</div>
    ) : null
  }

  const handleReauthorize = (provider, { accountMode } = {}) => {
    const intent = 'admin'
    if (provider === 'microsoft') {
      window.location.href = `${API_BASE_URL}/integrations/microsoft/connect?intent=${intent}&return_to=integrations`
      return
    }
    // The connect endpoint defaults to Workspace and rejects a personal Gmail
    // consent made in that mode, so a personal tenant must say so on re-authorize.
    const mode = accountMode || (data.google?.account_type === 'personal' ? 'personal' : null)
    window.location.href = `${API_BASE_URL}/integrations/google/connect?intent=${intent}&return_to=integrations${mode ? `&account_mode=${mode}` : ''}`
  }

  const handleDisconnect = async (provider) => {
    const label = provider === 'google' ? 'Google' : 'Microsoft 365'
    const storage = provider === 'google' ? 'Google Drive' : 'OneDrive or SharePoint'
    const confirmed = await confirmAction({
      title: `Disconnect ${label}?`,
      message: `LawHand stops using ${label} for the whole firm. Saving matter documents to ${storage}, email filing, sending from connected mailboxes and calendar updates stop working until someone reconnects, and every staff member's personal ${label} connection is removed too. Files already in ${storage} stay where they are.`,
      confirmLabel: `Disconnect ${label}`,
      destructive: true,
    })
    if (!confirmed) return
    setDisconnecting(provider)
    setError(null)
    try {
      await disconnectCloudProvider(provider)
      setData(await getAdminPermissions())
    } catch {
      setError(`Failed to disconnect ${label}. Reload this page to check its status, then try again.`)
    } finally {
      setDisconnecting(null)
    }
  }

  const providerName = (provider, info) => {
    if (provider === 'google') return info?.account_type === 'personal' ? 'Google (personal Gmail)' : 'Google Workspace'
    return info?.account_type === 'consumer' ? 'Microsoft (personal account)' : 'Microsoft 365'
  }

  const handleContentSync = async () => {
    setContentSyncing(true)
    setContentSyncResult(null)
    try {
      const result = await triggerCloudSync()
      setContentSyncResult(result)
    } catch {
      setContentSyncResult({ error: 'Cloud file/email sync failed.' })
    } finally {
      setContentSyncing(false)
    }
  }

  const overallColors = {
    healthy: 'bg-green-100 text-green-700 border-green-200',
    attention_needed: 'bg-amber-100 text-amber-700 border-amber-200',
    // Nothing connected yet is a starting point, not a failure.
    disconnected: 'bg-gray-100 text-gray-600 border-gray-200',
  }
  const storageReadiness = deriveStorageReadiness({
    primaryCloud,
    microsoft: data.microsoft,
    google: data.google,
    sharePointBinding,
  })
  const anyConnected = Boolean(data.microsoft?.connected || data.google?.connected)
  const storageSummary = storageReadiness.ready
    ? (primaryCloud
      ? `Connection available: ${storageReadiness.label} · matter folder access is checked when saving`
      : `Automatic provider: ${storageReadiness.label} · connection available; matter folder access is checked when saving`)
    : storageReadiness.reason
  const storageTone = storageReadiness.ready ? 'ok' : storageReadiness.status === 'not_connected' ? 'off' : 'warn'

  return (
    <div className="space-y-6">
      {error && (
        <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs font-medium">{error}</div>
      )}

      {returnNotice && (
        <div
          role={returnNotice.tone === 'error' ? 'alert' : 'status'}
          data-testid="connect-return"
          className={`flex items-start justify-between gap-3 px-4 py-3 rounded-xl border text-xs font-medium ${
            returnNotice.tone === 'error' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-green-50 border-green-200 text-green-800'
          }`}
        >
          <span>{returnNotice.text}</span>
          <button type="button" onClick={() => setReturnNotice(null)} className="shrink-0 font-bold" aria-label="Dismiss">×</button>
        </div>
      )}

      {/* Overall status — the one line an administrator needs first */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl border text-sm font-bold ${overallColors[data.overall_health] || overallColors.disconnected}`}>
          <span className={`w-2 h-2 rounded-full ${
            data.overall_health === 'healthy' ? 'bg-green-500' :
            data.overall_health === 'attention_needed' ? 'bg-amber-500' : 'bg-gray-400'
          }`} aria-hidden="true" />
          Integrations: {data.overall_health === 'healthy' ? 'Healthy' :
            data.overall_health === 'attention_needed' ? 'Needs Attention' : 'No integrations connected'}
        </div>

        {anyConnected && (
          <div className="flex items-center gap-3 flex-wrap justify-end">
            {contentSyncResult && !contentSyncResult.error && (
              <span className="text-xs text-green-700 font-medium">
                Synced {contentSyncResult.total ?? 0} cloud item{contentSyncResult.total === 1 ? '' : 's'}
              </span>
            )}
            {contentSyncResult?.error && (
              <span className="text-xs text-red-600 font-medium">{contentSyncResult.error}</span>
            )}
            <button
              onClick={handleContentSync}
              disabled={contentSyncing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-brand-line text-brand-ink font-sans text-xs font-medium rounded-lg hover:bg-brand-bg-soft transition-colors disabled:opacity-50"
            >
              {contentSyncing ? (
                <>
                  <span className="w-3 h-3 border-2 border-brand-ink border-t-transparent rounded-full animate-spin" />
                  Syncing…
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M21 12a9 9 0 11-2.64-6.36M21 3v6h-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Sync files + email
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Provider cards come first: they answer "is this working?" */}
      <ProviderCard
        name={providerName('microsoft', data.microsoft)}
        provider="microsoft"
        info={data.microsoft}
        scopeLabels={SCOPE_LABELS_MS}
        onReauthorize={handleReauthorize}
        onDisconnect={handleDisconnect}
        disconnecting={disconnecting === 'microsoft'}
        otherConnected={Boolean(data.google?.connected)}
        relTime={relTime}
        onSyncNow={handleSyncNow}
        syncing={syncing}
      />
      <ProviderCard
        name={providerName('google', data.google)}
        provider="google"
        info={data.google}
        scopeLabels={SCOPE_LABELS_GOOGLE}
        onReauthorize={handleReauthorize}
        onDisconnect={handleDisconnect}
        disconnecting={disconnecting === 'google'}
        otherConnected={Boolean(data.microsoft?.connected)}
        onConnectPersonal={() => handleReauthorize('google', { accountMode: 'personal' })}
        relTime={relTime}
        onSyncNow={handleSyncNow}
        syncing={syncing}
      />

      {/* Storage settings are rarely changed and dangerous to change casually;
          they open on their own only when a connected firm cannot save yet. */}
      <Disclosure
        title="Document storage"
        summary={storageSummary}
        tone={storageTone}
        defaultOpen={anyConnected && !storageReadiness.ready}
        testId="document-storage"
      >
        <div className="space-y-6">
          {!storageReadiness.ready && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 font-sans" aria-live="polite">
              <p className="font-semibold">Matter document storage is not ready.</p>
              <p className="mt-1">{storageReadiness.reason}</p>
            </div>
          )}
          <PrimaryCloudSelector
            value={primaryCloud}
            saving={cloudSaving}
            saved={cloudSaved}
            onChange={handlePrimaryCloudChange}
          />

          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={handleRetryCloudInit}
              disabled={retrying || !storageReadiness.ready}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-brand-line text-brand-ink font-sans text-xs font-medium rounded-lg hover:bg-brand-bg-soft transition-colors disabled:opacity-50"
            >
              {retrying ? (
                <>
                  <span className="w-3 h-3 border-2 border-brand-ink border-t-transparent rounded-full animate-spin" />
                  Setting up…
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M4 12a8 8 0 018-8V2L14 4l-2 2V4a6 6 0 100 12h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Create missing matter folders
                </>
              )}
            </button>
            <CloudRetryStatus result={retryResult} />
            {retryResult?.error && (
              <span className="text-xs text-red-600 font-medium">{retryResult.error}</span>
            )}
            <span className="text-[11px] text-brand-muted font-sans">
              Safe to run again: existing folders are detected and reused.
            </span>
          </div>

          {data.microsoft?.connected && (
            <SharePointBindingCard
              binding={sharePointBinding}
              onSaved={(binding) => {
                setSharePointBinding(binding)
                setPrimaryCloud(binding?.is_primary ? 'sharepoint' : primaryCloud)
                setSharePointFlash('SharePoint binding saved.')
              }}
              flash={sharePointFlash}
              onFlashClear={() => setSharePointFlash(null)}
            />
          )}
        </div>
      </Disclosure>
    </div>
  )
}

/**
 * Changing the primary provider repoints where every new matter document is
 * written. Cloud-bound writes fail rather than fall back to LawHand storage,
 * so this asks for an explicit confirmation instead of saving on change.
 */
export function PrimaryCloudSelector({ value, saving, saved, onChange }) {
  const [pending, setPending] = useState(null)
  const current = value ?? ''

  return (
    <div>
      <h3 className="text-brand-ink font-sans text-sm font-bold mb-1">Primary provider for matter documents</h3>
      <p className="text-brand-ink-2 font-sans text-xs mb-3">
        Customer-owned storage for matter files. Changing this repoints new writes; existing folders are not moved.
        {' '}Saving this preference does not verify an individual matter folder; access is checked when saving a document.
        Use Storage migration under Advanced to rebind existing matters.
      </p>
      <div className="flex items-center gap-3 flex-wrap">
        <select
          aria-label="Primary cloud provider"
          value={pending ?? current}
          onChange={(e) => setPending(e.target.value === current ? null : e.target.value)}
          disabled={saving}
          className="flex-1 max-w-xs px-3 py-2 bg-brand-bg border border-brand-line rounded-lg text-brand-ink font-sans text-sm disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-brand-ink/20"
        >
          <option value="">Auto (Microsoft 365 → OneDrive, otherwise Google Drive)</option>
          <option value="onedrive">Microsoft OneDrive</option>
          <option value="sharepoint">Microsoft SharePoint</option>
          <option value="google_drive">Google Drive</option>
        </select>
        {saving && (
          <span className="w-4 h-4 border-2 border-brand-ink border-t-transparent rounded-full animate-spin" />
        )}
        {!saving && saved && pending === null && (
          <span className="text-xs text-green-700 font-medium">Preference saved</span>
        )}
      </div>
      {pending !== null && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800 font-sans">
          <p className="font-semibold">
            Switch new matter documents to {pending ? PRIMARY_CLOUD_LABELS[pending] : 'automatic selection'}?
          </p>
          <p className="mt-1">Existing matter folders stay where they are. If the new provider is not connected, document writes will fail until it is.</p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => { const next = pending; setPending(null); onChange(next) }}
              className="px-3 py-1.5 bg-brand-ink text-white rounded-lg text-xs font-bold"
            >
              Confirm change
            </button>
            <button
              type="button"
              onClick={() => setPending(null)}
              className="px-3 py-1.5 border border-brand-line rounded-lg text-xs font-medium text-brand-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function SharePointBindingCard({ binding, onSaved, flash, onFlashClear }) {
  const [query, setQuery] = useState('')
  const [sites, setSites] = useState([])
  const [drives, setDrives] = useState([])
  const [siteId, setSiteId] = useState(binding?.site_id || '')
  const [siteWebUrl, setSiteWebUrl] = useState(binding?.site_web_url || '')
  const [driveId, setDriveId] = useState(binding?.drive_id || '')
  const [driveName, setDriveName] = useState(binding?.drive_name || '')
  const [loadingSites, setLoadingSites] = useState(false)
  const [loadingDrives, setLoadingDrives] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setSiteId(binding?.site_id || '')
    setSiteWebUrl(binding?.site_web_url || '')
    setDriveId(binding?.drive_id || '')
    setDriveName(binding?.drive_name || '')
  }, [binding])

  useEffect(() => {
    if (!flash) return
    const timer = setTimeout(onFlashClear, 3000)
    return () => clearTimeout(timer)
  }, [flash, onFlashClear])

  const handleSearch = async () => {
    setLoadingSites(true)
    setError(null)
    try {
      const result = await listSharePointSites(query.trim() || undefined)
      setSites(result.items || [])
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load SharePoint sites.')
    } finally {
      setLoadingSites(false)
    }
  }

  const handleSiteSelect = async (value) => {
    setSiteId(value)
    setDriveId('')
    setDriveName('')
    const site = sites.find((item) => item.id === value)
    setSiteWebUrl(site?.web_url || '')
    if (!value) return
    setLoadingDrives(true)
    setError(null)
    try {
      const result = await listSharePointDrives(value)
      setDrives(result.items || [])
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load document libraries.')
    } finally {
      setLoadingDrives(false)
    }
  }

  const handleDriveSelect = (value) => {
    setDriveId(value)
    const drive = drives.find((item) => item.id === value)
    setDriveName(drive?.name || '')
  }

  const handleSave = async () => {
    if (!siteId || !driveId) return
    setSaving(true)
    setError(null)
    try {
      const result = await saveSharePointBinding({
        site_id: siteId,
        site_web_url: siteWebUrl,
        drive_id: driveId,
        drive_name: driveName || 'Documents',
        root_item_id: 'root',
        folder_path: '/',
        is_primary: true,
      })
      onSaved(result.binding)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save SharePoint binding.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border-t border-brand-line pt-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="text-brand-ink font-sans text-sm font-bold mb-1">SharePoint library</h3>
          <p className="text-brand-ink-2 font-sans text-xs">
            Select the SharePoint site and document library used for matter folders and uploads.
          </p>
        </div>
        {binding?.drive_id && (
          <span className="shrink-0 text-[10px] font-bold uppercase text-green-700 bg-green-100 px-2 py-1 rounded-full">
            Configured
          </span>
        )}
      </div>

      {flash && (
        <div className="mb-3 px-3 py-2 bg-green-50 border border-green-200 text-green-700 rounded-lg text-xs font-medium">
          {flash}
        </div>
      )}
      {error && (
        <div className="mb-3 px-3 py-2 bg-red-50 border border-red-200 text-red-700 rounded-lg text-xs font-medium">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-3 mb-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search sites, or leave blank for root site"
          className="px-3 py-2 bg-brand-bg border border-brand-line rounded-lg text-brand-ink font-sans text-sm focus:outline-none focus:ring-2 focus:ring-brand-ink/20"
        />
        <button
          onClick={handleSearch}
          disabled={loadingSites}
          className="px-4 py-2 border border-brand-line text-brand-ink font-sans text-xs font-medium rounded-lg hover:bg-brand-bg-soft transition-colors disabled:opacity-50"
        >
          {loadingSites ? 'Loading...' : 'Load sites'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <select
          aria-label="SharePoint site"
          value={siteId}
          onChange={(e) => handleSiteSelect(e.target.value)}
          className="px-3 py-2 bg-brand-bg border border-brand-line rounded-lg text-brand-ink font-sans text-sm focus:outline-none focus:ring-2 focus:ring-brand-ink/20"
        >
          <option value="">Select site...</option>
          {siteId && !sites.some((site) => site.id === siteId) && (
            <option value={siteId}>{siteWebUrl || siteId}</option>
          )}
          {sites.map((site) => (
            <option key={site.id} value={site.id}>{site.name || site.web_url || site.id}</option>
          ))}
        </select>
        <select
          aria-label="SharePoint document library"
          value={driveId}
          onChange={(e) => handleDriveSelect(e.target.value)}
          disabled={!siteId || loadingDrives}
          className="px-3 py-2 bg-brand-bg border border-brand-line rounded-lg text-brand-ink font-sans text-sm disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-brand-ink/20"
        >
          <option value="">Select library...</option>
          {driveId && !drives.some((drive) => drive.id === driveId) && (
            <option value={driveId}>{driveName || driveId}</option>
          )}
          {drives.map((drive) => (
            <option key={drive.id} value={drive.id}>{drive.name || drive.id}</option>
          ))}
        </select>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || !siteId || !driveId}
          className="px-4 py-2 bg-brand-ink text-white font-sans text-xs font-medium rounded-lg hover:bg-brand-ink/90 transition-colors disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save SharePoint binding'}
        </button>
        {binding?.drive_name && (
          <span className="text-xs text-brand-muted truncate">
            Current library: {binding.drive_name}
          </span>
        )}
      </div>
    </div>
  )
}

export function CloudRetryStatus({ result }) {
  if (!result || result.error) return null

  const initialized = result.matters_initialized || 0
  const failed = result.matters_failed || 0
  if (failed) {
    return (
      <span className="text-xs text-amber-700 font-medium">
        Cloud folders partially ready · {initialized} matter{initialized !== 1 ? 's' : ''} set up · {failed} need{failed === 1 ? 's' : ''} retry
      </span>
    )
  }

  return (
    <span className="text-xs text-green-700 font-medium">
      Cloud folders ready · {initialized} matter{initialized !== 1 ? 's' : ''} set up
    </span>
  )
}

const HEALTH_TEXT = {
  healthy: 'Healthy',
  missing_scopes: 'Missing permissions',
  refresh_failed: 'Refresh Failed',
  revoked: 'Reconnect Required',
  disconnected: 'Not connected',
}

/**
 * A provider the firm has never connected. It explains what connecting asks
 * for and who has to do it, instead of listing every permission as a red
 * failure. When the firm already runs on the other suite it stays compact.
 */
function NotConnectedCard({ name, provider, requiredRows, scopeLabels, onReauthorize, onConnectPersonal, otherConnected }) {
  const asks = requiredRows.filter((scope) => !PLUMBING_SCOPES.has(scope)).map((scope) => scopeLabels[scope] || scope)
  const askList = (
    <ul className="mt-2 space-y-1" data-testid={`connect-asks-${provider}`}>
      {asks.map((label) => (
        <li key={label} className="flex gap-2 text-xs text-brand-ink-2 font-sans">
          <span className="text-brand-muted" aria-hidden="true">•</span>
          <span>{label}</span>
        </li>
      ))}
    </ul>
  )
  return (
    <div className="bg-brand-surface border border-brand-line rounded-xl p-6" data-testid={`provider-card-${provider}`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0 max-w-2xl">
          <h3 className="text-brand-ink font-sans text-base font-bold">{name}</h3>
          <span className="inline-block mt-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-gray-100 text-gray-600">Not connected</span>
          <p className="mt-2 text-xs text-brand-ink-2 font-sans">
            {otherConnected ? `Only needed if your firm also uses ${name}.` : CONNECT_WHO[provider]}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <button
            onClick={() => onReauthorize(provider)}
            className={`px-4 py-2 font-sans text-xs font-medium rounded-lg transition-colors ${
              otherConnected
                ? 'border border-brand-line text-brand-ink hover:bg-brand-bg-soft'
                : 'bg-brand-ink text-white hover:bg-brand-ink/90'
            }`}
          >
            Connect
          </button>
          {onConnectPersonal && !otherConnected && (
            <button type="button" onClick={onConnectPersonal} className="text-xs font-medium text-brand-accent hover:text-brand-ink font-sans">
              Solo practice on personal Gmail? Connect it instead
            </button>
          )}
        </div>
      </div>
      {asks.length > 0 && (otherConnected ? (
        <details className="group mt-3">
          <summary className="cursor-pointer list-none text-xs font-bold text-brand-ink font-sans marker:hidden [&::-webkit-details-marker]:hidden">
            What {name} will be asked to allow <span className="inline-block text-brand-muted transition-transform group-open:rotate-180" aria-hidden="true">⌄</span>
          </summary>
          {askList}
        </details>
      ) : (
        <div className="mt-4 rounded-lg bg-brand-bg px-4 py-3">
          <p className="text-xs font-bold text-brand-ink font-sans">What {name} will be asked to allow</p>
          {askList}
        </div>
      ))}
    </div>
  )
}

function ProviderError({ raw, testId }) {
  return (
    <details className="mt-1 text-xs font-sans" data-testid={testId}>
      <summary className="cursor-pointer text-red-700 font-medium">{describeProviderError(raw)} <span className="text-brand-muted font-normal">Technical details</span></summary>
      <p className="mt-1 text-red-600 font-mono bg-red-50 px-2 py-1 rounded break-all">{raw}</p>
    </details>
  )
}

const HEALTH_REMEDY = {
  revoked: 'The provider has revoked this grant. Re-authorize as an administrator to restore email, calendar and document access for the firm.',
  refresh_failed: 'LawHand could not refresh the firm-wide token. Re-authorize as an administrator; if it fails again, check the provider app configuration under Advanced.',
}

export function ProviderCard({
  name,
  provider,
  info,
  scopeLabels,
  onReauthorize,
  onDisconnect,
  disconnecting = false,
  onConnectPersonal,
  otherConnected = false,
  relTime,
  onSyncNow,
  syncing,
}) {
  if (!info.connected) {
    const rows = info.required_scopes?.length ? info.required_scopes : info.missing_required || []
    return (
      <NotConnectedCard
        name={name}
        provider={provider}
        requiredRows={rows}
        scopeLabels={scopeLabels}
        onReauthorize={onReauthorize}
        onConnectPersonal={onConnectPersonal}
        otherConnected={otherConnected}
      />
    )
  }
  const healthText = HEALTH_TEXT[info.health] || 'Needs Attention'
  const grantedScopes = info.granted_scopes || []
  const missingScopes = info.missing_required || []
  const requiredScopes = info.required_scopes || []
  const extraScopes = info.extra_scopes || []
  const requiredRows = requiredScopes.length ? requiredScopes : [...new Set([...grantedScopes, ...missingScopes])]
  const unusable = info.connected && UNUSABLE_HEALTH.has(info.health)
  // Scope counts describe consent, not whether the credential works now, so
  // an unusable credential never advertises a full green tally.
  const grantedRequiredCount = info.connected && !unusable ? Math.max(requiredRows.length - missingScopes.length, 0) : 0
  const directorySync = info.capabilities?.directory_sync
  const canSyncDirectory = info.connected && !unusable && directorySync?.status !== 'unavailable'
  const userTokens = info.user_tokens

  const scopeDetail = (
    <>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="px-3 py-2 rounded-lg bg-brand-bg">
          <p className="text-[11px] uppercase text-brand-ink-2 font-bold">Required</p>
          <p className="text-sm text-brand-ink font-bold" data-testid="scope-tally-required">{requiredRows.length}</p>
        </div>
        <div className="px-3 py-2 rounded-lg bg-brand-bg">
          <p className="text-[11px] uppercase text-brand-ink-2 font-bold">Granted</p>
          <p className={`text-sm font-bold ${grantedRequiredCount ? 'text-green-700' : 'text-brand-ink'}`} data-testid="scope-tally-granted">{grantedRequiredCount}</p>
        </div>
        <div className="px-3 py-2 rounded-lg bg-brand-bg">
          <p className="text-[11px] uppercase text-brand-ink-2 font-bold">Missing</p>
          <p className={`text-sm font-bold ${missingScopes.length ? 'text-red-600' : 'text-brand-ink'}`} data-testid="scope-tally-missing">
            {missingScopes.length}
          </p>
        </div>
      </div>

      <div className="space-y-1.5">
        {requiredRows.map((scope) => {
          const missing = missingScopes.includes(scope)
          const granted = info.connected && !unusable && !missing
          const label = scopeLabels[scope] || scope
          return (
            <div key={scope} className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-brand-bg">
              {granted ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="#16a34a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              )}
              <span className={`text-sm ${granted ? 'text-brand-ink' : 'text-red-600'}`}>
                {label}
              </span>
              {!granted && (
                <span className="ml-auto text-xs text-red-500 font-medium">{unusable ? 'Unusable' : 'Missing'}</span>
              )}
              {granted && (
                <span className="ml-auto text-xs text-green-700 font-medium">Granted</span>
              )}
            </div>
          )
        })}
        {extraScopes.length > 0 && (
          <div className="pt-2">
            <p className="text-[11px] uppercase text-brand-ink-2 font-bold mb-1.5">Additional granted scopes</p>
            <div className="space-y-1.5">
              {extraScopes.map((scope) => (
                <div key={scope} className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-brand-bg-soft">
                  <span className="w-2 h-2 rounded-full bg-brand-ink-2" />
                  <span className="text-sm text-brand-ink">{scopeLabels[scope] || scope}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )

  return (
    <div className="bg-brand-surface border border-brand-line rounded-xl p-6" data-testid={`provider-card-${provider}`}>
      <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        <div className="min-w-0">
          <h3 className="text-brand-ink font-sans text-base font-bold">{name}</h3>
          <span className={`inline-block mt-1 px-2.5 py-0.5 rounded-full text-xs font-bold ${
            info.health === 'healthy' ? 'bg-green-100 text-green-700' :
            info.health === 'missing_scopes' || info.health === 'refresh_failed' ? 'bg-amber-100 text-amber-700' :
            'bg-red-100 text-red-700'
          }`}>
            {healthText}
          </span>
          {info.account_label && (
            <span className="inline-block mt-1 ml-2 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
              {info.account_label}
            </span>
          )}
          {info.connected && (
            <p className="mt-2 text-[11px] uppercase tracking-wider font-bold text-brand-muted font-sans">Firm connection</p>
          )}
          {info.connected && info.service_account_email && (
            <p className="text-xs text-brand-ink-2 font-sans">Granted by {info.service_account_email}</p>
          )}
          {info.connected && (
            <p className="text-xs text-brand-ink-2 font-sans max-w-xl">
              Mail and calendar features that use this connection act as {info.service_account_email || 'the administrator who connected it'}. It does not open other staff mailboxes.
            </p>
          )}
          {info.connected && (
            <p className="mt-1 text-xs text-brand-ink-2 font-sans">
              {info.user_count ?? 0} users synced
              {info.last_sync_status === 'failed' ? ' · last sync failed' : info.last_sync_status === 'not_applicable' ? (isCapabilityUnconfirmed(info, 'directory_sync', directorySync) ? ' · directory access not confirmed' : ' · directory sync unavailable for this account') : ` · last run ${relTime(info.last_sync_at)}`}
            </p>
          )}
          {info.connected && (
            <p className="mt-1 text-xs text-brand-ink-2 font-sans">
              {info.last_refresh_error
                ? `Last token refresh attempt ${info.last_refresh_at ? relTime(info.last_refresh_at) : 'not recorded'} failed`
                : `Last successful token refresh ${info.last_refresh_at ? relTime(info.last_refresh_at) : 'not yet recorded'}`}
            </p>
          )}
          {info.connected && info.last_sync_error && info.last_sync_status === 'failed' && (
            <ProviderError raw={info.last_sync_error} testId={`sync-error-${provider}`} />
          )}
          {info.connected && info.last_refresh_error && (
            <ProviderError raw={info.last_refresh_error} testId={`refresh-error-${provider}`} />
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {canSyncDirectory && (
            <button
              onClick={onSyncNow}
              disabled={syncing}
              className="px-4 py-2 border border-brand-line text-brand-ink font-sans text-xs font-medium rounded-lg hover:bg-brand-bg-soft transition-colors disabled:opacity-50"
            >
              {syncing ? 'Syncing…' : 'Sync now'}
            </button>
          )}
          <button
            onClick={() => onReauthorize(provider)}
            className={`px-4 py-2 font-sans text-xs font-medium rounded-lg transition-colors ${
              unusable || missingScopes.length > 0
                ? 'bg-brand-ink text-white hover:bg-brand-ink/90'
                : 'border border-brand-line text-brand-ink hover:bg-brand-bg-soft'
            }`}
          >
            Re-authorize
          </button>
          {onDisconnect && (
            <button
              onClick={() => onDisconnect(provider)}
              disabled={disconnecting}
              className="px-4 py-2 font-sans text-xs font-medium rounded-lg border border-red-200 text-red-700 hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              {disconnecting ? 'Disconnecting…' : 'Disconnect'}
            </button>
          )}
        </div>
      </div>

      {unusable && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800 font-sans" role="alert">
          <p className="font-semibold">{healthText}: this firm-wide connection cannot be used right now.</p>
          <p className="mt-1">{HEALTH_REMEDY[info.health]}</p>
        </div>
      )}

      {!unusable && missingScopes.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900 font-sans" role="status" data-testid={`missing-scopes-${provider}`}>
          <p className="font-semibold">Some permissions were not granted, so part of this connection is off.</p>
          <p className="mt-1">
            Not granted: {missingScopes.map((scope) => scopeLabels[scope] || scope).join('; ')}.
            {' '}Choose Re-authorize and approve every permission on the consent screen.
          </p>
        </div>
      )}

      {info.connected && userTokens && (
        <div className="mb-4 rounded-lg border border-brand-line bg-brand-bg px-4 py-3" data-testid={`user-tokens-${provider}`}>
          <p className="text-[11px] uppercase tracking-wider font-bold text-brand-muted font-sans">Per-user connections</p>
          {userTokens.total > 0 ? (
            <p className="mt-1 text-xs text-brand-ink-2 font-sans">
              {userTokens.healthy} of {userTokens.total} connected
              {userTokens.needs_reauth > 0 && (
                <span className="text-amber-700 font-medium"> · {userTokens.needs_reauth} need to reconnect from Profile → Connected accounts</span>
              )}
            </p>
          ) : (
            <p className="mt-1 text-xs text-brand-ink-2 font-sans">No one has connected their own account yet. Each person connects from Profile → Connected accounts; an administrator cannot do it for them. It lets LawHand file their matter email, send approved client email from their address and put their tasks on their calendar.</p>
          )}
        </div>
      )}

      {info.recent_sync_runs?.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
          {info.recent_sync_runs.slice(0, 3).map((run) => (
            <div key={`${run.job_type}-${run.started_at}`} className="bg-brand-bg border border-brand-line rounded-lg px-3 py-2">
              <div className="text-[11px] uppercase font-bold text-brand-ink-2">{syncJobLabel(run.job_type)}</div>
              <div className={`text-xs font-bold ${run.status === 'completed' ? 'text-green-700' : 'text-red-600'}`}>
                {run.status === 'completed' ? 'Completed' : run.status === 'failed' ? 'Failed' : run.status} · {relTime(run.started_at)}
              </div>
              <div className="text-[11px] text-brand-ink-2">
                {run.items_ok || 0} ok · {run.items_failed || 0} failed
              </div>
            </div>
          ))}
        </div>
      )}

      {unusable ? (
        <details className="group rounded-lg border border-brand-line">
          <summary className="cursor-pointer list-none px-3 py-2 text-xs font-bold text-brand-ink marker:hidden [&::-webkit-details-marker]:hidden">
            Scope detail for support <span className="text-brand-muted transition-transform group-open:rotate-180 inline-block" aria-hidden="true">⌄</span>
          </summary>
          <div className="px-3 pb-3 pt-1">{scopeDetail}</div>
        </details>
      ) : (
        <>
          {scopeDetail}
          {requiredRows.length === 0 && (
            <p className="text-brand-ink-2 font-sans text-sm py-2">Not connected. Grant access to enable integration features.</p>
          )}
        </>
      )}

      {info.connected && !unusable && info.capabilities && (
        <div className="mt-4 pt-4 border-t border-brand-line">
          <p className="text-xs font-bold text-brand-ink mb-2 font-sans">Features on this account</p>
          {info.capabilities.directory_sync?.status === 'unavailable' && (
            <p className="mb-2 text-xs text-brand-muted font-sans">Directory sync imports organization users. Its availability is separate from document storage.</p>
          )}
          <div className="space-y-1.5">
            {Object.entries(info.capabilities).map(([key, reported]) => {
              const declined = missingScopes.filter((scope) => SCOPE_CAPABILITY[scope] === key)
              const capability = reported.status === 'ok' && declined.length
                ? {
                    ...reported,
                    status: 'needs_reauth',
                    reason: `Not granted: ${declined.map((scope) => scopeLabels[scope] || scope).join('; ')}.`,
                  }
                : reported
              const badge = CAP_BADGE[capability.status] || CAP_BADGE.unavailable
              const badgeText = isCapabilityUnconfirmed(info, key, capability)
                ? 'Not confirmed'
                : key === 'directory_sync' && capability.status === 'unavailable'
                  ? 'Unavailable for this account'
                  : badge.text
              return (
                <div key={key} data-testid={`capability-${key}`}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs text-brand-ink-2 font-sans">{CAPABILITY_LABELS[key] || key}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badge.cls}`}>{badgeText}</span>
                  </div>
                  {/* Reasons are sentences; a bare code such as "missing_scopes" is not shown. */}
                  {capability.status !== 'ok' && /\s/.test(capability.reason || '') && (
                    <p className="mt-0.5 text-[11px] text-brand-muted font-sans">{capability.reason}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
