import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CommunicationsPage from './CommunicationsPage'
import { getCommunications, getMattersV2, updateCommunication } from '../api'

vi.mock('../api', () => ({
  getCommunications: vi.fn(),
  createCommunication: vi.fn(),
  updateCommunication: vi.fn(),
  deleteCommunication: vi.fn(),
  scanEmailInbox: vi.fn(),
  searchContacts: vi.fn(),
  getContacts: vi.fn().mockResolvedValue({ items: [] }),
  getMattersV2: vi.fn(),
  matterCorrespondenceDownloadUrl: (matterId, commId) => `/api/matters/${matterId}/correspondence/${commId}/download`,
}))
vi.mock('../components/dialog/ConfirmProvider', () => ({ useConfirm: () => vi.fn().mockResolvedValue(true) }))
vi.mock('../components/toast/useToast', () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }))

describe('CommunicationsPage', () => {
  afterEach(cleanup)
  beforeEach(() => {
    vi.clearAllMocks()
    getCommunications.mockImplementation(({ offset }) => Promise.resolve({
      items: [{ id: `communication-${offset}`, channel: 'email', direction: 'inbound', subject: `Page ${offset}` }],
      total: 100,
    }))
  })

  it('resets pagination in the same filter update without refetching the old page', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><CommunicationsPage /></MemoryRouter>)
    await waitFor(() => expect(getCommunications).toHaveBeenCalledWith(expect.objectContaining({ offset: 0 })))

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(getCommunications).toHaveBeenCalledWith(expect.objectContaining({ offset: 50 })))
    await user.click(screen.getByRole('button', { name: 'Email' }))
    await waitFor(() => expect(getCommunications).toHaveBeenCalledTimes(3))

    expect(getCommunications.mock.calls.map(([params]) => params.offset)).toEqual([0, 50, 0])
  })

  it.each(['success', 'failure'])('ignores a late %s for the previous filter', async (outcome) => {
    let resolveOld, rejectOld
    getCommunications.mockReturnValueOnce(new Promise((resolve, reject) => {
      resolveOld = resolve; rejectOld = reject
    })).mockResolvedValueOnce({
      items: [{ id: 'current', channel: 'email', direction: 'inbound', subject: 'Current filtered message' }],
      total: 1,
    })
    const user = userEvent.setup()
    render(<MemoryRouter><CommunicationsPage /></MemoryRouter>)
    await user.click(screen.getByRole('button', { name: 'Email' }))
    expect(await screen.findByText('Current filtered message')).toBeInTheDocument()
    await act(async () => {
      if (outcome === 'success') resolveOld({ items: [{ id: 'stale', subject: 'Stale message' }], total: 100 })
      else rejectOld(new Error('Old request failed'))
    })
    expect(screen.getByText('Current filtered message')).toBeInTheDocument()
    expect(screen.queryByText('Stale message')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  const captured = {
    id: 'comm-1',
    channel: 'email',
    direction: 'inbound',
    subject: 'Hearing moved',
    body: 'The hearing is now on the 14th.',
    summary: 'Hearing date change',
    matter_id: 'matter-1',
    matter_name: 'Smith Divorce',
    matter_number: 'M-0042',
    contact_id: 'contact-1',
    contact_name: 'Jane Smith',
    document_id: 'doc-1',
    content_locked: true,
  }

  it('names the matter and contact and links back to them', async () => {
    getCommunications.mockResolvedValue({ items: [captured], total: 1 })
    render(<MemoryRouter><CommunicationsPage /></MemoryRouter>)

    const matterLink = await screen.findByRole('link', { name: 'Smith Divorce (M-0042)' })
    expect(matterLink).toHaveAttribute('href', '/matters/matter-1?tab=correspondence')
    expect(screen.getByRole('link', { name: 'Jane Smith' })).toHaveAttribute('href', '/contacts/contact-1')
    expect(screen.queryByText(/matter-1/)).not.toBeInTheDocument()
  })

  it('opens the record with its original message', async () => {
    getCommunications.mockResolvedValue({ items: [captured], total: 1 })
    const user = userEvent.setup()
    render(<MemoryRouter><CommunicationsPage /></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: 'Hearing moved' }))
    expect(screen.getByText('The hearing is now on the 14th.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Download original/ })).toHaveAttribute(
      'href',
      '/api/matters/matter-1/correspondence/comm-1/download',
    )
  })

  it('only lets a captured message be moved, never rewritten', async () => {
    getCommunications.mockResolvedValue({ items: [captured], total: 1 })
    getMattersV2.mockResolvedValue({ items: [{ id: 'matter-2', matter_name: 'Smith Custody', matter_number: 'M-0043' }] })
    updateCommunication.mockResolvedValue({ ...captured, matter_id: 'matter-2' })
    const user = userEvent.setup()
    render(<MemoryRouter><CommunicationsPage /></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: 'Move to another matter' }))
    expect(screen.queryByLabelText(/Subject/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Body')).not.toBeInTheDocument()

    const dialog = screen.getByRole('dialog', { name: 'Move to another matter' })
    await user.click(within(dialog).getByRole('button', { name: 'Change matter' }))
    await user.type(within(dialog).getByRole('textbox', { name: 'Matter' }), 'Custody')
    await user.click(await within(dialog).findByRole('button', { name: /Smith Custody/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Move' }))

    await waitFor(() => expect(updateCommunication).toHaveBeenCalledWith('comm-1', { matter_id: 'matter-2' }))
  })

  it('sends only the fields that changed on a hand-logged entry', async () => {
    const logged = { ...captured, id: 'comm-2', subject: 'Call with Jane', content_locked: false, document_id: null }
    getCommunications.mockResolvedValue({ items: [logged], total: 1 })
    updateCommunication.mockResolvedValue(logged)
    const user = userEvent.setup()
    render(<MemoryRouter><CommunicationsPage /></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    const summary = screen.getByLabelText('Summary')
    await user.clear(summary)
    await user.type(summary, 'Agreed to mediate')
    await user.click(screen.getByRole('button', { name: 'Save Changes' }))

    await waitFor(() => expect(updateCommunication).toHaveBeenCalledWith('comm-2', { summary: 'Agreed to mediate' }))
  })
})
