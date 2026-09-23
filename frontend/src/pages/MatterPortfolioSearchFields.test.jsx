import { cleanup, render, screen, waitFor } from '@testing-library/react'
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

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/matters']}>
      <Routes><Route path="/matters" element={<MatterPortfolioPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('all-accessible search scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    getMyMattersPage.mockResolvedValue({ items: [], total: 0 })
  })
  afterEach(cleanup)

  it('states the supported fields beside search instead of implying attorney/description', async () => {
    getMattersV2.mockResolvedValue({ items: [], total: 0 })
    renderPage()

    const input = await screen.findByLabelText('Search accessible matters')
    expect(input).toHaveAttribute('placeholder', 'Search matters')
    expect(input).toHaveAccessibleDescription(
      /matter name, matter number, client name, or organization/i,
    )
  })

  it('clears the load error after a successful retry', async () => {
    const user = userEvent.setup()
    getMattersV2.mockRejectedValueOnce(new Error('boom'))
    getMattersV2.mockResolvedValueOnce({ items: [{ id: 'a', matter_name: 'All Alpha', status: 'open' }], total: 1 })
    renderPage()

    expect(await screen.findByText('Matters could not be loaded')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('All Alpha')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByText('Matters could not be loaded')).not.toBeInTheDocument(),
    )
  })
})
