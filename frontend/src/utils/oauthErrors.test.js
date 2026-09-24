import { describe, expect, it } from 'vitest'
import { oauthErrorMessage, oauthProviderLabel } from './oauthErrors'

describe('oauthErrorMessage', () => {
  it('names the provider that actually failed', () => {
    expect(oauthErrorMessage('token_exchange_failed', 'microsoft')).toBe(
      'Microsoft 365 authorization could not be completed. No connection was saved; try again.',
    )
    expect(oauthErrorMessage('token_exchange_failed', 'google')).toMatch(/^Google authorization/)
  })

  it('explains cancellation and admin approval instead of a generic failure', () => {
    expect(oauthErrorMessage('access_denied', 'google')).toBe(
      'The Google sign-in was cancelled, so nothing was connected. Try again when you are ready.',
    )
    expect(oauthErrorMessage('consent_required', 'microsoft')).toMatch(/^Microsoft 365 needs an administrator to approve LawHand/)
    expect(oauthErrorMessage('invalid_state', 'microsoft')).toMatch(/took too long/)
  })

  it('keeps the existing account-type guidance for Google', () => {
    expect(oauthErrorMessage('account_mode_mismatch', 'google')).toMatch(/selected Google account type did not match/)
  })

  it('never echoes an unknown provider or code', () => {
    expect(oauthProviderLabel('<script>')).toBe('the cloud provider')
    expect(oauthErrorMessage('<b>boom</b>', 'evil')).toBe(
      'The cloud connection could not be completed. No connection was saved; try again.',
    )
    expect(oauthErrorMessage('token_exchange_failed', 'evil')).toBe(
      'The cloud provider authorization could not be completed. No connection was saved; try again.',
    )
  })
})

describe('oauthProviderLabel', () => {
  it('names the two supported providers and nothing else', () => {
    expect(oauthProviderLabel('microsoft')).toBe('Microsoft 365')
    expect(oauthProviderLabel('google')).toBe('Google')
    expect(oauthProviderLabel('Google')).toBe('the cloud provider')
    expect(oauthProviderLabel(undefined)).toBe('the cloud provider')
    expect(oauthProviderLabel(null)).toBe('the cloud provider')
    expect(oauthProviderLabel('')).toBe('the cloud provider')
  })
})

describe('oauthErrorMessage for every callback code', () => {
  const PROVIDERS = [
    ['microsoft', 'Microsoft 365'],
    ['google', 'Google'],
  ]

  it.each(PROVIDERS)('explains a cancelled %s sign-in by name', (provider, label) => {
    expect(oauthErrorMessage('access_denied', provider)).toBe(
      `The ${label} sign-in was cancelled, so nothing was connected. Try again when you are ready.`,
    )
  })

  it.each([['evil'], [undefined], [null]])('explains a cancelled sign-in without a name for provider %j', (provider) => {
    expect(oauthErrorMessage('access_denied', provider)).toBe(
      'The sign-in was cancelled, so nothing was connected. Try again when you are ready.',
    )
  })

  it.each(PROVIDERS)('asks for administrator approval from %s', (provider, label) => {
    expect(oauthErrorMessage('consent_required', provider)).toBe(
      `${label} needs an administrator to approve LawHand before this account can connect. Sign in with an administrator account, or ask your administrator to approve LawHand.`,
    )
  })

  it.each([
    ['interaction_required', 'microsoft', 'Microsoft 365 needs you to sign in again. Start the connection again.'],
    ['login_required', 'microsoft', 'Microsoft 365 needs you to sign in again. Start the connection again.'],
    ['login_required', 'google', 'Google needs you to sign in again. Start the connection again.'],
    ['interaction_required', undefined, 'The cloud provider needs you to sign in again. Start the connection again.'],
  ])('asks for a fresh sign-in on %s from %s', (code, provider, message) => {
    expect(oauthErrorMessage(code, provider)).toBe(message)
  })

  it.each([['microsoft'], ['google'], [undefined]])('names no provider when the state check fails (%s)', (provider) => {
    expect(oauthErrorMessage('invalid_state', provider)).toBe(
      'The connection took too long or was started in another tab. Start it again from this page.',
    )
  })

  it('keeps the Google account-type guidance whatever provider is passed', () => {
    const message = 'The selected Google account type did not match the consented account. Choose Google Workspace or Personal Google and try again.'
    expect(oauthErrorMessage('account_mode_mismatch', 'google')).toBe(message)
    expect(oauthErrorMessage('account_mode_mismatch')).toBe(message)
  })

  it.each([
    ['microsoft', 'Microsoft 365'],
    ['google', 'Google'],
    [undefined, 'The cloud provider'],
  ])('reports failed identity verification from %s', (provider, label) => {
    expect(oauthErrorMessage('identity_verification_failed', provider)).toBe(
      `${label} identity verification failed. No connection was saved; try again or contact LawHand support.`,
    )
  })

  it.each([
    ['token_exchange_failed', 'google', 'Google'],
    ['no_access_token', 'microsoft', 'Microsoft 365'],
    ['no_access_token', undefined, 'The cloud provider'],
  ])('reports %s from %s as an incomplete authorization', (code, provider, label) => {
    expect(oauthErrorMessage(code, provider)).toBe(
      `${label} authorization could not be completed. No connection was saved; try again.`,
    )
  })

  it.each([
    ['server_error', 'microsoft', 'The Microsoft 365 connection could not be completed. No connection was saved; try again.'],
    ['server_error', 'google', 'The Google connection could not be completed. No connection was saved; try again.'],
    ['server_error', undefined, 'The cloud connection could not be completed. No connection was saved; try again.'],
    [undefined, undefined, 'The cloud connection could not be completed. No connection was saved; try again.'],
    ['ACCESS_DENIED', 'google', 'The Google connection could not be completed. No connection was saved; try again.'],
  ])('falls back to a generic failure for the unrecognised code %j from %j', (code, provider, message) => {
    expect(oauthErrorMessage(code, provider)).toBe(message)
  })

  it.each([['constructor'], ['toString'], ['__proto__'], ['hasOwnProperty']])(
    'treats the Object prototype key %j as an unknown provider',
    (provider) => {
      expect(oauthProviderLabel(provider)).toBe('the cloud provider')
      expect(oauthErrorMessage('consent_required', provider)).toBe(
        'The cloud provider needs an administrator to approve LawHand before this account can connect. Sign in with an administrator account, or ask your administrator to approve LawHand.',
      )
      expect(oauthErrorMessage('access_denied', provider)).toBe(
        'The sign-in was cancelled, so nothing was connected. Try again when you are ready.',
      )
      expect(oauthErrorMessage('server_error', provider)).toBe(
        'The cloud connection could not be completed. No connection was saved; try again.',
      )
    },
  )
})
