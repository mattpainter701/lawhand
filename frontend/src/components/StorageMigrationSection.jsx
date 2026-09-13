import { useEffect, useState } from 'react'
import { getAdminPermissions, getAdminSettings, getSharePointBinding } from '../api'
import StorageMigrationPanel from './StorageMigrationPanel'
import { AlertBanner } from './ui'

/**
 * Mounts the storage migration tooling as an operator section of the hub.
 *
 * The migration service, router and tests already exist; this only gives
 * the panel its own data loading so it no longer has to sit inside the
 * firm-admin cloud panel to borrow that panel's state. It is a destructive,
 * rarely used flow: it belongs behind Advanced, not beside "Connect Google".
 */
export default function StorageMigrationSection() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [permissions, setPermissions] = useState(null)
  const [primaryProvider, setPrimaryProvider] = useState(null)
  const [sharePointBinding, setSharePointBinding] = useState(null)

  useEffect(() => {
    let active = true
    Promise.all([
      getAdminPermissions(),
      getAdminSettings(),
      getSharePointBinding().catch(() => ({ binding: null })),
    ])
      .then(([perms, settings, bindingData]) => {
        if (!active) return
        setPermissions(perms)
        setPrimaryProvider(settings?.primary_cloud_provider ?? null)
        setSharePointBinding(bindingData?.binding || null)
      })
      .catch(() => { if (active) setError('Unable to load connected storage for migration.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  if (loading) {
    return (
      <div className="flex justify-center py-8" role="status" aria-label="Loading storage migration">
        <div className="w-6 h-6 border-4 border-brand-ink border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }
  if (error) return <AlertBanner type="error">{error}</AlertBanner>

  return (
    <div className="space-y-4">
      <AlertBanner type="warning" title="Operator tool">
        Cutover rebinds every matter folder to the target provider. Reconcile first and confirm the evidence before you cut over.
        Re-run onboarding from the Onboarding section if the firm needs to choose storage again.
      </AlertBanner>
      <StorageMigrationPanel
        primaryProvider={primaryProvider}
        permissions={permissions}
        sharePointBinding={sharePointBinding}
      />
    </div>
  )
}
