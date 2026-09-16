import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TrialAccessControls } from './PlatformPage'

const tenant = {
  id: 'tenant-1',
  expires_at: '2026-10-15T23:59:59.000Z',
  premium_ai_trial_enabled: false,
}

afterEach(cleanup)

describe('Platform trial access controls', () => {
  it('extends a trial and surfaces successful customer email delivery', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn().mockResolvedValue({ trial_email_status: 'sent' })
    render(<TrialAccessControls tenant={tenant} onPatch={onPatch} />)

    await user.click(screen.getByRole('button', { name: 'Extend 6 months' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledOnce())
    expect(onPatch.mock.calls[0][0].trial_ends_at).toMatch(/^2027-04-15T/)
    expect(await screen.findByRole('status')).toHaveTextContent('firm administrators were emailed')
  })

  it('makes the premium cost override explicit and reversible', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn().mockResolvedValue({ trial_email_status: null })
    const { rerender } = render(<TrialAccessControls tenant={tenant} onPatch={onPatch} />)

    await user.click(screen.getByRole('button', { name: 'Enable Premium AI' }))
    expect(onPatch).toHaveBeenLastCalledWith({ premium_ai_trial_enabled: true })

    rerender(
      <TrialAccessControls
        tenant={{ ...tenant, premium_ai_trial_enabled: true }}
        onPatch={onPatch}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Disable Premium AI' }))
    expect(onPatch).toHaveBeenLastCalledWith({ premium_ai_trial_enabled: false })
  })

  it('uses an explicit past expiration for immediate revocation', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn().mockResolvedValue({ trial_email_status: null })
    render(<TrialAccessControls tenant={tenant} onPatch={onPatch} />)

    await user.click(screen.getByRole('button', { name: 'Revoke trial now' }))
    const sent = new Date(onPatch.mock.calls[0][0].trial_ends_at)
    expect(sent.getTime()).toBeLessThanOrEqual(Date.now())
  })
})
