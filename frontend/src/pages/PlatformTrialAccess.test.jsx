import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConfirmProvider } from '../components/dialog/ConfirmProvider'
import { PendingTrialApproval, ProvisionTrialTenantForm, TrialAccessControls } from './PlatformPage'

const tenant = {
  id: 'tenant-1',
  name: 'Northwind Legal',
  expires_at: '2026-10-15T23:59:59.000Z',
  premium_ai_trial_enabled: false,
}

const renderControls = (props) => render(
  <ConfirmProvider>
    <TrialAccessControls {...props} />
  </ConfirmProvider>,
)

afterEach(cleanup)

describe('Platform trial access controls', () => {
  it('extends a trial and surfaces successful customer email delivery', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn().mockResolvedValue({ trial_email_status: 'sent' })
    renderControls({ tenant, onPatch })

    await user.click(screen.getByRole('button', { name: 'Extend 6 months' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledOnce())
    expect(onPatch.mock.calls[0][0].trial_ends_at).toMatch(/^2027-04-15T/)
    expect(await screen.findByRole('status')).toHaveTextContent('firm administrators were emailed')
  })

  it('makes the premium cost override explicit and reversible', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn().mockResolvedValue({ trial_email_status: null })
    const { rerender } = renderControls({ tenant, onPatch })

    await user.click(screen.getByRole('button', { name: 'Enable Premium AI' }))
    // Sponsoring Premium AI spends LawHand's money, so it asks first.
    expect(screen.getByRole('alertdialog')).toHaveTextContent("at LawHand's cost")
    expect(onPatch).not.toHaveBeenCalled()
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Enable Premium AI' }))
    expect(onPatch).toHaveBeenLastCalledWith({ premium_ai_trial_enabled: true })

    rerender(
      <ConfirmProvider>
        <TrialAccessControls
          tenant={{ ...tenant, premium_ai_trial_enabled: true }}
          onPatch={onPatch}
        />
      </ConfirmProvider>,
    )
    // Turning the sponsorship off needs no confirmation.
    await user.click(screen.getByRole('button', { name: 'Disable Premium AI' }))
    expect(onPatch).toHaveBeenLastCalledWith({ premium_ai_trial_enabled: false })
  })

  it('uses an explicit past expiration for immediate revocation', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn().mockResolvedValue({ trial_email_status: null })
    renderControls({ tenant, onPatch })

    await user.click(screen.getByRole('button', { name: 'End access now' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Northwind Legal loses workspace access immediately')
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'End access now' }))
    const sent = new Date(onPatch.mock.calls[0][0].trial_ends_at)
    expect(sent.getTime()).toBeLessThanOrEqual(Date.now())
  })

  it('does nothing when the operator cancels ending access or removing the expiry', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn()
    renderControls({ tenant, onPatch })

    await user.click(screen.getByRole('button', { name: 'End access now' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Convert to active' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('no longer treated as a trial')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onPatch).not.toHaveBeenCalled()
  })
})

describe('Platform customer registration', () => {
  it('creates a six-month sponsored trial and surfaces invitation delivery', async () => {
    const user = userEvent.setup()
    const onProvision = vi.fn().mockResolvedValue({
      email_status: 'sent',
      invitation_url: 'https://app.example/accept-invite?token=once',
    })
    render(<ProvisionTrialTenantForm onProvision={onProvision} />)

    await user.type(screen.getByLabelText('Firm name'), 'Founding Law PLLC')
    await user.type(screen.getByLabelText('Attorney email'), 'founder@example.com')
    await user.type(screen.getByLabelText('Attorney name'), 'Founding Attorney')
    await user.click(screen.getByRole('button', { name: 'Use 6 months' }))
    await user.click(screen.getByRole('checkbox', { name: 'Sponsor Premium AI' }))
    await user.click(screen.getByRole('button', { name: 'Create trial and send invite' }))

    await waitFor(() => expect(onProvision).toHaveBeenCalledOnce())
    expect(onProvision).toHaveBeenCalledWith({
      firm_name: 'Founding Law PLLC',
      admin_email: 'founder@example.com',
      admin_name: 'Founding Attorney',
      trial_days: 180,
      plan: 'full-trial',
      premium_ai_trial_enabled: true,
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Email status: sent')
  })

  it('starts access only when the operator approves the pending firm', async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn().mockResolvedValue({ email_status: 'sent' })
    render(
      <PendingTrialApproval
        tenant={{ id: 'tenant-pending', name: 'Pending LLP', signup_status: 'pending' }}
        onApprove={onApprove}
      />,
    )

    expect(screen.getByText(/no workspace access, trial clock, or AI spend/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Use 6 months' }))
    await user.click(screen.getByRole('checkbox', { name: 'Sponsor Premium AI' }))
    await user.click(screen.getByRole('button', { name: 'Approve Pending LLP' }))

    expect(onApprove).toHaveBeenCalledWith({
      trial_days: 180,
      premium_ai_trial_enabled: true,
    })
    expect(await screen.findByRole('status')).toHaveTextContent('email status: sent')
  })
})
