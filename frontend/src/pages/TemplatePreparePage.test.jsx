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
}))
vi.mock('../api', () => api)
vi.mock('../components/templates/GeneratedPdfPreview', () => ({ default: ({ title }) => <section aria-label={`Preview of ${title}`} /> }))
vi.mock('../components/templates/TemplateFillSource', () => ({ default: () => <div>reference</div> }))
vi.mock('../components/templates/TemplateFactReview', () => ({ default: () => null }))

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
    await waitFor(() => expect(screen.getByLabelText(/Client name/)).toHaveValue('Ada Smith'))
    expect(screen.getByRole('navigation', { name: 'Prepare steps' })).toHaveTextContent('1 of 1 filled')
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByText('Dear Ada Smith')
    fireEvent.click(screen.getByRole('button', { name: 'Render & Save to Matter' }))
    await waitFor(() => expect(screen.getByLabelText('Location')).toHaveTextContent(`/matters/${M}?tab=documents&document=${DOC}`))
    expect(api.renderTemplate).toHaveBeenLastCalledWith(T, { variables: { client_name: 'Ada Smith' }, matter_id: M })
  })

  it('honours a return path and a destination folder', async () => {
    const F = '33333333-3333-4333-8333-333333333333'
    renderAt(`?template=${T}&matter=${M}&folder=${F}&return=${encodeURIComponent(`/matters/${M}?tab=probate`)}`)
    await waitFor(() => expect(screen.getByLabelText(/Client name/)).toHaveValue('Ada Smith'))
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
