export const STORAGE_PROVIDER_LABELS = {
  onedrive: 'Microsoft OneDrive',
  sharepoint: 'Microsoft SharePoint',
  google_drive: 'Google Drive',
}

const PROVIDER_CREDENTIALS = {
  onedrive: 'microsoft',
  sharepoint: 'microsoft',
  google_drive: 'google',
}

export const STORAGE_REQUIRED_SCOPES = {
  onedrive: ['Files.ReadWrite.All'],
  sharepoint: ['Files.ReadWrite.All', 'Sites.Read.All'],
  google_drive: ['https://www.googleapis.com/auth/drive'],
}

// `missing_scopes` is provider-wide audit state, so it may represent mail or
// calendar consent that document storage does not use. Storage scope checks
// below decide whether the selected document provider can accept a write.
const UNUSABLE_HEALTH = new Set(['revoked', 'refresh_failed'])

function credentialUsable(info) {
  const storageScopes = STORAGE_REQUIRED_SCOPES[info?.storageProvider] || []
  const missingStorage = (info?.missing_required || []).filter((scope) => storageScopes.includes(scope))
  return Boolean(
    info?.connected &&
    !UNUSABLE_HEALTH.has(info.health) &&
    !missingStorage.length,
  )
}

/**
 * Derive the provider that matter-file writes will use and whether it can
 * accept a write. This mirrors MatterFileStore's explicit/Auto policy while
 * also considering the credential health exposed by the admin permissions
 * audit. A connected OAuth row is not enough: refresh failures and missing
 * scopes make cloud-bound writes fail closed.
 */
export function deriveStorageReadiness({ primaryCloud = null, microsoft, google, sharePointBinding } = {}) {
  const explicit = primaryCloud || null
  const provider = explicit || (microsoft?.connected ? 'onedrive' : google?.connected ? 'google_drive' : null)
  const label = provider ? STORAGE_PROVIDER_LABELS[provider] || provider : 'document storage'
  const credential = provider ? PROVIDER_CREDENTIALS[provider] : null
  const baseInfo = credential === 'microsoft' ? microsoft : credential === 'google' ? google : null
  const info = baseInfo ? { ...baseInfo, storageProvider: provider } : null

  if (!provider) {
    return {
      provider: null,
      credential: null,
      label,
      ready: false,
      status: 'not_connected',
      reason: 'Connect Microsoft 365 or Google Workspace before saving matter documents.',
    }
  }

  if (!info?.connected) {
    return {
      provider,
      credential,
      label,
      ready: false,
      status: 'not_connected',
      reason: `Connect ${credential === 'microsoft' ? 'Microsoft 365' : 'Google Workspace'} before saving matter documents to ${label}.`,
    }
  }

  if (!credentialUsable(info)) {
    return {
      provider,
      credential,
      label,
      ready: false,
      status: 'needs_reconnect',
      reason: `Reconnect ${credential === 'microsoft' ? 'Microsoft 365' : 'Google Workspace'} before saving matter documents to ${label}.`,
    }
  }

  if (provider === 'sharepoint' && !sharePointBinding?.drive_id) {
    return {
      provider,
      credential,
      label,
      ready: false,
      status: 'needs_binding',
      reason: 'Choose and verify a SharePoint library before saving matter documents.',
    }
  }

  return { provider, credential, label, ready: true, status: 'ready', reason: `${label} connection is available. Access to each matter folder is checked when saving a document.` }
}
