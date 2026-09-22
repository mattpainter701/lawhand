import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import TemplateSetsPage from './TemplateSetsPage'

const api = vi.hoisted(() => ({
  listTemplateSets: vi.fn(),
  getTemplates: vi.fn(),
  createTemplateSet: vi.fn(),
  replaceTemplateSet: vi.fn(),
  deleteTemplateSet: vi.fn(),
}))
vi.mock('../api', () => api)

const A = '66666666-6666-4666-8666-666666666666'
const B = '77777777-7777-4777-8777-777777777777'
const S = '55555555-5555-4555-8555-555555555555'

function Location() { const loc = useLocation(); return <output aria-label="Location">{loc.pathname}{loc.search}</output> }

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/templates/sets']}>
      <Routes>
        <Route path="/templates/sets" element={<><TemplateSetsPage /><Location /></>} />
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.listTemplateSets.mockResolvedValue({ items: [{ id: S, title: 'Motion packet', jurisdiction: 'ND', items: [{ template_id: A, title: 'Motion', position: 0 }, { template_id: B, title: 'Order', position: 1 }] }], total: 1 })
  api.getTemplates.mockResolvedValue({ items: [{ id: A, title: 'Motion', is_active: true, published_version_no: 2 }, { id: B, title: 'Order', is_active: true, published_version_no: 1 }, { id: 'draft', title: 'Draft', is_active: false }] })
  api.createTemplateSet.mockResolvedValue({ id: 'new' })
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('template sets page', () => {
  it('lists sets and opens the Prepare route for one', async () => {
    renderPage()
    await screen.findByText('Motion packet')
    expect(screen.getByText('2 documents · ND')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare on a matter' }))
    expect(screen.getByLabelText('Location')).toHaveTextContent(`/templates/prepare?set=${S}`)
  })

  it('creates a set from published templates only, in the order given', async () => {
    renderPage()
    await screen.findByText('Motion packet')
    fireEvent.click(screen.getByRole('button', { name: 'New set' }))
    fireEvent.change(screen.getByLabelText('Set name'), { target: { value: 'Filing packet' } })
    const picker = screen.getByLabelText('Add a published template')
    expect(Array.from(picker.options).map((option) => option.textContent)).toEqual(['Choose a template…', 'Motion', 'Order'])
    fireEvent.change(picker, { target: { value: B } })
    fireEvent.change(screen.getByLabelText('Add a published template'), { target: { value: A } })
    fireEvent.change(screen.getByLabelText('Version for Motion'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create set' }))
    await waitFor(() => expect(api.createTemplateSet).toHaveBeenCalledWith({
      title: 'Filing packet', description: null, module: null, jurisdiction: null,
      items: [{ template_id: B }, { template_id: A, pinned_version_no: 2 }],
    }))
  })
})
