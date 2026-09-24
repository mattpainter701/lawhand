import { useState } from 'react'
import { FileText } from 'lucide-react'
import { SegmentedControl } from '../../components/ui'
import TenantPanelSettings from '../../components/TenantPanelSettings'
import PlatformComplianceCard from '../../components/PlatformComplianceCard'
import OperatorAuditLog from './OperatorAuditLog'
import SupportQueue from './SupportQueue'
import TenantHealth from './TenantHealth'
import {
  PendingTrialApproval,
  ReleaseTrialLogin,
  TenantAccountControls,
  TenantAliasOverride,
  TenantPlanOverride,
  TrialAccessControls,
} from './TenantControls'
import {
  CopyButton,
  DEBUG_SCOPE,
  TenantExpiry,
  TenantTypeBadge,
  TierBadge,
  formatDateTime,
  sessionHasScope,
  tenantType,
} from './shared'

export const TENANT_SECTIONS = [
  { value: 'overview', label: 'Overview' },
  { value: 'access', label: 'Access & billing' },
  { value: 'health', label: 'Health' },
  { value: 'support', label: 'Support' },
  { value: 'ai', label: 'AI & workspace' },
  { value: 'history', label: 'History' },
  { value: 'compliance', label: 'Compliance' },
]

function Fact({ label, children }) {
  return (
    <div className="flex justify-between gap-4 py-1">
      <dt className="text-brand-muted">{label}</dt>
      <dd className="min-w-0 text-right text-brand-ink">{children}</dd>
    </div>
  )
}

function SectionHeading({ children, description }) {
  return (
    <div className="mb-3">
      <h4 className="text-xs font-bold uppercase tracking-wider text-brand-ink">{children}</h4>
      {description && <p className="mt-1 text-xs text-brand-muted">{description}</p>}
    </div>
  )
}

function UserList({ users }) {
  if (!users?.length) return <p className="text-sm text-brand-muted">No users listed.</p>
  return (
    <ul className="max-h-80 divide-y divide-brand-line overflow-y-auto rounded-lg border border-brand-line bg-brand-surface">
      {users.map((user) => (
        <li key={user.id} className="flex items-start justify-between gap-3 px-3 py-2 text-sm">
          <div className="min-w-0">
            <p className="font-medium text-brand-ink">{user.full_name || `User ${user.id.slice(0, 8)}`}</p>
            <p className="flex items-center gap-1 text-xs text-brand-muted">
              <span className="truncate">{user.email}</span>
              <CopyButton value={user.email} label={`${user.email} address`} />
            </p>
            <p className="text-[11px] text-brand-muted">Added {formatDateTime(user.created_at)}</p>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-1 text-[11px]">
            <span className={`rounded px-1.5 py-0.5 ${user.role === 'admin' ? 'bg-brand-ink/10 text-brand-ink' : 'bg-brand-muted/10 text-brand-muted'}`}>{user.role}</span>
            {user.is_active === false && <span className="rounded bg-brand-rose/10 px-1.5 py-0.5 text-brand-rose" title="Deactivated, or has not accepted their invitation yet">Not active</span>}
            {user.license_active === false && <span className="rounded bg-brand-amber/10 px-1.5 py-0.5 text-brand-amber">Unlicensed</span>}
            {user.premium_ai_enabled && <span className="rounded bg-brand-amber/10 px-1.5 py-0.5 text-brand-amber">Premium AI</span>}
          </div>
        </li>
      ))}
    </ul>
  )
}

const lifecycleLabel = (detail) => {
  if (detail.signup_status === 'pending') return { text: 'Pending approval', tone: 'text-brand-amber' }
  if (!detail.is_active) return { text: 'Inactive', tone: 'text-brand-rose' }
  if (detail.expires_at && new Date(detail.expires_at).getTime() <= Date.now()) return { text: 'Expired', tone: 'text-brand-rose' }
  if (detail.on_trial) return { text: 'On trial', tone: 'text-brand-amber' }
  return { text: 'Active', tone: 'text-brand-accent' }
}

/**
 * Everything about one firm, split into sections so the common support
 * questions — who is this, can they get in, what is failing, what did we
 * already do — are each one click away instead of one long scroll.
 */
export default function TenantDetailPanel({
  tenant,
  detail,
  platformKey,
  session,
  llmConfig,
  onPatch,
  onApprove,
  onUpdate,
  onDetailChange,
  onRefresh,
  onError,
  onAuthError,
  onOpenLogs,
  initialSection = 'overview',
}) {
  const [section, setSection] = useState(initialSection)
  const [savingAi, setSavingAi] = useState(false)
  const canDebug = sessionHasScope(session, DEBUG_SCOPE)
  const isDemo = tenantType(detail) === 'demo'
  const pending = detail.signup_status === 'pending'
  const lifecycle = lifecycleLabel(detail)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-serif text-lg font-bold text-brand-ink">{detail.name}</h3>
            <TierBadge tier={detail.billing_tier} />
            {isDemo && <TenantTypeBadge type="demo" />}
            <span className={`text-xs font-semibold ${lifecycle.tone}`}>{lifecycle.text}</span>
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-brand-muted">
            <span>{detail.domain}</span>
            <span className="inline-flex items-center gap-1 font-mono">
              {detail.id}
              <CopyButton value={detail.id} label="tenant ID" />
            </span>
            {detail.signup_email && (
              <span className="inline-flex items-center gap-1">
                Admin {detail.signup_email}
                <CopyButton value={detail.signup_email} label="admin email" />
              </span>
            )}
          </p>
        </div>
        {onOpenLogs && (
          <button type="button" onClick={() => onOpenLogs(detail.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line bg-brand-surface px-3 py-1.5 text-xs font-semibold text-brand-ink">
            <FileText size={13} aria-hidden="true" /> Error logs
          </button>
        )}
      </div>

      {pending && (
        <PendingTrialApproval tenant={detail} onApprove={onApprove} />
      )}

      <SegmentedControl label={`${detail.name} sections`} items={TENANT_SECTIONS} value={section} onChange={setSection} />

      <div className="rounded-xl border border-brand-line bg-brand-bg p-4">
        {section === 'overview' && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <SectionHeading>Account</SectionHeading>
              <dl className="divide-y divide-brand-line text-sm">
                <Fact label="Company">{detail.company_name || '—'}</Fact>
                <Fact label="Plan">{detail.module_config?.plan || 'Default (full platform)'}</Fact>
                <Fact label="Access expiration"><TenantExpiry tenant={detail} /></Fact>
                <Fact label="Trial started">{detail.trial_started_at ? formatDateTime(detail.trial_started_at) : '—'}</Fact>
                <Fact label="Premium AI during trial">{detail.premium_ai_trial_enabled ? 'Sponsored' : 'Off'}</Fact>
                <Fact label="Seats">{detail.flat_seat_count ?? '—'}</Fact>
                <Fact label="Stripe customer">{detail.stripe_customer_id ? 'Linked' : '—'}</Fact>
                <Fact label="Subscription">{detail.stripe_subscription_status || '—'}</Fact>
                <Fact label="Research MCP">{detail.mcp_entitlement_status || '—'}</Fact>
                <Fact label="Model usage (30d)">{(detail.usage_30d?.requests ?? detail.requests_30d ?? 0).toLocaleString()} requests · ${Number(detail.usage_30d?.cost_usd ?? detail.cost_usd_30d ?? 0).toFixed(2)}</Fact>
                <Fact label="Created">{formatDateTime(detail.created_at)}</Fact>
              </dl>
            </div>
            <div>
              <SectionHeading description="“Not active” covers deactivated users and invitations not yet accepted.">
                Users ({detail.users?.length ?? detail.user_count ?? 0})
              </SectionHeading>
              <UserList users={detail.users} />
            </div>
          </div>
        )}

        {section === 'access' && (
          isDemo ? (
            <p className="text-sm text-brand-muted">
              Use the Demos tab to end this disposable workspace. Access and billing controls stay off for demos so a live demo cannot be interrupted by accident.
            </p>
          ) : pending ? (
            <p className="text-sm text-brand-muted">Approve the registration above to start the trial; the other access controls unlock once it is live.</p>
          ) : (
            <div className="space-y-6">
              <div>
                <SectionHeading description="Each change here applies to the whole firm and is recorded in its History.">Account</SectionHeading>
                <TenantAccountControls tenant={detail} onPatch={onPatch} />
              </div>
              <TrialAccessControls tenant={detail} onPatch={onPatch} />
              <div className="border-t border-brand-line pt-4">
                <SectionHeading description="Selects the module bundle the firm sees.">Plan</SectionHeading>
                <TenantPlanOverride tenant={tenant} tenantDetail={detail} platformKey={platformKey} onUpdate={onUpdate} onError={onError} />
              </div>
              {detail.on_trial && (
                <div className="border-t border-brand-line pt-4">
                  <ReleaseTrialLogin tenant={detail} users={detail.users} platformKey={platformKey} onRevoked={onRefresh} />
                </div>
              )}
            </div>
          )
        )}

        {section === 'health' && (
          <TenantHealth platformKey={platformKey} tenantId={detail.id} canDebug={canDebug} onAuthError={onAuthError} onOpenLogs={onOpenLogs} />
        )}

        {section === 'support' && (
          <SupportQueue platformKey={platformKey} tenantId={detail.id} onAuthError={onAuthError} />
        )}

        {section === 'ai' && (
          <div className="space-y-6">
            <div>
              <SectionHeading>AI routing</SectionHeading>
              <TenantAliasOverride
                tenant={tenant}
                tenantDetail={detail}
                platformKey={platformKey}
                defaultAliases={{
                  standard: llmConfig?.standard_model || 'lawhand-standard',
                  premium: llmConfig?.premium_model || 'lawhand-premium',
                }}
                onUpdate={onUpdate}
                onError={onError}
                saving={savingAi}
                setSaving={setSavingAi}
              />
            </div>
            <TenantPanelSettings
              key={detail.id}
              tenantId={detail.id}
              hiddenPanels={detail.hidden_matter_panels}
              platformKey={platformKey}
              onSaved={(hidden) => onDetailChange((previous) => ({ ...previous, hidden_matter_panels: hidden }))}
            />
          </div>
        )}

        {section === 'history' && (
          <OperatorAuditLog platformKey={platformKey} tenantId={detail.id} canDebug={canDebug} onAuthError={onAuthError} />
        )}

        {section === 'compliance' && (
          <PlatformComplianceCard platformKey={platformKey} tenantId={detail.id} />
        )}
      </div>
    </div>
  )
}
