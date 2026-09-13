import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import BillingFees from './BillingFees'
import BillingSchedule from './BillingSchedule'
import InvoicePaymentPlan from './InvoicePaymentPlan'
import ReadyToBill from './ReadyToBill'
import * as api from '../api'

vi.mock('../api', () => ({
  getBillingFees: vi.fn(), createBillingFee: vi.fn(), updateBillingFee: vi.fn(),
  getBillingSchedules: vi.fn(), createBillingSchedule: vi.fn(), pauseBillingSchedule: vi.fn(),
  setInvoicePaymentPlan: vi.fn(), getReadyToBill: vi.fn(),
}))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('records a stage as pending and explicitly marks it ready', async () => {
  api.getBillingFees.mockResolvedValueOnce({ items: [] }).mockResolvedValue({ items: [{ id: 'stage', description: 'Filing', amount: '300', service_date: '2026-09-01', status: 'pending' }] })
  api.createBillingFee.mockResolvedValue({})
  api.updateBillingFee.mockResolvedValue({})
  const changed = vi.fn()
  const user = userEvent.setup()
  render(<BillingFees matterId="matter" onChange={changed} />)
  await user.type(screen.getByLabelText('Stage description'), 'Filing')
  await user.type(screen.getByLabelText('Agreed amount'), '300')
  fireEvent.change(screen.getByLabelText('Stage billing date'), { target: { value: '2026-09-01' } })
  await user.click(screen.getByRole('button', { name: 'Add stage fee' }))
  await waitFor(() => expect(api.createBillingFee).toHaveBeenCalledWith({ matter_id: 'matter', description: 'Filing', amount: '300', service_date: '2026-09-01' }))
  await user.click(await screen.findByRole('button', { name: 'Mark ready' }))
  await waitFor(() => expect(api.updateBillingFee).toHaveBeenCalledWith('stage', 'ready'))
  expect(changed).toHaveBeenCalled()
})

it('does not enable recurring billing until the user opts in', async () => {
  api.getBillingSchedules.mockResolvedValue({ items: [] })
  api.createBillingSchedule.mockResolvedValue({ id: 'schedule', next_date: '2026-10-01', paused: false, config: { timezone: 'UTC' } })
  api.pauseBillingSchedule.mockResolvedValue({ id: 'schedule', next_date: '2026-10-01', paused: true, config: { timezone: 'UTC' } })
  const user = userEvent.setup()
  render(<BillingSchedule matterId="matter" />)
  const date = await screen.findByLabelText('First recurring invoice date')
  expect(api.createBillingSchedule).not.toHaveBeenCalled()
  fireEvent.change(date, { target: { value: '2026-10-01' } })
  await user.click(screen.getByRole('button', { name: 'Enable recurring drafts' }))
  await waitFor(() => expect(api.createBillingSchedule).toHaveBeenCalledWith(expect.objectContaining({ matter_id: 'matter', first_invoice_date: '2026-10-01', include_unbilled_work: true })))
  await user.click(await screen.findByRole('button', { name: 'Pause recurring drafts' }))
  await waitFor(() => expect(api.pauseBillingSchedule).toHaveBeenCalledWith('schedule', true))
  expect(await screen.findByRole('button', { name: 'Resume recurring drafts' })).toBeInTheDocument()
})

it('keeps a failed installment edit visible and prevents edits after payment', async () => {
  api.setInvoicePaymentPlan.mockRejectedValue({ response: { data: { detail: 'Installments must equal the invoice total' } } })
  const invoice = { id: 'invoice', issue_date: '2026-09-01', status: 'draft', amount_paid: '0', billing_details: {} }
  const saved = vi.fn()
  const user = userEvent.setup()
  const view = render(<InvoicePaymentPlan invoice={invoice} onSaved={saved} />)
  await user.click(screen.getByRole('button', { name: 'Add installment' }))
  fireEvent.change(screen.getByLabelText('Installment date 1'), { target: { value: '2026-10-01' } })
  await user.type(screen.getByLabelText('Installment amount 1'), '50')
  await user.click(screen.getByRole('button', { name: 'Save payment plan' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Installments must equal')
  expect(screen.getByLabelText('Installment amount 1')).toHaveValue(50)
  expect(saved).not.toHaveBeenCalled()
  view.rerender(<InvoicePaymentPlan invoice={{ ...invoice, status: 'partially_paid', amount_paid: '25' }} onSaved={saved} />)
  expect(screen.queryByRole('button', { name: 'Save payment plan' })).not.toBeInTheDocument()
  expect(screen.getByLabelText('Installment amount 1')).toBeDisabled()
})

it('searches closed-matter work and opens the selected review', async () => {
  const row = { matter_id: 'closed', matter_name: 'Closing matter', closed: true, count: 1, amount: '450', oldest: '2026-08-01' }
  api.getReadyToBill.mockResolvedValue({ items: [row], total: 1, total_amount: '450' })
  const selected = vi.fn()
  const user = userEvent.setup()
  render(<ReadyToBill cutoff="2026-09-30" onSelect={selected} />)
  await user.click(await screen.findByRole('button', { name: 'Review work' }))
  expect(selected).toHaveBeenCalledWith(row)
  await user.type(screen.getByLabelText('Find matter'), 'Closing')
  await waitFor(() => expect(api.getReadyToBill).toHaveBeenCalledWith({ q: 'Closing', page: 1, date_to: '2026-09-30' }))
})
