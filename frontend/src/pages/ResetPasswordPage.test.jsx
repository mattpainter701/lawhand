import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ResetPasswordPage from './ResetPasswordPage'

vi.mock('../api', () => ({ resetPassword: vi.fn() }))

function AcceptProbe() {
  const location = useLocation()
  return <p>accept page {location.search}</p>
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/accept-invite" element={<AcceptProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('reset password', () => {
  afterEach(() => cleanup())

  it('hands an old invitation link to the accept page', () => {
    // Invitation emails sent before the accept page existed point at the
    // reset page, which cannot redeem an invitation.
    renderAt('/reset-password?token=abc%2Bdef&invite=1')

    expect(screen.getByText('accept page ?token=abc%2Bdef')).toBeInTheDocument()
  })

  it('keeps an ordinary reset link on the reset form', () => {
    renderAt('/reset-password?token=reset-token')

    expect(screen.getByRole('heading', { name: /Set new password/i })).toBeInTheDocument()
  })
})
