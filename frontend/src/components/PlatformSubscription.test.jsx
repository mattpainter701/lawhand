import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import PlatformSubscription from './PlatformSubscription'
import api from '../api'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
afterEach(() => { cleanup(); vi.resetAllMocks(); delete window.appendHelcimPayIframe })

it('requires price review and consent before opening checkout', async () => {
  api.get.mockResolvedValue({ data: { name: 'Firm plan', currency: 'USD', recurring_amount: '100.00', setup_amount: '0.00', seats: 2, billing_period: 'monthly', billing_period_increments: 1, trial_days: 0, fingerprint: 'price' } })
  api.post.mockResolvedValue({ data: { checkout_token: 'token' } })
  window.appendHelcimPayIframe = vi.fn()
  const changed = vi.fn()
  render(<PlatformSubscription onChanged={changed} />)
  fireEvent.click(screen.getByText('Review subscription price'))
  const subscribe = await screen.findByText('Verify card and subscribe')
  expect(subscribe.disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(subscribe)
  await waitFor(() => expect(window.appendHelcimPayIframe).toHaveBeenCalledWith('token', true))
  expect(api.post).toHaveBeenCalledWith('/billing/subscription/checkout', { fingerprint: 'price', update_method: false })
  const message = { eventName: 'helcim-pay-js-token', eventStatus: 'SUCCESS', eventMessage: JSON.stringify({ data: { data: { status: 'APPROVED' }, hash: 'proof' } }) }
  window.dispatchEvent(new MessageEvent('message', { origin: 'https://attacker.example', data: message }))
  expect(changed).not.toHaveBeenCalled()
  window.dispatchEvent(new MessageEvent('message', { origin: 'https://secure.helcim.app', data: message }))
  await waitFor(() => expect(changed).toHaveBeenCalled())
  expect(api.post).toHaveBeenCalledWith('/billing/subscription/complete', { checkout_token: 'token', data: { status: 'APPROVED' }, signature: 'proof' })
})

it('keeps hosted card entry on the full billing page', () => {
  render(<PlatformSubscription embedded onChanged={vi.fn()} />)
  expect(screen.getByRole('link').getAttribute('href')).toBe('/billing')
  expect(api.get).not.toHaveBeenCalled()
})

it('requires explicit immediate-cancellation acknowledgment', async () => {
  api.post.mockResolvedValue({ data: {} })
  const changed = vi.fn()
  render(<PlatformSubscription subscription={{ has_subscription: true, subscription_status: 'active' }} onChanged={changed} />)
  const cancel = screen.getByText('Cancel subscription immediately')
  expect(cancel.disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(cancel)
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/billing/subscription/cancel'))
  expect(changed).toHaveBeenCalled()
})
