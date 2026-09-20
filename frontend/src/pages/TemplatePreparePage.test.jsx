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
  getTemplateSet: vi.fn(),
  getTemplateSetInterview: vi.fn(),
  getTemplateSetDocumentsVariables: vi.fn(),
  getFillSession: vi.fn(),
  writeFillSession: vi.fn(),
  renderFillSession: vi.fn(),
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
  api.writeFillSession.mockImplementation(async (data) => ({ id: data.id || '99999999-9999-4999-8999-999999999999', status: 'open', members: [], ...data }))
  api.getFillSession.mockResolvedValue({ id: '99999999-9999-4999-8999-999999999999', status: 'open', answers: {}, verified: [], members: [] })
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

  it('prepares a set: one answer reaches every document, previews retry alone, saves run one at a time', async () => {
    const S = '55555555-5555-4555-8555-555555555555'
    const A = '66666666-6666-4666-8666-666666666666'
    const B = '77777777-7777-4777-8777-777777777777'
    const C = '88888888-8888-4888-8888-888888888888'
    api.getTemplateSet.mockResolvedValue({ id: S, title: 'Motion packet', items: [
      { template_id: A, title: 'Motion', position: 0, resolved_version_no: 2 },
      { template_id: B, title: 'Order', position: 1, resolved_version_no: 1 },
      { template_id: C, title: 'Old form', position: 2, unavailable_reason: 'Publish a tested version first.' },
    ] })
    api.getTemplate.mockImplementation(async (id) => id === A
      ? { id: A, title: 'Motion', format: 'pdf', source_sha256: 'a', is_active: true, variable_schema: { fields: [{ name: 'def_name', binding: 'defendant.full_name' }, { name: 'sig', field_type: 'signature', signer_role: 'client' }] } }
      : { id: B, title: 'Order', format: 'markdown', body: '{{DEFENDANT}} {{hearing}}', is_active: true, variable_schema: { fields: [{ name: 'DEFENDANT', binding: 'defendant.full_name' }, { name: 'hearing', label: 'Hearing date', required: true }] } })
    api.getTemplateSetInterview.mockResolvedValue({ set_id: S, title: 'Motion packet', questions: [
      { key: 'defendant.full_name', label: 'Defendant', value_kind: 'text', required: true, card: 'defendant', binding: 'defendant.full_name', shared: true, appears_in: [{ template_id: A, template_title: 'Motion', field_name: 'def_name', label: 'Defendant' }, { template_id: B, template_title: 'Order', field_name: 'DEFENDANT', label: 'Defendant' }], suggested_value: 'Ada Lovelace', provenance: { source_type: 'matter_party', confidence: 1 }, review_required: false },
      { key: `manual:${B}:hearing`, label: 'Hearing date', value_kind: 'text', required: true, card: '', binding: '', shared: false, appears_in: [{ template_id: B, template_title: 'Order', field_name: 'hearing', label: 'Hearing date' }] },
    ], unavailable: [{ template_id: C, title: 'Old form', position: 2, unavailable_reason: 'Publish a tested version first.' }] })
    api.getTemplateSetDocumentsVariables.mockResolvedValue({ set_id: S, documents: { [A]: { def_name: 'Ada Lovelace' }, [B]: { DEFENDANT: 'Ada Lovelace', hearing: '2026-10-01' } }, unanswered_required: [], unavailable: [], resolved_versions: { [A]: 2, [B]: 1 } })
    let motionPreviews = 0
    api.renderTemplateFile.mockImplementation(async () => { motionPreviews += 1; if (motionPreviews === 1) throw new Error('Renderer busy'); return { blob: new Blob(['%PDF']), previewId: 'prev-a', previewPurpose: 'generation', filename: 'motion.pdf' } })
    const saves = []
    api.renderTemplate.mockImplementation(async (id, payload) => {
      if (!payload.matter_id) return { rendered: 'Ada Lovelace 2026-10-01', output_format: 'markdown', output_filename: 'order.md' }
      saves.push(id)
      if (id === B && saves.filter((s) => s === B).length === 1) { const err = new Error('Storage unavailable'); err.response = { status: 500, data: { detail: 'Storage unavailable' } }; throw err }
      return id === A
        ? { rendered: 'PDF saved', matter_document_id: DOC, output_format: 'pdf', output_filename: 'motion.pdf', signing_roles: ['client'], positioned_fields: [{ field_id: 'sig', role: 'client' }], signing_placement_problems: [] }
        : { rendered: 'saved', matter_document_id: '99999999-9999-4999-8999-999999999999', output_format: 'markdown', output_filename: 'order.md' }
    })
    api.getMatterV2.mockResolvedValue({ id: M, client_name: 'Ada Lovelace', client_email: 'ada@example.test' })
    renderAt(`?set=${S}&matter=${M}`)
    await screen.findByRole('heading', { name: 'Prepare a packet' })
    await screen.findByText('Old form')
    expect(screen.getByRole('alert')).toHaveTextContent('Publish a tested version first.')
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('Motion packet')
    // The shared question was suggested by the matter and appears in both documents.
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Defendant/ })).toHaveValue('Ada Lovelace'))
    expect(screen.getByText(/Appears in 2 documents/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save all to matter' })).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: /Hearing date/ }), { target: { value: '2026-10-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate all' }))
    await waitFor(() => expect(api.getTemplateSetDocumentsVariables).toHaveBeenCalledWith(S, { matter_id: M, answers: { 'defendant.full_name': 'Ada Lovelace', [`manual:${B}:hearing`]: '2026-10-01' } }))
    await screen.findByText('Preview failed: Renderer busy')
    expect(screen.getByText('Preview ready')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry failed previews' }))
    await waitFor(() => expect(screen.getAllByText('Preview ready')).toHaveLength(2))
    expect(api.renderTemplateFile).toHaveBeenCalledTimes(2)
    expect(api.renderTemplateFile).toHaveBeenLastCalledWith(A, { variables: { def_name: 'Ada Lovelace' }, matter_id: M, preview_purpose: 'generation' })
    fireEvent.click(screen.getByRole('button', { name: 'Save all to matter' }))
    await screen.findByText('Save failed: Storage unavailable')
    expect(saves).toEqual([A, B])
    expect(api.renderTemplate).toHaveBeenCalledWith(A, { matter_id: M, preview_id: 'prev-a', variables: { def_name: 'Ada Lovelace' } })
    // The typed hearing date is verified by the act of typing it; the suggested defendant was not ticked.
    expect(api.renderTemplate).toHaveBeenCalledWith(B, { matter_id: M, variables: { DEFENDANT: 'Ada Lovelace', hearing: '2026-10-01' }, verified_fields: ['hearing'] })
    fireEvent.click(screen.getByRole('button', { name: 'Retry failed saves' }))
    await waitFor(() => expect(screen.getAllByText('Saved')).toHaveLength(2))
    expect(saves).toEqual([A, B, B])
    // Every document is saved; the PDF with a signing role gets a Send card.
    await screen.findByText('Every document is saved to the matter.')
    await screen.findByRole('heading', { name: 'Send for signature' })
    expect(screen.getByPlaceholderText('Signer 1 full name')).toHaveValue('Ada Lovelace')
  })

  it('keeps typed values in a session and resumes them for a single template', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      api.discoverTemplateVariables.mockResolvedValue({ variables: [] })
      renderAt(`?template=${T}&matter=${M}`)
      await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
      fireEvent.change(screen.getByRole('textbox', { name: /Client name/ }), { target: { value: 'Grace Hopper' } })
      await vi.advanceTimersByTimeAsync(900)
      await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledWith(expect.objectContaining({ template_id: T, matter_id: M, answers: { client_name: 'Grace Hopper' }, verified: ['client_name'] })))
    } finally {
      vi.useRealTimers()
    }
    cleanup()
    const X = '99999999-9999-4999-8999-999999999999'
    api.getFillSession.mockResolvedValue({ id: X, status: 'open', template_id: T, matter_id: M, answers: { client_name: 'Grace Hopper' }, verified: ['client_name'], members: [] })
    renderAt(`?template=${T}&session=${X}`)
    await screen.findByRole('heading', { name: 'Prepare: Fee agreement' })
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Client name/ })).toHaveValue('Grace Hopper'))
    expect(screen.getByRole('checkbox', { name: 'Verified: Client name' })).toBeChecked()
  })

  it('saves a previewed packet in the background and follows the session until it settles', async () => {
    const S = '55555555-5555-4555-8555-555555555555'
    const A = '66666666-6666-4666-8666-666666666666'
    const X = '99999999-9999-4999-8999-999999999999'
    api.getTemplateSet.mockResolvedValue({ id: S, title: 'Packet', items: [{ template_id: A, title: 'Motion', position: 0, resolved_version_no: 2 }] })
    api.getTemplate.mockResolvedValue({ id: A, title: 'Motion', format: 'pdf', source_sha256: 'a', is_active: true, variable_schema: { fields: [{ name: 'def_name', binding: 'defendant.full_name' }] } })
    api.getTemplateSetInterview.mockResolvedValue({ set_id: S, title: 'Packet', questions: [
      { key: 'defendant.full_name', label: 'Defendant', value_kind: 'text', required: true, card: 'defendant', binding: 'defendant.full_name', shared: false, appears_in: [{ template_id: A, template_title: 'Motion', field_name: 'def_name', label: 'Defendant' }], suggested_value: 'Ada', provenance: { source_type: 'matter_party', confidence: 1 }, review_required: false },
    ], unavailable: [] })
    api.getTemplateSetDocumentsVariables.mockResolvedValue({ set_id: S, documents: { [A]: { def_name: 'Ada' } }, unanswered_required: [], unavailable: [], resolved_versions: { [A]: 2 } })
    api.renderTemplateFile.mockResolvedValue({ blob: new Blob(['%PDF']), previewId: 'prev-a', previewPurpose: 'generation', filename: 'motion.pdf' })
    api.renderFillSession.mockResolvedValue({ id: X, status: 'saving', members: [{ template_id: A, status: 'queued' }] })
    api.getFillSession
      .mockResolvedValueOnce({ id: X, status: 'saving', members: [{ template_id: A, status: 'queued' }] })
      .mockResolvedValue({ id: X, status: 'saved', members: [{ template_id: A, status: 'saved', matter_document_id: DOC, output_filename: 'motion.pdf' }] })
    renderAt(`?set=${S}&matter=${M}`)
    await screen.findByRole('heading', { name: 'Prepare a packet' })
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Defendant/ })).toHaveValue('Ada'))
    fireEvent.click(screen.getByRole('button', { name: 'Generate all' }))
    await screen.findByText('Preview ready')
    fireEvent.click(screen.getByRole('button', { name: 'Save all in the background' }))
    await waitFor(() => expect(api.renderFillSession).toHaveBeenCalledWith(X, { members: [{ template_id: A, variables: { def_name: 'Ada' }, preview_id: 'prev-a', convert_to_pdf: false, output_format: 'pdf' }] }))
    await screen.findByText(/Saving in the background/)
    await waitFor(() => expect(screen.getByText('Saved')).toBeInTheDocument(), { timeout: 8000 })
    await screen.findByText('Every document is saved to the matter.')
  }, 15000)

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
