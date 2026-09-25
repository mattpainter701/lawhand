import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFillViewPreference, writeFillViewPreference } from './fillViewPreference'

afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe('fill view preference', () => {
  it('defaults to the document and remembers a valid choice', () => {
    expect(readFillViewPreference()).toBe('document')
    writeFillViewPreference('questions')
    expect(readFillViewPreference()).toBe('questions')
    writeFillViewPreference('final')
    expect(readFillViewPreference()).toBe('questions')
  })

  it('ignores unknown stored values and unavailable storage', () => {
    localStorage.setItem('lawhand.fill.view', 'sideways')
    expect(readFillViewPreference()).toBe('document')
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(readFillViewPreference()).toBe('document')
    expect(() => writeFillViewPreference('questions')).not.toThrow()
  })
})
