import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import usePrepareSet from './usePrepareSet'

const api = vi.hoisted(() => ({
  getFillSession: vi.fn(), getTemplate: vi.fn(), getTemplateSet: vi.fn(),
  getTemplateSetInterview: vi.fn(), getTemplateSetDocumentsVariables: vi.fn(),
  renderTemplate: vi.fn(), renderTemplateFile: vi.fn(),
  renderFillSession: vi.fn(), writeFillSession: vi.fn(),
}))
vi.mock('../../api', () => api)

const SET = 'set-1'
const MATTER_A = 'matter-a'
const MATTER_B = 'matter-b'
const template = { id: 'template-1', title: 'Notice', format: 'markdown', variable_schema: { fields: [{ name: 'name' }] } }
const interview = (suggested_value = null) => ({
  set_id: SET,
  questions: [{ key: 'manual:template-1:name', label: 'Name', value_kind: 'text', required: false, card: '', binding: '', shared: false, appears_in: [{ template_id: template.id, template_title: template.title, field_name: 'name', label: 'Name' }], suggested_value }],
  unavailable: [],
})

afterEach(cleanup)
beforeEach(() => {
  vi.resetAllMocks()
  api.getTemplateSet.mockResolvedValue({ id: SET, title: 'Packet', items: [{ template_id: template.id, title: template.title, position: 0, resolved_version_no: 1 }] })
  api.getTemplate.mockResolvedValue(template)
  api.getTemplateSetInterview.mockResolvedValue(interview())
  api.writeFillSession.mockResolvedValue({ id: 'session-1', status: 'open', answers: {}, verified: [], members: [] })
})

describe('usePrepareSet race handling', () => {
  it('surfaces restore failure and retries before loading the interview', async () => {
    api.getFillSession.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ id: 'session-1', set_id: SET, status: 'open', answers: { 'manual:template-1:name': 'Ada' }, verified: [], members: [], matter_id: MATTER_A })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, sessionId: 'session-1' }))
    await waitFor(() => expect(result.current.sessionRestoreError).toMatch(/offline|could not be restored/))
    expect(api.getTemplateSetInterview).not.toHaveBeenCalled()
    act(() => result.current.retrySessionRestore())
    await waitFor(() => expect(result.current.answers['manual:template-1:name']).toBe('Ada'))
    expect(api.getTemplateSetInterview).toHaveBeenCalledWith(SET, MATTER_A)
  })

  it('does not apply a restore response after the matter changes', async () => {
    let resolveRestore
    api.getFillSession.mockReturnValueOnce(new Promise(resolve => { resolveRestore = resolve }))
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A, sessionId: 'session-1' }))
    await waitFor(() => expect(api.getFillSession).toHaveBeenCalledWith('session-1'))
    act(() => result.current.selectMatter(MATTER_B))
    act(() => resolveRestore({ id: 'session-1', set_id: SET, status: 'open', matter_id: MATTER_A, answers: { 'manual:template-1:name': 'stale' }, verified: [], members: [] }))
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(result.current.matterId).toBe(MATTER_B)
    expect(result.current.answers).toEqual({})
    expect(result.current.session).toBe(null)
    expect(result.current.sessionRestored).toBe(false)
  })

  it('clears prior matter answers, verification, and previews on matter switch', async () => {
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'Ada'))
    act(() => result.current.toggleVerified('manual:template-1:name'))
    act(() => result.current.selectMatter(MATTER_B))
    expect(result.current.answers).toEqual({})
    expect(result.current.verifiedNames).toEqual({})
    expect(result.current.previews).toEqual({})
    expect(result.current.saves).toEqual({})
  })

  it('does not publish a preview that completed after an answer revision', async () => {
    let resolveFan
    api.getTemplateSetDocumentsVariables.mockReturnValueOnce(new Promise(resolve => { resolveFan = resolve }))
    api.renderTemplate.mockResolvedValue({ rendered: 'stale' })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => { result.current.generateAll() })
    await waitFor(() => expect(api.getTemplateSetDocumentsVariables).toHaveBeenCalled())
    act(() => result.current.setAnswer('manual:template-1:name', 'new value'))
    act(() => resolveFan({ documents: { [template.id]: { name: 'old value' } } }))
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.previews[template.id]?.status).toBe('idle')
    expect(api.renderTemplate).not.toHaveBeenCalled()
  })

  it('serializes answer saves and writes the latest queued snapshot', async () => {
    let resolveFirst
    api.writeFillSession.mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'old'))
    act(() => { result.current.retrySave() })
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(1))
    act(() => result.current.setAnswer('manual:template-1:name', 'new'))
    act(() => { result.current.retrySave() })
    expect(api.writeFillSession).toHaveBeenCalledTimes(1)
    act(() => resolveFirst({ id: 'session-1', status: 'open', answers: { 'manual:template-1:name': 'old' }, verified: [], members: [] }))
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(2))
    expect(api.writeFillSession.mock.calls[1][0].answers).toEqual({ 'manual:template-1:name': 'new' })
  })

  it('drains overlapping snapshots from the latest ref without writing an intermediate value', async () => {
    let resolveFirst
    api.writeFillSession.mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'first'))
    act(() => { result.current.retrySave() })
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(1))
    act(() => result.current.setAnswer('manual:template-1:name', 'second'))
    act(() => { result.current.retrySave() })
    act(() => result.current.setAnswer('manual:template-1:name', 'third'))
    act(() => { result.current.retrySave() })
    act(() => resolveFirst({ id: 'session-1', status: 'open', answers: { 'manual:template-1:name': 'first' }, verified: [], members: [] }))
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(2))
    expect(api.writeFillSession.mock.calls[1][0].answers).toEqual({ 'manual:template-1:name': 'third' })
  })

  it.each([false, true])('saves the new matter after an old in-flight write settles (failure=%s)', async (failOld) => {
    let settleOld
    api.writeFillSession.mockImplementationOnce(() => new Promise((resolve, reject) => { settleOld = failOld ? reject : resolve }))
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'Old client'))
    act(() => { result.current.retrySave() })
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(1))
    act(() => result.current.selectMatter(MATTER_B))
    await waitFor(() => expect(result.current.smartFillState).toBe('ready'))
    act(() => result.current.setAnswer('manual:template-1:name', 'New client'))
    act(() => { result.current.retrySave() })
    act(() => settleOld(failOld ? new Error('old request failed') : { id: 'old-session', status: 'open' }))
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(2))
    expect(api.writeFillSession.mock.calls[1][0]).toMatchObject({ matter_id: MATTER_B, answers: { 'manual:template-1:name': 'New client' } })
    expect(api.writeFillSession.mock.calls[1][0]).not.toHaveProperty('id')
    await waitFor(() => expect(result.current.session?.id).toBe('session-1'))
  })

  it('does not queue a packet when the latest session snapshot fails to save', async () => {
    api.getTemplateSetDocumentsVariables.mockResolvedValue({ documents: { [template.id]: { name: 'Ada' } } })
    api.renderTemplate.mockResolvedValue({ rendered: 'Ada' })
    api.writeFillSession.mockRejectedValue(new Error('offline'))
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'Ada'))
    await act(async () => { await result.current.generateAll() })
    await waitFor(() => expect(result.current.previews[template.id]?.status).toBe('ready'))
    await act(async () => { await result.current.saveAllInBackground() })
    expect(api.renderFillSession).not.toHaveBeenCalled()
    expect(result.current.error).toMatch(/offline|could not be queued|saved/)
  })
})
