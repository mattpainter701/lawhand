import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import MatterPortfolioPage from './MatterPortfolioPage'
import { getMattersV2, getMyMattersPage } from '../api'
import { readRememberedListUrl, rememberListScroll } from '../utils/matterListMemory'

vi.mock('../App', () => ({ useAuth: () => ({ user: { id: 'user-1' } }) }))
vi.mock('../api', () => ({
  getMattersV2: vi.fn(),
  getMyMattersPage: vi.fn(),
  setAssignmentActive: vi.fn(),
  updateMatterV2: vi.fn(),
}))
vi.mock('../components/NewMatterModal', () => ({ default: () => null }))
vi.mock('../components/casesetup/CloseMatterDialog', () => ({ default: () => null }))

const matters = [{ id: 'm1', matter_name: 'Alpha', status: 'open' }]

function renderPage(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <div data-app-scroll style={{ overflow: 'auto' }}>
        <Routes><Route path="/matters" element={<MatterPortfolioPage />} /></Routes>
      </div>
    </MemoryRouter>,
  )
}

describe('matter portfolio list memory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.sessionStorage.clear()
    getMyMattersPage.mockResolvedValue({ items: [], total: 0 })
    getMattersV2.mockResolvedValue({ items: matters, total: 1 })
  })
  afterEach(cleanup)

  it('remembers the exact list view URL, query and sort included', async () => {
    renderPage('/matters?status=open&q=acme&msort=deadline&mdir=desc')

    await waitFor(() =>
      expect(readRememberedListUrl()).toBe('/matters?status=open&q=acme&msort=deadline&mdir=desc'),
    )
  })

  it('restores the saved scroll offset once the list has loaded', async () => {
    const url = '/matters?status=open'
    rememberListScroll(url, 420)

    const { container } = renderPage(url)
    const scroller = container.querySelector('[data-app-scroll]')

    await screen.findByText('Alpha')
    await waitFor(() => expect(scroller.scrollTop).toBe(420))
  })

  it('waits for My Matters before restoring, so the offset is not cut short', async () => {
    const url = '/matters?status=open'
    rememberListScroll(url, 420)
    let resolveMine
    getMyMattersPage.mockReturnValue(new Promise(resolve => { resolveMine = resolve }))

    const { container } = renderPage(url)
    const scroller = container.querySelector('[data-app-scroll]')

    await screen.findByText('Alpha')
    // The all-matters list is in, but My Matters (above it) is still loading.
    expect(scroller.scrollTop).toBe(0)

    await act(async () => { resolveMine({ items: [], total: 0 }) })
    await waitFor(() => expect(scroller.scrollTop).toBe(420))
  })
})
