import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ConflictChecksPage from './ConflictChecksPage'
import {
  closeConflictCheck,
  createConflictCheck,
  getMyMattersPage,
  listConflictChecks,
} from '../api'

vi.mock('../api', () => ({
  listConflictChecks: vi.fn(),
  createConflictCheck: vi.fn(),
  closeConflictCheck: vi.fn(),
  downloadConflictCheckReport: vi.fn(),
  getMyMattersPage: vi.fn(),
}))

const openRecord = {
  id: 'check-1',
  matter_id: null,
  label: 'Smith intake',
  query: { names: ['Alice Smith'], organizations: [], emails: [] },
  matches: [],
  match_count: 0,
  restricted_matter_count: 0,
  status: 'open',
  decision: 'needs_review',
  notes: null,
  created_at: '2026-08-27T12:00:00Z',
  closed_at: null,
}

describe('ConflictChecksPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listConflictChecks.mockResolvedValue({ items: [], total: 0 })
    getMyMattersPage.mockResolvedValue({ items: [], total: 0 })
    createConflictCheck.mockResolvedValue(openRecord)
    closeConflictCheck.mockResolvedValue({
      ...openRecord,
      status: 'closed',
      decision: 'no_conflict_found',
      notes: 'Reviewed the contact and representation history.',
      closed_at: '2026-08-27T12:10:00Z',
    })
  })

  afterEach(cleanup)

  it('runs a saved search and requires an acknowledged review before closing', async () => {
    const user = userEvent.setup()
    render(<ConflictChecksPage />)

    expect(await screen.findByRole('heading', { name: 'Conflict Search' })).toBeInTheDocument()
    await user.type(screen.getByLabelText(/Search label/), 'Smith intake')
    await user.type(screen.getByLabelText(/People and known aliases/), 'Alice Smith')
    await user.click(screen.getByRole('button', { name: /Run and save search/ }))

    await waitFor(() => expect(createConflictCheck).toHaveBeenCalledWith({
      label: 'Smith intake',
      names: ['Alice Smith'],
      organization_names: [],
      emails: [],
      matter_id: null,
    }))
    expect(await screen.findByText(/No potential matches were returned/)).toBeInTheDocument()

    await user.type(
      screen.getByPlaceholderText(/Document sources reviewed/),
      'Reviewed the contact and representation history.',
    )
    const closeButton = screen.getByRole('button', { name: /Close and lock record/ })
    expect(closeButton).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    await user.click(closeButton)

    await waitFor(() => expect(closeConflictCheck).toHaveBeenCalledWith(
      'check-1',
      expect.objectContaining({
        decision: 'no_conflict_found',
        acknowledge_attorney_review: true,
      }),
    ))
    expect(await screen.findByText(/This record is immutable/)).toBeInTheDocument()
  })

  it('offers every assigned matter as a link, past the first page', async () => {
    const firstPage = Array.from({ length: 200 }, (_, i) => ({ id: `m${i}`, matter_name: `Matter ${i}` }))
    getMyMattersPage.mockImplementation(({ page }) => Promise.resolve(
      page === 1
        ? { items: firstPage, total: 201 }
        : { items: [{ id: 'm200', matter_name: 'Matter 200 on page two' }], total: 201 },
    ))
    render(<ConflictChecksPage />)

    expect(await screen.findByRole('option', { name: 'Matter 200 on page two' })).toBeInTheDocument()
    expect(getMyMattersPage).toHaveBeenCalledWith({ page: 2, page_size: 200 })
    expect(screen.queryByText(/could not be loaded/)).not.toBeInTheDocument()
  })

  it('says the matters failed to load instead of showing an empty picker', async () => {
    const user = userEvent.setup()
    getMyMattersPage.mockRejectedValueOnce(new Error('offline'))
    render(<ConflictChecksPage />)

    expect(await screen.findByText(/Your assigned matters could not be loaded/)).toBeInTheDocument()
    // The search itself is still usable without a link.
    expect(screen.getByRole('option', { name: 'Not linked' })).toBeInTheDocument()

    getMyMattersPage.mockResolvedValueOnce({ items: [{ id: 'm1', matter_name: 'Smith v. Jones' }], total: 1 })
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('option', { name: 'Smith v. Jones' })).toBeInTheDocument()
    expect(screen.queryByText(/Your assigned matters could not be loaded/)).not.toBeInTheDocument()
  })

  it('states when only part of a very large assigned set is listed', async () => {
    getMyMattersPage.mockImplementation(({ page }) => Promise.resolve({
      items: Array.from({ length: 200 }, (_, i) => ({ id: `p${page}-${i}`, matter_name: `P${page} ${i}` })),
      total: 2500,
    }))
    render(<ConflictChecksPage />)

    expect(await screen.findByText(/Showing the 2000 most recently updated of your 2500 assigned matters/)).toBeInTheDocument()
    expect(getMyMattersPage).toHaveBeenCalledTimes(10)
  })
})
