import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MatterPortfolioPage, { needsAttention } from './MatterPortfolioPage'
import { getMyMattersPage } from '../api'

vi.mock('../App', () => ({
  useAuth: () => ({ user: { id: 'u1', role: 'admin', enabled_modules: [] }, refreshUser: vi.fn(), logout: vi.fn() }),
}))

vi.mock('../utils/reportError', () => ({ reportError: vi.fn() }))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getMattersV2: vi.fn().mockResolvedValue({ items: [] }),
    getMyMattersPage: vi.fn(),
    setAssignmentActive: vi.fn(),
    updateMatterV2: vi.fn(),
  }
})

const matter = (overrides = {}) => ({
  id: 'm1',
  matter_name: 'Matter',
  matter_number: 'M-1',
  client_name: 'Client',
  status: 'open',
  risk_level: 'low',
  created_at: '2026-01-01T00:00:00Z',
  ...overrides,
})

describe('Needs attention view (S3.04)', () => {
  afterEach(cleanup)

  it('opens exactly the counted set and clears back to the full list', async () => {
    const overdue = matter({ id: 'a', matter_name: 'Overdue matter', overdue_deadline_label: '3 days overdue' })
    const normal = matter({ id: 'b', matter_name: 'Normal matter' })
    const closedOverdue = matter({
      id: 'c',
      matter_name: 'Closed overdue matter',
      status: 'closed',
      overdue_deadline_label: '4 days overdue',
    })
    getMyMattersPage.mockResolvedValue({ items: [overdue, normal, closedOverdue], total: 3, page: 1, page_size: 200 })

    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/matters']}>
        <MatterPortfolioPage />
      </MemoryRouter>,
    )

    // The predicate the count and the view share excludes closed matters.
    expect(needsAttention(overdue)).toBe(true)
    expect(needsAttention(closedOverdue)).toBe(false)

    const attentionButton = await screen.findByRole('button', { name: /need attention/ })
    expect(attentionButton).toHaveTextContent('1 matter need attention')

    // Before filtering, all assigned matters are listed.
    expect(await screen.findByText('Normal matter')).toBeInTheDocument()

    await user.click(attentionButton)

    expect(await screen.findByText('Overdue matter')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Normal matter')).not.toBeInTheDocument())
    // The view must match the count: the closed stale matter is not shown.
    expect(screen.queryByText('Closed overdue matter')).not.toBeInTheDocument()

    // Clearing the attention filter restores the full list.
    await user.click(screen.getByRole('button', { name: 'Needs attention' }))
    expect(await screen.findByText('Normal matter')).toBeInTheDocument()
  })
})
