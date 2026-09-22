import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CloudSearchAdmin from './CloudSearchAdmin'

const mocks = vi.hoisted(() => ({
  getCloudSearchStatus: vi.fn(),
  testCloudSearch: vi.fn(),
  triggerCloudSync: vi.fn(),
  getCloudMetadata: vi.fn(),
  invalidateCloudCache: vi.fn(),
}))

vi.mock('../api', () => mocks)
vi.mock('../components/ui', () => ({ Spinner: () => <div>Loading</div> }))
vi.mock('../components/toast/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getCloudSearchStatus.mockResolvedValue({ enabled: true, metadata_total: 0, providers: {} })
})
afterEach(cleanup)

describe('CloudSearchAdmin', () => {
  it('renders fetched content returned by the cloud search API', async () => {
    mocks.testCloudSearch.mockResolvedValue({
      hits: [{ provider: 'microsoft', source: 'onedrive', title: 'validation.txt', relevance_score: 0.65, snippet: 'metadata hit' }],
      total_hits: 1,
      fetch_content_results: [{
        hit: { title: 'validation.txt' },
        content: 'CSA-OD-20260907-QUARTZ-OTTER-4826',
      }],
    })

    render(<CloudSearchAdmin />)
    fireEvent.click(screen.getByRole('button', { name: 'Test Search' }))
    fireEvent.change(screen.getByLabelText('Search Query'), { target: { value: 'validation marker' } })
    fireEvent.click(screen.getByLabelText('Fetch full content'))
    fireEvent.click(screen.getByRole('button', { name: 'Run Search' }))

    expect(await screen.findByText('Fetched Content (1)')).toBeInTheDocument()
    expect(screen.getByText('CSA-OD-20260907-QUARTZ-OTTER-4826')).toBeInTheDocument()
    expect(mocks.testCloudSearch).toHaveBeenCalledWith({
      query: 'validation marker',
      sources: ['gmail', 'drive', 'outlook', 'onedrive', 'sharepoint'],
      max_hits: 10,
      exact_query: false,
      fetch_content: true,
    })
  })

  it('allows an exact OneDrive filename diagnostic without fetching content', async () => {
    mocks.testCloudSearch.mockResolvedValue({ hits: [], total_hits: 0 })

    render(<CloudSearchAdmin />)
    fireEvent.click(screen.getByRole('button', { name: 'Test Search' }))
    fireEvent.change(screen.getByLabelText('Search Query'), { target: { value: 'd1245828.pdf' } })
    fireEvent.click(screen.getByLabelText('Gmail'))
    fireEvent.click(screen.getByLabelText('Google Drive'))
    fireEvent.click(screen.getByLabelText('Outlook'))
    fireEvent.click(screen.getByLabelText('SharePoint'))
    fireEvent.click(screen.getByRole('button', { name: 'Run Search' }))

    await screen.findByText('0 results')
    expect(mocks.testCloudSearch).toHaveBeenCalledWith({
      query: 'd1245828.pdf',
      sources: ['onedrive'],
      max_hits: 10,
      exact_query: true,
      fetch_content: false,
    })
  })
})
