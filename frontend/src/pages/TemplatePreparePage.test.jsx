import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import TemplatePreparePage from './TemplatePreparePage'

const api = vi.hoisted(() => ({
  getTemplate: vi.fn(),
  getMattersV2: vi.fn(),
  discoverTemplateVariables: vi.fn(),
  renderTemplate: vi.fn(),
  renderTemplateFile: vi.fn(),
  getMatterDocumentDownloadUrl: vi.fn(() => '/download'),
  triggerBlobDownload: vi.fn(),
  getTemplateSource: vi.fn(),
  getTemplateSourcePreview: vi.fn(),
  getTemplateOutline: vi.fn(),
  getMatterV2: vi.fn(),
  createSignatureRequest: vi.fn(),
  getSignatureRequestFields: vi.fn(),
  sendSignatureRequest: vi.fn(),
  voidSignatureRequest: vi.fn(),
  getMatterDocumentSigningSource: vi.fn(),
}))
vi.mock('../api', () => api)
vi.mock('../components/templates/GeneratedPdfPreview', () => ({ default: ({ title }) => <section aria-label={`Preview of ${title}`} /> }))
vi.mock('../components/templates/TemplateFillSource', () => ({ default: () => <div>reference</div> }))
vi.mock('../components/templates/TemplateFactReview', () => ({ default: () => null }))
vi.mock('../components/templates/GeneratedSigningPlacementReview', () => ({ default: () => null }))

const T = '11111111-1111-4111-8111-111111111111'
const M = '22222222-2222-4222-8222-222222222222'
const DOC = '44444444-4444-4444-8444-444444444444'

const published = {
  id: T, title: 'Fee agreement', format: 'markdown', body: 'Dear {{client_name}}', is_active: true,
  current_version_no: 3, published_version_no: 3,
  variable_schema: { fields: [{ name: 'client_name', label: 'Client name', required: true }] },
}

function Location() { const loc = useLocation(); return <output aria-label="Location">{loc.pathname}{loc.search}</output> }

function renderAt(search) {
  return render(
    <MemoryRouter initialEntries={[`/templates/prepare${search}`]}>
      <Routes>
        <Route path="/templates/prepare" element={<><TemplatePreparePage /><Location /></>} />
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.getTemplate.mockResolvedValue(published)
  api.getMattersV2.mockResolvedValue({ items: [{ id: M, matter_name: 'Smith Matter', client_name: 'Ada Smith' }] })
  api.discoverTemplateVariables.mockResolvedValue({ variables: [{ variable: 'client_name', suggested_value: 'Ada Smith', source_type: 'contact', confidence: 1, review_required: false }] })
  api.renderTemplate.mockResolvedValue({ rendered: 'Dear Ada Smith', matter_document_id: DOC, output_format: 'markdown', output_filename: 'fee.md' })
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('the Prepare route', () => {
  it('loads the published release when the workspace holds a newer draft', async () => {
    api.getTemplate.mockResolvedValueOnce({ ...published, current_version_no: 4 }).mockResolvedValueOnce(published)
    renderAt(`?template=${T}`)
    await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
    expect(api.getTemplate).toHaveBeenNthCalledWith(1, T)
    expect(api.getTemplate).toHaveBeenNthCalledWith(2, T, { published: true })
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('2. Matter')
  })

  it('preselects the matter, fills once, and lands on the saved document', async () => {
    renderAt(`?template=${T}&matter=${M}`)
    await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
    await waitFor(() => expect(api.discoverTemplateVariables).toHaveBeenCalledTimes(1))
    expect(api.discoverTemplateVariables).toHaveBeenCalledWith(T, { matter_id: M, published: true, variables: ['client_name'] })
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Client name/ })).toHaveValue('Ada Smith'))
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('1 of 1 filled')
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByText('Dear Ada Smith')
    fireEvent.click(screen.getByRole('button', { name: 'Render & Save to Matter' }))
    await waitFor(() => expect(screen.getByLabelText('Location')).toHaveTextContent(`/matters/${M}?tab=documents&document=${DOC}`))
    expect(api.renderTemplate).toHaveBeenLastCalledWith(T, { variables: { client_name: 'Ada Smith' }, matter_id: M })
  })

  it('lets the preparer verify a filled row and sends the verified names with the save', async () => {
    api.getTemplate.mockResolvedValue({
      ...published,
      body: 'Dear {{client_name}} re {{matter_name}}',
      variable_schema: { fields: [{ name: 'client_name', label: 'Client name', required: true }, { name: 'matter_name', label: 'Matter name' }] },
    })
    api.discoverTemplateVariables.mockResolvedValue({ variables: [
      { variable: 'client_name', suggested_value: 'Ada Smith', source_type: 'contact', confidence: 1, review_required: false },
      { variable: 'matter_name', suggested_value: 'Smith v. Jones', source_type: 'matter', confidence: 1, review_required: false },
    ] })
    renderAt(`?template=${T}&matter=${M}`)
    await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Client name/ })).toHaveValue('Ada Smith'))
    const completion = screen.getByRole('region', { name: 'Document completion' })
    expect(completion).toHaveTextContent('0 of 2 verified')
    expect(screen.getByRole('button', { name: 'Unverified (2)' })).toBeInTheDocument()
    // Enter on the first row's Verified control verifies it and moves on to the next unverified row.
    const first = screen.getByRole('checkbox', { name: 'Verified: Client name' })
    first.focus()
    fireEvent.keyDown(first, { key: 'Enter' })
    await waitFor(() => expect(first).toBeChecked())
    expect(document.activeElement).toBe(screen.getByRole('checkbox', { name: 'Verified: Matter name' }))
    expect(completion).toHaveTextContent('1 of 2 verified')
    // Typing a value counts as checking it; clearing it does not.
    fireEvent.change(screen.getByRole('textbox', { name: /Matter name/ }), { target: { value: 'Smith v. Jones (2026)' } })
    expect(screen.getByRole('checkbox', { name: 'Verified: Matter name' })).toBeChecked()
    expect(completion).toHaveTextContent('2 of 2 verified')
    fireEvent.click(screen.getByRole('button', { name: 'Unverified (0)' }))
    expect(screen.getByText('Every filled field is verified.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'All fields (2)' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Verified: Matter name' }))
    expect(completion).toHaveTextContent('1 of 2 verified')
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByText('Dear Ada Smith')
    fireEvent.click(screen.getByRole('button', { name: 'Render & Save to Matter' }))
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled())
    expect(api.renderTemplate).toHaveBeenLastCalledWith(T, {
      variables: { client_name: 'Ada Smith', matter_name: 'Smith v. Jones (2026)' },
      matter_id: M,
      verified_fields: ['client_name'],
    })
  })

  it('honours a return path and a destination folder', async () => {
    const F = '33333333-3333-4333-8333-333333333333'
    renderAt(`?template=${T}&matter=${M}&folder=${F}&return=${encodeURIComponent(`/matters/${M}?tab=probate`)}`)
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Client name/ })).toHaveValue('Ada Smith'))
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', `/matters/${M}?tab=probate`)
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByText('Dear Ada Smith')
    fireEvent.click(screen.getByRole('button', { name: 'Render & Save to Matter' }))
    await waitFor(() => expect(screen.getByLabelText('Location')).toHaveTextContent(`/matters/${M}?tab=probate&document=${DOC}`))
    expect(api.renderTemplate).toHaveBeenLastCalledWith(T, { variables: { client_name: 'Ada Smith' }, matter_id: M, folder_id: F })
  })

  it('keeps a draft in preview-only mode', async () => {
    api.getTemplate.mockResolvedValue({ ...published, is_active: false, published_version_no: null })
    renderAt(`?template=${T}&matter=${M}`)
    await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
    expect(screen.getAllByRole('status').some((node) => /Draft preview/.test(node.textContent))).toBe(true)
    expect(screen.getByRole('button', { name: 'Render & Save to Matter' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Preview draft' })).toBeEnabled()
  })

  it('stays for the Send step when the saved PDF carries signing fields, and sends to the matter client', async () => {
    const pdf = {
      ...published, format: 'pdf', source_sha256: 'abc',
      variable_schema: { fields: [{ name: 'client_name', label: 'Client name', required: true }, { name: 'sig', field_type: 'signature', signer_role: 'client' }] },
    }
    api.getTemplate.mockResolvedValue(pdf)
    api.renderTemplateFile.mockResolvedValue({ blob: new Blob(['%PDF']), previewId: 'prev-1', previewPurpose: 'generation', filename: 'fee.pdf' })
    api.renderTemplate.mockResolvedValue({
      rendered: 'PDF saved', matter_document_id: DOC, output_format: 'pdf', output_filename: 'fee.pdf',
      signing_roles: ['client'], signing_placement_required: true,
      positioned_fields: [{ field_id: 'sig', role: 'client', source: 'acroform', source_sha256: 'x' }], signing_placement_problems: [],
    })
    api.getMatterV2.mockResolvedValue({ id: M, client_name: 'Ada Smith', client_email: 'ada@example.test' })
    api.createSignatureRequest.mockResolvedValue({ id: 'req', document_name: 'fee.pdf', signers: [{ role: 'client' }], plan_review_required: false })
    api.getSignatureRequestFields.mockResolvedValue({ fields: [{ field_id: 'sig', role: 'client', kind: 'signature', page: 1, source: 'acroform' }] })
    api.sendSignatureRequest.mockResolvedValue({ id: 'req', status: 'sent', signers: [{ email: 'ada@example.test', invitation_delivery_status: 'sent' }] })
    renderAt(`?template=${T}&matter=${M}`)
    await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('6. Send')
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Client name/ })).toHaveValue('Ada Smith'))
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await waitFor(() => expect(api.renderTemplateFile).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole('button', { name: 'Render & Save to Matter' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'Render & Save to Matter' }))
    await screen.findByRole('heading', { name: 'Send for signature' })
    // Still on the Prepare route: the Send step is here, not on the matter.
    expect(screen.getByLabelText('Location')).toHaveTextContent('/templates/prepare')
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('Send for signature')
    expect(screen.getByPlaceholderText('Signer 1 full name')).toHaveValue('Ada Smith')
    expect(screen.getByPlaceholderText('Signer email')).toHaveValue('ada@example.test')
    expect(screen.getByRole('link', { name: "Open it in the matter's documents" })).toHaveAttribute('href', `/matters/${M}?tab=documents&document=${DOC}`)
    fireEvent.click(screen.getByRole('button', { name: 'Prepare for signature' }))
    await screen.findByRole('region', { name: 'Where each signer will sign' })
    expect(api.createSignatureRequest).toHaveBeenCalledWith(M, expect.objectContaining({
      document_id: DOC, provider: 'internal',
      signers: [{ name: 'Ada Smith', email: 'ada@example.test', role: 'client', sign_order: 0 }],
      positioned_fields: [{ field_id: 'sig', role: 'client', source: 'acroform', source_sha256: 'x' }],
    }))
    fireEvent.click(screen.getByRole('button', { name: 'Send for signature' }))
    await screen.findByRole('region', { name: 'Sent for signature' })
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('Sent for signature')
    expect(screen.getByRole('link', { name: "Open the matter's documents" })).toHaveAttribute('href', `/matters/${M}?tab=documents&document=${DOC}`)
  })

  it('generates a Word template with signature fields as PDF unless told otherwise', async () => {
    const docx = {
      ...published, format: 'docx', source_sha256: 'abc',
      variable_schema: { fields: [{ name: 'client_name', label: 'Client name', required: true }, { name: 'sig', field_type: 'signature', signer_role: 'client' }] },
    }
    api.getTemplate.mockResolvedValue(docx)
    renderAt(`?template=${T}&matter=${M}`)
    await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
    const pdfChoice = screen.getByRole('radio', { name: /PDF for signature/ })
    expect(pdfChoice).toBeChecked()
    expect(screen.getByText(/PDF is preselected because this template has signature fields/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /Editable Word document/ }))
    expect(screen.getByText(/A Word document cannot be sent for signature/)).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('Needs PDF output to send for signature')
  })

  it('explains itself without a template and reports a load failure', async () => {
    renderAt('')
    expect(await screen.findByText('Choose a template to prepare')).toBeVisible()
    expect(api.getTemplate).not.toHaveBeenCalled()
    cleanup()
    api.getTemplate.mockRejectedValue({ response: { data: { detail: 'Template not found' } } })
    renderAt(`?template=${T}`)
    expect(await screen.findByRole('alert')).toHaveTextContent('Template not found')
  })
})
