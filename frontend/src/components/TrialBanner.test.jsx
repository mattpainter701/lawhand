import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import TrialBanner, { resolveTrialState, trialDaysLeft } from './TrialBanner'

afterEach(cleanup)

const NOW = new Date('2026-09-15T12:00:00Z').getTime()
const inDays = (days) => new Date(NOW + days * 86_400_000).toISOString()

const renderBanner = (props) =>
  render(<MemoryRouter><TrialBanner now={NOW} {...props} /></MemoryRouter>)

describe('TrialBanner', () => {
  it('stays out of the way for a paid firm', () => {
    const { container } = renderBanner({ user: { access_state: 'active' } })
    expect(container).toBeEmptyDOMElement()
  })

  it('counts down the days left in a trial', () => {
    renderBanner({ user: { access_state: 'trial', trial_ends_at: inDays(12) } })
    expect(screen.getByRole('status', { name: /free trial status/i })).toHaveTextContent('12 days left')
  })

  it('says so on the last day rather than showing zero', () => {
    renderBanner({ user: { access_state: 'trial', trial_ends_at: inDays(0.25) } })
    expect(screen.getByRole('status')).toHaveTextContent(/ends today|1 day left/i)
  })

  it('explains an ended trial and only links billing when checkout is available', () => {
    renderBanner({ user: { access_state: 'trial_expired', trial_ends_at: inDays(-1), billing_checkout_available: true }, canManageBilling: true })
    expect(screen.getByRole('status')).toHaveTextContent(/free trial has ended/i)
    expect(screen.getByRole('link', { name: /subscribe now/i })).toHaveAttribute('href', '/billing')
  })

  it('does not promise checkout when billing is unavailable', () => {
    renderBanner({ user: { access_state: 'trial_expired' }, canManageBilling: true })
    expect(screen.queryByRole('link', { name: /subscribe now/i })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(/contact LawHand/i)
  })

  it('tells a non-admin who to ask instead of offering a link they cannot use', () => {
    renderBanner({ user: { access_state: 'trial_expired' }, canManageBilling: false })
    expect(screen.queryByRole('link', { name: /subscribe now/i })).not.toBeInTheDocument()
    expect(screen.getByText(/ask a firm administrator/i)).toBeInTheDocument()
  })

  it('mentions premium AI only while the trial is still running', () => {
    const { unmount } = renderBanner({
      user: { access_state: 'trial', trial_ends_at: inDays(5), premium_ai_available: false },
    })
    expect(screen.getByRole('status')).toHaveTextContent(/premium ai is available after you subscribe/i)
    unmount()
    cleanup()

    renderBanner({ user: { access_state: 'trial_expired', premium_ai_available: false } })
    expect(screen.getByRole('status')).not.toHaveTextContent(/premium ai/i)
  })

  it('never nags a demo session, which has its own banner', () => {
    expect(resolveTrialState({ access_state: 'trial', trial_ends_at: inDays(3), demo: { quota: 10 } })).toBeNull()
  })

  it('ignores a trial with no end date and an unknown state', () => {
    expect(resolveTrialState({ access_state: 'trial' }, NOW)).toBeNull()
    expect(resolveTrialState({ access_state: 'something_else' }, NOW)).toBeNull()
    expect(resolveTrialState(null, NOW)).toBeNull()
  })

  it('never reports a negative countdown', () => {
    expect(trialDaysLeft(inDays(-9), NOW)).toBe(0)
    expect(trialDaysLeft(null, NOW)).toBeNull()
    expect(trialDaysLeft('not a date', NOW)).toBeNull()
  })
})
