import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MatterTemplatePicker from './MatterTemplatePicker'

const harness = vi.hoisted(() => ({
  getTemplates: vi.fn(), getTemplate: vi.fn(), getSampleTemplates: vi.fn(),
  getSampleTemplateSource: vi.fn(), navigate: vi.fn(),
}))
vi.mock('../../api', () => harness)
vi.mock('react-router-dom', () => ({ useNavigate: () => harness.navigate }))
vi.mock('../../pages/TemplatesPage', () => ({ RenderModal: ({ fixedMatterId, folderId, onSaved }) => <button onClick={() => onSaved({ matter_document_id: 'saved' })}>Review {fixedMatterId} in {folderId}</button> }))

const firmItem = (overrides = {}) => ({ id: 'firm-1', title: 'Firm motion', is_active: true, current_version_no: 2, published_version_no: 2, ...overrides })
const sampleItem = (overrides = {}) => ({ id: 'sample-1', title: 'Global lease', category: 'Lease', jurisdictions: ['California'], provenance: { source_name: 'Court', edition: '2024' }, ...overrides })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const renderPicker = (props = {}) => render(<MatterTemplatePicker matterId="matter/one" folderId="intake" onClose={vi.fn()} onSaved={vi.fn()} {...props} />)

beforeEach(() => {
  harness.getTemplates.mockResolvedValue({ items: [firmItem()], total: 1 })
  harness.getTemplate.mockResolvedValue(firmItem())
  harness.getSampleTemplates.mockResolvedValue({ items: [sampleItem()] })
  harness.getSampleTemplateSource.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('matter template attachment catalog', () => {
  it('shows distinct firm and global sources with concise readiness cues', async () => {
    harness.getTemplates.mockResolvedValue({ items: [firmItem(), firmItem({ id: 'draft', title: 'Intake draft', is_active: false, status: 'draft' })], total: 2 })
    renderPicker()
    expect(await screen.findByText('Firm motion')).toBeVisible()
    expect(await screen.findByText('Global lease')).toBeVisible()
    expect(screen.getByRole('heading', { name: /Firm templates/ })).toBeVisible()
    expect(screen.getByText('Global library', { selector: 'span' })).toBeVisible()
    expect(screen.getByText('Published v2')).toBeVisible()
    expect(screen.getByText('Draft')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Use template' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Review in Studio' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Global library' }))
    expect(screen.queryByText('Firm motion')).not.toBeInTheDocument()
    expect(screen.getByText('Global lease')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(harness.getTemplates).toHaveBeenCalledWith(expect.objectContaining({ include_inactive: true, limit: 20, offset: 0 }))
  })

  it('filters firm and global sources while keeping failed-source errors separate', async () => {
    harness.getTemplates.mockRejectedValue(new Error('offline'))
    harness.getSampleTemplates.mockRejectedValue(new Error('offline'))
    renderPicker()
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(2))
    expect(screen.queryByText('No matching templates.')).not.toBeInTheDocument()
    harness.getTemplates.mockResolvedValue({ items: [firmItem()], total: 1 })
    fireEvent.click(screen.getByRole('button', { name: 'Retry firm templates' }))
    expect(await screen.findByText('Firm motion')).toBeVisible()
    harness.getSampleTemplates.mockResolvedValue({ items: [sampleItem()] })
    fireEvent.click(screen.getByRole('button', { name: 'Retry global library' }))
    expect(await screen.findByText('Global lease')).toBeVisible()
  })

  it('paginates the entire global catalog and resets its page for a new search', async () => {
    harness.getSampleTemplates.mockResolvedValue({ items: Array.from({ length: 25 }, (_, index) => sampleItem({ id: `sample-${index}`, title: `Global form ${index}` })) })
    renderPicker()
    expect(await screen.findByText('Global form 0')).toBeVisible()
    expect(screen.queryByText('Global form 24')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next global results' }))
    expect(await screen.findByText('Global form 24')).toBeVisible()
    expect(screen.getByText(/Page 2 of 2/)).toBeVisible()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'form 0' } })
    expect(await screen.findByText('Global form 0')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Previous global results' })).not.toBeInTheDocument()
  })

  it('searches both catalogs, matches global provenance, and drops stale firm responses', async () => {
    const oldSearch = deferred()
    harness.getTemplates.mockImplementation(({ query }) => query === 'first' ? oldSearch.promise : query === '2022' ? Promise.resolve({ items: [firmItem({ id: 'fresh', title: 'Fresh result' })], total: 1 }) : Promise.resolve({ items: [firmItem()], total: 1 }))
    harness.getSampleTemplates.mockResolvedValue({ items: [sampleItem(), sampleItem({ id: 'sample-2', title: 'Old pleading', category: 'Court', jurisdictions: ['Texas'], provenance: { source_name: 'State bar', edition: '2022' } })] })
    renderPicker()
    await screen.findByText('Firm motion')
    const search = screen.getByRole('textbox')
    fireEvent.change(search, { target: { value: 'first' } })
    await waitFor(() => expect(harness.getTemplates).toHaveBeenLastCalledWith(expect.objectContaining({ query: 'first' })))
    fireEvent.change(search, { target: { value: '2022' } })
    await screen.findByText('Fresh result')
    await waitFor(() => expect(harness.getTemplates).toHaveBeenLastCalledWith(expect.objectContaining({ query: '2022' })))
    oldSearch.resolve({ items: [firmItem({ id: 'stale', title: 'Stale result' })], total: 1 })
    expect(await screen.findByText('Old pleading')).toBeVisible()
    expect(screen.queryByText('Stale result')).not.toBeInTheDocument()
  })

  it('carries matter and folder context to Studio and global intake, and previews samples in-app', async () => {
    harness.getTemplates.mockResolvedValue({ items: [firmItem({ id: 'draft', is_active: false, status: 'paused' })], total: 1 })
    renderPicker()
    fireEvent.click(await screen.findByRole('button', { name: 'Review in Studio' }))
    expect(harness.navigate).toHaveBeenCalledWith('/templates/draft/studio', { state: { preparationContext: { matterId: 'matter/one', folderId: 'intake', returnTo: '/matters/matter%2Fone?tab=documents' } } })
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
    expect(await screen.findByRole('dialog', { name: /Preview: Global lease/ })).toBeVisible()
    expect(harness.getSampleTemplateSource).toHaveBeenCalledWith('sample-1')
    fireEvent.click(screen.getByRole('button', { name: 'Close PDF preview' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add to firm' }))
    expect(harness.navigate).toHaveBeenLastCalledWith('/templates/new?sample=sample-1', { state: { preparationContext: { matterId: 'matter/one', folderId: 'intake', returnTo: '/matters/matter%2Fone?tab=documents' } } })
  })

  it('uses the published snapshot when a newer draft exists and keeps the matter fixed', async () => {
    harness.getTemplates.mockResolvedValue({ items: [firmItem({ current_version_no: 4, published_version_no: 3 })], total: 1 })
    harness.getTemplate.mockResolvedValue(firmItem({ current_version_no: 4, published_version_no: 3 }))
    renderPicker()
    fireEvent.click(await screen.findByRole('button', { name: 'Use template' }))
    await waitFor(() => expect(harness.getTemplate).toHaveBeenNthCalledWith(2, 'firm-1', { published: true }))
    expect(harness.getTemplate).toHaveBeenNthCalledWith(1, 'firm-1')
    expect(await screen.findByText('Review matter/one in intake')).toBeVisible()
  })

  it('routes a row that became inactive to Studio instead of using it', async () => {
    harness.getTemplate.mockResolvedValue(firmItem({ is_active: false, published_version_no: null, status: 'draft' }))
    renderPicker()
    fireEvent.click(await screen.findByRole('button', { name: 'Use template' }))
    await waitFor(() => expect(harness.navigate).toHaveBeenCalledWith('/templates/firm-1/studio', { state: { preparationContext: { matterId: 'matter/one', folderId: 'intake', returnTo: '/matters/matter%2Fone?tab=documents' } } }))
  })

  it('preserves initialTemplateId direct-open behavior', async () => {
    harness.getTemplate.mockResolvedValueOnce(firmItem({ current_version_no: 4, published_version_no: 3 }))
      .mockResolvedValueOnce(firmItem({ current_version_no: 3, published_version_no: 3 }))
    renderPicker({ initialTemplateId: 'prepared' })
    expect(await screen.findByText('Review matter/one in intake')).toBeVisible()
    expect(harness.getTemplate).toHaveBeenNthCalledWith(1, 'prepared')
    expect(harness.getTemplate).toHaveBeenNthCalledWith(2, 'prepared', { published: true })
    expect(harness.getTemplates).not.toHaveBeenCalled()
    expect(harness.getSampleTemplates).not.toHaveBeenCalled()
  })

  it('offers retry for a failed source preview', async () => {
    harness.getSampleTemplateSource.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(new Blob(['pdf'], { type: 'application/pdf' }))
    renderPicker()
    fireEvent.click(await screen.findByRole('button', { name: 'Preview' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('preview for “Global lease” could not be loaded')
    fireEvent.click(screen.getByRole('button', { name: 'Retry preview' }))
    await waitFor(() => expect(harness.getSampleTemplateSource).toHaveBeenCalledTimes(2))
  })
})
