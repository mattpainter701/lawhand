import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import * as api from '../api'
import { SignatureRequestsPanel } from './MatterDetailPage'

vi.mock('../api', async () => {
  const actual = await vi.importActual('../api')
  return Object.fromEntries(Object.entries(actual).map(([key, value]) => [key, typeof value === 'function' ? vi.fn().mockResolvedValue([]) : value]))
})
vi.mock('../App', () => ({ useAuth: () => ({ user: { id: 'user' } }) }))
vi.mock('../components/templates/GeneratedSigningPlacementReview', () => ({ default: ({ onChange }) => <button type="button" onClick={() => onChange([{ field_id: 'manual', role: 'client', source_sha256: 'verified-final' }])}>Confirm final PDF placement</button> }))

beforeEach(() => {
  vi.clearAllMocks()
  api.createSignatureRequest.mockResolvedValue({ id: 'request' })
  api.sendSignatureRequest.mockResolvedValue({ id: 'request', status: 'sent' })
  // The URL helper is synchronous; the blanket stub above makes it a promise.
  api.getMatterDocumentDownloadUrl.mockImplementation((matterId, docId) => `/api/matters/${matterId}/documents/${docId}/download`)
})
afterEach(cleanup)

async function fillSigner() {
  fireEvent.change(screen.getByPlaceholderText('Signer 1 full name'), { target: { value: 'Client Name' } })
  fireEvent.change(screen.getByPlaceholderText('Signer email'), { target: { value: 'client@example.test' } })
}

it('always sends through the portal provider with the generated PDF descriptor', async () => {
  const fields = [{ field_id: 'client', role: 'client', source_sha256: 'final' }]
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'pdf', filename: 'Generated.pdf', positioned_fields: fields, signing_placement_required: true }] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Generated.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'pdf' } })
  // Dropbox Sign is gone: there is nothing to choose.
  expect(screen.queryByLabelText('Signing provider')).not.toBeInTheDocument()
  expect(screen.queryByText(/Dropbox/)).not.toBeInTheDocument()
  expect(screen.getByText(/Place a signature, initials, or date block per signer on the PDF \(optional/)).toBeInTheDocument()
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  // Nothing reaches the client until staff have seen where each signer signs.
  fireEvent.click(within(await screen.findByRole('region', { name: 'Where each signer will sign' })).getByRole('button', { name: 'Send for signature' }))
  await waitFor(() => expect(api.sendSignatureRequest).toHaveBeenCalledWith('matter', 'request'))
  expect(api.createSignatureRequest).toHaveBeenCalledWith('matter', expect.objectContaining({ provider: 'internal', document_id: 'pdf', positioned_fields: fields }))
  expect(await screen.findByText(/Signature request sent\. Signers will see it/)).toBeInTheDocument()
})

it('requires final placement review for a reflowed Word document before sending', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'word-pdf', filename: 'Reflowed.pdf', signing_placement_required: true, positioned_fields: [] }] })
  api.getMatterDocumentSigningSource.mockResolvedValue(new Blob(['final pdf']))
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Reflowed.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'word-pdf' } })
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  expect(api.createSignatureRequest).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Review PDF signing positions' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm final PDF placement' }))
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  fireEvent.click(within(await screen.findByRole('region', { name: 'Where each signer will sign' })).getByRole('button', { name: 'Send for signature' }))
  await waitFor(() => expect(api.sendSignatureRequest).toHaveBeenCalledOnce())
  expect(api.getMatterDocumentSigningSource).toHaveBeenCalledWith('matter', 'word-pdf')
  expect(api.createSignatureRequest.mock.calls[0][1].positioned_fields[0].source_sha256).toBe('verified-final')
})


it('retains custom Word roles and rejects a partial final placement review', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'roles', filename: 'Roles.pdf', signing_placement_required: true, signing_roles: ['client', 'landlord'], positioned_fields: [] }] })
  api.getMatterDocumentSigningSource.mockResolvedValue(new Blob(['final pdf']))
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Roles.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'roles' } })
  expect(screen.getByRole('option', { name: 'landlord' })).toBeInTheDocument()
  await fillSigner()
  fireEvent.click(screen.getByRole('button', { name: 'Review PDF signing positions' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm final PDF placement' }))
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  expect(await screen.findByText('Add signing fields for every role required by this document.')).toBeInTheDocument()
  expect(api.createSignatureRequest).not.toHaveBeenCalled()
})

it('says the invitation email was not delivered instead of reporting it sent', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'auth', filename: 'Fee agreement.pdf' }] })
  api.sendSignatureRequest.mockResolvedValue({
    id: 'request',
    status: 'sent',
    signers: [{ id: 's1', email: 'client@example.test', status: 'pending', invitation_delivery_status: 'unconfigured' }],
  })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Fee agreement.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'auth' } })
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  fireEvent.click(within(await screen.findByRole('region', { name: 'Where each signer will sign' })).getByRole('button', { name: 'Send for signature' }))
  const status = await screen.findByRole('status')
  expect(status).toHaveTextContent('the email invitation to client@example.test was not delivered')
  expect(status).toHaveTextContent('the outbound email settings are incomplete')
  expect(screen.queryByText(/Signature request sent\./)).not.toBeInTheDocument()
})

it('gives each added signer their own role so their fields stay separate', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'auth', filename: 'Fee agreement.pdf' }] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Fee agreement.pdf' })
  fireEvent.click(screen.getByRole('button', { name: 'Add signer' }))
  const roles = screen.getAllByRole('combobox').filter((node) => node.querySelector('option[value="co_client"]'))
  expect(roles.map((node) => node.value)).toEqual(['client', 'co_client'])
  // Two signers on one role would leave the placement review unable to tell
  // their signature fields apart, so it is called out before sending.
  fireEvent.change(roles[1], { target: { value: 'client' } })
  expect(screen.getByRole('alert')).toHaveTextContent('Client is used by more than one signer')
})

it('sends a due date so the signature raises a follow-up task', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'auth', filename: 'Medical authorization.pdf' }] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Medical authorization.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'auth' } })
  fireEvent.change(screen.getByLabelText('Due from client'), { target: { value: '2026-10-02' } })
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  await waitFor(() => expect(api.createSignatureRequest).toHaveBeenCalled())
  const [, payload] = api.createSignatureRequest.mock.calls.at(-1)
  // A deadline is what the firm chases; expiry is what voids the request.
  expect(payload.due_at).toMatch(/^2026-10-02T/)
  expect(payload.expires_at).toBeNull()
})

it('leaves the due date out when the firm sets none', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'auth', filename: 'Medical authorization.pdf' }] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Medical authorization.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'auth' } })
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  await waitFor(() => expect(api.createSignatureRequest).toHaveBeenCalled())
  expect(api.createSignatureRequest.mock.calls.at(-1)[1].due_at).toBeNull()
})

it('uploads a prepared PDF to the matter and selects it as the document to sign', async () => {
  api.getMatterDocuments
    .mockResolvedValueOnce({ items: [{ id: 'old', filename: 'Existing.pdf' }] })
    .mockResolvedValue({ items: [{ id: 'old', filename: 'Existing.pdf' }, { id: 'new', filename: 'Prepared.pdf' }] })
  api.uploadMatterDocument.mockResolvedValue({ id: 'new', filename: 'Prepared.pdf', content_type: 'application/pdf' })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Existing.pdf' })
  const input = screen.getByLabelText('Upload a prepared PDF')
  expect(input).toHaveAttribute('accept', 'application/pdf')
  fireEvent.change(input, { target: { files: [new File(['%PDF-1.4'], 'Prepared.pdf', { type: 'application/pdf' })] } })
  await waitFor(() => expect(api.uploadMatterDocument).toHaveBeenCalledOnce())
  const [matterId, form] = api.uploadMatterDocument.mock.calls[0]
  expect(matterId).toBe('matter')
  expect(form.get('file').name).toBe('Prepared.pdf')
  await waitFor(() => expect(screen.getByLabelText('Document to sign')).toHaveValue('new'))
  expect(screen.getByRole('option', { name: 'Prepared.pdf' })).toBeInTheDocument()
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  await waitFor(() => expect(api.createSignatureRequest).toHaveBeenCalledWith('matter', expect.objectContaining({ document_id: 'new', provider: 'internal' })))
})

it('shows the upload failure inline and keeps the selection unchanged', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'old', filename: 'Existing.pdf' }] })
  api.uploadMatterDocument.mockRejectedValue({ response: { data: { detail: 'File exceeds maximum size of 25MB' } } })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Existing.pdf' })
  fireEvent.change(screen.getByLabelText('Upload a prepared PDF'), { target: { files: [new File(['%PDF-1.4'], 'Big.pdf', { type: 'application/pdf' })] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('File exceeds maximum size of 25MB')
  expect(screen.getByLabelText('Document to sign')).toHaveValue('')
})

const queued = (overrides = {}) => ({
  id: 'req-1', status: 'partially_signed', document_name: 'Fee agreement.pdf',
  sent_at: '2026-09-10T12:00:00Z', created_at: '2026-09-10T11:00:00Z', expires_at: null,
  signers: [{ id: 's1', role: 'client', name: 'Client Name', email: 'client@example.test', status: 'signed', signed_at: '2026-09-11T12:00:00Z' }],
  ...overrides,
})

it('lets staff accept an uploaded signed copy', async () => {
  api.listSignatureRequests.mockResolvedValue([queued({ submitted_document_id: 'uploaded', signature_fields_count: 2 })])
  api.acceptSignatureSubmission.mockResolvedValue(queued({ status: 'completed', executed_document_id: 'uploaded' }))
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  expect(await screen.findByText('Signed copy uploaded — review')).toBeInTheDocument()
  expect(screen.getByText(/2 signature fields/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open uploaded copy' })).toHaveAttribute('href', expect.stringContaining('/matters/matter/documents/uploaded/download'))
  fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
  await waitFor(() => expect(api.acceptSignatureSubmission).toHaveBeenCalledWith('matter', 'req-1'))
  expect(await screen.findByText('Signed copy accepted and filed to the matter.')).toBeInTheDocument()
  // The queue reloads so the row reflects the completed request.
  expect(api.listSignatureRequests).toHaveBeenCalledTimes(2)
})

it('requires a reason to reject an uploaded signed copy and sends it', async () => {
  api.listSignatureRequests.mockResolvedValue([queued({ submitted_document_id: 'uploaded' })])
  api.rejectSignatureSubmission.mockResolvedValue(queued())
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Reject' }))
  expect(api.rejectSignatureSubmission).not.toHaveBeenCalled()
  expect(screen.getByText(/Tell the client what to redo/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Rejection reason'), { target: { value: 'Page 2 was not initialed' } })
  fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
  await waitFor(() => expect(api.rejectSignatureSubmission).toHaveBeenCalledWith('matter', 'req-1', { reason: 'Page 2 was not initialed' }))
  expect(await screen.findByText(/Signed copy rejected/)).toBeInTheDocument()
})

it('tells staff when the signed copy is waiting on storage, and links the filed copy once it lands', async () => {
  api.listSignatureRequests.mockResolvedValue([
    queued({ completion_pending: true, completion_error: 'Configured Microsoft OneDrive storage is unavailable' }),
    queued({ id: 'req-2', status: 'completed', executed_document_id: 'executed' }),
  ])
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  const pending = await screen.findByRole('status')
  expect(pending).toHaveTextContent('Filing the signed copy… storage unavailable: Configured Microsoft OneDrive storage is unavailable')
  expect(pending).toHaveTextContent(/retried automatically every few minutes/)
  expect(screen.getByRole('link', { name: 'Signed copy filed' })).toHaveAttribute('href', expect.stringContaining('/documents/executed/download'))
  expect(screen.queryByRole('button', { name: 'Accept' })).not.toBeInTheDocument()
})

const unbound = (overrides = {}) => ({
  id: 'blocked',
  filename: 'Fee agreement.pdf',
  content_type: 'application/pdf',
  signing_placement_required: true,
  positioned_fields: [],
  signing_placement_problems: [{
    code: 'missing_signer_role',
    detail: "Signing field 'client_sig' requires a signer role before it can be positioned",
    field: 'client_sig',
    role: '',
    remedy: 'Open the template, select this field, and set its signer role.',
  }],
  ...overrides,
})

it('names the unbound signing field instead of asking for a blind re-review', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [unbound()] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Fee agreement.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'blocked' } })

  // Visible before the form is filled in, not only after Send is refused.
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('client_sig')
  expect(alert).toHaveTextContent('set its signer role')
})

it('puts the same reason on the error when staff press send', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [unbound()] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Fee agreement.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'blocked' } })
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))

  expect(api.createSignatureRequest).not.toHaveBeenCalled()
  const alerts = screen.getAllByRole('alert').map((node) => node.textContent).join(' ')
  expect(alerts).toContain('client_sig')
})

it('offers the placement review for a PDF, which can still be rescued by hand', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [unbound()] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Fee agreement.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'blocked' } })

  expect(screen.getByRole('button', { name: 'Review PDF signing positions' })).toBeInTheDocument()
})

it('withholds the review for a Word document and says to regenerate it as a PDF', async () => {
  // The dead end: the review canvas renders with pdf.js, so this button could
  // never have cleared the block on a .docx however many times it was pressed.
  api.getMatterDocuments.mockResolvedValue({ items: [unbound({
    id: 'word',
    filename: 'Engagement letter.docx',
    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    signing_placement_problems: [{
      code: 'no_pdf_output',
      detail: 'This document was generated as DOCX, which has no PDF page to position signing fields on',
      field: '',
      role: '',
      remedy: 'Regenerate this document with Word-to-PDF conversion enabled: signing positions can only be placed on a PDF.',
    }],
  })] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Engagement letter.docx' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'word' } })

  expect(screen.queryByRole('button', { name: 'Review PDF signing positions' })).not.toBeInTheDocument()
  expect(await screen.findByRole('alert')).toHaveTextContent('Word-to-PDF conversion')
})

it('stops warning once the fields have been placed by hand', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [unbound()] })
  api.getMatterDocumentSigningSource.mockResolvedValue(new Blob(['final pdf']))
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Fee agreement.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'blocked' } })
  expect(await screen.findByRole('alert')).toHaveTextContent('client_sig')

  fireEvent.click(screen.getByRole('button', { name: 'Review PDF signing positions' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm final PDF placement' }))

  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
})

it('says nothing about placements for a document that needs none', async () => {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'plain', filename: 'Letter.pdf' }] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Letter.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'plain' } })

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Review PDF signing positions' })).toBeInTheDocument()
})


// ── The plan is looked at before it is sent ──────────────────────────────

const plannedRequest = (overrides = {}) => ({
  id: 'request',
  status: 'draft',
  document_name: 'Fee agreement.pdf',
  signers: [{ id: 's1', name: 'Client Name', email: 'client@example.test', role: 'client', sign_order: 0, status: 'pending' }],
  plan_review: [],
  plan_review_required: false,
  ...overrides,
})

const found = (overrides = {}) => ({
  field_id: 'auto:sig:1', kind: 'signature', page: 2, label: 'Client', role: 'client', source: 'detected', ...overrides,
})

async function createDraft() {
  api.getMatterDocuments.mockResolvedValue({ items: [{ id: 'pdf', filename: 'Fee agreement.pdf' }] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)
  await screen.findByRole('option', { name: 'Fee agreement.pdf' })
  fireEvent.change(screen.getByLabelText('Document to sign'), { target: { value: 'pdf' } })
  await fillSigner()
  fireEvent.submit(screen.getByPlaceholderText('Signer 1 full name').closest('form'))
  return screen.findByRole('region', { name: 'Where each signer will sign' })
}

it('shows where each signer will sign before anything is sent', async () => {
  api.createSignatureRequest.mockResolvedValue(plannedRequest())
  api.getSignatureRequestFields.mockResolvedValue({ fields: [found(), found({ field_id: 'auto:date:1', kind: 'date', label: 'Date signed' })] })
  const plan = await createDraft()

  expect(plan).toHaveTextContent('Page 2 · Signature “Client” · a signature line found on the page')
  expect(plan).toHaveTextContent('Page 2 · Date signed · a signature line found on the page')
  expect(api.getSignatureRequestFields).toHaveBeenCalledWith('matter', 'request')
  expect(api.sendSignatureRequest).not.toHaveBeenCalled()
})

it('sends a plan with nothing to review without an acknowledgement', async () => {
  api.createSignatureRequest.mockResolvedValue(plannedRequest())
  api.getSignatureRequestFields.mockResolvedValue({ fields: [found()] })
  await createDraft()

  const plan = screen.getByRole('region', { name: 'Where each signer will sign' })
  expect(within(plan).queryByRole('checkbox', { name: /checked where each signer/ })).not.toBeInTheDocument()
  fireEvent.click(within(plan).getByRole('button', { name: 'Send for signature' }))
  await waitFor(() => expect(api.sendSignatureRequest).toHaveBeenCalledWith('matter', 'request'))
  expect(await screen.findByText(/Signature request sent\./)).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Where each signer will sign' })).not.toBeInTheDocument()
})

it('holds a guessed plan until staff tick that they have checked it', async () => {
  // The server found no line for the client and invented a block: the case
  // that used to reach the client first.
  api.createSignatureRequest.mockResolvedValue(plannedRequest({
    plan_review: [{ level: 'warn', code: 'fallback', role: 'client', detail: 'No signature line was found for client: a signature block was placed at the foot of the last page.' }],
    plan_review_required: true,
  }))
  api.getSignatureRequestFields.mockResolvedValue({ fields: [found({ source: 'fallback', page: 3, label: 'Client signature' })] })
  const plan = await createDraft()

  expect(plan).toHaveTextContent('no line found — a block at the foot of the last page')
  expect(within(plan).getByRole('alert')).toHaveTextContent('No signature line was found for client')
  const send = within(plan).getByRole('button', { name: 'Send for signature' })
  expect(send).toBeDisabled()
  fireEvent.click(within(plan).getByRole('checkbox', { name: /checked where each signer/ }))
  expect(send).toBeEnabled()
  fireEvent.click(send)
  await waitFor(() => expect(api.sendSignatureRequest).toHaveBeenCalledWith('matter', 'request', { acknowledge_review: true }))
})

it('shows what was left for parties who are not signers without holding up sending', async () => {
  api.createSignatureRequest.mockResolvedValue(plannedRequest({
    plan_review: [{ level: 'info', code: 'left_for_others', role: '', detail: 'Lines captioned Notary Public were left blank: those parties are not among the signers.' }],
  }))
  api.getSignatureRequestFields.mockResolvedValue({ fields: [found()] })
  const plan = await createDraft()

  expect(within(plan).getByRole('status')).toHaveTextContent('Notary Public')
  expect(within(plan).getByRole('button', { name: 'Send for signature' })).toBeEnabled()
})

it('discards a draft by voiding it and clears the plan', async () => {
  api.createSignatureRequest.mockResolvedValue(plannedRequest())
  api.getSignatureRequestFields.mockResolvedValue({ fields: [found()] })
  api.voidSignatureRequest.mockResolvedValue({})
  const plan = await createDraft()

  fireEvent.click(within(plan).getByRole('button', { name: 'Discard draft' }))
  await waitFor(() => expect(api.voidSignatureRequest).toHaveBeenCalledWith('matter', 'request', { reason: 'Discarded before sending' }))
  expect(screen.queryByRole('region', { name: 'Where each signer will sign' })).not.toBeInTheDocument()
  expect(api.sendSignatureRequest).not.toHaveBeenCalled()
})

it('surfaces the server refusal when a guessed plan is sent unacknowledged', async () => {
  api.createSignatureRequest.mockResolvedValue(plannedRequest())
  api.getSignatureRequestFields.mockResolvedValue({ fields: [found()] })
  api.sendSignatureRequest.mockRejectedValue({ response: { data: { detail: '"Fee agreement.pdf" has a signing plan that needs a look before it is sent' } } })
  const plan = await createDraft()

  fireEvent.click(within(plan).getByRole('button', { name: 'Send for signature' }))
  expect(await screen.findByText(/needs a look before it is sent/)).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Where each signer will sign' })).toBeInTheDocument()
})

it('lets a draft left behind be reviewed and sent from the list', async () => {
  api.listSignatureRequests.mockResolvedValue([plannedRequest({ id: 'old-draft', document_name: 'Old draft.pdf', created_at: '2026-09-10T11:00:00Z', sent_at: null, expires_at: null })])
  api.getSignatureRequestFields.mockResolvedValue({ fields: [found({ page: 1 })] })
  render(<MemoryRouter><SignatureRequestsPanel matterId="matter" /></MemoryRouter>)

  fireEvent.click(await screen.findByRole('button', { name: 'Review and send' }))
  const plan = await screen.findByRole('region', { name: 'Where each signer will sign' })
  expect(plan).toHaveTextContent('Old draft.pdf')
  expect(plan).toHaveTextContent('Page 1 · Signature “Client”')
  expect(api.getSignatureRequestFields).toHaveBeenCalledWith('matter', 'old-draft')
})
