import { describe, expect, it } from 'vitest'
import { deriveStorageReadiness } from './storageReadiness'

const healthy = { connected: true, health: 'healthy', missing_required: [] }

describe('deriveStorageReadiness', () => {
  it('uses Microsoft first in Auto mode, including its unhealthy state', () => {
    expect(deriveStorageReadiness({ microsoft: { ...healthy, health: 'refresh_failed' }, google: healthy }).status).toBe('needs_reconnect')
    expect(deriveStorageReadiness({ microsoft: healthy, google: healthy }).provider).toBe('onedrive')
  })

  it('falls back to Google only when Microsoft is not connected', () => {
    const result = deriveStorageReadiness({ microsoft: { connected: false }, google: healthy })
    expect(result).toMatchObject({ provider: 'google_drive', status: 'ready', ready: true })
  })

  it('requires the selected credential to be healthy and fully scoped', () => {
    const result = deriveStorageReadiness({ primaryCloud: 'google_drive', google: { ...healthy, missing_required: ['https://www.googleapis.com/auth/drive'] } })
    expect(result).toMatchObject({ status: 'needs_reconnect', ready: false })
    expect(result.reason).toMatch(/Reconnect Google Workspace/)
  })

  it('does not block document storage for unrelated mail or calendar scopes', () => {
    const result = deriveStorageReadiness({
      primaryCloud: 'google_drive',
      google: { ...healthy, health: 'missing_scopes', missing_required: ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/gmail.send'] },
    })
    expect(result).toMatchObject({ status: 'ready', ready: true })
  })

  it('requires a verified SharePoint library after Microsoft is healthy', () => {
    const result = deriveStorageReadiness({ primaryCloud: 'sharepoint', microsoft: healthy })
    expect(result).toMatchObject({ status: 'needs_binding', ready: false })
  })
})
