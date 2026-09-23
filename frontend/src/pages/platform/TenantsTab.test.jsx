import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfirmProvider } from '../../components/dialog/ConfirmProvider'
import {
  findPlatformUsers,
  getLLMRoutingProfiles,
  getPlatformOperatorAudit,
  getPlatformPlans,
  getPlatformSupportQueue,
  getPlatformTenant,
  getPlatformTenantDiagnostics,
  getPlatformTenantLogs,
  getPlatformTenants,
  getPublicSupportPolicy,
  updatePlatformTenant,
} from '../../api'
import TenantsTab from './TenantsTab'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal()),
  approvePlatformTenantTrial: vi.fn(),
  findPlatformUsers: vi.fn(),
  getLLMRoutingProfiles: vi.fn(),
  getPlatformOperatorAudit: vi.fn(),
  getPlatformPlans: vi.fn(),
  getPlatformSupportQueue: vi.fn(),
  getPlatformTenant: vi.fn(),
  getPlatformTenantCompliance: vi.fn(),
  getPlatformTenantDiagnostics: vi.fn(),
  getPlatformTenantLogs: vi.fn(),
  getPlatformTenants: vi.fn(),
  getPublicSupportPolicy: vi.fn(),
  provisionPlatformTenant: vi.fn(),
  updatePlatformTenant: vi.fn(),
}))

const TENANT_ID = '10000000-0000-0000-0000-000000000001'

const summary = {
  id: TENANT_ID,
  name: 'Northwind Legal',
  domain: 'northwind-1a2b3c4d',
  company_name: 'Northwind Legal PLLC',
  billing_tier: 'payg',
  tenant_type: 'platform',
  expires_at: '2099-01-01T00:00:00Z',
  on_trial: true,
  signup_status: 'approved',
  signup_email: 'owner@northwind.example',
  premium_ai_trial_enabled: false,
  flat_seat_count: 1,
  is_active: true,
  stripe_subscription_status: 'none',
  mcp_entitlement_status: 'disabled',
  mcp_billing_status: 'disabled',
  user_count: 2,
  requests_30d: 40,
  cost_usd_30d: 1.5,
  created_at: '2026-09-01T00:00:00Z',
}

const counts = { all: 5, platform: 4, pending: 1, active: 3, trial: 2, expiring: 1, expired: 0, inactive: 0, demo: 1 }

const detail = {
  tenant: summary,
  users: [
    { id: 'u1', email: 'owner@northwind.example', full_name: 'Olive Owner', role: 'admin', is_active: true, license_active: true, premium_ai_enabled: false, created_at: '2026-09-01T00:00:00Z' },
    { id: 'u2', email: 'new@northwind.example', full_name: null, role: 'user', is_active: false, license_active: false, premium_ai_enabled: false, created_at: '2026-09-02T00:00:00Z' },
  ],
  usage_30d: { requests: 40, tokens_in: 0, tokens_out: 0, cost_usd: 1.5 },
  llm_config: { routing_profile_id: null, routing_profile: null },
  module_config: { plan: 'full-trial' },
  assistant_config: { background_assistant_enabled: false },
  hidden_matter_panels: [],
}

function renderTab(props = {}) {
  const onNavigate = vi.fn()
  const view = render(
    <ConfirmProvider>
      <TenantsTab
        platformKey="token"
        session={{ scopes: ['platform:read', 'platform:write', 'platform:debug'] }}
        llmConfig={null}
        view="platform"
        query=""
        page={1}
        expandedId=""
        onNavigate={onNavigate}
        onOpenTenant={vi.fn()}
        onOpenLogs={vi.fn()}
        onAuthError={vi.fn()}
        {...props}
      />
    </ConfirmProvider>,
  )
  return { ...view, onNavigate }
}

beforeEach(() => {
  vi.clearAllMocks()
  getPlatformTenants.mockResolvedValue({ tenants: [summary], total: 1, page: 1, limit: 50, counts })
  getPlatformTenant.mockResolvedValue(detail)
  getLLMRoutingProfiles.mockResolvedValue({ profiles: [] })
  getPlatformPlans.mockResolvedValue({ plans: [] })
  getPlatformSupportQueue.mockResolvedValue({ items: [], total: 0, counts: {} })
  getPublicSupportPolicy.mockResolvedValue({ severities: [] })
  getPlatformTenantDiagnostics.mockResolvedValue({
    tenant_id: TENANT_ID, tenant_name: 'Northwind Legal', is_active: true, billing_tier: 'payg', window_hours: 24,
    requests: 200, error_rate: 0.05, errors_by_severity: { error: 3 }, unresolved_errors: 2,
    top_failing_endpoints: [{ endpoint: '/api/calendar/sync', status_code: 502, count: 9 }],
    failed_sync_runs: [{ id: 's1', provider: 'google', job_type: 'calendar', status: 'failed', started_at: '2026-09-23T08:00:00Z', items_ok: 0, items_failed: 4, error_summary: 'invalid_grant: Token has been expired or revoked.' }],
    stuck_jobs: [], active_users: 2, last_activity_at: '2026-09-23T08:59:00Z',
  })
  getPlatformTenantLogs.mockResolvedValue({ errors: [], total: 0, page: 1, limit: 10 })
  getPlatformOperatorAudit.mockResolvedValue({
    entries: [{
      id: 'a1', action: 'tenant.updated', actor_type: 'platform_key', actor_id: 'ops@lawhand', resource_type: 'tenant',
      resource_id: TENANT_ID, ip_address: null, created_at: '2026-09-22T12:00:00Z',
      metadata: { tenant_id: TENANT_ID, changes: { seat_count: { from: 1, to: 4 } } },
    }],
    total: 1, page: 1, limit: 25,
  })
  updatePlatformTenant.mockResolvedValue({ status: 'updated' })
})

afterEach(cleanup)

describe('firm directory', () => {
  it('searches on the server and shows every lifecycle view with its count', async () => {
    const user = userEvent.setup()
    const { onNavigate } = renderTab()

    expect(await screen.findByText('Northwind Legal')).toBeInTheDocument()
    expect(getPlatformTenants).toHaveBeenCalledWith('token', 1, { status: 'platform', limit: 50 })
    const views = screen.getByRole('group', { name: 'Firm lifecycle view' })
    expect(within(views).getByRole('button', { name: /Needs approval/ })).toHaveTextContent('1')

    await user.click(within(views).getByRole('button', { name: /Ending ≤14 days/ }))
    expect(onNavigate).toHaveBeenCalledWith({ view: 'expiring', page: 1 })

    await user.type(screen.getByRole('searchbox', { name: 'Search firms' }), 'north')
    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith({ q: 'north', page: 1 }, { replace: true }))
  })

  it('passes the committed search and view to the API', async () => {
    renderTab({ view: 'pending', query: 'north', page: 2 })
    await waitFor(() => expect(getPlatformTenants).toHaveBeenCalledWith('token', 2, { status: 'pending', limit: 50, q: 'north' }))
  })

  it('finds a firm from a user’s email address', async () => {
    findPlatformUsers.mockResolvedValue([{ id: 'u1', email: 'owner@northwind.example', full_name: 'Olive Owner', role: 'admin', is_active: true, tenant_id: TENANT_ID, tenant_name: 'Northwind Legal' }])
    const onOpenTenant = vi.fn()
    const user = userEvent.setup()
    renderTab({ query: 'owner@northwind', onOpenTenant })

    await user.click(await screen.findByRole('button', { name: 'Open Northwind Legal' }))
    expect(findPlatformUsers).toHaveBeenCalledWith('token', 'owner@northwind')
    expect(onOpenTenant).toHaveBeenCalledWith(TENANT_ID)
  })

  it('keeps registration out of the way until it is needed', async () => {
    const user = userEvent.setup()
    renderTab()
    await screen.findByText('Northwind Legal')
    expect(screen.queryByLabelText('Firm name')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Register customer' }))
    expect(screen.getByLabelText('Firm name')).toBeInTheDocument()
  })
})

describe('firm panel', () => {
  it('opens on an overview with user status, and switches sections', async () => {
    const user = userEvent.setup()
    renderTab({ expandedId: TENANT_ID })

    expect(await screen.findByRole('heading', { name: 'Northwind Legal' })).toBeInTheDocument()
    const users = screen.getByRole('heading', { name: 'Users (2)' }).parentElement.parentElement
    expect(within(users).getByText('Not active')).toBeInTheDocument()
    expect(within(users).getByText('Unlicensed')).toBeInTheDocument()

    const sections = screen.getByRole('group', { name: 'Northwind Legal sections' })
    await user.click(within(sections).getByRole('button', { name: 'Health' }))
    expect(await screen.findByText('/api/calendar/sync')).toBeInTheDocument()
    expect(screen.getByText(/needs to reconnect this integration/)).toBeInTheDocument()
    expect(getPlatformTenantDiagnostics).toHaveBeenCalledWith('token', TENANT_ID, 24)

    await user.click(within(sections).getByRole('button', { name: 'History' }))
    expect(await screen.findByText('seat_count: 1 → 4')).toBeInTheDocument()
    expect(getPlatformOperatorAudit).toHaveBeenCalledWith('token', { page: 1, limit: 25, days: 90, exclude_requests: true, tenant_id: TENANT_ID })

    await user.click(within(sections).getByRole('button', { name: 'Support' }))
    await waitFor(() => expect(getPlatformSupportQueue).toHaveBeenCalledWith('token', { status: 'all', limit: 100, tenant_id: TENANT_ID }))
  })

  it('asks before deactivating and refreshes the firm afterwards', async () => {
    const user = userEvent.setup()
    renderTab({ expandedId: TENANT_ID })

    const sections = await screen.findByRole('group', { name: 'Northwind Legal sections' })
    await user.click(within(sections).getByRole('button', { name: 'Access & billing' }))
    await user.click(screen.getByRole('button', { name: 'Deactivate firm' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Deactivate firm' }))

    await waitFor(() => expect(updatePlatformTenant).toHaveBeenCalledWith('token', TENANT_ID, { is_active: false }))
    await waitFor(() => expect(getPlatformTenant).toHaveBeenCalledTimes(2))
    expect(screen.getByText(/Revoke trial and release its login/)).toBeInTheDocument()
  })

  it('shows a firm opened from a link even when it is not in the current view', async () => {
    getPlatformTenants.mockResolvedValue({ tenants: [], total: 0, page: 1, limit: 50, counts })
    renderTab({ expandedId: TENANT_ID })

    const opened = await screen.findByRole('region', { name: 'Open firm' })
    expect(await within(opened).findByRole('heading', { name: 'Northwind Legal' })).toBeInTheDocument()
  })

  it('hides debug-only sections behind a scope notice', async () => {
    const user = userEvent.setup()
    renderTab({ expandedId: TENANT_ID, session: { scopes: ['platform:read', 'platform:write'] } })

    const sections = await screen.findByRole('group', { name: 'Northwind Legal sections' })
    await user.click(within(sections).getByRole('button', { name: 'Health' }))
    expect(screen.getByText(/Tenant health shows failing endpoints/)).toBeInTheDocument()
    expect(getPlatformTenantDiagnostics).not.toHaveBeenCalled()
  })
})
