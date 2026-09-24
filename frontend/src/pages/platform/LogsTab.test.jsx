import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getPlatformAccessLogs,
  getPlatformAccessLogsSummary,
  getPlatformErrorDetail,
  getPlatformLogs,
  getPlatformLogsSummary,
  getPlatformTenantLogsSummary,
  getPlatformTenants,
} from '../../api'
import LogsTab, { statusClassTotals } from './LogsTab'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal()),
  getPlatformAccessLogs: vi.fn(),
  getPlatformAccessLogsSummary: vi.fn(),
  getPlatformErrorDetail: vi.fn(),
  getPlatformLogs: vi.fn(),
  getPlatformLogsSummary: vi.fn(),
  getPlatformTenantLogsSummary: vi.fn(),
  getPlatformTenants: vi.fn(),
}))

const TENANT_ID = '10000000-0000-0000-0000-000000000001'

const errorRow = (index) => ({
  id: `err-${index}`,
  tenant_id: TENANT_ID,
  tenant_name: 'Northwind Legal',
  error_type: 'llm_error',
  severity: 'error',
  message: `Failure ${index}`,
  endpoint: '/api/chat',
  status_code: 500,
  is_resolved: index === 1,
  created_at: '2026-09-23T09:00:00Z',
})

beforeEach(() => {
  vi.clearAllMocks()
  getPlatformLogs.mockImplementation(async (_key, params) => ({
    errors: [errorRow(params.page)],
    total: 120,
    page: params.page,
    limit: 50,
  }))
  getPlatformLogsSummary.mockResolvedValue({
    total_errors: 120,
    unresolved: 90,
    by_severity: { error: 100, critical: 20 },
    by_type: { llm_error: 100, db_error: 20 },
    by_tenant: [
      { tenant_id: TENANT_ID, tenant_name: 'Northwind Legal', count: 100 },
      { tenant_id: 'None', tenant_name: 'System', count: 20 },
    ],
    trend: [],
    days: 7,
  })
  getPlatformTenantLogsSummary.mockResolvedValue({
    total_errors: 100, unresolved: 70, by_severity: { error: 100 }, by_type: {}, trend: [], days: 7,
  })
  getPlatformAccessLogs.mockResolvedValue({ entries: [], total: 0, page: 1, limit: 50 })
  getPlatformAccessLogsSummary.mockResolvedValue({
    total_requests: 1000,
    by_status: { 200: 700, 201: 50, 404: 30, 401: 5, 500: 12, 502: 3 },
    avg_latency_ms: 120,
    by_endpoint: [],
    by_tenant: [{ tenant_id: TENANT_ID, tenant_name: 'Northwind Legal', count: 1000 }],
    days: 1,
  })
  getPlatformTenants.mockResolvedValue({ tenants: [{ id: TENANT_ID, name: 'Northwind Legal' }], total: 1 })
})

afterEach(cleanup)

describe('statusClassTotals', () => {
  it('buckets every status code instead of summing a fixed list', () => {
    // The old card added six named codes; one missing code made it NaN → 0.
    expect(statusClassTotals({ 200: 5, 204: 1, 404: 2, 499: 1, 500: 3 })).toEqual({ '2xx': 6, '4xx': 3, '5xx': 3 })
    expect(statusClassTotals(undefined)).toEqual({})
  })
})

describe('error log', () => {
  it('actually moves to the next page', async () => {
    const user = userEvent.setup()
    render(<LogsTab platformKey="token" session={{ scopes: ['platform:read'] }} tenantId="" onTenantChange={vi.fn()} />)

    expect(await screen.findByText('Failure 1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next →' }))

    expect(await screen.findByText('Failure 2')).toBeInTheDocument()
    expect(getPlatformLogs).toHaveBeenLastCalledWith('token', { page: 2, limit: 50, days: 7 })
    expect(screen.getByText('Page 2 of 3 (120 total)')).toBeInTheDocument()
  })

  it('returns to the first page when a filter changes and offers error types', async () => {
    const user = userEvent.setup()
    render(<LogsTab platformKey="token" session={{ scopes: ['platform:read'] }} tenantId="" onTenantChange={vi.fn()} />)
    await screen.findByText('Failure 1')
    await user.click(screen.getByRole('button', { name: 'Next →' }))
    await screen.findByText('Failure 2')

    await user.selectOptions(screen.getByLabelText('Error type'), 'db_error')

    await waitFor(() => expect(getPlatformLogs).toHaveBeenLastCalledWith('token', { page: 1, limit: 50, days: 7, error_type: 'db_error' }))
  })

  it('scopes rows and summary cards to the selected firm', async () => {
    const onTenantChange = vi.fn()
    const user = userEvent.setup()
    const { rerender } = render(<LogsTab platformKey="token" session={{ scopes: ['platform:read'] }} tenantId="" onTenantChange={onTenantChange} />)
    await screen.findByText('Failure 1')

    const firm = screen.getByLabelText('Firm')
    expect(within(firm).queryByText(/System/)).not.toBeInTheDocument()
    await user.selectOptions(firm, TENANT_ID)
    expect(onTenantChange).toHaveBeenCalledWith(TENANT_ID)

    rerender(<LogsTab platformKey="token" session={{ scopes: ['platform:read'] }} tenantId={TENANT_ID} onTenantChange={onTenantChange} />)
    await waitFor(() => expect(getPlatformLogs).toHaveBeenLastCalledWith('token', { page: 1, limit: 50, days: 7, tenant_id: TENANT_ID }))
    expect(getPlatformTenantLogsSummary).toHaveBeenCalledWith('token', TENANT_ID, { days: 7 })
    expect(await screen.findByText('Firm errors')).toBeInTheDocument()
  })

  it('opens an error in place and explains when the scope is missing', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<LogsTab platformKey="token" session={{ scopes: ['platform:read'] }} tenantId="" onTenantChange={vi.fn()} />)
    await screen.findByText('Failure 1')
    await user.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText(/need the platform:debug scope/)).toBeInTheDocument()
    expect(getPlatformErrorDetail).not.toHaveBeenCalled()
    unmount()

    getPlatformErrorDetail.mockResolvedValue({ ...errorRow(1), stack_trace: 'Traceback…', request_id: 'req-1' })
    render(<LogsTab platformKey="token" session={{ scopes: ['platform:debug'] }} tenantId="" onTenantChange={vi.fn()} />)
    await screen.findByText('Failure 1')
    await user.click(screen.getByRole('button', { name: 'Details' }))
    expect(await screen.findByText('Stack trace')).toBeInTheDocument()
    expect(getPlatformErrorDetail).toHaveBeenCalledWith('token', 'err-1', TENANT_ID)
  })

  it('shows a load failure instead of an empty table', async () => {
    getPlatformLogs.mockRejectedValue(Object.assign(new Error('boom'), { response: { status: 500, data: { detail: 'Database unavailable' } } }))
    render(<LogsTab platformKey="token" session={{ scopes: ['platform:read'] }} tenantId="" onTenantChange={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
  })
})

describe('API traffic', () => {
  it('counts every 4xx and 5xx code and filters the summary by firm', async () => {
    const user = userEvent.setup()
    render(<LogsTab platformKey="token" session={{ scopes: ['platform:read'] }} tenantId={TENANT_ID} onTenantChange={vi.fn()} />)

    await user.click(screen.getByRole('tab', { name: 'API traffic' }))

    await waitFor(() => expect(getPlatformAccessLogsSummary).toHaveBeenCalledWith('token', { hours: 24, tenant_id: TENANT_ID }))
    const card = (label) => screen.getByText(label, { selector: 'p' }).closest('div').parentElement
    expect(within(card('2xx')).getByText('750')).toBeInTheDocument()
    expect(within(card('4xx')).getByText('35')).toBeInTheDocument()
    expect(within(card('5xx')).getByText('15')).toBeInTheDocument()
  })
})
