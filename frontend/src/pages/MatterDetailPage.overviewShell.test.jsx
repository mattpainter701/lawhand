import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as api from '../api'
import MatterDetailPage from './MatterDetailPage'

vi.mock('../api', async () => {
  const actual = await vi.importActual('../api')
  return Object.fromEntries(
    Object.entries(actual).map(([key, value]) => [
      key,
      typeof value === 'function' ? vi.fn().mockResolvedValue([]) : value,
    ]),
  )
})
vi.mock('../App', () => ({ useAuth: () => ({ user: { id: 'user', role: 'admin' } }) }))
vi.mock('../components/toast/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))
// Setup and client communication are the "optional" panels that S3.09 moves
// below the work. Mark them so their order is observable.
vi.mock('../components/casesetup/CaseSetupCard', () => ({ default: () => <div>Case setup panel</div> }))
vi.mock('../components/casesetup/ClientConversation', () => ({ default: () => <div>Client conversation panel</div> }))

beforeEach(() => {
  vi.clearAllMocks()
  api.getMatterV2.mockResolvedValue({ id: 'A', matter_name: 'Matter A', status: 'open' })
  api.getMatterDashboard.mockResolvedValue({ open_tasks: 0, active_workers: [] })
  api.getMatterBudgetV2.mockResolvedValue({})
})
afterEach(cleanup)

function renderMatter() {
  return render(
    <MemoryRouter initialEntries={['/matters/A']}>
      <Routes><Route path="/matters/:id" element={<MatterDetailPage />} /></Routes>
    </MemoryRouter>,
  )
}

const before = (first, second) =>
  Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING)

it('leads the overview with next work, ahead of optional setup', async () => {
  renderMatter()
  await screen.findByRole('heading', { name: 'Matter A' })

  const nextWork = await screen.findByRole('heading', { name: 'Next work' })
  const keyDates = screen.getByRole('heading', { name: 'Key Dates' })
  const setup = screen.getByText('Case setup panel')
  const conversation = screen.getByText('Client conversation panel')

  expect(before(nextWork, setup)).toBe(true)
  expect(before(keyDates, setup)).toBe(true)
  expect(before(keyDates, conversation)).toBe(true)
})
