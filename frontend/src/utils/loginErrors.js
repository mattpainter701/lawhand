// Plain-language explanations for sign-in refusals. The backend sends only a
// code (`/login?error=<code>`); the wording lives here so no server text is
// ever echoed into the page. Unknown codes fall back to the generic message.

export const INVITATION_ERROR_MESSAGES = {
  invite_invalid: 'This invitation link is not valid. Ask your firm administrator to send a new one.',
  invite_expired: 'This invitation has expired. Ask your firm administrator to resend it.',
  invite_accepted: 'This invitation has already been used. Sign in instead.',
  account_active: 'This account is already active. Sign in instead.',
  invite_email_mismatch:
    'That account does not match the address the invitation was sent to. Open the invitation again and use the matching account.',
  tenant_inactive: "Your firm's LawHand account is not active. Contact your firm administrator.",
}

export const LOGIN_ERROR_MESSAGES = {
  ...INVITATION_ERROR_MESSAGES,
  not_invited:
    'This account has not been invited to a LawHand firm yet. Ask your firm administrator to send you an invitation.',
  microsoft_not_linked:
    'This Microsoft account is not linked to a LawHand user. If you were invited, open the link in your invitation email. Otherwise, sign in the way you usually do.',
  account_inactive:
    'This account is not active. If you were invited, open the link in your invitation email. Otherwise, contact your firm administrator.',
  signup_disabled: 'LawHand accounts are set up by invitation. Use Request access below to get started.',
  identity_conflict:
    'This sign-in matches more than one LawHand account. Contact support and we will sort it out.',
  identity_already_linked:
    'That Google or Microsoft account is already linked to another LawHand user. Use a different account or contact your firm administrator.',
  google_email_unverified: 'Google has not verified that email address yet. Verify it with Google, then try again.',
  provider_unavailable: 'That sign-in option is not available right now. Try another way to sign in.',
  oauth_state_expired: 'That sign-in took too long or was already used. Please try again.',
  oauth_failed: 'Sign in did not complete. Please try again.',
}

export const loginErrorMessage = (code) =>
  code ? LOGIN_ERROR_MESSAGES[code] || LOGIN_ERROR_MESSAGES.oauth_failed : null
