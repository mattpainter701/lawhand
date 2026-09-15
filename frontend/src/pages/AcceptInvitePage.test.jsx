import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { axe } from 'jest-axe'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AcceptInvitePage from './AcceptInvitePage'
import { acceptInvitation, loginGoogle, loginMicrosoft, lookupInvitation } from '../api'

const authLogin = vi.fn()

vi.mock('../App', () => ({ useAuth: () => ({ login: authLogin }) }))
vi.mock('../api', () => ({
  lookupInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
  loginGoogle: vi.fn(),
  loginMicrosoft: vi.fn(),
}))

const pendingInvitation = {
  email_masked: 'j•••@firm.com',
  full_name: 'Jane Doe',
  firm_name: 'Doe & Partners',
  expires_at: '2026-09-22T12:00:00Z',
  providers: { password: true, google: true, microsoft: true },
}

const refusal = (code, status = 400) => Object.assign(new Error(code), {
  response: { status, data: { code, detail: 'server text' } },
})

function renderAt(path = '/accept-invite?token=raw-token') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/accept-invite" element={<AcceptInvitePage />} />
        <Route path="/matters" element={<p>Matters home</p>} />
        <Route path="/login" element={<p>Sign in page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('accept invitation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authLogin.mockResolvedValue({ default_route: '/matters' })
  })
  afterEach(() => cleanup())

  it('names the firm and masked address without axe violations', async () => {
    lookupInvitation.mockResolvedValue(pendingInvitation)
    const { container } = renderAt()

    expect(await screen.findByRole('heading', { name: /Doe & Partners/ })).toBeInTheDocument()
    expect(screen.getAllByText(/j•••@firm\.com/).length).toBeGreaterThan(0)
    expect(lookupInvitation).toHaveBeenCalledWith('raw-token')
    expect(screen.getByLabelText(/Choose a password/i)).toHaveAttribute('autocomplete', 'new-password')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('accepts with a password, signs in, and opens the workspace', async () => {
    lookupInvitation.mockResolvedValue(pendingInvitation)
    acceptInvitation.mockResolvedValue({ user_id: 'u1' })
    const user = userEvent.setup()
    renderAt()

    await user.type(await screen.findByLabelText(/Choose a password/i), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Accept invitation' }))

    expect(await screen.findByText('Matters home')).toBeInTheDocument()
    expect(acceptInvitation).toHaveBeenCalledWith('raw-token', 'correct-horse-battery')
    expect(authLogin).toHaveBeenCalled()
  })

  it('refuses a short password before calling the server', async () => {
    lookupInvitation.mockResolvedValue(pendingInvitation)
    const user = userEvent.setup()
    renderAt()

    await user.type(await screen.findByLabelText(/Choose a password/i), 'short')
    await user.click(screen.getByRole('button', { name: 'Accept invitation' }))

    expect(screen.getByRole('alert')).toHaveTextContent(/at least 12 characters/i)
    expect(acceptInvitation).not.toHaveBeenCalled()
  })

  it('sends the invitation token with Google and Microsoft sign-in', async () => {
    lookupInvitation.mockResolvedValue(pendingInvitation)
    const user = userEvent.setup()
    renderAt()

    await user.click(await screen.findByRole('button', { name: 'Continue with Google' }))
    await user.click(screen.getByRole('button', { name: 'Continue with Microsoft' }))

    expect(loginGoogle).toHaveBeenCalledWith(null, { invite: 'raw-token' })
    expect(loginMicrosoft).toHaveBeenCalledWith(null, { invite: 'raw-token' })
  })

  it('hides provider buttons that are not configured', async () => {
    lookupInvitation.mockResolvedValue({
      ...pendingInvitation,
      providers: { password: true, google: false, microsoft: false },
    })
    renderAt()

    expect(await screen.findByLabelText(/Choose a password/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Continue with/ })).not.toBeInTheDocument()
  })

  it.each([
    ['invite_expired', /expired/i, /Go to sign in/i],
    ['invite_accepted', /already been used/i, /^Sign in$/],
    ['invite_invalid', /not valid/i, /Go to sign in/i],
  ])('explains a %s link without showing server text', async (code, message, linkName) => {
    lookupInvitation.mockRejectedValue(refusal(code))
    renderAt()

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByText('server text')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: linkName })).toHaveAttribute('href', '/login')
  })

  it('treats a missing token as an invalid link without calling the server', async () => {
    renderAt('/accept-invite')

    expect(await screen.findByRole('alert')).toHaveTextContent(/not valid/i)
    expect(lookupInvitation).not.toHaveBeenCalled()
  })

  it('shows the refusal if the invitation is used up while the page is open', async () => {
    lookupInvitation.mockResolvedValue(pendingInvitation)
    acceptInvitation.mockRejectedValue(refusal('invite_accepted'))
    const user = userEvent.setup()
    renderAt()

    await user.type(await screen.findByLabelText(/Choose a password/i), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Accept invitation' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/already been used/i))
    expect(authLogin).not.toHaveBeenCalled()
  })
})
