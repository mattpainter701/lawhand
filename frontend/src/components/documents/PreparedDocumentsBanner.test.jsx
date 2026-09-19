import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PreparedDocumentsBanner, { summarize } from './PreparedDocumentsBanner'

const api = vi.hoisted(() => ({ getMatterDocumentPrefill: vi.fn() }))
vi.mock('../../api', () => api)
afterEach(() => { cleanup(); vi.clearAllMocks() })

const readiness = {
  event_id: 'e1', prepared_at: '2026-09-19T10:00:00Z', trigger_event: 'matter_created', stale: false, ready: 2,
  templates: [
    { template_id: 't1', title: 'Fee agreement', status: 'ready', fields: 20, filled: 16, percent: 80, missing_required: 1, review: 2 },
    { template_id: 't2', title: 'Intake form', status: 'ready', fields: 10, filled: 6, percent: 60, missing_required: 0, review: 0 },
    { template_id: 't3', title: 'Unfilled', status: 'empty', fields: 4, filled: 0, percent: 0, missing_required: 0, review: 0 },
  ],
}

describe('prepared documents banner', () => {
  it('lists ready templates with counts and opens one into review', async () => {
    api.getMatterDocumentPrefill.mockResolvedValue(readiness)
    const onOpen = vi.fn()
    render(<PreparedDocumentsBanner matterId="m1" onOpen={onOpen} />)
    expect(await screen.findByText(/2 documents ready to review, 70% filled/)).toBeVisible()
    expect(screen.getByText('Fee agreement')).toBeVisible()
    expect(screen.getByText(/16 of 20 fields · 1 required still blank · 2 to confirm/)).toBeVisible()
    expect(screen.queryByText('Unfilled')).toBeNull()
    fireEvent.click(screen.getAllByText('Review and save')[0])
    expect(onOpen).toHaveBeenCalledWith('t1')
  })

  it('says when the matter moved on since the run', async () => {
    api.getMatterDocumentPrefill.mockResolvedValue({ ...readiness, stale: true })
    render(<PreparedDocumentsBanner matterId="m1" onOpen={vi.fn()} />)
    expect(await screen.findByText(/matter details changed since/)).toBeVisible()
  })

  it('renders nothing before a run, when nothing is ready, or on failure', async () => {
    api.getMatterDocumentPrefill.mockResolvedValue(null)
    const { container, rerender } = render(<PreparedDocumentsBanner matterId="m1" onOpen={vi.fn()} />)
    await Promise.resolve()
    expect(container).toBeEmptyDOMElement()
    api.getMatterDocumentPrefill.mockRejectedValue(new Error('offline'))
    rerender(<PreparedDocumentsBanner matterId="m2" onOpen={vi.fn()} />)
    await Promise.resolve()
    expect(container).toBeEmptyDOMElement()
    expect(summarize({ templates: [{ status: 'empty' }] })).toBeNull()
  })

  it('refetches when the version changes', async () => {
    api.getMatterDocumentPrefill.mockResolvedValue(readiness)
    const { rerender } = render(<PreparedDocumentsBanner matterId="m1" version={0} onOpen={vi.fn()} />)
    await screen.findByText(/ready to review/)
    rerender(<PreparedDocumentsBanner matterId="m1" version={1} onOpen={vi.fn()} />)
    expect(api.getMatterDocumentPrefill).toHaveBeenCalledTimes(2)
  })
})
