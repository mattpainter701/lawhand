import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearMatterListMemory,
  readListScroll,
  readRememberedListUrl,
  rememberListScroll,
  rememberListUrl,
} from './matterListMemory'

beforeEach(() => window.sessionStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('matter list memory', () => {
  it('round-trips the last list URL', () => {
    rememberListUrl('/matters?status=open&q=acme')
    expect(readRememberedListUrl()).toBe('/matters?status=open&q=acme')
  })

  it('refuses to remember a matter detail URL as the list', () => {
    rememberListUrl('/matters/1a2b3c')
    expect(readRememberedListUrl()).toBe('')
  })

  it('ignores non-list and off-origin targets', () => {
    rememberListUrl('https://evil.example/matters')
    rememberListUrl('/clients')
    expect(readRememberedListUrl()).toBe('')
  })

  it('keeps a scroll offset per list URL', () => {
    rememberListScroll('/matters?status=open', 421.6)
    expect(readListScroll('/matters?status=open')).toBe(422)
    expect(readListScroll('/matters?status=closed')).toBeNull()
  })

  it('clamps a negative offset and drops non-finite values', () => {
    rememberListScroll('/matters', -30)
    expect(readListScroll('/matters')).toBe(0)
    rememberListScroll('/matters', Number.NaN)
    expect(readListScroll('/matters')).toBe(0)
  })

  it('degrades quietly when session storage is unavailable', () => {
    vi.spyOn(window, 'sessionStorage', 'get').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(() => rememberListUrl('/matters')).not.toThrow()
    expect(readRememberedListUrl()).toBe('')
    expect(() => rememberListScroll('/matters', 10)).not.toThrow()
    expect(readListScroll('/matters')).toBeNull()
  })

  it('forgets the last view and every scroll offset on sign-out, and nothing else', () => {
    rememberListUrl('/matters?q=acme')
    rememberListScroll('/matters?q=acme', 300)
    rememberListScroll('/matters', 120)
    window.sessionStorage.setItem('unrelated', 'kept')

    clearMatterListMemory()

    expect(readRememberedListUrl()).toBe('')
    expect(readListScroll('/matters?q=acme')).toBeNull()
    expect(readListScroll('/matters')).toBeNull()
    expect(window.sessionStorage.getItem('unrelated')).toBe('kept')
  })
})
