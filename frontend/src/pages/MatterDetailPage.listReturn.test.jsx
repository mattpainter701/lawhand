import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { rememberListUrl } from '../utils/matterListMemory'

// Stub every api export; the resolver error path only needs getMatterByNumber
// to reject. Mirrors MatterDetailPage.matterNumber.test.jsx.
const { getMatterByNumber } = vi.hoisted(() => ({ getMatterByNumber: vi.fn() }))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  const stubbed = Object.fromEntries(
    Object.entries(actual).map(([key, value]) => [
      key,
      typeof value === 'function' ? vi.fn().mockResolvedValue({}) : value,
    ]),
  )
  return { ...stubbed, getMatterByNumber }
})
vi.mock('../App', () => ({ useAuth: () => ({ user: { hidden_matter_panels: [] } }) }))
vi.mock('../components/toast/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

import MatterDetailPage from './MatterDetailPage'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="path">{`${location.pathname}${location.search}`}</div>
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/matters/:id" element={<MatterDetailPage />} />
        <Route path="/matters" element={<div>Matter Portfolio</div>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('matter detail returns to the remembered list view', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    getMatterByNumber.mockReset()
    getMatterByNumber.mockRejectedValue(new Error('404'))
  })
  afterEach(cleanup)

  it('returns to the filtered, sorted list instead of a reset portfolio', async () => {
    const user = userEvent.setup()
    rememberListUrl('/matters?status=open&q=acme&msort=deadline&mdir=desc')
    renderAt('/matters/SMIT9999')

    await user.click(await screen.findByRole('button', { name: /Back to Matter Portfolio/i }))

    expect(screen.getByTestId('path')).toHaveTextContent(
      '/matters?status=open&q=acme&msort=deadline&mdir=desc',
    )
  })

  it('falls back to the bare portfolio when no list view was recorded', async () => {
    const user = userEvent.setup()
    renderAt('/matters/SMIT9999')

    await user.click(await screen.findByRole('button', { name: /Back to Matter Portfolio/i }))

    expect(screen.getByTestId('path')).toHaveTextContent(/^\/matters$/)
  })
})
