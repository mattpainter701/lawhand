// Messages for the ?error=<code>&provider=<provider> query a cloud connect
// callback returns with (backend/app/routers/integrations.py _error_redirect).
// Codes are fixed identifiers; provider text is never echoed from the URL.

const PROVIDER_LABELS = {
  microsoft: 'Microsoft 365',
  google: 'Google',
}

// The provider comes from the URL, so inherited keys such as "constructor"
// must not read as a known provider.
const knownProvider = (provider) => typeof provider === 'string' && Object.hasOwn(PROVIDER_LABELS, provider)

export function oauthProviderLabel(provider) {
  return knownProvider(provider) ? PROVIDER_LABELS[provider] : 'the cloud provider'
}

const sentence = (text) => text.charAt(0).toUpperCase() + text.slice(1)

export function oauthErrorMessage(code, provider) {
  const known = knownProvider(provider)
  const name = oauthProviderLabel(provider)
  const connection = known ? `${name} connection` : 'cloud connection'
  switch (code) {
    case 'access_denied':
      return `The ${known ? `${name} ` : ''}sign-in was cancelled, so nothing was connected. Try again when you are ready.`
    case 'consent_required':
      return `${sentence(name)} needs an administrator to approve LawHand before this account can connect. Sign in with an administrator account, or ask your administrator to approve LawHand.`
    case 'interaction_required':
    case 'login_required':
      return `${sentence(name)} needs you to sign in again. Start the connection again.`
    case 'invalid_state':
      return 'The connection took too long or was started in another tab. Start it again from this page.'
    case 'account_mode_mismatch':
      return 'The selected Google account type did not match the consented account. Choose Google Workspace or Personal Google and try again.'
    case 'identity_verification_failed':
      return `${sentence(name)} identity verification failed. No connection was saved; try again or contact LawHand support.`
    case 'token_exchange_failed':
    case 'no_access_token':
      return `${sentence(name)} authorization could not be completed. No connection was saved; try again.`
    default:
      return `The ${connection} could not be completed. No connection was saved; try again.`
  }
}
