import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, expect, it, beforeEach, afterEach } from 'vitest'
import ProfilePage from './ProfilePage'
import { getMyMattersPage } from '../api'

const user = { id: 'u1', full_name: 'Test Attorney', email: 'a@firm.com', role: 'admin', license_active: true, is_active: true }

vi.mock('../App', () => ({ useAuth: () => ({ user, refreshUser: vi.fn() }) }))
vi.mock('../api', () => ({
  getMyMattersPage: vi.fn(),
  getTimeEntries: vi.fn().mockResolvedValue([]),
  getWorkspaceMcpGrants: vi.fn().mockResolvedValue({ items: [] }),
  revokeAllSessions: vi.fn(),
  updateMe: vi.fn(),
}))
vi.mock('../components/ReleaseInfoPanel', () => ({ default: () => null }))
vi.mock('../components/WorkspaceMcpGrantsPanel', () => ({ default: () => null }))
vi.mock('../components/ConnectedAccountsCard', () => ({ default: () => null }))

const renderPage = () => render(<MemoryRouter><ProfilePage /></MemoryRouter>)
const matter = (id, name) => ({ id, matter_name: name, status: 'open', is_closed: false })

// S3.03: Profile lists every assigned matter, and a failure is not "no matters".
describe('Profile assigned matters', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(cleanup)

  it('counts the server total and says the list is partial', async () => {
    const firstPage = Array.from({ length: 3 }, (_, i) => matter(`m${i}`, `Matter ${i}`))
    getMyMattersPage.mockResolvedValue({ items: firstPage, total: 250 })
    renderPage()

    expect(await screen.findByRole('link', { name: 'Matter 0' })).toBeInTheDocument()
    expect(getMyMattersPage).toHaveBeenCalledWith({ page: 1, page_size: 200 })
    expect(screen.getByText('250')).toBeInTheDocument()
    expect(screen.getByText(/Showing the 3 most recently updated of your 250 assigned matters/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See them all in Matters' })).toHaveAttribute('href', '/matters')
  })

  it('counts active matters when the whole set is listed', async () => {
    getMyMattersPage.mockResolvedValue({ items: [matter('a', 'Alpha'), matter('b', 'Beta')], total: 2 })
    renderPage()

    expect(await screen.findByText('My Matters (2 active)')).toBeInTheDocument()
    expect(screen.queryByText(/Showing the/)).not.toBeInTheDocument()
  })

  it('shows a load failure with a retry, not an empty list', async () => {
    const actor = userEvent.setup()
    getMyMattersPage.mockRejectedValueOnce(new Error('offline'))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Your assigned matters could not be loaded')
    expect(screen.queryByText('You have no assigned matters.')).not.toBeInTheDocument()
    expect(screen.getByText('My Matters (could not load)')).toBeInTheDocument()

    getMyMattersPage.mockResolvedValueOnce({ items: [matter('m1', 'Smith v. Jones')], total: 1 })
    await actor.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('link', { name: 'Smith v. Jones' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('treats a malformed response as a failure', async () => {
    getMyMattersPage.mockResolvedValue({ detail: 'unexpected' })
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Your assigned matters could not be loaded')
  })

  it('still reads as empty when the user truly has no matters', async () => {
    getMyMattersPage.mockResolvedValue({ items: [], total: 0 })
    renderPage()

    expect(await screen.findByText('You have no assigned matters.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
