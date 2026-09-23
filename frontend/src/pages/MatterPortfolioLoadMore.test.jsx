import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

const matter = (id, name) => ({ id, matter_name: name, status: 'open' })

function renderPage(path = '/matters') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/matters" element={<MatterPortfolioPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('matter list load-more', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    getMattersV2.mockResolvedValue({ items: [], total: 0 })
  })
  afterEach(cleanup)

  it('pages the assigned list and appends without duplicates', async () => {
    const user = userEvent.setup()
    getMyMattersPage.mockImplementation(({ page }) => Promise.resolve(
      page === 1
        ? { items: [matter('a', 'My Alpha'), matter('b', 'My Beta')], total: 3, page: 1, page_size: 200 }
        : { items: [matter('c', 'My Gamma')], total: 3, page: 2, page_size: 200 },
    ))
    renderPage()

    expect(await screen.findByText('My Alpha')).toBeInTheDocument()
    expect(screen.getByText(/Showing 2 of 3 assigned matters/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Load more/ }))

    expect(await screen.findByText('My Gamma')).toBeInTheDocument()
    expect(getMyMattersPage).toHaveBeenCalledWith({ page: 2, page_size: 200 })
    // The whole set is now loaded, so the control is gone.
    expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument()
  })

  it('pages the all-accessible list', async () => {
    const user = userEvent.setup()
    getMyMattersPage.mockResolvedValue({ items: [], total: 0 })
    getMattersV2.mockImplementation(({ page }) => Promise.resolve(
      page === 1
        ? { items: [matter('x', 'All Alpha'), matter('y', 'All Beta')], total: 3 }
        : { items: [matter('z', 'All Gamma')], total: 3 },
    ))
    renderPage()

    expect(await screen.findByText('All Alpha')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Load more/ }))

    expect(await screen.findByText('All Gamma')).toBeInTheDocument()
    expect(getMattersV2).toHaveBeenCalledWith({ page: 2, page_size: 100 })
    expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument()
  })
})
