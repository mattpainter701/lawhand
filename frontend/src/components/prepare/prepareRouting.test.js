import { describe, expect, it } from 'vitest'
import { buildPrepareTarget, buildSavedTarget, readPrepareQuery, safeReturnPath } from './prepareRouting'

const T = '11111111-1111-4111-8111-111111111111'
const M = '22222222-2222-4222-8222-222222222222'
const F = '33333333-3333-4333-8333-333333333333'
const D = '44444444-4444-4444-8444-444444444444'

describe('prepare route addresses', () => {
  it('builds a link from ids and a same-app return path', () => {
    const target = buildPrepareTarget({ templateId: T.toUpperCase(), matterId: M, folderId: F, returnTo: `/matters/${M}?tab=documents` })
    expect(target.pathname).toBe('/templates/prepare')
    expect(readPrepareQuery(target.search)).toEqual({ templateId: T, setId: null, matterId: M, folderId: F, returnTo: `/matters/${M}?tab=documents` })
    expect(target.url).toBe(`/templates/prepare${target.search}`)
  })

  it('drops anything that is not an id and never carries an off-site return', () => {
    const target = buildPrepareTarget({ templateId: 'not-an-id', matterId: '<script>', returnTo: 'https://evil.example/x' })
    expect(target.url).toBe('/templates/prepare')
    expect(safeReturnPath('//evil.example')).toBe('')
    expect(safeReturnPath('/\\evil.example')).toBe('')
    expect(safeReturnPath('\\\\evil.example')).toBe('')
    expect(safeReturnPath('/matters/x\\..\\evil')).toBe('')
    expect(safeReturnPath('/matters/x')).toBe('/matters/x')
  })

  it('prefers a template over a set when both are given', () => {
    expect(readPrepareQuery(buildPrepareTarget({ templateId: T, setId: M }).search).setId).toBeNull()
    expect(readPrepareQuery(buildPrepareTarget({ setId: M }).search).setId).toBe(M)
  })

  it('lands a saved document on the matter documents tab with it opened', () => {
    expect(buildSavedTarget({ matterId: M, documentId: D })).toBe(`/matters/${M}?tab=documents&document=${D}`)
    expect(buildSavedTarget({ matterId: M, documentId: D, returnTo: `/matters/${M}?tab=probate` })).toBe(`/matters/${M}?tab=probate&document=${D}`)
    expect(buildSavedTarget({ matterId: M, documentId: 'nope' })).toBe(`/matters/${M}?tab=documents`)
  })
})
