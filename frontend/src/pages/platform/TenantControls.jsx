import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { getLLMRoutingProfiles, getPlatformPlans, revokePlatformTenantTrial, updatePlatformTenant } from '../../api'
import { useConfirm } from '../../components/dialog/ConfirmProvider'
import { CopyButton, apiErrorMessage } from './shared'

/** Operator controls for one firm's access, trial, plan and AI routing. */

const trialDateInputValue = (value) => {
  if (!value) return ''
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString().slice(0, 10)
}

const extensionInstant = (currentValue, days) => {
  const current = currentValue ? new Date(currentValue) : null
  const base = current && current.getTime() > Date.now() ? current : new Date()
  return new Date(base.getTime() + days * 24 * 60 * 60 * 1000).toISOString()
}

const extensionMonthInstant = (currentValue, months) => {
  const current = currentValue ? new Date(currentValue) : null
  const base = current && current.getTime() > Date.now() ? current : new Date()
  const extended = new Date(base)
  extended.setUTCMonth(extended.getUTCMonth() + months)
  return extended.toISOString()
}

export function TrialAccessControls({ tenant, onPatch }) {
  const confirm = useConfirm()
  const [endDate, setEndDate] = useState(() => trialDateInputValue(tenant.expires_at))
  const [extendDays, setExtendDays] = useState(14)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [localError, setLocalError] = useState('')

  useEffect(() => {
    setEndDate(trialDateInputValue(tenant.expires_at))
  }, [tenant.expires_at])

  const patch = async (payload, successMessage) => {
    setSaving(true)
    setNotice('')
    setLocalError('')
    try {
      const result = await onPatch(payload)
      let message = successMessage
      if (result?.trial_email_status === 'sent') {
        message += ' The firm administrators were emailed.'
      } else if (result?.trial_email_status) {
        message += ` Access changed, but email delivery was ${result.trial_email_status}.`
      }
      setNotice(message)
    } catch (error) {
      setLocalError(error?.response?.data?.detail || 'Could not update trial access.')
    } finally {
      setSaving(false)
    }
  }

  const saveExactDate = (event) => {
    event.preventDefault()
    if (!endDate) return
    patch(
      { trial_ends_at: new Date(`${endDate}T23:59:59.000Z`).toISOString() },
      `Trial access now ends ${endDate}.`,
    )
  }

  const firm = tenant.name || 'This firm'

  // The three buttons below act on the whole firm at once, so each asks first.
  const endAccessNow = async () => {
    const approved = await confirm({
      title: 'End trial access now?',
      message: `${firm} loses workspace access immediately. Its data and logins are kept, and extending the trial restores access.`,
      confirmLabel: 'End access now',
      destructive: true,
    })
    if (approved) patch({ trial_ends_at: new Date(Date.now() - 1000).toISOString() }, 'Trial access ended immediately.')
  }

  const convertToActive = async () => {
    const approved = await confirm({
      title: 'Remove the trial expiry?',
      message: `${firm} keeps workspace access with no end date and is no longer treated as a trial.`,
      confirmLabel: 'Convert to active',
    })
    if (approved) patch({ trial_ends_at: null }, 'Trial cleared; the firm now has active access without an expiration.')
  }

  const togglePremium = async () => {
    if (!tenant.premium_ai_trial_enabled) {
      const approved = await confirm({
        title: 'Sponsor Premium AI for this firm?',
        message: `Every licensed user at ${firm} gets Premium AI at LawHand's cost until you turn it off.`,
        confirmLabel: 'Enable Premium AI',
      })
      if (!approved) return
    }
    patch(
      { premium_ai_trial_enabled: !tenant.premium_ai_trial_enabled },
      tenant.premium_ai_trial_enabled ? 'Sponsored Premium AI disabled.' : 'Sponsored Premium AI enabled for licensed users.',
    )
  }

  return (
    <div className="mt-4 pt-4 border-t border-brand-line">
      <h4 className="text-xs font-bold text-brand-ink uppercase tracking-wider font-sans">Trial & Premium AI</h4>
      <p className="mt-1 text-xs leading-5 text-brand-muted">
        Trial access and sponsored Premium AI are separate. Premium is off for new trials unless you explicitly enable it here.
      </p>

      <form onSubmit={saveExactDate} className="mt-3 flex flex-wrap items-end gap-2">
        <label className="block">
          <span className="block text-xs font-medium text-brand-muted">Trial end date (UTC)</span>
          <input
            aria-label="Trial end date"
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className="mt-1 rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm text-brand-ink"
          />
        </label>
        <button type="submit" disabled={saving || !endDate} className="rounded-lg border border-brand-accent/30 px-3 py-2 text-xs font-medium text-brand-accent disabled:opacity-50">
          Set date
        </button>
        <button type="button" disabled={saving} onClick={() => patch({ trial_ends_at: extensionInstant(tenant.expires_at, 30) }, 'Trial extended by 30 days.')} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink-2 disabled:opacity-50">
          Extend 30 days
        </button>
        <button type="button" disabled={saving} onClick={() => patch({ trial_ends_at: extensionMonthInstant(tenant.expires_at, 6) }, 'Trial extended by 6 months.')} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink-2 disabled:opacity-50">
          Extend 6 months
        </button>
        <label className="block">
          <span className="block text-xs font-medium text-brand-muted">Extend by (days)</span>
          <input
            aria-label="Extend by days"
            type="number"
            min="1"
            max="365"
            value={extendDays}
            onChange={(event) => setExtendDays(event.target.value)}
            className="mt-1 w-24 rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm text-brand-ink"
          />
        </label>
        <button type="button" disabled={saving || !extendDays} onClick={() => patch({ trial_ends_at: extensionInstant(tenant.expires_at, Number(extendDays)) }, `Trial extended by ${extendDays} days.`)} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink-2 disabled:opacity-50">
          Extend by days
        </button>
      </form>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <button type="button" disabled={saving} onClick={endAccessNow} className="rounded-lg border border-brand-rose/30 px-3 py-2 text-xs font-medium text-brand-rose disabled:opacity-50">
          End access now
        </button>
        <button type="button" disabled={saving} onClick={convertToActive} className="rounded-lg border border-brand-accent/30 px-3 py-2 text-xs font-medium text-brand-accent disabled:opacity-50">
          Convert to active
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={togglePremium}
          className={`rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-50 ${tenant.premium_ai_trial_enabled ? 'border-brand-rose/30 text-brand-rose' : 'border-brand-amber/30 text-brand-amber'}`}
        >
          {tenant.premium_ai_trial_enabled ? 'Disable Premium AI' : 'Enable Premium AI'}
        </button>
      </div>
      {notice && <p role="status" className="mt-3 text-xs text-brand-accent">{notice}</p>}
      {localError && <p role="alert" className="mt-3 text-xs text-brand-rose">{localError}</p>}
    </div>
  )
}

export function ProvisionTrialTenantForm({ onProvision }) {
  const [form, setForm] = useState({
    firm_name: '',
    admin_email: '',
    admin_name: '',
    trial_days: 30,
    plan: 'full-trial',
    premium_ai_trial_enabled: false,
  })
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)
  const [localError, setLocalError] = useState('')

  const setField = (field) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value
    setForm((current) => ({ ...current, [field]: value }))
  }

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setResult(null)
    setLocalError('')
    try {
      const created = await onProvision({
        ...form,
        trial_days: Number(form.trial_days),
        admin_name: form.admin_name.trim() || null,
      })
      setResult(created)
      setForm((current) => ({ ...current, firm_name: '', admin_email: '', admin_name: '' }))
    } catch (error) {
      setLocalError(error?.response?.data?.detail || 'Could not provision the customer.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="mb-6 rounded-xl border border-brand-line bg-brand-surface p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-serif font-bold text-brand-ink">Register a customer</h2>
          <p className="mt-1 max-w-3xl text-sm text-brand-muted">
            Creates a private trial and emails the founding administrator a secure account-setup link. Public self-registration remains off.
          </p>
        </div>
        <span className="rounded-full bg-brand-accent/10 px-3 py-1 text-xs font-medium text-brand-accent">Operator-only</span>
      </div>
      <form onSubmit={submit} className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
        <label className="block">
          <span className="text-xs font-medium text-brand-muted">Firm name</span>
          <input required value={form.firm_name} onChange={setField('firm_name')} className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-brand-muted">Attorney email</span>
          <input required type="email" value={form.admin_email} onChange={setField('admin_email')} className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-brand-muted">Attorney name</span>
          <input value={form.admin_name} onChange={setField('admin_name')} className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-brand-muted">Trial days</span>
          <input required type="number" min="1" max="365" value={form.trial_days} onChange={setField('trial_days')} className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-brand-muted">Workspace access</span>
          <select value={form.plan} onChange={setField('plan')} className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm">
            <option value="full-trial">Full workspace trial</option>
            <option value="intake-only">Intake + tasks trial</option>
            <option value="full-platform">Full platform trial</option>
          </select>
        </label>
        <label className="flex items-center gap-2 self-end rounded-lg border border-brand-line px-3 py-2 text-sm text-brand-ink-2">
          <input type="checkbox" checked={form.premium_ai_trial_enabled} onChange={setField('premium_ai_trial_enabled')} />
          Sponsor Premium AI
        </label>
        <div className="md:col-span-3 flex flex-wrap items-center gap-3">
          <button type="submit" disabled={saving} className="inline-flex items-center gap-2 rounded-lg bg-brand-ink px-4 py-2 text-sm font-medium text-brand-surface disabled:opacity-50">
            <Plus size={15} /> {saving ? 'Registering…' : 'Create trial and send invite'}
          </button>
          <button type="button" onClick={() => setForm((current) => ({ ...current, trial_days: 180 }))} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink-2">
            Use 6 months
          </button>
        </div>
      </form>
      {result && (
        <div role="status" className="mt-4 rounded-lg border border-brand-accent/20 bg-brand-accent/5 px-4 py-3 text-sm text-brand-ink-2">
          Customer created. Email status: <strong>{result.email_status}</strong>.
          {result.email_status !== 'sent' && ' The invitation email did not go out — send the customer the backup link below yourself.'}
          {result.invitation_url && (
            <span className="mt-2 flex items-center gap-2">
              <label className="min-w-0 flex-1">
                <span className="sr-only">Backup invitation link</span>
                <input readOnly value={result.invitation_url} onFocus={(event) => event.target.select()} className="w-full rounded border border-brand-line bg-brand-surface px-2 py-1 font-mono text-xs" />
              </label>
              <CopyButton value={result.invitation_url} label="backup invitation link" />
            </span>
          )}
          <span className="mt-1 block text-xs text-brand-muted">The link sets up the customer administrator&apos;s login — share it only with them, and don&apos;t open it yourself.</span>
        </div>
      )}
      {localError && <p role="alert" className="mt-3 text-sm text-brand-rose">{localError}</p>}
    </section>
  )
}

export function PendingTrialApproval({ tenant, onApprove }) {
  const [trialDays, setTrialDays] = useState(30)
  const [premium, setPremium] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [localError, setLocalError] = useState('')

  const approve = async () => {
    setSaving(true)
    setNotice('')
    setLocalError('')
    try {
      const result = await onApprove({
        trial_days: Number(trialDays),
        premium_ai_trial_enabled: premium,
      })
      setNotice(`Trial approved. Customer email status: ${result.email_status}.`)
    } catch (error) {
      setLocalError(error?.response?.data?.detail || 'Could not approve the registration.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-brand-amber/30 bg-brand-amber/5 p-4">
      <h4 className="text-sm font-bold text-brand-ink">Pending registration</h4>
      <p className="mt-1 text-xs leading-5 text-brand-muted">
        This firm has no workspace access, trial clock, or AI spend until approval.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label>
          <span className="block text-xs font-medium text-brand-muted">Trial days</span>
          <input aria-label="Approval trial days" type="number" min="1" max="365" value={trialDays} onChange={(event) => setTrialDays(event.target.value)} className="mt-1 w-28 rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
        </label>
        <button type="button" onClick={() => setTrialDays(180)} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink-2">Use 6 months</button>
        <label className="flex items-center gap-2 rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-xs text-brand-ink-2">
          <input type="checkbox" checked={premium} onChange={(event) => setPremium(event.target.checked)} />
          Sponsor Premium AI
        </label>
        <button type="button" disabled={saving} onClick={approve} className="rounded-lg bg-brand-ink px-4 py-2 text-xs font-medium text-white disabled:opacity-50">
          {saving ? 'Approving…' : `Approve ${tenant.name}`}
        </button>
      </div>
      {notice && <p role="status" className="mt-3 text-xs text-brand-accent">{notice}</p>}
      {localError && <p role="alert" className="mt-3 text-xs text-brand-rose">{localError}</p>}
    </div>
  )
}

export function TenantAliasOverride({ tenant, tenantDetail, platformKey, defaultAliases, onUpdate, onError, saving, setSaving }) {
  const config = tenantDetail?.llm_config || {}
  const assistantConfig = tenantDetail?.assistant_config || {}
  const [profiles, setProfiles] = useState([])
  const [value, setValue] = useState(config.routing_profile_id || '')
  const [backgroundEnabled, setBackgroundEnabled] = useState(Boolean(assistantConfig.background_assistant_enabled))
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setValue(config.routing_profile_id || '')
    setSaved(false)
  }, [config.routing_profile_id])

  useEffect(() => {
    setBackgroundEnabled(Boolean(assistantConfig.background_assistant_enabled))
    setSaved(false)
  }, [assistantConfig.background_assistant_enabled])

  useEffect(() => {
    getLLMRoutingProfiles(platformKey).then((data) => setProfiles(data.profiles || [])).catch(() => setProfiles([]))
  }, [platformKey])

  const selected = profiles.find((profile) => profile.id === value)
    || (!value ? profiles.find((profile) => profile.is_default) : null)
    || config.routing_profile
  const changed = value !== (config.routing_profile_id || '')
    || backgroundEnabled !== Boolean(assistantConfig.background_assistant_enabled)

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const payload = {
        llm_routing_profile_id: value || null,
        background_assistant_enabled: backgroundEnabled,
      }
      await updatePlatformTenant(platformKey, tenant.id, payload)
      onUpdate(tenant.id, {
        llm_config: { ...config, routing_profile_id: value || null, routing_profile: selected || null },
        assistant_config: { ...assistantConfig, background_assistant_enabled: backgroundEnabled },
      })
      setSaved(true)
    } catch (e) {
      onError?.(e?.response?.data?.detail || 'Failed to save tenant AI alias override.')
    }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor={`tenant-${tenant.id}-routing-profile`} className="block text-xs text-brand-muted font-sans mb-1">AI routing profile</label>
        <select id={`tenant-${tenant.id}-routing-profile`} value={value} onChange={(e) => { setValue(e.target.value); setSaved(false) }} className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm font-sans bg-brand-surface">
          <option value="">Inherit default profile</option>
          {profiles.filter((profile) => profile.assignable).map((profile) => <option key={profile.id} value={profile.id}>{profile.name}{profile.is_default ? ' (default)' : ''}</option>)}
        </select>
      </div>
      {selected && <div className="rounded-lg border border-brand-line bg-brand-bg px-4 py-3 text-xs font-sans"><p className="font-medium text-brand-ink">{selected.name}{!value ? ' · inherited default' : ' · tenant assignment'}</p><p className="mt-1 text-brand-muted">Standard matter context: {selected.standard_allow_matter_context ? 'Allowed' : 'Blocked'} · Premium matter context: {selected.premium_allow_matter_context ? 'Allowed' : 'Blocked'} · {selected.is_active ? 'Active' : 'Inactive'}</p></div>}
      <label className="flex gap-3 rounded-lg border border-brand-line bg-brand-bg px-4 py-3 cursor-pointer">
        <input
          type="checkbox"
          checked={backgroundEnabled}
          onChange={(event) => { setBackgroundEnabled(event.target.checked); setSaved(false) }}
          className="mt-0.5 h-4 w-4 accent-brand-ink"
        />
        <span>
          <span className="block text-sm font-medium text-brand-ink font-sans">Enable Background Automations for this firm</span>
          <span className="block mt-1 text-xs text-brand-muted font-sans">Tenant kill switch. Global feature and confidential-data gates must also be enabled before any model call can run.</span>
        </span>
      </label>
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || !changed}
          className={`px-4 py-2 rounded-lg text-xs font-medium font-sans border transition-colors ${
            saved
              ? 'bg-brand-accent/10 border-brand-accent/20 text-brand-accent'
              : 'bg-brand-ink text-white border-brand-ink hover:bg-brand-ink-2 disabled:opacity-40'
          }`}
        >
          {saved ? 'Saved' : saving ? 'Saving...' : 'Save AI Controls'}
        </button>
        <p className="text-xs text-brand-muted font-sans">Unassigned tenants inherit the default profile.</p>
      </div>
    </div>
  )
}

export function TenantPlanOverride({ tenant, tenantDetail, platformKey, onUpdate, onError }) {
  const currentPlan = tenantDetail?.module_config?.plan || ''
  const [plans, setPlans] = useState([])
  const [value, setValue] = useState(currentPlan)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => { setValue(currentPlan); setSaved(false) }, [currentPlan])

  useEffect(() => {
    let cancelled = false
    getPlatformPlans(platformKey)
      .then((data) => { if (!cancelled) setPlans(data.plans || []) })
      .catch(() => { if (!cancelled) setPlans([]) })
    return () => { cancelled = true }
  }, [platformKey])

  const save = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await updatePlatformTenant(platformKey, tenant.id, { plan: value || null })
      onUpdate(tenant.id, { module_config: { ...(tenantDetail?.module_config || {}), plan: value || null } })
      setSaved(true)
    } catch (e) {
      onError?.(e?.response?.data?.detail || 'Failed to save tenant plan.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-end gap-3">
      <div className="flex-1">
        <label htmlFor="platformpage-plan" className="block text-xs text-brand-muted font-sans mb-1">Plan</label>
        <select id="platformpage-plan"
          value={value}
          onChange={(e) => { setValue(e.target.value); setSaved(false) }}
          className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm font-sans bg-brand-surface focus:outline-none focus:ring-2 focus:ring-brand-accent"
        >
          <option value="">(default / full platform)</option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>{p.label} ({p.id})</option>
          ))}
        </select>
      </div>
      <button
        onClick={save}
        disabled={saving || value === currentPlan}
        className={`px-4 py-2 rounded-lg text-xs font-medium font-sans border transition-colors ${
          saved
            ? 'bg-brand-accent/10 border-brand-accent/20 text-brand-accent'
            : 'bg-brand-ink text-white border-brand-ink hover:bg-brand-ink-2 disabled:opacity-40'
        }`}
      >
        {saved ? 'Saved' : saving ? 'Saving...' : 'Set Plan'}
      </button>
    </div>
  )
}

const MCP_ENTITLEMENTS = ['disabled', 'enabled', 'suspended']

/**
 * Whole-firm switches that used to fire on a single click: access, billing
 * model, seats and Research MCP entitlement. Each consequential change asks
 * first and every change is written to the operator audit trail server-side.
 */
export function TenantAccountControls({ tenant, onPatch }) {
  const confirm = useConfirm()
  const [seats, setSeats] = useState(String(tenant.flat_seat_count ?? ''))
  const [mcp, setMcp] = useState(tenant.mcp_entitlement_status || 'disabled')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [localError, setLocalError] = useState('')
  const firm = tenant.name || 'This firm'

  useEffect(() => { setSeats(String(tenant.flat_seat_count ?? '')) }, [tenant.flat_seat_count])
  useEffect(() => { setMcp(tenant.mcp_entitlement_status || 'disabled') }, [tenant.mcp_entitlement_status])

  const patch = async (payload, successMessage) => {
    setSaving(true)
    setNotice('')
    setLocalError('')
    try {
      await onPatch(payload)
      setNotice(successMessage)
    } catch (error) {
      setLocalError(apiErrorMessage(error, 'Could not update this firm.'))
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async () => {
    if (tenant.is_active) {
      const approved = await confirm({
        title: `Deactivate ${firm}?`,
        message: 'Every user at the firm loses access immediately. Nothing is deleted, and activating the firm again restores access.',
        confirmLabel: 'Deactivate firm',
        destructive: true,
      })
      if (!approved) return
      patch({ is_active: false }, 'Firm deactivated.')
    } else {
      patch({ is_active: true }, 'Firm activated.')
    }
  }

  const setTier = async (tier) => {
    if (tier === tenant.billing_tier) return
    const label = tier === 'flat' ? 'flat-seat' : 'pay-as-you-go'
    const approved = await confirm({
      title: `Switch ${firm} to ${label} billing?`,
      message: 'This changes how the firm is billed from now on.',
      confirmLabel: `Use ${label}`,
    })
    if (approved) patch({ billing_tier: tier }, `Billing switched to ${label}.`)
  }

  const saveSeats = (event) => {
    event.preventDefault()
    const count = Number(seats)
    if (!Number.isInteger(count) || count < 0) {
      setLocalError('Seats must be a whole number of zero or more.')
      return
    }
    patch({ seat_count: count }, `Seat count set to ${count}.`)
  }

  const saveMcp = async () => {
    if (mcp === 'suspended') {
      const approved = await confirm({
        title: `Suspend Research MCP for ${firm}?`,
        message: "The firm's Research MCP keys stop working until the entitlement is enabled again.",
        confirmLabel: 'Suspend',
        destructive: true,
      })
      if (!approved) return
    }
    patch({ mcp_entitlement_status: mcp }, `Research MCP entitlement set to ${mcp}.`)
  }

  const seatsChanged = seats !== String(tenant.flat_seat_count ?? '')
  const mcpChanged = mcp !== (tenant.mcp_entitlement_status || 'disabled')

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={toggleActive}
          className={`rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-50 ${tenant.is_active ? 'border-brand-rose/30 text-brand-rose hover:bg-brand-rose/5' : 'border-brand-accent/30 text-brand-accent hover:bg-brand-accent/5'}`}
        >
          {tenant.is_active ? 'Deactivate firm' : 'Activate firm'}
        </button>
        <div role="group" aria-label="Billing model" className="inline-flex rounded-lg border border-brand-line p-0.5">
          {[['flat', 'Flat-seat'], ['payg', 'PAYG']].map(([tier, label]) => (
            <button
              key={tier}
              type="button"
              aria-pressed={tenant.billing_tier === tier}
              disabled={saving}
              onClick={() => setTier(tier)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${tenant.billing_tier === tier ? 'bg-brand-ink text-white' : 'text-brand-muted hover:text-brand-ink'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-end gap-4">
        <form onSubmit={saveSeats} className="flex items-end gap-2">
          <label className="block">
            <span className="block text-xs font-medium text-brand-muted">Seats</span>
            <input type="number" min="0" step="1" value={seats} onChange={(event) => setSeats(event.target.value)} className="mt-1 w-24 rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
          </label>
          <button type="submit" disabled={saving || !seatsChanged} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink disabled:opacity-40">Save seats</button>
        </form>
        <div className="flex items-end gap-2">
          <label className="block">
            <span className="block text-xs font-medium text-brand-muted">Research MCP entitlement</span>
            <select value={mcp} onChange={(event) => setMcp(event.target.value)} className="mt-1 rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm">
              {MCP_ENTITLEMENTS.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <button type="button" disabled={saving || !mcpChanged} onClick={saveMcp} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-medium text-brand-ink disabled:opacity-40">Save entitlement</button>
        </div>
        {tenant.mcp_billing_status && <p className="text-xs text-brand-muted">MCP billing: {tenant.mcp_billing_status}</p>}
      </div>
      {notice && <p role="status" className="text-xs text-brand-accent">{notice}</p>}
      {localError && <p role="alert" className="text-xs text-brand-rose">{localError}</p>}
    </div>
  )
}

/**
 * Retires an abandoned or test trial so its address can onboard again.
 * The server refuses firms with billing or work product, so this can only
 * reach a genuinely unused trial; typing a login address is the confirmation.
 */
export function ReleaseTrialLogin({ tenant, users = [], platformKey, onRevoked }) {
  const [email, setEmail] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)
  const [localError, setLocalError] = useState('')
  const logins = users.map((user) => String(user.email || '').toLowerCase())
  const matches = logins.includes(email.trim().toLowerCase())

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setLocalError('')
    try {
      const revoked = await revokePlatformTenantTrial(platformKey, tenant.id, {
        confirm_email: email.trim(),
        reason: reason.trim() || null,
      })
      setResult(revoked)
      setEmail('')
      setReason('')
      await onRevoked?.(revoked)
    } catch (error) {
      setLocalError(apiErrorMessage(error, 'Could not revoke this trial.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-lg border border-brand-rose/30 bg-brand-rose/5 p-4">
      <h5 className="text-sm font-bold text-brand-ink">Revoke trial and release its login</h5>
      <p className="mt-1 text-xs leading-5 text-brand-ink-2">
        For an abandoned or test trial whose owner needs to start over. Deactivates every login, frees each address to register again, removes stored Google or Microsoft access and marks the firm inactive. Agreement evidence and cloud-drive content are kept. Refused for firms with billing or any work product.
      </p>
      <form onSubmit={submit} className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-[1fr_1fr_auto]">
        <label className="block">
          <span className="block text-xs font-medium text-brand-muted">Type a login address at this firm to confirm</span>
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder={tenant.signup_email || users[0]?.email || 'owner@firm.com'} autoComplete="off" className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-brand-muted">Reason (recorded in the audit trail)</span>
          <input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={300} placeholder="Abandoned test trial" className="mt-1 w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm" />
        </label>
        <button type="submit" disabled={saving || !matches} className="self-end rounded-lg bg-brand-rose px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">
          {saving ? 'Revoking…' : 'Revoke trial'}
        </button>
      </form>
      {email.trim() && !matches && <p className="mt-2 text-xs text-brand-muted">That address is not a login at this firm.</p>}
      {result && (
        <p role="status" className="mt-2 text-xs text-brand-accent">
          Trial revoked. Released {result.released_emails?.join(', ') || 'no addresses'}; {result.users_revoked} login{result.users_revoked === 1 ? '' : 's'} deactivated and {result.credentials_revoked} stored credential{result.credentials_revoked === 1 ? '' : 's'} removed.
        </p>
      )}
      {localError && <p role="alert" className="mt-2 text-xs text-brand-rose">{localError}</p>}
    </div>
  )
}
