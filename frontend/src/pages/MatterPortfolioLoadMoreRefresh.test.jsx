import { act, cleanup, render, screen } from '@testing-library/react'
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
// An import finishing is one of the page-1 reloads; expose it as a button.
vi.mock('../components/NewMatterModal', () => ({
  default: ({ onImportComplete }) => (
    <button type="button" onClick={onImportComplete}>Finish import</button>
  ),
}))
vi.mock('../components/casesetup/CloseMatterDialog', () => ({ default: () => null }))

const matter = (id, name) => ({ id, matter_name: name, status: 'open' })

function deferred() {
  let resolve
  const promise = new Promise(r => { resolve = r })
  return { promise, resolve }
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/matters']}>
      <Routes><Route path="/matters" element={<MatterPortfolioPage />} /></Routes>
    </MemoryRouter>,
  )
}

// S3.03: a page-1 reload while "Load more" is in flight must not leave the
// control stuck on "Loading…".
describe('load-more superseded by a page-1 reload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })
  afterEach(cleanup)

  it('leaves the assigned list able to load more', async () => {
    const user = userEvent.setup()
    const pageTwo = deferred()
    getMattersV2.mockResolvedValue({ items: [], total: 0 })
    getMyMattersPage.mockImplementation(({ page }) => (
      page === 1
        ? Promise.resolve({ items: [matter('a', 'My Alpha'), matter('b', 'My Beta')], total: 3 })
        : pageTwo.promise
    ))
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Load more \(1 more\)/ }))
    expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Finish import' }))
    await act(async () => { pageTwo.resolve({ items: [matter('c', 'My Gamma')], total: 3 }) })

    const more = await screen.findByRole('button', { name: /Load more \(1 more\)/ })
    expect(more).toBeEnabled()
    // The superseded page did not append onto the reloaded first page.
    expect(screen.queryByText('My Gamma')).not.toBeInTheDocument()
  })

  it('leaves the all-accessible list able to load more', async () => {
    const user = userEvent.setup()
    const pageTwo = deferred()
    getMyMattersPage.mockResolvedValue({ items: [], total: 0 })
    getMattersV2.mockImplementation(({ page }) => (
      page === 1
        ? Promise.resolve({ items: [matter('x', 'All Alpha'), matter('y', 'All Beta')], total: 3 })
        : pageTwo.promise
    ))
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Load more \(1 more\)/ }))
    expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Finish import' }))
    await act(async () => { pageTwo.resolve({ items: [matter('z', 'All Gamma')], total: 3 }) })

    const more = await screen.findByRole('button', { name: /Load more \(1 more\)/ })
    expect(more).toBeEnabled()
    expect(screen.queryByText('All Gamma')).not.toBeInTheDocument()
  })
})
