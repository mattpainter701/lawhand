import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AppShell from './AppShell'
import { usePageGuideTopic } from './GuideLink'

let currentUser

vi.mock('../App', () => ({
  useAuth: () => ({ user: currentUser, logout: vi.fn(), refreshUser: vi.fn() }),
}))

vi.mock('../api', () => ({
  getConversations: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  getDocuments: vi.fn().mockResolvedValue([]),
  deleteDocument: vi.fn(),
  logout: vi.fn().mockResolvedValue(undefined),
  updateMe: vi.fn().mockResolvedValue({}),
}))

vi.mock('./dialog/ConfirmProvider', () => ({ useConfirm: () => vi.fn() }))
vi.mock('./Sidebar', () => ({ default: () => null }))

const staff = { id: 'u1', role: 'user', enabled_modules: ['matters', 'tasks', 'calendar'] }
const admin = { id: 'a1', role: 'admin', enabled_modules: ['matters', 'tasks', 'admin'] }
const accountant = { id: 'c1', role: 'accountant', enabled_modules: ['admin', 'invoices'] }

function renderAt(entry, user, children = <div>Page</div>) {
  currentUser = user
  render(
    <MemoryRouter initialEntries={[entry]}>
      <AppShell title="Page">{children}</AppShell>
    </MemoryRouter>,
  )
}

function MatterTabProbe() {
  usePageGuideTopic('user', 'matters-and-documents', 'correspondence-and-matter-email', 'Correspondence')
  return <div>Correspondence tab</div>
}

describe('AppShell guide link', () => {
  afterEach(() => {
    cleanup()
    currentUser = undefined
  })

  it('opens the chapter that documents the current screen', () => {
    renderAt('/tasks/42', staff)
    const link = screen.getByRole('link', { name: 'Open the guide for Tasks' })
    expect(link).toHaveAttribute('href', '/guide/tasks-calendar-communications')
  })

  it('lets a page narrow the link to the panel in view', () => {
    renderAt('/matters/42', staff, <MatterTabProbe />)
    expect(screen.getByRole('link', { name: 'Open the guide for Correspondence' }))
      .toHaveAttribute('href', '/guide/matters-and-documents#correspondence-and-matter-email')
  })

  it('does not link to the guide from the guide itself', () => {
    renderAt('/guide/getting-started', staff)
    expect(screen.queryByTestId('shell-guide-link')).toBeNull()
  })

  it('opens Administration chapters inside the Admin Guide for administrators only', () => {
    renderAt('/admin?tab=integrations&integration=zoom', admin)
    expect(screen.getByRole('link', { name: 'Open the guide for Zoom' }))
      .toHaveAttribute('href', '/admin?tab=guide&chapter=zoom-phone-administration')

    cleanup()
    renderAt('/admin?tab=licensing', accountant)
    expect(screen.queryByTestId('shell-guide-link')).toBeNull()
  })
})
