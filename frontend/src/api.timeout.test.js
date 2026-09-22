import { describe, expect, it } from 'vitest'
import api, { isLongRunningPath, LONG_REQUEST_TIMEOUT_MS, REQUEST_TIMEOUT_MS } from './api'

describe('request deadlines', () => {
  it('keeps bounded list and query calls on the short deadline', () => {
    for (const path of ['/tasks', '/matters', '/clients', '/auth/me', '/billing/status']) {
      expect(isLongRunningPath(path)).toBe(false)
    }
  })

  it('gives the gateway deadline to routes nginx allows 300s', () => {
    // nginx/snippets/api_proxy.conf sets proxy_read_timeout 300s; aborting
    // these client-side would leave the server working and invite a retry that
    // duplicates the effect.
    for (const path of [
      '/documents/upload',
      '/matters/abc/documents/upload',
      '/imports/tabs3/upload',
      '/imports/run-1/reconcile',
      '/templates/t1/render-file',
      '/templates/t1/preview-render',
      '/templates/t1/render',
      '/templates/intake/analyze',
      '/billing/invoices/i1/export',
      '/intake/dashboard/calls/export',
      '/matters/m1/documents/d1/revisions',
      '/matters/m1/documents/d1/facts/from-form',
    ]) {
      expect(isLongRunningPath(path)).toBe(true)
    }
  })

  it('does not match a path that merely contains a keyword mid-segment', () => {
    expect(isLongRunningPath('/exports-summary')).toBe(false)
    expect(isLongRunningPath('/uploaded-files')).toBe(false)
  })

  it('tolerates a missing url', () => {
    expect(isLongRunningPath(undefined)).toBe(false)
    expect(isLongRunningPath(null)).toBe(false)
  })

  it('leaves the long deadline well clear of the short one', () => {
    expect(LONG_REQUEST_TIMEOUT_MS).toBeGreaterThan(REQUEST_TIMEOUT_MS)
  })

  it('applies the long deadline to an actual printed-form request', async () => {
    const previousAdapter = api.defaults.adapter
    let requestConfig
    api.defaults.adapter = async (config) => {
      requestConfig = config
      return { data: { candidates: [] }, status: 200, statusText: 'OK', headers: {}, config, request: {} }
    }
    try {
      await api.post('/matters/m1/documents/d1/facts/from-form', { template_id: 't1' })
    } finally {
      api.defaults.adapter = previousAdapter
    }
    expect(requestConfig.timeout).toBe(LONG_REQUEST_TIMEOUT_MS)
  })
})
