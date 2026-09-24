import { describe, expect, it } from 'vitest'
import { summarizeAuditMetadata } from './OperatorAuditLog'
import { formatRelative, isScopeDenied, isSessionEnded, sessionHasScope } from './shared'

const forbidden = (detail) => ({ response: { status: 403, data: { detail } } })

describe('platform session errors', () => {
  it('tells a missing scope apart from an ended session', () => {
    expect(isScopeDenied(forbidden('Platform token scope denied'))).toBe(true)
    expect(isSessionEnded(forbidden('Platform token scope denied'))).toBe(false)
    expect(isSessionEnded(forbidden('Invalid or expired platform token'))).toBe(true)
    expect(isSessionEnded({ response: { status: 500 } })).toBe(false)
  })

  it('assumes a scope is present only when the session does not list its scopes', () => {
    expect(sessionHasScope({ scopes: ['platform:read'] }, 'platform:debug')).toBe(false)
    expect(sessionHasScope({ scopes: ['platform:debug'] }, 'platform:debug')).toBe(true)
    expect(sessionHasScope({ scopes: null }, 'platform:debug')).toBe(true)
  })
})

describe('formatRelative', () => {
  const now = Date.parse('2026-09-23T12:00:00Z')
  it('describes past and future times coarsely', () => {
    expect(formatRelative('2026-09-23T12:23:00Z', now)).toBe('in 23 min')
    expect(formatRelative('2026-09-23T09:00:00Z', now)).toBe('3 h ago')
    expect(formatRelative('2026-09-20T12:00:00Z', now)).toBe('3 days ago')
    expect(formatRelative(null, now)).toBe('')
  })
})

describe('summarizeAuditMetadata', () => {
  it('turns recorded changes into from → to lines', () => {
    expect(summarizeAuditMetadata({
      metadata: { tenant_id: 't1', changes: { billing_tier: { from: 'payg', to: 'flat' }, enabled_modules: { from: null, to: ['intake'] } } },
    })).toEqual(['billing_tier: payg → flat', 'enabled_modules: — → intake'])
  })

  it('shows recorded timestamps as local date-times, not raw ISO strings', () => {
    const [line] = summarizeAuditMetadata({ metadata: { expires_at: '2026-09-23T19:40:30.029125+00:00' } })
    expect(line).toMatch(/^expires_at: /)
    expect(line).not.toContain('T19:40')
  })

  it('lists plain metadata without the tenant id already on screen', () => {
    expect(summarizeAuditMetadata({ metadata: { tenant_id: 't1', severity: 'S1', escalation_level: 2 } }))
      .toEqual(['severity: S1', 'escalation_level: 2'])
  })
})
