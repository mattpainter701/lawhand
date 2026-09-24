import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import MatterPortfolioPage from './MatterPortfolioPage'
import { getMattersV2, getMyMattersPage } from '../api'

vi.mock('../App', () => ({ useAuth: () => ({ user: { id: 'user-1' } }) }))
vi.mock('../api', () => ({
  getMattersV2: vi.fn(),
  getMyMattersPage: vi.fn(),
  setAssignmentActive: vi.fn(),
  updateMatterV2: vi.fn(),
}))
vi.mock('../components/NewMatterModal', () => ({ default: () => null }))
vi.mock('../components/casesetup/CloseMatterDialog', () => ({ default: () => null }))

const pageOf = (n) => Array.from({ length: n }, (_, i) => ({
  id: `matter-${i}`,
  matter_name: `Matter ${i}`,
  matter_number: `M${i}`,
  status: 'open',
}))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/matters']}>
      <Routes><Route path="/matters" element={<MatterPortfolioPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('All accessible matters access count', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    getMyMattersPage.mockResolvedValue({ items: [], total: 0 })
  })
  afterEach(() => { cleanup() })

  it('reports the server access total, not the loaded page size', async () => {
    getMattersV2.mockResolvedValue({ items: pageOf(2), total: 250, page: 1, page_size: 100 })

    renderPage()

    expect(await screen.findByText('250 matters you can access')).toBeInTheDocument()
    expect(screen.queryByText('2 matters you can access')).not.toBeInTheDocument()
    expect(
      screen.getByText(/Showing 2 of 250 loaded\. Search, filters, and the status cards below apply to these loaded matters\./),
    ).toBeInTheDocument()
  })

  it('omits the loaded-scope caveat once the whole access set is shown', async () => {
    getMattersV2.mockResolvedValue({ items: pageOf(2), total: 2, page: 1, page_size: 100 })

    renderPage()

    expect(await screen.findByText('2 matters you can access')).toBeInTheDocument()
    expect(screen.queryByText(/loaded\./)).not.toBeInTheDocument()
  })

  it('shows no access count while loading or after a failure, and clears the error on a successful retry', async () => {
    let finishFirst
    getMattersV2
      .mockImplementationOnce(() => new Promise((_, reject) => { finishFirst = reject }))
      .mockResolvedValueOnce({ items: pageOf(3), total: 3, page: 1, page_size: 100 })

    renderPage()

    expect(screen.queryByText(/you can access/)).not.toBeInTheDocument()
    finishFirst(new Error('network'))
    expect(await screen.findByText('Matters could not be loaded')).toBeInTheDocument()
    expect(screen.queryByText(/you can access/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('3 matters you can access')).toBeInTheDocument()
    expect(screen.queryByText('Matters could not be loaded')).not.toBeInTheDocument()
  })
})
