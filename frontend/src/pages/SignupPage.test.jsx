import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SignupPage from './SignupPage'
import { signupWithPlan } from '../api'

const { login } = vi.hoisted(() => ({ login: vi.fn() }))

vi.mock('../api', () => ({
  signupWithPlan: vi.fn(),
}))

vi.mock('../App', () => ({
  useAuth: () => ({ login }),
}))

async function fillAndSubmit(buttonName) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Firm / Company Name'), 'Launch Firm')
  await user.type(screen.getByLabelText('Email *'), 'owner@launchfirm.com')
  await user.type(screen.getByLabelText('Password *'), 'LaunchReadyPass123!')
  await user.type(screen.getByLabelText('Your Name'), 'Owner One')
  await user.click(screen.getByRole('button', { name: buttonName }))
}

describe('plan signup', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.clearAllMocks()
  })

  it('auto-starts a trial by default and opens the session', async () => {
    vi.stubEnv('VITE_PUBLIC_SIGNUP_ENABLED', 'true')
    login.mockResolvedValue({ default_route: '/matters' })
    signupWithPlan.mockResolvedValue({ user_id: 'u-1', tenant_id: 't-1' })

    render(
      <MemoryRouter initialEntries={['/signup?plan=intake-only']}>
        <SignupPage />
      </MemoryRouter>
    )

    expect(screen.getByText('Call Intake + Tasks')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /sign up with google/i })).not.toBeInTheDocument()

    await fillAndSubmit('Start free trial')

    expect(signupWithPlan).toHaveBeenCalledWith(expect.objectContaining({
      plan: 'intake-only',
      firm_name: 'Launch Firm',
      email: 'owner@launchfirm.com',
    }))
    expect(login).toHaveBeenCalled()
    expect(screen.queryByText(/Registration received/i)).not.toBeInTheDocument()
  })

  it('shows the pending screen in approval-gated mode', async () => {
    vi.stubEnv('VITE_PUBLIC_SIGNUP_ENABLED', 'true')
    vi.stubEnv('VITE_PUBLIC_SIGNUP_REQUIRES_APPROVAL', 'true')
    signupWithPlan.mockResolvedValue({ status: 'pending_approval' })

    render(
      <MemoryRouter initialEntries={['/signup?plan=intake-only']}>
        <SignupPage />
      </MemoryRouter>
    )

    await fillAndSubmit('Request LawHand access')

    expect(login).not.toHaveBeenCalled()
    expect(await screen.findByRole('heading', { name: 'Registration received' })).toBeInTheDocument()
    expect(screen.getByText(/pending approval/i)).toBeInTheDocument()
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
    expect(screen.queryByRole('button', { name: 'Start free trial' })).not.toBeInTheDocument()
  })
})
