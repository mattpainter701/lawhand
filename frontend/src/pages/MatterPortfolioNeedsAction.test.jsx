import { StrictMode } from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import MatterPortfolioPage, { needsAction } from './MatterPortfolioPage'
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

const matters = [
  { id: 'attention-1', my_assignment_id: 'a1', matter_name: 'Overdue Alpha', status: 'pending', overdue_deadline_label: '3 days overdue' },
  { id: 'attention-2', my_assignment_id: 'a2', matter_name: 'Threatened Beta', status: 'threatened' },
  { id: 'quiet', my_assignment_id: 'a3', matter_name: 'Quiet Gamma', status: 'open', updated_at: '2026-09-21T12:00:00Z' },
  { id: 'closed', my_assignment_id: 'a4', matter_name: 'Closed Delta', status: 'closed', overdue_deadline_label: '10 days overdue' },
  { id: 'settled', my_assignment_id: 'a5', matter_name: 'Settled Epsilon', status: 'settled', overdue_deadline_label: '10 days overdue' },
  { id: 'dismissed', my_assignment_id: 'a6', matter_name: 'Dismissed Zeta', status: 'dismissed', overdue_deadline_label: '10 days overdue' },
]

const daysAgo = (days) => new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString()

describe('needsAction predicate', () => {
  it('flags threatened, overdue, due-today, and stale active matters', () => {
    expect(needsAction({ status: 'threatened' })).toBe(true)
    expect(needsAction({ status: 'open', overdue_deadline_label: '3 days overdue' })).toBe(true)
    expect(needsAction({ status: 'open', overdue_deadline_label: 'Due today' })).toBe(true)
    expect(needsAction({ status: 'active', updated_at: daysAgo(20) })).toBe(true)
  })

  it('does not flag terminal, recent, or on-track matters', () => {
    expect(needsAction({ status: 'closed', overdue_deadline_label: '3 days overdue' })).toBe(false)
    expect(needsAction({ status: 'settled', overdue_deadline_label: '3 days overdue' })).toBe(false)
    expect(needsAction({ status: 'dismissed', overdue_deadline_label: '3 days overdue' })).toBe(false)
    expect(needsAction({ status: 'open', updated_at: daysAgo(2) })).toBe(false)
    expect(needsAction({ status: 'open', overdue_deadline_label: 'Due in 6 days' })).toBe(false)
  })
})

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="Current query">{location.search}</output>
}

function renderAt(path, strict = false) {
  const content = (
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <Routes><Route path="/matters" element={<MatterPortfolioPage />} /></Routes>
    </MemoryRouter>
  )
  return render(strict ? <StrictMode>{content}</StrictMode> : content)
}

function query() {
  return new URLSearchParams(screen.getByLabelText('Current query').textContent)
}

describe('My Matters needs-attention interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-22T12:00:00Z'))
    localStorage.clear()
    getMyMattersPage.mockResolvedValue({ items: matters, total: matters.length })
    getMattersV2.mockResolvedValue({ items: [] })
  })
  afterEach(() => { cleanup(); vi.useRealTimers() })

  it('opens the complete attention list from board and atomically drops its incompatible filters', async () => {
    const user = userEvent.setup()
    renderAt('/matters?view=board&mq=unmatched&mstatus=pending&firmq=client&status=open&msort=deadline&mdir=desc')

    await user.click(await screen.findByRole('button', { name: /need attention/i }))

    expect(query().get('view')).toBeNull()
    expect(query().get('mq')).toBeNull()
    expect(query().get('mstatus')).toBeNull()
    expect(query().get('matn')).toBe('1')
    expect(query().get('firmq')).toBe('client')
    expect(query().get('status')).toBe('open')
    expect(query().get('msort')).toBe('deadline')
    expect(query().get('mdir')).toBe('desc')
    expect(await screen.findByText('Overdue Alpha')).toBeInTheDocument()
    expect(screen.getByText('Threatened Beta')).toBeInTheDocument()
    expect(screen.queryByText('Quiet Gamma')).not.toBeInTheDocument()
    expect(screen.queryByText('Closed Delta')).not.toBeInTheDocument()
    expect(screen.queryByText('Settled Epsilon')).not.toBeInTheDocument()
    expect(screen.queryByText('Dismissed Zeta')).not.toBeInTheDocument()
  })

  it('honors matn on reload and the chip removes only attention mode', async () => {
    const user = userEvent.setup()
    renderAt('/matters?matn=1&mq=alpha&mstatus=pending&msort=deadline&mdir=desc&status=open')

    expect(await screen.findByText('Overdue Alpha')).toBeInTheDocument()
    expect(screen.queryByText('Threatened Beta')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /needs attention/i }))

    expect(query().get('matn')).toBeNull()
    expect(query().get('mq')).toBe('alpha')
    expect(query().get('mstatus')).toBe('pending')
    expect(query().get('msort')).toBe('deadline')
    expect(query().get('mdir')).toBe('desc')
    expect(query().get('status')).toBe('open')
  })

  it('clears attention and the assigned-list filters together while preserving firm filters', async () => {
    const user = userEvent.setup()
    renderAt('/matters?matn=1&mq=missing&mstatus=pending&status=active&q=client')
    await screen.findByRole('heading', { name: 'My Matters' })
    await user.click(await screen.findByRole('button', { name: 'Clear filter' }))

    expect(query().get('matn')).toBeNull()
    expect(query().get('mq')).toBeNull()
    expect(query().get('mstatus')).toBeNull()
    expect(query().get('status')).toBe('active')
    expect(query().get('q')).toBe('client')
    expect(await screen.findByText('Quiet Gamma')).toBeInTheDocument()
  })

  it('clears attention mode when switching back to the board', async () => {
    const user = userEvent.setup()
    renderAt('/matters?matn=1&mq=alpha&mstatus=pending')
    await screen.findByText('Overdue Alpha')
    await user.click(screen.getByRole('button', { name: 'Board' }))

    expect(query().get('view')).toBe('board')
    expect(query().get('matn')).toBeNull()
    expect(query().get('mq')).toBe('alpha')
    expect(query().get('mstatus')).toBe('pending')
  })

  it('labels a partial loaded set and uses the server total in the assigned summary', async () => {
    getMyMattersPage.mockResolvedValue({ items: matters.slice(0, 3), total: 250 })
    renderAt('/matters?view=board')

    expect(await screen.findByText('250 assigned to you')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /2 loaded matters need attention/i })).toBeInTheDocument()
    expect(screen.getByText(/Showing 3 of 250 assigned matters\. Search and filters apply to these loaded matters\./i)).toBeInTheDocument()
  })

  it('ignores a superseded request after the newer list has loaded', async () => {
    let resolveOld
    getMyMattersPage.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    getMyMattersPage.mockResolvedValueOnce({ items: [matters[1]], total: 1 })
    renderAt('/matters?matn=1', true)

    expect(await screen.findByText('Threatened Beta')).toBeInTheDocument()
    await act(async () => { resolveOld({ items: [matters[0]], total: 250 }) })
    expect(screen.getByText('Threatened Beta')).toBeInTheDocument()
    expect(screen.queryByText('Overdue Alpha')).not.toBeInTheDocument()
    expect(screen.getByText('1 assigned to you')).toBeInTheDocument()
  })

  it('offers retry when an empty page does not confirm zero assignments', async () => {
    getMyMattersPage.mockResolvedValueOnce({ items: [], total: 250 })
    renderAt('/matters')
    expect(await screen.findByText('Could not load your matters')).toBeInTheDocument()
    expect(screen.queryByText('No assigned matters')).not.toBeInTheDocument()
    expect(screen.queryByText('250 assigned to you')).not.toBeInTheDocument()
  })

  it('shows a recoverable load error instead of claiming there are no assigned matters', async () => {
    getMyMattersPage.mockRejectedValueOnce(new Error('temporary failure'))
    renderAt('/matters?view=board')

    expect(await screen.findByText('Could not load your matters')).toBeInTheDocument()
    expect(screen.queryByText('No assigned matters')).not.toBeInTheDocument()
    getMyMattersPage.mockResolvedValueOnce({ items: matters })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Overdue Alpha')).toBeInTheDocument()
  })
})
