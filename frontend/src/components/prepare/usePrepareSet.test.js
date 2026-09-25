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

  it('maps a state code suggestion to the selectable state option', async () => {
    api.getTemplateSetInterview.mockResolvedValue({
      ...interview(),
      questions: [{ ...interview().questions[0], value_kind: 'choice', options: ['North Dakota', 'Minnesota'], suggested_value: 'ND' }],
    })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.answers['manual:template-1:name']).toBe('North Dakota'))
    expect(result.current.progress.completed).toBe(1)
    expect(result.current.interview.questions[0].suggested_value).toBe('North Dakota')
  })

  it('matches a case-insensitive state name to an option export value', async () => {
    api.getTemplateSetInterview.mockResolvedValue({
      ...interview(),
      questions: [{ ...interview().questions[0], value_kind: 'choice', options: [{ value: 'ND', label: 'North Dakota' }, { value: 'MN', label: 'Minnesota' }], suggested_value: 'north dakota' }],
    })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.answers['manual:template-1:name']).toBe('ND'))
    expect(result.current.interview.questions[0].suggested_value).toBe('ND')
  })

  it('leaves an unrecognized choice suggestion missing', async () => {
    api.getTemplateSetInterview.mockResolvedValue({
      ...interview(),
      questions: [{ ...interview().questions[0], value_kind: 'choice', options: ['North Dakota', 'Minnesota'], suggested_value: 'Colorado' }],
    })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    expect(result.current.answers['manual:template-1:name']).toBeUndefined()
    expect(result.current.progress.completed).toBe(0)
    expect(result.current.progress.remaining.map((row) => row.name)).toContain('manual:template-1:name')
    expect(result.current.interview.questions[0].suggested_value).toBeNull()
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

  it('autosaves an edit made while the earlier write finishes before its debounce', async () => {
    let resolveFirst
    api.writeFillSession.mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'old'))
    act(() => { result.current.retrySave() })
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(1))
    act(() => result.current.setAnswer('manual:template-1:name', 'new'))
    await act(async () => resolveFirst({ id: 'session-1', status: 'open', answers: { 'manual:template-1:name': 'old' }, verified: [], members: [] }))
    expect(result.current.persistStatus).toBe('pending')
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(2), { timeout: 1500 })
    expect(api.writeFillSession.mock.calls[1][0].answers).toEqual({ 'manual:template-1:name': 'new' })
    await waitFor(() => expect(result.current.persistStatus).toBe('saved'))
  })

  it('keeps a failed queued snapshot dirty so Retry can persist it', async () => {
    let resolveFirst
    api.writeFillSession
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockRejectedValueOnce(new Error('second write failed'))
      .mockResolvedValue({ id: 'session-1', status: 'open', answers: { 'manual:template-1:name': 'new' }, verified: [], members: [] })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'old'))
    act(() => { result.current.retrySave() })
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(1))
    act(() => result.current.setAnswer('manual:template-1:name', 'new'))
    act(() => { result.current.retrySave() })
    act(() => resolveFirst({ id: 'session-1', status: 'open', answers: { 'manual:template-1:name': 'old' }, verified: [], members: [] }))
    await waitFor(() => expect(result.current.persistStatus).toBe('error'))
    act(() => { result.current.retrySave() })
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(3))
    expect(result.current.persistStatus).toBe('saved')
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
    await act(async () => { await result.current.saveAll() })
    expect(api.renderFillSession).not.toHaveBeenCalled()
    expect(result.current.error).toMatch(/offline|could not be queued|saved/)
  })

  it('flushes a pending answer when the packet unmounts before the autosave timer', async () => {
    const { result, unmount } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'Ada'))
    expect(api.writeFillSession).not.toHaveBeenCalled()
    act(() => unmount())
    await waitFor(() => expect(api.writeFillSession).toHaveBeenCalledTimes(1))
    expect(api.writeFillSession.mock.calls[0][0].answers).toEqual({ 'manual:template-1:name': 'Ada' })
  })

  it.each(['saving', 'saved'])('recovers a lost queue response from durable %s state without submitting again', async (status) => {
    api.getTemplateSetDocumentsVariables.mockResolvedValue({ documents: { [template.id]: { name: 'Ada' } } })
    api.renderTemplate.mockResolvedValue({ rendered: 'Ada' })
    const recovered = { id: 'session-1', status, members: [{ template_id: template.id, status: status === 'saved' ? 'saved' : 'queued', ...(status === 'saved' ? { matter_document_id: 'document-1', output_format: 'markdown' } : {}) }] }
    api.getFillSession.mockResolvedValueOnce({ id: 'session-1', status: 'open', members: [] }).mockResolvedValue(recovered)
    api.renderFillSession.mockRejectedValue(new Error('Response lost'))
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'Ada'))
    await act(async () => { await result.current.generateAll() })
    await act(async () => { await result.current.saveAll() })
    expect(result.current.session.status).toBe(status)
    expect(result.current.error).toBe('')
    expect(result.current.saving).toBe(status === 'saving')
    expect(result.current.allSaved).toBe(status === 'saved')
    expect(api.writeFillSession.mock.invocationCallOrder[0]).toBeLessThan(api.renderFillSession.mock.invocationCallOrder[0])
    await act(async () => { await result.current.saveAll() })
    expect(api.renderFillSession).toHaveBeenCalledTimes(1)
    expect(api.renderTemplate.mock.calls.every(([, payload]) => !payload.matter_id)).toBe(true)
  })

  it('reconciles an already completed server save before queueing a retry', async () => {
    api.getTemplateSetDocumentsVariables.mockResolvedValue({ documents: { [template.id]: { name: 'Ada' } } })
    api.renderTemplate.mockResolvedValue({ rendered: 'Ada' })
    api.getFillSession.mockResolvedValue({ id: 'session-1', status: 'saved', members: [{ template_id: template.id, status: 'saved', matter_document_id: 'document-1', output_format: 'markdown' }] })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'Ada'))
    await act(async () => { await result.current.generateAll() })
    await act(async () => { await result.current.saveAll() })
    expect(api.renderFillSession).not.toHaveBeenCalled()
    expect(result.current.allSaved).toBe(true)
    expect(result.current.savedDocuments[0].matter_document_id).toBe('document-1')
  })

  it('creates a session when explicitly saving a reviewed packet with no answers', async () => {
    api.getTemplateSetDocumentsVariables.mockResolvedValue({ documents: { [template.id]: {} } })
    api.renderTemplate.mockResolvedValue({ rendered: 'Blank optional form' })
    api.getFillSession.mockResolvedValue({ id: 'session-1', status: 'open', members: [] })
    api.renderFillSession.mockResolvedValue({ id: 'session-1', status: 'saving', members: [{ template_id: template.id, status: 'queued' }] })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    await act(async () => { await result.current.generateAll() })
    await act(async () => { await result.current.saveAll() })
    expect(api.writeFillSession).toHaveBeenCalledWith(expect.objectContaining({ set_id: SET, answers: {} }))
    expect(api.renderFillSession).toHaveBeenCalledWith('session-1', { members: [{ template_id: template.id, variables: {}, preview_id: null, convert_to_pdf: false, output_format: 'markdown' }] })
  })

  it('warns before leaving with an unsaved packet answer', async () => {
    const { result, unmount } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.interview).toBeTruthy())
    act(() => result.current.setAnswer('manual:template-1:name', 'Ada'))
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    act(() => unmount())
  })

  it('previews one member once its own required answers are in, while another member still waits', async () => {
    const other = { id: 'template-2', title: 'Order', format: 'markdown', variable_schema: { fields: [{ name: 'hearing', required: true }] } }
    api.getTemplateSet.mockResolvedValue({ id: SET, title: 'Packet', items: [
      { template_id: template.id, title: template.title, position: 0, resolved_version_no: 1 },
      { template_id: other.id, title: other.title, position: 1, resolved_version_no: 1 },
    ] })
    api.getTemplate.mockImplementation(async (id) => (id === other.id ? other : template))
    api.getTemplateSetInterview.mockResolvedValue({ set_id: SET, unavailable: [], questions: [
      { ...interview().questions[0], required: true },
      { key: 'manual:template-2:hearing', label: 'Hearing', value_kind: 'text', required: true, card: '', appears_in: [{ template_id: other.id, template_title: other.title, field_name: 'hearing' }] },
    ] })
    api.getTemplateSetDocumentsVariables.mockResolvedValue({ documents: { [template.id]: { name: 'Ada' }, [other.id]: {} } })
    api.renderTemplate.mockResolvedValue({ rendered: 'Ada' })
    const { result } = renderHook(() => usePrepareSet({ setId: SET, initialMatterId: MATTER_A }))
    await waitFor(() => expect(result.current.questions).toHaveLength(2))
    expect(result.current.requiredMissingFor([template.id])).toEqual(['manual:template-1:name'])
    expect(result.current.requiredMissingFor()).toEqual(['manual:template-1:name', 'manual:template-2:hearing'])
    await act(async () => { await result.current.generateAll([template.id]) })
    expect(result.current.error).toMatch(/Answer 1 required question before generating/)
    act(() => result.current.setAnswer('manual:template-1:name', 'Ada'))
    expect(result.current.requiredMissingFor([template.id])).toEqual([])
    await act(async () => { await result.current.generateAll([template.id]) })
    expect(api.renderTemplate).toHaveBeenCalledTimes(1)
    expect(api.renderTemplate).toHaveBeenCalledWith(template.id, { variables: { name: 'Ada' } })
    expect(result.current.previewOf({ template_id: template.id }).status).toBe('ready')
    expect(result.current.previewOf({ template_id: other.id }).status).toBe('idle')
    // The whole packet still waits on the other document's answer.
    await act(async () => { await result.current.generateAll() })
    expect(result.current.error).toMatch(/Answer 1 required question before generating/)
  })
})
