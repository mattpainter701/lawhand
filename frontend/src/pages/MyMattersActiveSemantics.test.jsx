// Regression coverage for the two "My Matters" findings:
//   #503 — the hover `View →` affordance was a decorative <span>.
//   #502 — "Active" named the lifecycle status, the status filter tab, and a
//          personal assignment flag, all on one screen.
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  MY_MATTER_STATUS_TABS,
  MatterCard,
  MyMatterRow,
  NOT_WORKING_LABEL,
  WORKING_ON_LABEL,
} from './MatterPortfolioPage'

afterEach(() => cleanup())

const matter = (overrides = {}) => ({
  id: 'matter-1',
  matter_name: 'Acme contract review',
  client_name: 'Acme Corp',
  status: 'active',
  risk_level: 'low',
  my_assignment_id: 'assignment-1',
  is_active_working: false,
  ...overrides,
})

const renderRow = (m, props = {}) =>
  render(
    <MemoryRouter>
      <table>
        <tbody>
          <MyMatterRow m={m} onToggleActive={vi.fn()} togglingId={null} {...props} />
        </tbody>
      </table>
    </MemoryRouter>,
  )

describe('#503 — the row View affordance navigates', () => {
  it('is a link to the matter, not a decorative span', () => {
    renderRow(matter())
    const view = screen.getByRole('link', { name: 'View Acme contract review' })
    expect(view).toHaveAttribute('href', '/matters/matter-1')
    expect(view).toHaveTextContent('View →')
  })

  it('is reachable by keyboard and stays revealed on focus', async () => {
    const user = userEvent.setup()
    renderRow(matter())
    const view = screen.getByRole('link', { name: 'View Acme contract review' })

    // Row order: matter title, working toggle, then View.
    await user.tab()
    await user.tab()
    await user.tab()
    expect(view).toHaveFocus()
    // Hover-only reveal would hide it from exactly the readers who tab to it.
    expect(view).toHaveClass('focus-visible:opacity-100')
  })

  it('names the matter it opens, so the label is not a bare "View" out of context', () => {
    renderRow(matter({ matter_name: 'Rivera custody' }))
    expect(screen.getByRole('link', { name: 'View Rivera custody' })).toBeInTheDocument()
  })
})

describe('#502 — "Active" has one meaning on screen', () => {
  it('names the assignment flag for what it does, not for the lifecycle status', () => {
    renderRow(matter({ is_active_working: false }))
    expect(screen.getByRole('button', { name: NOT_WORKING_LABEL })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Set Active' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Active' })).not.toBeInTheDocument()
  })

  it('exposes the flag as a toggle rather than a label that looks like a state change', () => {
    renderRow(matter({ is_active_working: true }))
    const toggle = screen.getByRole('button', { name: WORKING_ON_LABEL })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    expect(toggle.getAttribute('title')).toMatch(/does not change the matter status/i)
  })

  it('patches the assignment, never the matter status', async () => {
    const user = userEvent.setup()
    const onToggleActive = vi.fn()
    renderRow(matter(), { onToggleActive })

    await user.click(screen.getByRole('button', { name: NOT_WORKING_LABEL }))
    expect(onToggleActive).toHaveBeenCalledWith('assignment-1', 'matter-1', true)
  })

  it('does not dress the personal flag in the lifecycle status palette', () => {
    // StatusBadge renders lifecycle "active" in green. If the flag were green
    // too, the two Actives would still be indistinguishable at a glance.
    renderRow(matter({ is_active_working: true }))
    const toggle = screen.getByRole('button', { name: WORKING_ON_LABEL })
    expect(toggle.className).not.toMatch(/green/)
    expect(toggle.className).toMatch(/brand-accent/)
  })

  it('keeps the lifecycle badge and the personal flag separately readable in a row', () => {
    renderRow(matter({ status: 'active', is_active_working: true }))
    // The lifecycle status is still its own badge, spelled "active"...
    expect(screen.getByText('active')).toBeInTheDocument()
    // ...and the flag no longer borrows that word.
    expect(screen.getByRole('button', { name: WORKING_ON_LABEL })).toBeInTheDocument()
  })

  it('uses the same wording on the board card as in the list row', () => {
    render(
      <MemoryRouter>
        <MatterCard
          m={matter()}
          onToggleActive={vi.fn()}
          togglingId={null}
          showAlert={false}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('button', { name: NOT_WORKING_LABEL })).toBeInTheDocument()
  })

  it('leaves the status filter tab owning the word Active', () => {
    const tab = MY_MATTER_STATUS_TABS.find(t => t.key === 'active')
    expect(tab.label).toBe('Active')
    expect([WORKING_ON_LABEL, NOT_WORKING_LABEL]).not.toContain(tab.label)
  })

  it('disables the flag while its patch is in flight', () => {
    const { container } = renderRow(matter(), { togglingId: 'assignment-1' })
    const toggle = within(container).getByRole('button', { name: NOT_WORKING_LABEL })
    expect(toggle).toBeDisabled()
  })
})
