import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfirmProvider } from '../../components/dialog/ConfirmProvider'
import { revokePlatformTenantTrial } from '../../api'
import { ReleaseTrialLogin, TenantAccountControls } from './TenantControls'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal()),
  revokePlatformTenantTrial: vi.fn(),
}))

const firm = {
  id: 'tenant-1',
  name: 'Northwind Legal',
  is_active: true,
  billing_tier: 'payg',
  flat_seat_count: 3,
  mcp_entitlement_status: 'enabled',
  mcp_billing_status: 'active',
}

const renderControls = (props) => render(
  <ConfirmProvider>
    <TenantAccountControls {...props} />
  </ConfirmProvider>,
)

const dialog = () => screen.getByRole('alertdialog')

beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

describe('tenant account controls', () => {
  it('asks before locking a whole firm out', async () => {
    const onPatch = vi.fn().mockResolvedValue({})
    const user = userEvent.setup()
    renderControls({ tenant: firm, onPatch })

    await user.click(screen.getByRole('button', { name: 'Deactivate firm' }))
    expect(dialog()).toHaveTextContent('Every user at the firm loses access immediately')
    await user.click(within(dialog()).getByRole('button', { name: 'Cancel' }))
    expect(onPatch).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Deactivate firm' }))
    await user.click(within(dialog()).getByRole('button', { name: 'Deactivate firm' }))
    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({ is_active: false }))
    expect(await screen.findByRole('status')).toHaveTextContent('Firm deactivated.')
  })

  it('reactivates without a prompt', async () => {
    const onPatch = vi.fn().mockResolvedValue({})
    const user = userEvent.setup()
    renderControls({ tenant: { ...firm, is_active: false }, onPatch })

    await user.click(screen.getByRole('button', { name: 'Activate firm' }))
    expect(onPatch).toHaveBeenCalledWith({ is_active: true })
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('confirms a billing model change and ignores the current one', async () => {
    const onPatch = vi.fn().mockResolvedValue({})
    const user = userEvent.setup()
    renderControls({ tenant: firm, onPatch })

    await user.click(screen.getByRole('button', { name: 'PAYG' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Flat-seat' }))
    expect(dialog()).toHaveTextContent('Switch Northwind Legal to flat-seat billing?')
    await user.click(within(dialog()).getByRole('button', { name: 'Use flat-seat' }))
    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({ billing_tier: 'flat' }))
  })

  it('edits seats and the Research MCP entitlement that were read-only before', async () => {
    const onPatch = vi.fn().mockResolvedValue({})
    const user = userEvent.setup()
    renderControls({ tenant: firm, onPatch })

    const seats = screen.getByLabelText('Seats')
    expect(screen.getByRole('button', { name: 'Save seats' })).toBeDisabled()
    await user.clear(seats)
    await user.type(seats, '5')
    await user.click(screen.getByRole('button', { name: 'Save seats' }))
    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({ seat_count: 5 }))

    await user.selectOptions(screen.getByLabelText('Research MCP entitlement'), 'suspended')
    await user.click(screen.getByRole('button', { name: 'Save entitlement' }))
    expect(dialog()).toHaveTextContent('Research MCP keys stop working')
    await user.click(within(dialog()).getByRole('button', { name: 'Suspend' }))
    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({ mcp_entitlement_status: 'suspended' }))
  })

  it('shows why the server refused a change', async () => {
    const onPatch = vi.fn().mockRejectedValue(Object.assign(new Error('conflict'), {
      response: { status: 409, data: { detail: 'Use the demo workspace panel to terminate disposable demos' } },
    }))
    const user = userEvent.setup()
    renderControls({ tenant: { ...firm, is_active: false }, onPatch })

    await user.click(screen.getByRole('button', { name: 'Activate firm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Use the demo workspace panel')
  })
})

describe('release trial login', () => {
  const users = [{ id: 'u1', email: 'Owner@Northwind.example' }]

  it('only arms once a login at this firm is typed, then revokes', async () => {
    revokePlatformTenantTrial.mockResolvedValue({
      tenant_id: 'tenant-1', released_emails: ['owner@northwind.example'], users_revoked: 1, credentials_revoked: 2,
    })
    const onRevoked = vi.fn()
    const user = userEvent.setup()
    render(<ReleaseTrialLogin tenant={firm} users={users} platformKey="token" onRevoked={onRevoked} />)

    const submit = screen.getByRole('button', { name: 'Revoke trial' })
    const address = screen.getByLabelText(/Type a login address/)
    await user.type(address, 'someone@else.example')
    expect(submit).toBeDisabled()
    expect(screen.getByText('That address is not a login at this firm.')).toBeInTheDocument()

    await user.clear(address)
    await user.type(address, 'owner@northwind.example')
    await user.type(screen.getByLabelText(/Reason/), 'Abandoned test trial')
    await user.click(submit)

    await waitFor(() => expect(revokePlatformTenantTrial).toHaveBeenCalledWith('token', 'tenant-1', {
      confirm_email: 'owner@northwind.example', reason: 'Abandoned test trial',
    }))
    expect(await screen.findByRole('status')).toHaveTextContent('1 login deactivated and 2 stored credentials removed')
    expect(onRevoked).toHaveBeenCalled()
  })

  it('surfaces the refusal for a firm with work product', async () => {
    revokePlatformTenantTrial.mockRejectedValue(Object.assign(new Error('conflict'), {
      response: { status: 409, data: { detail: 'Tenant holds customer work product; revoke is refused: matters=2' } },
    }))
    const user = userEvent.setup()
    render(<ReleaseTrialLogin tenant={firm} users={users} platformKey="token" />)

    await user.type(screen.getByLabelText(/Type a login address/), 'owner@northwind.example')
    await user.click(screen.getByRole('button', { name: 'Revoke trial' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('matters=2')
  })
})
