import { Clock } from 'lucide-react'
import { Link } from 'react-router-dom'

// A firm on a trial had no way to see it: the countdown existed only in the
// database, so the first signal was being locked out on day 30. /auth/me now
// carries access_state and trial_ends_at, and this says so while there is
// still time to act.

const DAY_MS = 86_400_000

export function trialDaysLeft(trialEndsAt, now = Date.now()) {
  if (!trialEndsAt) return null
  const ends = new Date(trialEndsAt).getTime()
  if (Number.isNaN(ends)) return null
  return Math.max(0, Math.ceil((ends - now) / DAY_MS))
}

export function resolveTrialState(user, now = Date.now()) {
  // Demo workspaces report access_state "active" from the API and carry their
  // own banner; nothing here should fire for them.
  if (!user || user.demo) return null
  if (user.access_state === 'trial_expired') {
    return {
      tone: 'rose',
      message: 'Your free trial has ended. Contact LawHand to restore firm access.',
      daysLeft: 0,
    }
  }
  if (user.access_state !== 'trial') return null
  const daysLeft = trialDaysLeft(user.trial_ends_at, now)
  if (daysLeft === null) return null
  return {
    tone: daysLeft <= 2 ? 'rose' : daysLeft <= 7 ? 'amber' : 'neutral',
    message:
      daysLeft === 0
        ? 'Your free trial ends today.'
        : `${daysLeft} day${daysLeft === 1 ? '' : 's'} left in your free trial.`,
    daysLeft,
  }
}

const TONES = {
  neutral: 'border-brand-line bg-brand-bg-soft text-brand-ink',
  amber: 'border-amber-300 bg-amber-50 text-amber-950',
  rose: 'border-brand-rose/40 bg-brand-rose/10 text-brand-ink',
}

export default function TrialBanner({ user, canManageBilling = false, now }) {
  const state = resolveTrialState(user, now)
  if (!state) return null

  return (
    <div
      role="status"
      aria-label="Free trial status"
      className={`flex flex-wrap items-center justify-center gap-x-2 gap-y-1 border-b px-4 py-2 text-center text-xs font-semibold md:text-sm ${TONES[state.tone]}`}
    >
      <Clock size={15} aria-hidden="true" className="shrink-0" />
      <span>{state.message}</span>
      {canManageBilling && user?.billing_checkout_available ? (
        <Link to="/billing" className="underline underline-offset-2 hover:no-underline">
          Subscribe now
        </Link>
      ) : (
        <span className="font-normal opacity-90">
          {canManageBilling ? 'Contact LawHand to request activation.' : 'Ask a firm administrator to contact LawHand.'}
        </span>
      )}
      {user?.premium_ai_available === false && state.daysLeft > 0 && (
        <span className="font-normal opacity-90">Premium AI is available after you subscribe.</span>
      )}
    </div>
  )
}
