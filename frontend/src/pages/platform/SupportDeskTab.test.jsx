import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  findPlatformUsers,
  getPlatformErrorDetail,
  getPlatformSupportQueue,
  getPublicSupportPolicy,
  resolvePlatformError,
  tracePlatformRequest,
  updatePlatformSupportRequest,
} from '../../api'
import SupportDeskTab, { lookupKind } from './SupportDeskTab'
import SupportQueue from './SupportQueue'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal()),
  findPlatformUsers: vi.fn(),
  getPlatformErrorDetail: vi.fn(),
  getPlatformSupportQueue: vi.fn(),
  getPublicSupportPolicy: vi.fn(),
  resolvePlatformError: vi.fn(),
  tracePlatformRequest: vi.fn(),
  updatePlatformSupportRequest: vi.fn(),
}))

const ERROR_ID = '6f1c0b3e-8d7a-4c2b-9e1f-0a1b2c3d4e5f'
const TENANT_ID = '10000000-0000-0000-0000-000000000001'

const overdueRequest = {
  id: 'req-1',
  tenant_id: TENANT_ID,
  tenant_name: 'Northwind Legal',
  severity: 'S1',
  status: 'open',
  channel: 'workspace',
  subject: 'Nobody can sign in',
  safe_summary: 'Every user sees an error after entering their password.',
  requested_by_email: 'partner@northwind.example',
  acknowledgement_due_at: '2026-09-23T10:00:00Z',
  escalation_level: 2,
  overdue: true,
  created_at: '2026-09-23T09:00:00Z',
}

const acknowledgedRequest = {
  ...overdueRequest,
  id: 'req-2',
  severity: 'S3',
  status: 'acknowledged',
  subject: 'Export is slow',
  overdue: false,
  escalation_level: 0,
  acknowledged_at: '2026-09-23T09:30:00Z',
  acknowledgement_due_at: '2099-01-01T00:00:00Z',
}

const queue = (items, counts = { open: 1, acknowledged: 1, mitigated: 0, resolved: 4, overdue: 1 }) => ({
  items,
  total: items.length,
  counts,
  checked_at: new Date().toISOString(),
})

const scopeDenied = () => Object.assign(new Error('forbidden'), {
  response: { status: 403, data: { detail: 'Platform token scope denied' } },
})

const notFound = () => Object.assign(new Error('missing'), { response: { status: 404, data: { detail: 'Not found' } } })

beforeEach(() => {
  vi.clearAllMocks()
  getPublicSupportPolicy.mockResolvedValue({
    severities: [{ severity: 'S1', escalation: 'Escalate to executive owner if not acknowledged in 30 minutes.' }],
  })
  getPlatformSupportQueue.mockResolvedValue(queue([overdueRequest, acknowledgedRequest]))
  updatePlatformSupportRequest.mockResolvedValue({})
})

afterEach(cleanup)

describe('lookupKind', () => {
  it('routes what a customer pastes to the right lookup', () => {
    expect(lookupKind('someone@firm.com')).toBe('email')
    expect(lookupKind('firm.com')).toBe('email')
    expect(lookupKind(ERROR_ID)).toBe('id')
    expect(lookupKind('0123456789abcdef0123456789abcdef')).toBe('request')
    expect(lookupKind('  ')).toBeNull()
    expect(lookupKind(ERROR_ID, 'request')).toBe('request')
  })
})

describe('support queue', () => {
  it('shows each request with its firm, requester and acknowledgement clock', async () => {
    const onOpenTenant = vi.fn()
    const onCountsChange = vi.fn()
    const user = userEvent.setup()
    render(<SupportQueue platformKey="token" onOpenTenant={onOpenTenant} onCountsChange={onCountsChange} />)

    const overdue = (await screen.findByText('Nobody can sign in')).closest('li')
    expect(within(overdue).getByText(/Acknowledgement overdue/)).toBeInTheDocument()
    expect(within(overdue).getByRole('link', { name: 'partner@northwind.example' })).toHaveAttribute('href', 'mailto:partner@northwind.example')
    expect(within(overdue).getByText(/Escalate to executive owner/)).toBeInTheDocument()
    expect(screen.getByText('1 overdue')).toBeInTheDocument()
    expect(onCountsChange).toHaveBeenCalledWith(expect.objectContaining({ overdue: 1 }))
    expect(getPlatformSupportQueue).toHaveBeenCalledWith('token', { status: 'active', limit: 100 })

    await user.click(within(overdue).getByRole('button', { name: 'Northwind Legal' }))
    expect(onOpenTenant).toHaveBeenCalledWith(TENANT_ID)
  })

  it('acknowledges without resetting the escalation level', async () => {
    const user = userEvent.setup()
    render(<SupportQueue platformKey="token" />)

    const overdue = (await screen.findByText('Nobody can sign in')).closest('li')
    expect(within(overdue).queryByRole('button', { name: 'Resolve…' })).not.toBeInTheDocument()
    await user.click(within(overdue).getByRole('button', { name: 'Acknowledge' }))

    await waitFor(() => expect(updatePlatformSupportRequest).toHaveBeenCalledWith(
      'token', TENANT_ID, 'req-1', { status: 'acknowledged', escalation_level: 2 },
    ))
    expect(getPlatformSupportQueue).toHaveBeenCalledTimes(2)
  })

  it('resolves with a summary the firm will see', async () => {
    const user = userEvent.setup()
    render(<SupportQueue platformKey="token" />)

    const acknowledged = (await screen.findByText('Export is slow')).closest('li')
    await user.click(within(acknowledged).getByRole('button', { name: 'Resolve…' }))
    await user.type(within(acknowledged).getByLabelText(/the firm's administrators see this/), 'Raised the export worker limit.')
    await user.selectOptions(within(acknowledged).getByLabelText('Escalation'), '1')
    await user.click(within(acknowledged).getByRole('button', { name: 'Resolve request' }))

    await waitFor(() => expect(updatePlatformSupportRequest).toHaveBeenCalledWith(
      'token', TENANT_ID, 'req-2',
      { status: 'resolved', escalation_level: 1, resolution_summary: 'Raised the export worker limit.' },
    ))
  })

  it('shows the API reason when a transition is refused', async () => {
    updatePlatformSupportRequest.mockRejectedValue(Object.assign(new Error('conflict'), {
      response: { status: 409, data: { detail: 'invalid support transition: open -> mitigated' } },
    }))
    const user = userEvent.setup()
    render(<SupportQueue platformKey="token" />)

    const acknowledged = (await screen.findByText('Export is slow')).closest('li')
    await user.click(within(acknowledged).getByRole('button', { name: 'Mark mitigated' }))

    expect(await within(acknowledged).findByRole('alert')).toHaveTextContent('invalid support transition')
  })

  it('filters by status and scopes to one firm inside its panel', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<SupportQueue platformKey="token" />)
    await screen.findByText('Nobody can sign in')
    await user.click(screen.getByRole('button', { name: /^Resolved/ }))
    await waitFor(() => expect(getPlatformSupportQueue).toHaveBeenLastCalledWith('token', { status: 'resolved', limit: 100 }))
    unmount()

    render(<SupportQueue platformKey="token" tenantId={TENANT_ID} />)
    await waitFor(() => expect(getPlatformSupportQueue).toHaveBeenLastCalledWith('token', { status: 'all', limit: 100, tenant_id: TENANT_ID }))
  })
})

describe('support desk lookup', () => {
  it('finds a user’s firm from their email', async () => {
    findPlatformUsers.mockResolvedValue([{
      id: 'user-1', email: 'partner@northwind.example', full_name: 'Pat Partner', role: 'admin',
      is_active: false, tenant_id: TENANT_ID, tenant_name: 'Northwind Legal', created_at: '2026-09-01T00:00:00Z',
    }])
    const onOpenTenant = vi.fn()
    const user = userEvent.setup()
    render(<SupportDeskTab platformKey="token" session={{ scopes: ['platform:read', 'platform:debug'] }} onOpenTenant={onOpenTenant} />)

    await user.type(screen.getByLabelText('Email, error ID or request ID'), 'partner@northwind')
    await user.click(screen.getByRole('button', { name: 'Look up' }))

    const table = await screen.findByRole('table', { name: /Users matching/ })
    expect(within(table).getByText('Inactive or invite not accepted')).toBeInTheDocument()
    await user.click(within(table).getByRole('button', { name: 'Northwind Legal' }))
    expect(onOpenTenant).toHaveBeenCalledWith(TENANT_ID)
    expect(getPlatformErrorDetail).not.toHaveBeenCalled()
  })

  it('looks a UUID up as an error and a request at once, and resolves the error', async () => {
    getPlatformErrorDetail.mockResolvedValue({
      id: ERROR_ID, tenant_id: TENANT_ID, tenant_name: 'Northwind Legal', error_type: 'llm_error', severity: 'error',
      message: 'Upstream gateway returned 502', is_resolved: false, created_at: '2026-09-23T09:00:00Z',
      request_id: 'req-abc', stack_trace: 'Traceback…',
    })
    tracePlatformRequest.mockRejectedValue(notFound())
    resolvePlatformError.mockResolvedValue({ id: ERROR_ID, is_resolved: true, resolution_notes: 'Gateway restarted' })
    const user = userEvent.setup()
    render(<SupportDeskTab platformKey="token" session={{ scopes: ['platform:debug'] }} onOpenTenant={vi.fn()} />)

    await user.type(screen.getByLabelText('Email, error ID or request ID'), ERROR_ID)
    await user.click(screen.getByRole('button', { name: 'Look up' }))

    const card = await screen.findByRole('article', { name: `Error ${ERROR_ID}` })
    expect(tracePlatformRequest).toHaveBeenCalledWith('token', ERROR_ID)
    expect(within(card).getByText('Stack trace')).toBeInTheDocument()
    await user.type(within(card).getByLabelText(/Resolution notes/), 'Gateway restarted')
    await user.click(within(card).getByRole('button', { name: 'Mark resolved' }))

    await waitFor(() => expect(resolvePlatformError).toHaveBeenCalledWith(
      'token', ERROR_ID, { is_resolved: true, resolution_notes: 'Gateway restarted' }, TENANT_ID,
    ))
    expect(await within(card).findByText('Resolved')).toBeInTheDocument()
  })

  it('says plainly when nothing is recorded for an id', async () => {
    getPlatformErrorDetail.mockRejectedValue(notFound())
    tracePlatformRequest.mockResolvedValue({ request_id: ERROR_ID, tenant_ids: [], errors: [], access_entries: [] })
    const user = userEvent.setup()
    render(<SupportDeskTab platformKey="token" session={{ scopes: ['platform:debug'] }} onOpenTenant={vi.fn()} />)

    await user.type(screen.getByLabelText('Email, error ID or request ID'), ERROR_ID)
    await user.click(screen.getByRole('button', { name: 'Look up' }))

    expect(await screen.findByText(/Nothing recorded for/)).toHaveTextContent('request logs for 30')
  })

  it('explains the missing scope instead of signing the operator out', async () => {
    findPlatformUsers.mockRejectedValue(scopeDenied())
    const onAuthError = vi.fn()
    const user = userEvent.setup()
    render(<SupportDeskTab platformKey="token" session={{ scopes: null }} onOpenTenant={vi.fn()} onAuthError={onAuthError} />)

    await user.type(screen.getByLabelText('Email, error ID or request ID'), 'someone@firm.com')
    await user.click(screen.getByRole('button', { name: 'Look up' }))

    expect(await screen.findByText(/stack traces, so it needs/)).toBeInTheDocument()
    expect(onAuthError).not.toHaveBeenCalled()
  })

  it('hides the lookup when the session is known to lack platform:debug', async () => {
    render(<SupportDeskTab platformKey="token" session={{ scopes: ['platform:read', 'platform:write'] }} onOpenTenant={vi.fn()} />)

    expect(screen.queryByLabelText('Email, error ID or request ID')).not.toBeInTheDocument()
    expect(screen.getByText(/Looking up users, errors and requests needs/)).toBeInTheDocument()
    expect(await screen.findByText('Nobody can sign in')).toBeInTheDocument()
  })
})
