import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import * as api from '../api'
import MatterDetailPage from './MatterDetailPage'

vi.mock('../api', async () => {
  const actual = await vi.importActual('../api')
  return Object.fromEntries(Object.entries(actual).map(([key, value]) => [key, typeof value === 'function' ? vi.fn().mockResolvedValue([]) : value]))
})
vi.mock('../App', () => ({ useAuth: () => ({ user: { id: 'user', role: 'admin' } }) }))
vi.mock('../components/toast/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))

beforeEach(() => {
  vi.clearAllMocks()
  api.getMatterV2.mockImplementation(async id => ({ id, matter_name: `Matter ${id}`, assignments: [], key_dates: {}, status: 'open' }))
  api.getMatterDashboard.mockResolvedValue({ open_tasks: 0, active_workers: [] })
  api.getMatterBudgetV2.mockResolvedValue({})
})
afterEach(cleanup)

it.each(['details', 'people'])('shows the API save error and keeps the %s editor open', async section => {
  api.updateMatterV2.mockRejectedValueOnce(new Error('Hourly request limit exceeded. Please retry in 20 minutes.'))
  render(<MemoryRouter initialEntries={['/matters/A?tab=settings']}>
    <Routes><Route path="/matters/:id" element={<MatterDetailPage />} /></Routes>
  </MemoryRouter>)
  await screen.findByRole('heading', { name: 'Matter A' })
  const editors = screen.getAllByRole('button', { name: 'Edit', exact: true })
  fireEvent.click(editors[section === 'details' ? 0 : 1])
  if (section === 'details') {
    fireEvent.click(screen.getByRole('button', { name: 'Edit Details', exact: true }))
    fireEvent.change(screen.getByLabelText('Description', { exact: true }), { target: { value: 'Preserve this draft' } })
  }
  fireEvent.click(screen.getByRole('button', { name: section === 'details' ? 'Save Changes' : 'Save', exact: true }))
  expect((await screen.findAllByText('Hourly request limit exceeded. Please retry in 20 minutes.')).length).toBeGreaterThan(0)
  expect(screen.getAllByRole('button', { name: 'Cancel', exact: true }).length).toBeGreaterThan(0)
  if (section === 'details') expect(screen.getByLabelText('Description', { exact: true })).toHaveValue('Preserve this draft')
})

it.each(['resolve', 'reject'])('ignores a late note %s after switching away and back to the same matter', async outcome => {
  let settle
  api.addMatterNote.mockImplementationOnce(() => new Promise((resolve, reject) => { settle = outcome === 'resolve' ? resolve : reject }))
  render(<MemoryRouter initialEntries={['/matters/A']}>
    <Link to="/matters/A">Go A</Link><Link to="/matters/B">Go B</Link>
    <Routes><Route path="/matters/:id" element={<MatterDetailPage />} /></Routes>
  </MemoryRouter>)
  await screen.findByRole('heading', { name: 'Matter A' })
  fireEvent.click(screen.getByRole('button', { name: 'Quick note' }))
  fireEvent.change(screen.getByLabelText('Title', { exact: true }), { target: { value: 'Old A draft' } })
  fireEvent.change(screen.getByLabelText('Content', { exact: true }), { target: { value: 'Original note' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save Note', exact: true }))
  await waitFor(() => expect(api.addMatterNote).toHaveBeenCalledOnce())
  fireEvent.click(screen.getByRole('link', { name: 'Go B' }))
  await screen.findByRole('heading', { name: 'Matter B' })
  fireEvent.click(screen.getByRole('link', { name: 'Go A' }))
  await screen.findByRole('heading', { name: 'Matter A' })
  fireEvent.click(screen.getByRole('button', { name: 'Quick note' }))
  fireEvent.change(screen.getByLabelText('Title', { exact: true }), { target: { value: 'New A draft' } })
  fireEvent.change(screen.getByLabelText('Content', { exact: true }), { target: { value: 'Do not replace this' } })
  const timelineCalls = api.getMatterTimeline.mock.calls.length
  await act(async () => settle(outcome === 'resolve' ? { id: 'saved-original' } : new Error('late failure')))
  expect(screen.getByLabelText('Title', { exact: true })).toHaveValue('New A draft')
  expect(screen.getByLabelText('Content', { exact: true })).toHaveValue('Do not replace this')
  expect(screen.queryByText('Note saved.')).not.toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(api.getMatterTimeline).toHaveBeenCalledTimes(timelineCalls)
})
