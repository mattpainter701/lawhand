// Plain-language labels for the OAuth scopes LawHand requests. Shared by the
// admin integrations card and the onboarding wizard, so what an administrator
// is told before consenting cannot drift between the two screens.
//
// Firm connections are delegated grants: every call acts as the account that
// connected, so the labels say "the connected account" rather than implying
// organization-wide mailbox access.
import scopeMatrix from '../marketing/integration-scopes.json'

export const SCOPE_LABELS_MS = {
  offline_access: 'Stay connected without signing in again',
  'User.Read': "Read the connected account's profile",
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

export const SCOPE_LABELS_GOOGLE = {
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
export const PLUMBING_SCOPES = new Set([
  'openid',
  'email',
  'profile',
  'offline_access',
  'https://www.googleapis.com/auth/userinfo.email',
  'https://www.googleapis.com/auth/userinfo.profile',
])

const GOOGLE_DIRECTORY_SCOPE = 'https://www.googleapis.com/auth/admin.directory.user.readonly'

const LABELS_BY_PROVIDER = { microsoft: SCOPE_LABELS_MS, google: SCOPE_LABELS_GOOGLE }

// The labels an administrator weighs before consenting, in request order.
export function consentLabels(provider, scopes) {
  const labels = LABELS_BY_PROVIDER[provider] || {}
  return (scopes || [])
    .filter((scope) => !PLUMBING_SCOPES.has(scope))
    .map((scope) => labels[scope] || scope)
}

// What each firm (admin) connection asks for, taken from the published scope
// matrix that backend/tests/test_public_integration_scopes.py pins to the
// backend constants. A personal Google account gets the Workspace set without
// the directory scope (GOOGLE_SOLO_SCOPES, pinned by the same test file).
export function firmConsentLabels(provider, { googleAccountMode = 'workspace' } = {}) {
  let scopes = scopeMatrix.providers[provider]?.admin || []
  if (provider === 'google' && googleAccountMode === 'personal') {
    scopes = scopes.filter((scope) => scope !== GOOGLE_DIRECTORY_SCOPE)
  }
  return consentLabels(provider, scopes)
}
