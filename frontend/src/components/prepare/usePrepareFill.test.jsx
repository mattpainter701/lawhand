import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import usePrepareFill from './usePrepareFill'
import { discoverTemplateVariables, renderTemplate, renderTemplateFile } from '../../api'

vi.mock('../../api', () => ({
  discoverTemplateVariables: vi.fn(),
  renderTemplate: vi.fn(),
  renderTemplateFile: vi.fn(),
}))

const pdfTemplate = (active = true) => ({
  id: 'template-1',
  title: 'Matter form',
  format: 'pdf',
  is_active: active,
  published_version_no: 1,
  variable_schema: { fields: [{ name: 'client_name', label: 'Client name', field_type: 'text', required: true }] },
})
const previewResult = (id = 'preview-1') => ({
  blob: new Blob(['%PDF']),
  filename: 'matter-form.pdf',
  previewId: id,
  previewPurpose: 'generation',
})

beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:preview'), revokeObjectURL: vi.fn() })
  discoverTemplateVariables.mockResolvedValue({ variables: [] })
  renderTemplateFile.mockResolvedValue(previewResult())
  renderTemplate.mockResolvedValue({ matter_document_id: 'document-1' })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

const renderFill = (options = {}) => {
  const template = options.template || pdfTemplate()
  const hookOptions = { ...options, template, initialMatterId: options.initialMatterId || 'matter-1' }
  return renderHook(() => usePrepareFill(hookOptions))
}
const pause = (milliseconds) => act(async () => { await vi.advanceTimersByTimeAsync(milliseconds) })

describe('usePrepareFill automatic fill and preview', () => {
  it('waits for matter prefill before rendering the automatic PDF preview', async () => {
    discoverTemplateVariables.mockResolvedValueOnce({ variables: [{ variable: 'client_name', suggested_value: 'Ada', source_type: 'matter' }] })
    const { result } = renderFill()

    await pause(0)
    expect(discoverTemplateVariables).toHaveBeenCalledTimes(1)
    expect(renderTemplateFile).not.toHaveBeenCalled()
    await pause(700)
    expect(renderTemplateFile).toHaveBeenCalledWith('template-1', expect.objectContaining({
      variables: { client_name: 'Ada' }, matter_id: 'matter-1', preview_purpose: 'generation',
    }))
    expect(renderTemplate).not.toHaveBeenCalled()
    expect(result.current.previewId).toBe('preview-1')
  })

  it('does not smart-fill or auto-preview while restoring a draft', async () => {
    renderFill({ autoFillEnabled: false })
    await pause(700)
    expect(discoverTemplateVariables).not.toHaveBeenCalled()
    expect(renderTemplateFile).not.toHaveBeenCalled()
    expect(renderTemplate).not.toHaveBeenCalled()
  })

  it('debounces rapid edits into one latest-value preview', async () => {
    const { result } = renderFill()
    await pause(0)
    expect(discoverTemplateVariables).toHaveBeenCalledTimes(1)
    await pause(700)
    expect(renderTemplateFile).toHaveBeenCalledTimes(1)
    renderTemplateFile.mockClear()

    act(() => {
      result.current.setVariable('client_name', 'A')
      result.current.setVariable('client_name', 'Ada')
      result.current.setVariable('client_name', 'Ada Lovelace')
    })
    expect(result.current.filePreview).not.toBeNull()
    expect(result.current.previewId).toBe('')
    await pause(600)
    expect(renderTemplateFile).not.toHaveBeenCalled()
    await pause(100)
    expect(renderTemplateFile).toHaveBeenCalledTimes(1)
    expect(renderTemplateFile).toHaveBeenCalledWith('template-1', expect.objectContaining({ variables: { client_name: 'Ada Lovelace' } }))
  })

  it('discards an in-flight preview and serializes the latest edit', async () => {
    let resolveFirst
    renderTemplateFile.mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    const { result } = renderFill()
    await pause(0)
    await pause(700)
    expect(renderTemplateFile).toHaveBeenCalledTimes(1)
    act(() => result.current.setVariable('client_name', 'Latest'))
    await pause(1400)
    expect(renderTemplateFile).toHaveBeenCalledTimes(1)
    await act(async () => { resolveFirst(previewResult('stale-preview')); await Promise.resolve() })
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview')
    expect(result.current.previewId).toBe('')
    await pause(700)
    expect(renderTemplateFile).toHaveBeenCalledTimes(2)
    expect(renderTemplateFile.mock.calls[1][1]).toEqual(expect.objectContaining({ variables: { client_name: 'Latest' } }))
    expect(result.current.previewId).toBe('preview-1')
  })

  it('stops retrying after a preview error and manual retry recovers', async () => {
    renderTemplateFile.mockRejectedValueOnce(new Error('renderer unavailable'))
    const { result } = renderFill()
    await pause(0)
    await pause(700)
    expect(result.current.previewError).toContain('renderer unavailable')
    expect(renderTemplateFile).toHaveBeenCalledTimes(1)
    await pause(700)
    expect(renderTemplateFile).toHaveBeenCalledTimes(1)
    renderTemplateFile.mockResolvedValueOnce(previewResult('recovered-preview'))
    await act(async () => { await result.current.handleRender() })
    expect(renderTemplateFile).toHaveBeenCalledTimes(2)
    expect(result.current.previewId).toBe('recovered-preview')
  })

  it('clears old matter values and output when switching matters', async () => {
    const { result } = renderFill()
    await pause(0)
    act(() => result.current.setVariable('client_name', 'Old matter'))
    act(() => result.current.setPreviewId('old-preview'))
    act(() => result.current.selectMatter('matter-2'))
    expect(result.current.matterId).toBe('matter-2')
    expect(result.current.variables.client_name).toBe('')
    expect(result.current.previewId).toBe('')
    expect(result.current.filePreview).toBe(null)
  })

  it('never auto-renders inactive drafts or saves without an explicit action', async () => {
    const inactiveTemplate = pdfTemplate(false)
    const { result } = renderHook(() => usePrepareFill({ template: inactiveTemplate, initialMatterId: 'matter-1' }))
    await pause(700)
    expect(renderTemplateFile).not.toHaveBeenCalled()
    expect(renderTemplate).not.toHaveBeenCalled()
    expect(result.current.canSaveToMatter).toBe(false)
  })

  it('renders restored answers after prefill without replacing them or verifying them', async () => {
    const template = pdfTemplate()
    const view = renderHook(({ enabled }) => usePrepareFill({ template, initialMatterId: 'matter-1', autoFillEnabled: enabled }), { initialProps: { enabled: false } })
    await pause(1400)
    act(() => view.result.current.setVariables({ client_name: 'Restored answer' }))
    discoverTemplateVariables.mockResolvedValueOnce({ variables: [{ variable: 'client_name', suggested_value: 'Matter answer', source_type: 'matter' }] })
    view.rerender({ enabled: true })
    await pause(0)
    await pause(700)
    expect(renderTemplateFile).toHaveBeenCalledExactlyOnceWith('template-1', expect.objectContaining({ variables: { client_name: 'Restored answer' } }))
    expect(view.result.current.verifiedNames).toEqual({})
    expect(renderTemplate).not.toHaveBeenCalled()
  })

  it('can update a saved PDF without saving the changed answers automatically', async () => {
    const view = renderFill()
    await pause(0)
    act(() => view.result.current.setVariable('client_name', 'First answer'))
    await pause(700)
    await act(async () => view.result.current.handleSave())
    expect(view.result.current.saved).toBe(true)
    act(() => view.result.current.setVariable('client_name', 'Changed answer'))
    expect(view.result.current.matterDocId).toBe(null)
    expect(view.result.current.savedDownloadUrl).toBe('')
    await pause(700)
    expect(view.result.current.saved).toBe(false)
    expect(renderTemplateFile).toHaveBeenLastCalledWith('template-1', expect.objectContaining({ variables: { client_name: 'Changed answer' } }))
    expect(renderTemplate).toHaveBeenCalledTimes(1)
    view.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview')
  })
})
