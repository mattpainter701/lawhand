import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfirmProvider } from '../components/dialog/ConfirmProvider'
import {
  createPlatformSession,
  getPlatformLLMConfig,
  getPlatformLogsSummary,
  getPlatformSupportQueue,
  getPlatformTenant,
  getPlatformTenants,
  getPlatformUsage,
  getPublicSupportPolicy,
} from '../api'
import PlatformPage, { operatorFromToken } from './PlatformPage'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal()),
  createPlatformSession: vi.fn(),
  getPlatformLLMConfig: vi.fn(),
  getPlatformLogsSummary: vi.fn(),
  getPlatformSupportQueue: vi.fn(),
  getPlatformTenant: vi.fn(),
  getPlatformTenants: vi.fn(),
  getPlatformUsage: vi.fn(),
  getPublicSupportPolicy: vi.fn(),
}))

// A session token whose payload names the operator ("sub").
const token = (sub = 'ops@lawhand.example') => `header.${btoa(JSON.stringify({ sub }))}.signature`

function Location() {
  const location = useLocation()
  return <output aria-label="Location">{`${location.pathname}${location.search}`}</output>
}

function renderConsole(entry = '/platform') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <ConfirmProvider>
        <PlatformPage />
        <Location />
      </ConfirmProvider>
    </MemoryRouter>,
  )
}

async function signIn(user) {
  await user.type(screen.getByLabelText('Platform bootstrap secret'), 'bootstrap-secret-value')
  await user.click(screen.getByRole('button', { name: 'Access Console' }))
}

const sessionEnded = () => Object.assign(new Error('forbidden'), {
  response: { status: 403, data: { detail: 'Invalid or expired platform token' } },
})

beforeEach(() => {
  vi.clearAllMocks()
  createPlatformSession.mockResolvedValue({
    access_token: token(),
    expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
    scopes: ['platform:read', 'platform:write', 'platform:debug'],
  })
  getPlatformLLMConfig.mockResolvedValue({ config: { standard_model: 'lawhand-standard' } })
  getPlatformUsage.mockResolvedValue({
    total_tenants: 6, active_tenants: 5, total_users: 14, requests_30d: 1234, cost_usd_30d: 56.78,
    top_tenants: [{ id: 't-busy', name: 'Busy Firm', domain: 'busy', billing_tier: 'flat', requests_30d: 900, cost_usd_30d: 40 }],
  })
  getPlatformTenants.mockResolvedValue({
    tenants: [{ id: 't-new', name: 'Newest Firm', domain: 'newest', billing_tier: 'payg', signup_status: 'pending', created_at: '2026-09-22T00:00:00Z' }],
    total: 1,
    counts: { all: 6, platform: 5, pending: 2, active: 3, trial: 2, expiring: 1, expired: 1, inactive: 0, demo: 1 },
  })
  getPlatformSupportQueue.mockResolvedValue({ items: [], total: 3, counts: { open: 2, acknowledged: 1, mitigated: 0, resolved: 5, overdue: 1 } })
  getPlatformLogsSummary.mockResolvedValue({
    total_errors: 30, unresolved: 24, by_severity: {}, unresolved_by_severity: { critical: 1, error: 2, warning: 21 },
    by_type: {}, by_tenant: [], trend: [], days: 1,
  })
  // Opening a firm loads its detail; never let a unit test reach a real server.
  getPlatformTenant.mockResolvedValue({
    tenant: { id: 't-busy', name: 'Busy Firm', domain: 'busy', billing_tier: 'flat', tenant_type: 'platform', is_active: true, created_at: '2026-01-01T00:00:00Z' },
    users: [], llm_config: {}, module_config: {}, assistant_config: {}, hidden_matter_panels: [],
  })
  getPublicSupportPolicy.mockResolvedValue({ severities: [] })
})

afterEach(cleanup)

describe('operatorFromToken', () => {
  it('reads the operator id and tolerates a malformed token', () => {
    expect(operatorFromToken(token('alice@lawhand.example'))).toBe('alice@lawhand.example')
    expect(operatorFromToken('not-a-token')).toBeNull()
  })
})

describe('operator console', () => {
  it('opens on what needs attention and identifies the operator', async () => {
    const user = userEvent.setup()
    renderConsole()
    await signIn(user)

    expect(await screen.findByText('Signed in as', { exact: false })).toHaveTextContent('ops@lawhand.example')
    expect(screen.getByText(/Session ends/)).toBeInTheDocument()
    const attention = screen.getByRole('heading', { name: 'Needs attention' }).closest('section')
    expect(within(attention).getByRole('button', { name: /Registrations awaiting approval\s*2/ })).toBeInTheDocument()
    expect(within(attention).getByRole('button', { name: /Support requests needing work\s*3\s*1 past/ })).toBeInTheDocument()
    // Warnings (every client 4xx) are left out of the triage count.
    expect(within(attention).getByRole('button', { name: /Unresolved errors \(24h\)\s*3\s*1 critical/ })).toBeInTheDocument()
    expect(screen.getByText('Model cost (30d)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Busy Firm/ })).toBeInTheDocument()

    const nav = screen.getByRole('navigation', { name: 'Operator console' })
    expect(within(nav).getByRole('button', { name: 'Support, 3 needing work, 1 overdue' })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Overview' })).toHaveAttribute('aria-current', 'page')
  })

  it('jumps from an attention card to the matching firm view', async () => {
    const user = userEvent.setup()
    renderConsole()
    await signIn(user)

    await user.click(await screen.findByRole('button', { name: /Registrations awaiting approval/ }))

    expect(screen.getByRole('status', { name: 'Location' })).toHaveTextContent('/platform?tab=tenants&view=pending')
    await waitFor(() => expect(getPlatformTenants).toHaveBeenLastCalledWith(token(), 1, { status: 'pending', limit: 50 }))
  })

  it('opens a firm from the dashboard by its id', async () => {
    const user = userEvent.setup()
    renderConsole()
    await signIn(user)

    await user.click(await screen.findByRole('button', { name: /Busy Firm/ }))

    expect(screen.getByRole('status', { name: 'Location' })).toHaveTextContent('tab=tenants&view=all&q=t-busy&tenant=t-busy')
    await waitFor(() => expect(getPlatformTenant).toHaveBeenCalledWith(token(), 't-busy'))
    expect(await screen.findByRole('heading', { name: 'Busy Firm' })).toBeInTheDocument()
  })

  it('restores the tab from the address after signing in', async () => {
    const user = userEvent.setup()
    renderConsole('/platform?tab=support')
    await signIn(user)

    expect(await screen.findByRole('heading', { name: 'Customer support queue' })).toBeInTheDocument()
    expect(within(screen.getByRole('navigation', { name: 'Operator console' })).getByRole('button', { name: /Support/ })).toHaveAttribute('aria-current', 'page')
  })

  it('returns to sign-in with an explanation when the session ends, keeping the place', async () => {
    const user = userEvent.setup()
    renderConsole('/platform?tab=tenants&view=trial')
    getPlatformTenants.mockRejectedValue(sessionEnded())
    await signIn(user)

    expect(await screen.findByText(/session expired or was revoked/)).toBeInTheDocument()
    expect(screen.getByLabelText('Platform bootstrap secret')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Location' })).toHaveTextContent('tab=tenants&view=trial')
  })

  it('shows why sign-in failed', async () => {
    createPlatformSession.mockRejectedValue(Object.assign(new Error('forbidden'), {
      response: { status: 403, data: { detail: 'Platform bootstrap credential expired' } },
    }))
    const user = userEvent.setup()
    renderConsole()
    await signIn(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('Platform bootstrap credential expired')
  })
})
