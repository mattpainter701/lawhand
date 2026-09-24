import { canAccessModuleList, hasFinanceAccess } from './moduleAccess'

// Tabs are grouped by what an administrator is trying to do, with the
// day-to-day groups first. Tab ids are stable because links across the app
// (and the in-product guides) deep-link with ?tab=<id>. `advanced` tabs can
// change AI behaviour for every user and are gated on the admin_settings
// capability, not just the role.
//
// This lives outside AdminPage so the app shell can decide whether a guide
// link into Administration is reachable without loading the portal bundle.
export const ADMIN_TAB_GROUPS = [
  { id: 'people', label: 'People', tabs: [
    { id: 'users', label: 'Users' },
    { id: 'roles', label: 'Roles' },
  ] },
  { id: 'firm', label: 'Firm', tabs: [
    { id: 'integrations', label: 'Integrations' },
    { id: 'firm', label: 'Firm Profile' },
    { id: 'settings', label: 'Settings' },
  ] },
  { id: 'billing', label: 'Billing', tabs: [
    { id: 'billing', label: 'Subscription' },
    { id: 'licensing', label: 'Licensing' },
    { id: 'usage', label: 'Usage' },
  ] },
  { id: 'support', label: 'Support', tabs: [
    { id: 'guide', label: 'Admin Guide' },
    { id: 'support', label: 'Support' },
    { id: 'tenant', label: 'Tenant' },
    { id: 'prompts', label: 'Prompts', advanced: true },
  ] },
]

export const ADMIN_TABS = ADMIN_TAB_GROUPS.flatMap((group) => group.tabs)

const ACCOUNTANT_TABS = ADMIN_TABS.filter((tab) =>
  ['licensing', 'billing', 'usage', 'integrations'].includes(tab.id)
)

// Keep the standalone intake product focused on the few settings needed to
// launch and operate a reception team. Unrelated platform integrations remain
// hidden until the tenant upgrades.
const INTAKE_ADMIN_TABS = ADMIN_TABS.filter((tab) =>
  ['users', 'firm', 'licensing', 'billing', 'usage', 'tenant', 'integrations', 'settings', 'guide', 'support'].includes(tab.id)
)
const INTAKE_ACCOUNTANT_TABS = INTAKE_ADMIN_TABS.filter((tab) =>
  ['licensing', 'billing', 'usage'].includes(tab.id)
)

export function canUseAdvancedSettings(user) {
  if (user?.role !== 'admin') return false
  const caps = user?.capabilities
  if (Array.isArray(caps) && caps.length > 0) return caps.includes('admin_settings')
  return true
}

export function adminTabsFor(user) {
  const base = user?.plan === 'intake-only'
    ? (user?.role === 'accountant' ? INTAKE_ACCOUNTANT_TABS : INTAKE_ADMIN_TABS)
    : (user?.role === 'accountant' ? ACCOUNTANT_TABS : ADMIN_TABS)
  return canUseAdvancedSettings(user) ? base : base.filter((tab) => !tab.advanced)
}

// Mirrors the /admin route guard (financeOnly, module "admin") plus the tab
// list, so a guide link is only offered where it will actually open.
export function canOpenAdminTab(user, tab) {
  if (!hasFinanceAccess(user)) return false
  if (!canAccessModuleList(user?.enabled_modules, 'admin')) return false
  return adminTabsFor(user).some((item) => item.id === tab)
}

export function canOpenAdminGuide(user) {
  return canOpenAdminTab(user, 'guide')
}
