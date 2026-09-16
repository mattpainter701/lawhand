import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SignupPage from './SignupPage'
import { signupWithPlan } from '../api'

vi.mock('../api', () => ({
  signupWithPlan: vi.fn().mockResolvedValue({ status: 'pending_approval' }),
}))

describe('plan signup', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
  })

  it('requests the selected intake plan without opening a session', async () => {
    vi.stubEnv('VITE_PUBLIC_SIGNUP_ENABLED', 'true')
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/signup?plan=intake-only']}>
        <SignupPage />
      </MemoryRouter>
    )

    expect(screen.getByText('Call Intake + Tasks')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /sign up with google/i })).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('Firm / Company Name'), 'Launch Firm')
    await user.type(screen.getByLabelText('Email *'), 'owner@launchfirm.com')
    await user.type(screen.getByLabelText('Password *'), 'LaunchReadyPass123!')
    await user.type(screen.getByLabelText('Your Name'), 'Owner One')
    await user.click(screen.getByRole('button', { name: 'Request LawHand access' }))

    expect(signupWithPlan).toHaveBeenCalledWith(expect.objectContaining({
      plan: 'intake-only',
      firm_name: 'Launch Firm',
      email: 'owner@launchfirm.com',
    }))
    expect(await screen.findByRole('heading', { name: 'Registration received' })).toBeInTheDocument()
    expect(screen.getByText(/No trial time has started yet/i)).toBeInTheDocument()
  })

  it('routes launch visitors to operator-assisted provisioning', () => {
    vi.stubEnv('VITE_PUBLIC_SIGNUP_ENABLED', 'false')
    render(
      <MemoryRouter initialEntries={['/signup?plan=intake-only']}>
        <SignupPage />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: 'Request access' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Contact the LawHand team' })).toHaveAttribute(
      'href',
      '/request-demo?source=signup',
    )
    expect(screen.queryByRole('button', { name: 'Request LawHand access' })).not.toBeInTheDocument()
  })
})
