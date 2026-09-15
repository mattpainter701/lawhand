import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { acceptInvitation, loginGoogle, loginMicrosoft, lookupInvitation } from '../api'
import { useAuth } from '../App'
import FormField from '../components/form/FormField'
import LawHandLogo from '../components/LawHandLogo'
import { INVITATION_ERROR_MESSAGES } from '../utils/loginErrors'

const MIN_PASSWORD_LENGTH = 12
const GENERIC_REFUSAL = INVITATION_ERROR_MESSAGES.invite_invalid
const SIGN_IN_INSTEAD = new Set(['invite_accepted', 'account_active'])

const refusalCode = (err) => err?.response?.data?.code || null

export default function AcceptInvitePage() {
  const [searchParams] = useSearchParams()
  // Read once: the token is removed from the address bar below.
  const [token] = useState(() => searchParams.get('token') || '')
  const navigate = useNavigate()
  const { login: authLogin } = useAuth()

  const [invitation, setInvitation] = useState(null)
  const [refusal, setRefusal] = useState(token ? null : 'invite_invalid')
  const [loading, setLoading] = useState(Boolean(token))
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    // Keep the token out of history, bookmarks, and the Referer sent to
    // Google or Microsoft when a provider button is used.
    if (token && window.location.search.includes('token=')) {
      window.history.replaceState(window.history.state, '', window.location.pathname)
    }
  }, [token])

  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    lookupInvitation(token)
      .then((data) => {
        if (!cancelled) setInvitation(data)
      })
      .catch((err) => {
        if (!cancelled) setRefusal(refusalCode(err) || 'invite_invalid')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (password.length < MIN_PASSWORD_LENGTH) {
      setSubmitError(`Use at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      await acceptInvitation(token, password)
      const user = await authLogin()
      navigate(user?.default_route || '/matters', { replace: true })
    } catch (err) {
      const code = refusalCode(err)
      if (code) {
        setRefusal(code)
      } else if (err?.response?.status === 422) {
        setSubmitError('Choose a longer, less common password.')
      } else {
        setSubmitError(
          err?.response
            ? 'We could not accept the invitation. Please try again.'
            : 'Unable to reach LawHand. Check your connection and try again.',
        )
      }
    } finally {
      setSubmitting(false)
    }
  }

  const providerOptions = { invite: token }

  return (
    <div className="min-h-screen bg-brand-bg flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md bg-brand-surface border border-brand-line rounded-2xl shadow-xl px-8 py-10">
        <div className="text-center mb-8">
          <LawHandLogo className="justify-center" />
        </div>

        {loading && (
          <p role="status" aria-live="polite" className="text-center text-sm text-brand-muted font-sans">
            Checking your invitation…
          </p>
        )}

        {!loading && refusal && (
          <div className="text-center">
            <h1 className="font-serif text-2xl text-brand-ink mb-3">Invitation unavailable</h1>
            <p role="alert" className="text-sm text-brand-ink-2 font-sans">
              {INVITATION_ERROR_MESSAGES[refusal] || GENERIC_REFUSAL}
            </p>
            <p className="mt-6 text-sm font-sans">
              <Link to="/login" className="text-brand-accent hover:text-brand-accent-2 font-medium">
                {SIGN_IN_INSTEAD.has(refusal) ? 'Sign in' : 'Go to sign in'}
              </Link>
            </p>
          </div>
        )}

        {!loading && !refusal && invitation && (
          <>
            <h1 className="font-serif text-2xl text-brand-ink mb-2 text-center">
              Join {invitation.firm_name || 'your firm'} on LawHand
            </h1>
            <p className="text-sm text-brand-muted font-sans text-center mb-8">
              This invitation is for <span className="font-medium text-brand-ink">{invitation.email_masked}</span>.
            </p>

            {(invitation.providers?.microsoft || invitation.providers?.google) && (
              <>
                <div className="space-y-3">
                  {invitation.providers?.microsoft && (
                    <button
                      type="button"
                      onClick={() => loginMicrosoft(null, providerOptions)}
                      className="w-full px-5 py-3 rounded-xl border border-brand-line bg-brand-surface text-brand-ink text-sm font-medium font-sans hover:border-brand-ink hover:bg-brand-bg-soft transition-all"
                    >
                      Continue with Microsoft
                    </button>
                  )}
                  {invitation.providers?.google && (
                    <button
                      type="button"
                      onClick={() => loginGoogle(null, providerOptions)}
                      className="w-full px-5 py-3 rounded-xl border border-brand-line bg-brand-surface text-brand-ink text-sm font-medium font-sans hover:border-brand-ink hover:bg-brand-bg-soft transition-all"
                    >
                      Continue with Google
                    </button>
                  )}
                </div>
                <p className="mt-3 text-xs text-brand-muted font-sans text-center">
                  Use the account for {invitation.email_masked}. Other accounts are refused.
                </p>
                <div className="flex items-center gap-4 my-6">
                  <div className="h-[1px] flex-1 bg-brand-line"></div>
                  <span className="text-xs text-brand-muted font-sans">or set a password</span>
                  <div className="h-[1px] flex-1 bg-brand-line"></div>
                </div>
              </>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              {submitError && (
                <div role="alert" className="bg-brand-rose/10 border border-brand-rose/20 rounded-lg px-4 py-3 text-sm text-brand-rose font-sans">
                  {submitError}
                </div>
              )}
              <FormField label="Choose a password" hint={`At least ${MIN_PASSWORD_LENGTH} characters.`} required>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={MIN_PASSWORD_LENGTH}
                  maxLength={128}
                  className="w-full border border-brand-line rounded-lg px-4 py-2.5 text-[14px] font-sans text-brand-ink focus:outline-none focus:border-brand-accent focus:ring-1 focus:ring-brand-accent bg-brand-surface"
                />
              </FormField>
              <button
                type="submit"
                disabled={submitting}
                className="w-full px-5 py-3 rounded-xl bg-brand-ink text-white text-sm font-medium font-sans hover:bg-brand-ink-2 disabled:opacity-60 transition-all"
              >
                {submitting ? 'Joining…' : 'Accept invitation'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
