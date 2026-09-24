import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./IntegrationsPanel', () => ({ default: () => <div>Cloud configuration</div> }))
vi.mock('./TeamsPanel', () => ({ default: () => <div>Teams configuration</div> }))
vi.mock('./ZoomPanel', () => ({ default: () => <div>Zoom configuration</div> }))
vi.mock('./QBOPanel', () => ({ default: () => <div>QuickBooks configuration</div> }))
vi.mock('../pages/MCPPage', () => ({ default: () => <div>MCP configuration</div> }))
vi.mock('../pages/CloudSearchAdmin', () => ({ default: () => <div>Search configuration</div> }))
vi.mock('../pages/SmbAdminPage', () => ({ default: () => <div>File share configuration</div> }))
vi.mock('./StorageMigrationSection', () => ({ default: () => <div>Storage migration configuration</div> }))
vi.mock('./Tabs3ImportPanel', () => ({ default: () => <div>Tabs3 configuration</div> }))
vi.mock('./IntegrationReadinessCard', () => ({ default: () => <div>Readiness configuration</div> }))
vi.mock('../api', () => ({
  getAdminPermissions: vi.fn(),
  getQBOStatus: vi.fn(),
  getZoomStatus: vi.fn(),
}))

import IntegrationsHub, {
  LEGACY_INTEGRATION_TABS,
  availableIntegrationSections,
  canOperateIntegrations,
  operatorIntegrationSections,
} from './IntegrationsHub'
import { getAdminPermissions, getQBOStatus, getZoomStatus } from '../api'

afterEach(cleanup)

const admin = { role: 'admin', plan: 'professional', capabilities: ['manage_integrations', 'manage_users'], enabled_modules: ['admin'] }

function renderHub(props = {}) {
  const onSectionChange = vi.fn()
  render(
    <MemoryRouter>
      <IntegrationsHub user={admin} section="overview" onSectionChange={onSectionChange} {...props} />
    </MemoryRouter>
  )
  return onSectionChange
}

describe('IntegrationsHub', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAdminPermissions.mockResolvedValue({
      overall_health: 'attention_needed',
      microsoft: { connected: false, health: 'disconnected', capabilities: {} },
      google: { connected: true, health: 'revoked' },
    })
    getZoomStatus.mockResolvedValue({ configured: true, connected: false })
    getQBOStatus.mockResolvedValue({ connected: true, company_name: 'Painter Law' })
  })

  it('keeps firm integrations in the catalog and nests operator tooling separately', () => {
    expect(availableIntegrationSections(admin).map((section) => section.id)).toEqual([
      'email-intake',
      'cloud',
      'cloud-search',
      'file-shares',
      'teams',
      'zoom',
      'quickbooks',
    ])
    expect(operatorIntegrationSections(admin).map((section) => section.id)).toEqual([
      'mcp',
      'storage-migration',
      'data-import',
      'readiness',
    ])
    expect(LEGACY_INTEGRATION_TABS).toMatchObject({ mcp: 'mcp', smb: 'file-shares', qbo: 'quickbooks' })
  })

  it('gates operator tooling on role and capability, not on the disclosure', () => {
    expect(canOperateIntegrations(admin)).toBe(true)
    expect(canOperateIntegrations({ role: 'admin', plan: 'professional' })).toBe(true)
    expect(canOperateIntegrations({ role: 'admin', plan: 'professional', capabilities: ['manage_users'] })).toBe(false)
    expect(canOperateIntegrations({ role: 'user', capabilities: ['manage_integrations'] })).toBe(false)
    expect(canOperateIntegrations({ role: 'accountant' })).toBe(false)
    expect(canOperateIntegrations({ role: 'admin', plan: 'intake-only' })).toBe(false)
    expect(operatorIntegrationSections({ role: 'admin', plan: 'professional', capabilities: ['manage_users'] })).toEqual([])
  })

  it('answers "is this working?" from the overview without expanding anything', async () => {
    renderHub()

    const cloud = screen.getByTestId('integration-card-cloud')
    expect(await within(cloud).findByText('Needs attention')).toBeInTheDocument()
    expect(within(cloud).getByText('Open')).toBeInTheDocument()

    const teams = screen.getByTestId('integration-card-teams')
    expect(within(teams).getByText('Connect Microsoft 365 first')).toBeInTheDocument()
    expect(within(teams).getByText('Set up')).toBeInTheDocument()

    const zoom = screen.getByTestId('integration-card-zoom')
    expect(within(zoom).getByText('Not connected')).toBeInTheDocument()

    const qbo = screen.getByTestId('integration-card-quickbooks')
    expect(within(qbo).getByText('Connected to Painter Law')).toBeInTheDocument()

    // Every card is collapsed: permissions and setup stay behind a disclosure.
    expect(screen.getAllByText('Permissions & setup').length).toBeGreaterThan(0)
    expect(screen.queryByText('Directory profiles for user provisioning')).not.toBeVisible()
  })

  it('shows purpose, expandable permissions, setup requirements, and guide links', async () => {
    const onSectionChange = renderHub()

    expect(screen.getByText('Every external connection, in one place.')).toBeInTheDocument()
    expect(screen.getByText('Connect Microsoft 365 or Google Workspace and choose where matter documents live.')).toBeInTheDocument()

    const cloud = screen.getByTestId('integration-card-cloud')
    await userEvent.click(within(cloud).getByText('Permissions & setup'))
    expect(screen.getByText('Directory profiles for user provisioning')).toBeVisible()
    expect(within(cloud).getByRole('link', { name: /Integration setup guide/ })).toHaveAttribute('href', '/admin?tab=guide&chapter=integrations#connect-microsoft-365-or-google-workspace')
    expect(screen.getByRole('link', { name: /Full data visibility guide/ })).toHaveAttribute('href', '/admin?tab=guide&chapter=integration-data-visibility')

    await userEvent.click(within(cloud).getByText('Open'))
    expect(onSectionChange).toHaveBeenCalledWith('cloud')
  })

  it('keeps operator tools behind a closed Advanced disclosure and out of the main nav', async () => {
    const onSectionChange = renderHub()

    const nav = screen.getByRole('navigation', { name: 'Integration sections' })
    expect(within(nav).queryByRole('button', { name: /Migration/ })).toBeNull()
    expect(within(nav).queryByRole('button', { name: /MCP/ })).toBeNull()

    const advanced = screen.getByTestId('integrations-advanced')
    expect(advanced).not.toHaveAttribute('open')
    expect(within(advanced).getByText('Storage migration')).not.toBeVisible()

    await userEvent.click(within(advanced).getByText('Advanced'))
    expect(within(advanced).getByText('Storage migration')).toBeVisible()
    await userEvent.click(within(screen.getByTestId('integration-card-storage-migration')).getByText('Open'))
    expect(onSectionChange).toHaveBeenCalledWith('storage-migration')

    await userEvent.click(within(nav).getByRole('button', { name: /Advanced/ }))
    expect(within(nav).getByRole('button', { name: /Migration/ })).toBeInTheDocument()
  })

  it('renders an operator section with its badge when selected directly', async () => {
    renderHub({ section: 'storage-migration' })

    expect(await screen.findByText('Storage migration configuration')).toBeInTheDocument()
    expect(screen.getByText('Operator tool')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Integration sections' })
    expect(within(nav).getByRole('button', { name: /Migration/ })).toBeInTheDocument()
  })

  it('hides operator tools entirely from an administrator without the capability', () => {
    renderHub({ user: { role: 'admin', plan: 'professional', capabilities: ['manage_users'] }, section: 'storage-migration' })

    expect(screen.queryByTestId('integrations-advanced')).toBeNull()
    expect(screen.queryByText('Storage migration configuration')).toBeNull()
    // An unknown or forbidden section falls back to the overview.
    expect(screen.getByTestId('integrations-overview')).toBeInTheDocument()
  })

  it('limits the catalog for accountant and intake-only roles', async () => {
    expect(availableIntegrationSections({ role: 'accountant' }).map((section) => section.id)).toEqual(['quickbooks'])
    expect(availableIntegrationSections({ role: 'admin', plan: 'intake-only' }).map((section) => section.id)).toEqual(['zoom'])

    renderHub({ user: { role: 'accountant' } })
    await waitFor(() => expect(getQBOStatus).toHaveBeenCalled())
    expect(getAdminPermissions).not.toHaveBeenCalled()
    expect(screen.queryByTestId('integrations-advanced')).toBeNull()
  })

  it('tells an unconfirmed Microsoft account type apart from an unsupported one', async () => {
    const teamsUnavailable = { teams: { available: false, status: 'unavailable', reason: 'x' } }
    getAdminPermissions.mockResolvedValueOnce({
      overall_health: 'healthy',
      microsoft: { connected: true, health: 'healthy', account_type: 'unknown', capabilities: teamsUnavailable },
      google: { connected: false, health: 'disconnected' },
    })
    renderHub()
    const teams = screen.getByTestId('integration-card-teams')
    expect(await within(teams).findByText('Account type not confirmed')).toBeInTheDocument()
    cleanup()

    getAdminPermissions.mockResolvedValueOnce({
      overall_health: 'healthy',
      microsoft: { connected: true, health: 'healthy', account_type: 'consumer', capabilities: teamsUnavailable },
      google: { connected: false, health: 'disconnected' },
    })
    renderHub()
    const personal = screen.getByTestId('integration-card-teams')
    expect(await within(personal).findByText('Not available on this account')).toBeInTheDocument()
  })

  it('marks the active section in the navigation for assistive technology', () => {
    renderHub({ section: 'cloud' })
    const nav = screen.getByRole('navigation', { name: 'Integration sections' })
    expect(within(nav).getByRole('button', { name: /Cloud/ })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('button', { name: /Overview/ })).not.toHaveAttribute('aria-current')
  })

  it('shows the selected section status in its header', async () => {
    renderHub({ section: 'cloud' })
    expect(await screen.findByText('Cloud configuration')).toBeInTheDocument()
    expect(await screen.findByText('Needs attention')).toBeInTheDocument()
  })

  it('links each open section to the Admin Guide chapter that documents it', async () => {
    renderHub({ section: 'cloud-search' })
    expect(await screen.findByText('Search configuration')).toBeInTheDocument()
    // The header pill and the Permissions & setup link both open the chapter.
    const searchGuides = screen.getAllByRole('link', { name: 'Cloud Search operations guide' })
    expect(searchGuides).toHaveLength(2)
    searchGuides.forEach((link) => expect(link).toHaveAttribute('href', '/admin?tab=guide&chapter=cloud-search-operations'))

    cleanup()
    renderHub({ section: 'data-import' })
    expect(await screen.findByText('Tabs3 configuration')).toBeInTheDocument()
    screen.getAllByRole('link', { name: 'Storage, imports & readiness guide' })
      .forEach((link) => expect(link).toHaveAttribute('href', '/admin?tab=guide&chapter=storage-imports-and-readiness#import-from-tabs3'))
  })

  it('does not offer Admin Guide links to roles that cannot open the Admin Guide', async () => {
    renderHub({ user: { role: 'accountant', enabled_modules: ['admin'] }, section: 'quickbooks' })
    expect(await screen.findByText('QuickBooks configuration')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /guide/i })).toBeNull()
  })
})
