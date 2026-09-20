import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import FillSessionsList from './FillSessionsList'
import { abandonFillSession, getMatterFillSessions } from '../../api'

vi.mock('../../api', () => ({ getMatterFillSessions: vi.fn(), abandonFillSession: vi.fn() }))
afterEach(cleanup)
const M = '22222222-2222-4222-8222-222222222222'
const S = '55555555-5555-4555-8555-555555555555'
const X = '99999999-9999-4999-8999-999999999999'
beforeEach(() => {
  vi.clearAllMocks()
  getMatterFillSessions.mockResolvedValue({ items: [
    { id: X, set_id: S, template_id: null, title: 'Motion packet', status: 'saving', members: [{ template_id: 'a', status: 'saved' }, { template_id: 'b', status: 'queued' }] },
  ] })
  abandonFillSession.mockResolvedValue(null)
})

it('lists the packets in progress, resumes one, and discards one', async () => {
  const onResume = vi.fn()
  render(<FillSessionsList matterId={M} onResume={onResume} />)
  const region = await screen.findByRole('region', { name: 'Documents in progress' })
  expect(region).toHaveTextContent('Motion packet')
  expect(region).toHaveTextContent('Saving in the background… · 1 of 2 saved')
  fireEvent.click(screen.getByRole('button', { name: 'Resume' }))
  expect(onResume).toHaveBeenCalledWith(`/templates/prepare?set=${S}&matter=${M}&session=${X}&return=%2Fmatters%2F${M}%3Ftab%3Ddocuments`)
  fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
  await waitFor(() => expect(abandonFillSession).toHaveBeenCalledWith(X))
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Documents in progress' })).not.toBeInTheDocument())
})

it('renders nothing when the matter has no packet in progress', async () => {
  getMatterFillSessions.mockResolvedValue({ items: [] })
  const { container } = render(<FillSessionsList matterId={M} onResume={vi.fn()} />)
  await waitFor(() => expect(getMatterFillSessions).toHaveBeenCalled())
  expect(container).toBeEmptyDOMElement()
})
