export const GENERAL_MODULES = new Set([
  'matters',
  'chat',
  'calendar',
  'tasks',
  'communications',
  'contacts',
  'intake',
  'intake-dashboard',
  'time-tracking',
])

export function isGeneralModule(module) {
  return GENERAL_MODULES.has(module)
}

export function canAccessModuleList(enabledModules, module) {
  if (!module) return true
  if (!Array.isArray(enabledModules)) return false
  return enabledModules.includes(module)
}

export function canAccessAddonList(activeAddons, addon) {
  if (!addon) return true
  if (!Array.isArray(activeAddons)) return false
  return activeAddons.includes(addon)
}

export function hasCapability(capabilities, capability) {
  if (!capability) return true
  if (!Array.isArray(capabilities)) return false
  return capabilities.includes(capability)
}

// Mirrors the backend's require_finance_admin: a billing capability from any
// role, with the legacy admin/accountant roles as the fallback.
export function hasFinanceAccess(user) {
  const capabilities = user?.capabilities
  if (Array.isArray(capabilities)) {
    if (capabilities.includes('view_billing') || capabilities.includes('manage_billing')) {
      return true
    }
  }
  return user?.role === 'admin' || user?.role === 'accountant'
}
