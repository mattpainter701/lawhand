import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import NewMatterModal from './NewMatterModal'

const mocks = vi.hoisted(() => ({
  createMatterV2: vi.fn(), getContacts: vi.fn(), getAdminUsers: vi.fn(), getPlugins: vi.fn(),
  createContact: vi.fn(), recordMatterEngagement: vi.fn(),
  getMatterCsvTemplate: vi.fn(), previewMatterCsvImport: vi.fn(), confirmMatterCsvImport: vi.fn(), getMatterCsvImport: vi.fn(),
  getMattersV2: vi.fn(), post: vi.fn(), get: vi.fn(),
}))
vi.mock('../api', () => ({
  default: { post: mocks.post, get: mocks.get },
  createMatterV2: mocks.createMatterV2, getContacts: mocks.getContacts, getAdminUsers: mocks.getAdminUsers,
  getPlugins: mocks.getPlugins, createContact: mocks.createContact, recordMatterEngagement: mocks.recordMatterEngagement,
  getMatterCsvTemplate: mocks.getMatterCsvTemplate, previewMatterCsvImport: mocks.previewMatterCsvImport,
  confirmMatterCsvImport: mocks.confirmMatterCsvImport, getMatterCsvImport: mocks.getMatterCsvImport,
  getMattersV2: mocks.getMattersV2,
}))

const today = new Date().toISOString().slice(0, 10)
const created = { id: 'matter-1', matter_number: 'SMIT0007', matter_name: 'Smith transfer' }

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getContacts.mockResolvedValue([])
  mocks.getAdminUsers.mockResolvedValue([])
  mocks.getPlugins.mockResolvedValue([])
  mocks.createMatterV2.mockResolvedValue(created)
  mocks.recordMatterEngagement.mockResolvedValue({ matter_id: 'matter-1', engagement: { status: 'no_agreement' }, stage: 'Active' })
})
afterEach(cleanup)

function renderModal(props = {}) {
  return render(<MemoryRouter><NewMatterModal open onClose={vi.fn()} onCreated={vi.fn()} {...props} /></MemoryRouter>)
}

describe('new matter modal', () => {
  it('sends the open date, defaulting to today, and no engagement for a new engagement', async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    const onClose = vi.fn()
    renderModal({ onCreated, onClose })

    expect(screen.getByLabelText('Open date')).toHaveValue(today)
    await user.type(screen.getByLabelText(/Matter Title/), 'Smith transfer')
    fireEvent.change(screen.getByLabelText('Open date'), { target: { value: '2025-03-01' } })
    await user.click(screen.getByRole('button', { name: 'Open Matter' }))

    await waitFor(() => expect(mocks.createMatterV2).toHaveBeenCalledWith(expect.objectContaining({ matter_name: 'Smith transfer', opened_on: '2025-03-01' })))
    expect(mocks.recordMatterEngagement).not.toHaveBeenCalled()
    expect(onCreated).toHaveBeenCalledWith(created)
    expect(onClose).toHaveBeenCalled()
  })

  it('records an existing engagement without a document right after creating the matter', async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    renderModal({ onCreated })

    await user.type(screen.getByLabelText(/Matter Title/), 'Legacy client')
    await user.click(screen.getByRole('radio', { name: /Already engaged/ }))
    await user.click(screen.getByRole('radio', { name: /No fee agreement/ }))
    // The reason is required before the matter can be opened this way.
    expect(screen.getByRole('button', { name: 'Open Matter' })).toBeDisabled()
    await user.type(screen.getByLabelText('Why there is no fee agreement'), 'Billed under the 2019 retainer letter')
    await user.click(screen.getByRole('button', { name: 'Open Matter' }))

    await waitFor(() => expect(mocks.recordMatterEngagement).toHaveBeenCalledWith('matter-1', expect.any(FormData)))
    const [, body] = mocks.recordMatterEngagement.mock.calls[0]
    expect(JSON.parse(body.get('options'))).toEqual({
      status: 'no_agreement', signed_on: null, document_id: null,
      note: 'Billed under the 2019 retainer letter', replace: false, confirm: true,
    })
    expect(body.get('agreement')).toBeNull()
    expect(onCreated).toHaveBeenCalledWith(created)
  })

  it('uploads the signed fee agreement with the signing date', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.type(screen.getByLabelText(/Matter Title/), 'Signed already')
    await user.click(screen.getByRole('radio', { name: /Already engaged/ }))
    expect(screen.getByRole('button', { name: 'Open Matter' })).toBeDisabled()
    const pdf = new File(['%PDF-1.4'], 'signed.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('Signed fee agreement (PDF)'), { target: { files: [pdf] } })
    fireEvent.change(screen.getByLabelText('Date signed (optional)'), { target: { value: '2024-06-01' } })
    await user.click(screen.getByRole('button', { name: 'Open Matter' }))

    await waitFor(() => expect(mocks.recordMatterEngagement).toHaveBeenCalled())
    const [, body] = mocks.recordMatterEngagement.mock.calls[0]
    expect(JSON.parse(body.get('options'))).toMatchObject({ status: 'signed_on_file', signed_on: '2024-06-01' })
    expect(body.get('agreement')).toBe(pdf)
  })

  it('retries recording against the matter it already opened, never creating a second one', async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    mocks.recordMatterEngagement
      .mockRejectedValueOnce({ response: { data: { detail: 'Agreement storage is unavailable.' } } })
      .mockResolvedValueOnce({ matter_id: 'matter-1', engagement: { status: 'signed_no_copy' } })
    renderModal({ onCreated })

    await user.type(screen.getByLabelText(/Matter Title/), 'Flaky storage')
    await user.click(screen.getByRole('radio', { name: /Already engaged/ }))
    await user.click(screen.getByRole('radio', { name: /Signed, no copy on hand/ }))
    await user.type(screen.getByLabelText('Where it was signed'), 'Signed at the client office')
    await user.click(screen.getByRole('button', { name: 'Open Matter' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Agreement storage is unavailable.')
    expect(screen.getByRole('alert')).toHaveTextContent('Matter SMIT0007 is open')
    expect(onCreated).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Retry recording engagement' }))
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
    expect(mocks.createMatterV2).toHaveBeenCalledTimes(1)
    expect(mocks.recordMatterEngagement).toHaveBeenCalledTimes(2)
  })

  it('lets the firm open the matter without the record when recording keeps failing', async () => {
    const user = userEvent.setup()
    const onCreated = vi.fn()
    mocks.recordMatterEngagement.mockRejectedValue(new Error('boom'))
    renderModal({ onCreated })

    await user.type(screen.getByLabelText(/Matter Title/), 'Give up')
    await user.click(screen.getByRole('radio', { name: /Already engaged/ }))
    await user.click(screen.getByRole('radio', { name: /No fee agreement/ }))
    await user.type(screen.getByLabelText('Why there is no fee agreement'), 'reason')
    await user.click(screen.getByRole('button', { name: 'Open Matter' }))
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: 'Open matter without recording' }))
    expect(onCreated).toHaveBeenCalledWith(created)
    expect(mocks.createMatterV2).toHaveBeenCalledTimes(1)
  })

  it('switches between the single, folder and CSV modes', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByRole('button', { name: 'Bulk create from CSV' }))
    expect(screen.getByRole('heading', { name: 'Bulk create matters from CSV' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Import existing matters' }))
    expect(screen.getByRole('heading', { name: 'Import existing matters' })).toBeInTheDocument()
  })
})
