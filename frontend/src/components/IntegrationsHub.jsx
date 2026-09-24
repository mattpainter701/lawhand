import { useEffect, useState } from 'react'
import {
  ArrowRight,
  BookOpen,
  Boxes,
  Cloud,
  DatabaseZap,
  FolderKey,
  HardDriveUpload,
  KeyRound,
  MessageSquare,
  Phone,
  ReceiptText,
  Search,
  ServerCog,
  ShieldCheck,
  Upload,
  Wrench,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { getAdminPermissions, getQBOStatus, getZoomStatus } from '../api'
import IntegrationsPanel from './IntegrationsPanel'
import TeamsPanel from './TeamsPanel'
import ZoomPanel from './ZoomPanel'
import QBOPanel from './QBOPanel'
import MCPPage from '../pages/MCPPage'
import CloudSearchAdmin from '../pages/CloudSearchAdmin'
import SmbAdminPage from '../pages/SmbAdminPage'
import FirmEmailIntake from './FirmEmailIntake'
import StorageMigrationSection from './StorageMigrationSection'
import Tabs3ImportPanel from './Tabs3ImportPanel'
import IntegrationReadinessCard from './IntegrationReadinessCard'

/*
 * Audience decides who a section is for, and it is authorization, not
 * presentation:
 *   firm       — a firm administrator connects and reviews these.
 *   operator   — app credentials, migration and readiness tooling. Shown only
 *                to administrators who hold manage_integrations, and even then
 *                nested under Advanced so they are reached deliberately.
 *   accounting — QuickBooks; accountants see only this.
 *   all        — Zoom, which the intake-only plan also uses.
 */
const NOT_CONNECTED = { tone: 'off', label: 'Not connected' }

function cloudStatus(summary) {
  const perms = summary?.permissions
  if (!perms) return null
  if (perms.overall_health === 'healthy') return { tone: 'ok', label: 'Connected' }
  if (perms.overall_health === 'attention_needed') return { tone: 'warn', label: 'Needs attention' }
  return NOT_CONNECTED
}

export const INTEGRATION_SECTIONS = [
  {
    id: 'email-intake', label: 'Email intake', shortLabel: 'Email intake', icon: MessageSquare,
    eyebrow: 'Email to matter to-dos', audience: 'firm',
    description: 'Give staff one LawHand contact for forwarding email into matter to-dos.',
    permissions: ['Accepts registered staff senders with verified DKIM signatures', 'Staff review the matter, owner and date before filing'],
    setup: ['Enable the firm address and choose the firm time zone', 'Save the LawHand contact on staff phones', 'Forward a test email with [TASK] at the start of its subject'],
    guide: '/guide/email-intake', guideLabel: 'Email to-dos user guide',
    render: () => <FirmEmailIntake admin />,
  },
  {
    id: 'cloud',
    label: 'Cloud accounts & storage',
    shortLabel: 'Cloud',
    icon: Cloud,
    eyebrow: 'Identity, mail, calendar & files',
    description: 'Connect Microsoft 365 or Google Workspace and choose where matter documents live.',
    permissions: [
      'Directory profiles for user provisioning',
      'Mail and calendar access for enabled workflows',
      'OneDrive, SharePoint, or Google Drive access for matter documents',
    ],
    setup: [
      'An administrator account for the organization provider',
      'Approved OAuth redirect URLs and application credentials',
      'A documented storage owner and destination',
    ],
    guide: '/guide/integrations',
    guideLabel: 'Integration setup guide',
    audience: 'firm',
    status: cloudStatus,
    render: () => <IntegrationsPanel />,
  },
  {
    id: 'cloud-search',
    label: 'Cloud Search',
    shortLabel: 'Search',
    icon: Search,
    eyebrow: 'Approved content discovery',
    description: 'Search and synchronize authorized Gmail, Outlook, Drive, OneDrive, and SharePoint sources.',
    permissions: [
      'Uses the connected provider grant; it does not create a separate permission boundary',
      'Can expose result metadata, previews, provider links, and selected file contents',
    ],
    setup: [
      'Connect the provider account first',
      'Confirm the permitted site, drive, or mailbox boundary',
      'Run a non-sensitive test query before broader use',
    ],
    guide: '/guide/cloud-search-operations',
    guideLabel: 'Cloud Search operations guide',
    audience: 'firm',
    status: (summary) => {
      const cloud = cloudStatus(summary)
      if (!cloud) return null
      return cloud.tone === 'off' ? { tone: 'off', label: 'Connect a cloud account first' } : { tone: 'ok', label: 'Available' }
    },
    render: () => <CloudSearchAdmin />,
  },
  {
    id: 'file-shares',
    label: 'File shares',
    shortLabel: 'File shares',
    icon: FolderKey,
    eyebrow: 'On-premises document access',
    description: 'Connect approved SMB shares through a firm-managed agent without exposing file-server credentials to users.',
    permissions: [
      'Service-account access to explicitly configured network paths',
      'File metadata and content required for enabled search and document workflows',
    ],
    setup: [
      'A Windows host with network access to the share',
      'A least-privilege service account and approved root paths',
      'Agent installation, registration, and connectivity validation',
    ],
    guide: '/guide/file-share-operations',
    guideLabel: 'File Share operations guide',
    audience: 'firm',
    render: () => <SmbAdminPage />,
  },
  {
    id: 'teams',
    label: 'Microsoft Teams',
    shortLabel: 'Teams',
    icon: MessageSquare,
    eyebrow: 'Collaboration & call intake',
    description: 'Route approved matter updates to Teams and, when separately configured, capture inbound Teams Phone calls.',
    permissions: [
      'Team and channel lookup plus approved message and activity delivery',
      'Optional application-only call-record access for Teams Phone',
    ],
    setup: [
      'Microsoft 365 authorization with Teams selected',
      'Approved team/channel mappings and audience review',
      'Separate administrator consent for Teams Phone capture',
    ],
    guide: '/guide/microsoft-teams-administration',
    guideLabel: 'Microsoft Teams administration guide',
    audience: 'firm',
    status: (summary) => {
      const ms = summary?.permissions?.microsoft
      if (!summary?.permissions) return null
      if (!ms?.connected) return { tone: 'off', label: 'Connect Microsoft 365 first' }
      const teams = ms.capabilities?.teams
      if (teams?.status === 'ok') return { tone: 'ok', label: 'Connected' }
      if (teams?.status === 'needs_reauth') return { tone: 'warn', label: 'Reconnect with Teams enabled' }
      // An unconfirmed account type is not the same as an unsupported one.
      if (!ms.account_type || ms.account_type === 'unknown') return { tone: 'warn', label: 'Account type not confirmed' }
      return { tone: 'off', label: 'Not available on this account' }
    },
    render: () => <TeamsPanel />,
  },
  {
    id: 'zoom',
    label: 'Zoom',
    shortLabel: 'Zoom',
    icon: Phone,
    eyebrow: 'Meetings & phone intake',
    description: 'Connect Zoom Meetings and Zoom Phone as separate grants for meeting workflows and completed-call intake.',
    permissions: [
      'Meeting profile and meeting read/write access for enabled meeting workflows',
      'Account-level completed-call history and detail access for Zoom Phone',
    ],
    setup: [
      'An approved Zoom administrator and target account',
      'OAuth application credentials and redirect configuration',
      'Webhook verification plus recording/transcription consent policy',
    ],
    guide: '/guide/zoom-phone-administration',
    guideLabel: 'Zoom administration guide',
    audience: 'all',
    status: (summary) => {
      const zoom = summary?.zoom
      if (!zoom) return null
      if (zoom.connected) return { tone: 'ok', label: 'Connected' }
      return zoom.configured ? NOT_CONNECTED : { tone: 'off', label: 'Not configured' }
    },
    render: () => <ZoomPanel />,
  },
  {
    id: 'quickbooks',
    label: 'QuickBooks Online',
    shortLabel: 'QuickBooks',
    icon: ReceiptText,
    eyebrow: 'Accounting synchronization',
    description: 'Map and send approved customers, time activity, invoices, and payments to the intended QuickBooks company.',
    permissions: [
      'Accounting access and connected-company identity',
      'Reads service items and sync state; writes configured accounting records',
    ],
    setup: [
      'An Intuit administrator for the intended company',
      'Approved service-item and account mappings',
      'An accounting owner for reconciliation and exception review',
    ],
    guide: '/guide/quickbooks-administration',
    guideLabel: 'QuickBooks administration guide',
    audience: 'accounting',
    status: (summary) => {
      const qbo = summary?.qbo
      if (!qbo) return null
      return qbo.connected ? { tone: 'ok', label: qbo.company_name ? `Connected to ${qbo.company_name}` : 'Connected' } : NOT_CONNECTED
    },
    render: () => <QBOPanel />,
  },
  {
    id: 'mcp',
    label: 'MCP servers',
    shortLabel: 'MCP',
    icon: KeyRound,
    eyebrow: 'Approved external assistants',
    description: 'Govern tenant-scoped Workspace MCP access and separately keyed Research MCP clients, tools, and usage.',
    permissions: [
      'Workspace MCP acts as the consenting user within their LawHand permissions',
      'Research MCP keys are limited to the configured public-authority tool allowlist',
    ],
    setup: [
      'Choose tenant and per-user Workspace MCP policy',
      'Approve the exact assistant client and requested scopes',
      'For Research MCP, issue a named key and review its allowlist and owner',
    ],
    guide: '/guide/mcp-server-operations',
    guideLabel: 'MCP server operations guide',
    audience: 'operator',
    render: () => <MCPPage embedded />,
  },
  {
    id: 'storage-migration',
    label: 'Storage migration',
    shortLabel: 'Migration',
    icon: HardDriveUpload,
    eyebrow: 'Rebind matter folders to another provider',
    description: 'Discover, reconcile and cut over existing matter folders to a different connected provider. LawHand verifies; it does not copy files.',
    permissions: [
      'Reads folder metadata on the source and target providers',
      'Rewrites every matter folder binding at cutover',
    ],
    setup: [
      'Both providers connected and a primary provider chosen',
      'A reconciliation pass with zero missing or ambiguous matters',
      'A named operator who confirms the evidence before cutover',
    ],
    guide: '/guide/integrations',
    guideLabel: 'Integration setup guide',
    audience: 'operator',
    render: () => <StorageMigrationSection />,
  },
  {
    id: 'data-import',
    label: 'Data import',
    shortLabel: 'Import',
    icon: Upload,
    eyebrow: 'Practice-management migration',
    description: 'Stage an on-prem Tabs3 export bundle for review before cutover.',
    permissions: [
      'Reads the uploaded bundle only; nothing is written to matters until reconciled',
    ],
    setup: [
      'An exported Tabs3 bundle and its passphrase',
      'An accounting mode decision for imported billing records',
    ],
    guide: '/guide/integrations',
    guideLabel: 'Integration setup guide',
    audience: 'operator',
    render: () => <Tabs3ImportPanel />,
  },
  {
    id: 'readiness',
    label: 'Provider app readiness',
    shortLabel: 'Readiness',
    icon: ServerCog,
    eyebrow: 'Server-side OAuth configuration',
    description: 'Redacted view of which provider application settings are present and the redirect URIs the provider consoles must carry.',
    permissions: ['Reports only whether a setting is present; values are never shown'],
    setup: ['Compare the expected redirect URIs with the Google and Microsoft app registrations'],
    guide: '/guide/integrations',
    guideLabel: 'Integration setup guide',
    audience: 'operator',
    render: () => <IntegrationReadinessCard />,
  },
]

export const LEGACY_INTEGRATION_TABS = {
  mcp: 'mcp',
  'cloud-search': 'cloud-search',
  smb: 'file-shares',
  teams: 'teams',
  zoom: 'zoom',
  qbo: 'quickbooks',
}

/**
 * Operator tooling is gated on the administrator role plus the
 * manage_integrations capability when the session carries capabilities.
 * The Advanced disclosure that wraps these sections is presentation only.
 */
export function canOperateIntegrations(user) {
  if (user?.role !== 'admin') return false
  if (user?.plan === 'intake-only') return false
  const caps = user?.capabilities
  if (Array.isArray(caps) && caps.length > 0) return caps.includes('manage_integrations')
  return true
}

export function availableIntegrationSections(user) {
  if (user?.role === 'accountant') {
    return INTEGRATION_SECTIONS.filter((item) => item.audience === 'accounting')
  }
  if (user?.plan === 'intake-only') {
    return INTEGRATION_SECTIONS.filter((item) => item.id === 'zoom')
  }
  return INTEGRATION_SECTIONS.filter((item) => {
    if (item.audience === 'operator') return false
    if (item.audience === 'accounting') return user?.role === 'admin'
    return true
  })
}

export function operatorIntegrationSections(user) {
  if (!canOperateIntegrations(user)) return []
  return INTEGRATION_SECTIONS.filter((item) => item.audience === 'operator')
}

const STATUS_TONES = {
  ok: 'bg-green-100 text-green-700',
  warn: 'bg-amber-100 text-amber-700',
  off: 'bg-gray-100 text-gray-600',
}

function StatusPill({ status }) {
  if (!status) return null
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-bold ${STATUS_TONES[status.tone] || STATUS_TONES.off}`} data-testid="section-status">
      <span className={`h-1.5 w-1.5 rounded-full ${status.tone === 'ok' ? 'bg-green-500' : status.tone === 'warn' ? 'bg-amber-500' : 'bg-gray-400'}`} aria-hidden="true" />
      {status.label}
    </span>
  )
}

function useIntegrationSummary(user) {
  const [summary, setSummary] = useState(null)
  const role = user?.role
  const plan = user?.plan
  useEffect(() => {
    let active = true
    const isAdmin = role === 'admin'
    const intakeOnly = plan === 'intake-only'
    Promise.all([
      isAdmin && !intakeOnly ? getAdminPermissions().catch(() => null) : Promise.resolve(null),
      getZoomStatus().catch(() => null),
      isAdmin || role === 'accountant' ? getQBOStatus().catch(() => null) : Promise.resolve(null),
    ]).then(([permissions, zoom, qbo]) => {
      if (active) setSummary({ permissions, zoom, qbo })
    })
    return () => { active = false }
  }, [role, plan])
  return summary
}

function IntegrationDetails({ item }) {
  return (
    <details className="group border-t border-brand-line bg-brand-bg/55 px-5 py-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-bold text-brand-ink marker:hidden">
        Permissions & setup
        <span className="text-brand-muted transition-transform group-open:rotate-180" aria-hidden="true">⌄</span>
      </summary>
      <div className="grid gap-5 pt-4 text-xs leading-5 text-brand-ink-2 sm:grid-cols-2">
        <div>
          <p className="mb-2 flex items-center gap-2 font-bold text-brand-ink"><ShieldCheck size={14} /> Data & permissions</p>
          <ul className="space-y-1.5">
            {item.permissions.map((permission) => <li key={permission} className="flex gap-2"><span className="text-brand-accent">•</span><span>{permission}</span></li>)}
          </ul>
        </div>
        <div>
          <p className="mb-2 flex items-center gap-2 font-bold text-brand-ink"><DatabaseZap size={14} /> Setup required</p>
          <ul className="space-y-1.5">
            {item.setup.map((step) => <li key={step} className="flex gap-2"><span className="text-brand-accent">•</span><span>{step}</span></li>)}
          </ul>
        </div>
      </div>
      <Link to={item.guide} className="mt-4 inline-flex items-center gap-2 text-xs font-bold text-brand-accent hover:text-brand-ink">
        <BookOpen size={14} /> {item.guideLabel} <ArrowRight size={13} />
      </Link>
    </details>
  )
}

function SectionCard({ item, status, onSelect }) {
  const Icon = item.icon
  const actionLabel = status?.tone === 'off' ? 'Set up' : 'Open'
  return (
    <article className="overflow-hidden rounded-2xl border border-brand-line bg-brand-surface shadow-sm transition hover:border-brand-line-2 hover:shadow-md" data-testid={`integration-card-${item.id}`}>
      <button type="button" onClick={() => onSelect(item.id)} className="flex w-full items-start gap-4 p-5 text-left">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-bg text-brand-ink"><Icon size={20} /></span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center justify-between gap-2">
            <span className="block text-[10px] font-bold uppercase tracking-[0.14em] text-brand-muted">{item.eyebrow}</span>
            <StatusPill status={status} />
          </span>
          <span className="mt-1 block font-serif text-lg font-bold text-brand-ink">{item.label}</span>
          <span className="mt-2 block text-xs leading-5 text-brand-ink-2">{item.description}</span>
          <span className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold text-brand-accent">{actionLabel} <ArrowRight size={13} /></span>
        </span>
      </button>
      <IntegrationDetails item={item} />
    </article>
  )
}

function Overview({ sections, operatorSections, summary, onSelect }) {
  return (
    <div className="space-y-6" data-testid="integrations-overview">
      <div className="rounded-2xl border border-brand-line bg-brand-ink px-6 py-7 text-white shadow-sm md:px-8">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div className="max-w-2xl">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-white/55">Tenant connections</p>
            <h2 className="font-serif text-2xl font-bold tracking-tight text-white md:text-3xl">Every external connection, in one place.</h2>
            <p className="mt-3 text-sm leading-6 text-white/70">Each card shows whether the connection is working. Open one to connect it, review its permissions, or fix what needs attention.</p>
          </div>
          <Link to="/guide/integration-data-visibility" className="inline-flex w-fit shrink-0 items-center gap-2 rounded-lg border border-white/20 bg-white/10 px-4 py-2.5 text-xs font-bold text-white hover:bg-white/15">
            <BookOpen size={15} /> Full data visibility guide
          </Link>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {sections.map((item) => (
          <SectionCard key={item.id} item={item} status={item.status ? item.status(summary) : null} onSelect={onSelect} />
        ))}
      </div>

      {operatorSections.length > 0 && (
        <details className="group rounded-2xl border border-dashed border-brand-line-2 bg-brand-bg/40" data-testid="integrations-advanced">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-surface text-brand-ink"><Wrench size={16} /></span>
              <span>
                <span className="block text-sm font-bold text-brand-ink font-sans">Advanced</span>
                <span className="block text-xs text-brand-ink-2 font-sans">Operator tools: app credentials, migration and readiness. Changes here affect every matter.</span>
              </span>
            </span>
            <span className="text-brand-muted transition-transform group-open:rotate-180" aria-hidden="true">⌄</span>
          </summary>
          <div className="grid gap-4 border-t border-brand-line px-5 py-5 lg:grid-cols-2">
            {operatorSections.map((item) => (
              <SectionCard key={item.id} item={item} status={null} onSelect={onSelect} />
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

function NavButton({ active, onClick, icon: Icon, children }) {
  return (
    <button type="button" onClick={onClick} aria-current={active ? 'page' : undefined} className={`inline-flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold transition ${active ? 'border-brand-ink bg-brand-ink text-white' : 'border-brand-line bg-brand-surface text-brand-ink hover:border-brand-line-2'}`}>
      <Icon size={15} /> {children}
    </button>
  )
}

export default function IntegrationsHub({ user, section = 'overview', onSectionChange }) {
  const sections = availableIntegrationSections(user)
  const operatorSections = operatorIntegrationSections(user)
  const summary = useIntegrationSummary(user)
  const selected = [...sections, ...operatorSections].find((item) => item.id === section)
  const activeSection = selected ? section : 'overview'
  const activeIsOperator = selected?.audience === 'operator'
  const [advancedNav, setAdvancedNav] = useState(false)
  const showOperatorNav = operatorSections.length > 0 && (advancedNav || activeIsOperator)
  const ActiveIcon = selected?.icon || Boxes
  const selectedStatus = selected?.status ? selected.status(summary) : null

  return (
    <section aria-labelledby="integrations-heading">
      <div className="mb-6 flex flex-col gap-4 border-b border-brand-line pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.16em] text-brand-muted">Administration</p>
          <h2 id="integrations-heading" className="font-serif text-2xl font-bold tracking-tight text-brand-ink">Integrations</h2>
          <p className="mt-1 max-w-2xl text-sm text-brand-ink-2">Connect services deliberately, understand their access, and keep setup and health controls together.</p>
        </div>
      </div>

      <nav aria-label="Integration sections" className="mb-6 flex gap-2 overflow-x-auto pb-1">
        <NavButton active={activeSection === 'overview'} onClick={() => onSectionChange('overview')} icon={Boxes}>Overview</NavButton>
        {sections.map((item) => (
          <NavButton key={item.id} active={activeSection === item.id} onClick={() => onSectionChange(item.id)} icon={item.icon}>{item.shortLabel}</NavButton>
        ))}
        {operatorSections.length > 0 && (
          <>
            <span className="mx-1 w-px shrink-0 self-stretch bg-brand-line" aria-hidden="true" />
            <button
              type="button"
              onClick={() => setAdvancedNav((open) => !open)}
              aria-expanded={showOperatorNav}
              className={`inline-flex shrink-0 items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs font-bold transition ${showOperatorNav ? 'border-brand-ink text-brand-ink' : 'border-brand-line-2 text-brand-muted hover:text-brand-ink'}`}
            >
              <Wrench size={15} /> Advanced
            </button>
            {showOperatorNav && operatorSections.map((item) => (
              <NavButton key={item.id} active={activeSection === item.id} onClick={() => onSectionChange(item.id)} icon={item.icon}>{item.shortLabel}</NavButton>
            ))}
          </>
        )}
      </nav>

      {activeSection === 'overview' ? (
        <Overview sections={sections} operatorSections={operatorSections} summary={summary} onSelect={onSectionChange} />
      ) : (
        <div className="space-y-6" data-testid={`integration-section-${selected.id}`}>
          <div className="overflow-hidden rounded-2xl border border-brand-line bg-brand-surface shadow-sm">
            <div className="flex items-start gap-4 p-5 md:p-6">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-bg text-brand-ink"><ActiveIcon size={20} /></span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-brand-muted">{selected.eyebrow}</p>
                  {activeIsOperator && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">Operator tool</span>
                  )}
                  <StatusPill status={selectedStatus} />
                </div>
                <h3 className="mt-1 font-serif text-xl font-bold text-brand-ink">{selected.label}</h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-brand-ink-2">{selected.description}</p>
              </div>
            </div>
            <IntegrationDetails item={selected} />
          </div>
          {selected.render()}
        </div>
      )}
    </section>
  )
}
