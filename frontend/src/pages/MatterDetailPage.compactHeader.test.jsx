import { cleanup, render, screen, within } from '@testing-library/react'
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

beforeEach(() => {
  vi.clearAllMocks()
  api.getMatterV2.mockResolvedValue({
    id: 'A',
    matter_name: 'Matter A',
    client_name: 'Acme Corp',
    attorney_of_record_name: 'Dana Roe',
    partner_attorney_name: 'Sam Partner',
    status: 'active',
    risk_level: 'critical',
    description: 'A long description that used to lead the page.',
  })
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

it('leads with identity and responsibility, then lifecycle, then description', async () => {
  renderMatter()
  await screen.findByRole('heading', { name: 'Matter A' })

  // Identity and responsibility are on the page at all (not only in Settings).
  const identity = within(screen.getByTestId('matter-identity'))
  expect(identity.getByText('Acme Corp')).toBeInTheDocument()
  expect(identity.getByText('Dana Roe')).toBeInTheDocument()
  expect(identity.getByText('Sam Partner')).toBeInTheDocument()

  const client = identity.getByText('Acme Corp')
  const status = screen.getByText('active')
  const description = screen.getAllByText('A long description that used to lead the page.')[0]

  // Client and lifecycle come before the description; the old order had the
  // description first.
  expect(before(client, description)).toBe(true)
  expect(before(status, description)).toBe(true)
})
