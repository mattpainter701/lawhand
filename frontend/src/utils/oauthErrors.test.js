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
