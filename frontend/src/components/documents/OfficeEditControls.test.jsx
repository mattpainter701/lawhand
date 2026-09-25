import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reconcileMatterDocument, startMatterDocumentCloudEdit, uploadRevisedMatterDocument } from '../../api'
import OfficeEditControls, { isBeingEdited, officeEditState } from './OfficeEditControls'

// Opened a minute ago, so the 12-hour editing marker is live whenever the suite runs.
const RECENT = new Date(Date.now() - 60_000).toISOString()

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
const confirm = vi.hoisted(() => ({ answer: true }))

vi.mock('../../api', () => ({
  startMatterDocumentCloudEdit: vi.fn(),
  reconcileMatterDocument: vi.fn(),
  uploadRevisedMatterDocument: vi.fn(),
}))
vi.mock('../toast/useToast', () => ({ useToast: () => toast }))
vi.mock('../dialog/ConfirmProvider', () => ({ useConfirm: () => async () => confirm.answer }))

const base = {
  id: 'doc-1',
  filename: 'Engagement letter.docx',
  content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  storage_backend: 'sharepoint',
  provider_object_id: 'item-1',
  document_status: 'draft',
  storage_state: null,
}

function renderControls(doc = base, props = {}) {
  const onDocumentChange = vi.fn()
  const view = render(<OfficeEditControls matterId="m-1" doc={doc} onDocumentChange={onDocumentChange} {...props} />)
  return { onDocumentChange, ...view }
}

beforeEach(() => { confirm.answer = true })
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.restoreAllMocks() })

describe('officeEditState', () => {
  it('offers the round trip only for Word files it can safely replace', () => {
    expect(officeEditState(base)).toMatchObject({ canOpen: true, canUpload: true, suite: 'microsoft' })
    expect(officeEditState({ ...base, storage_backend: 'google_drive' }).suite).toBe('google')
    expect(officeEditState({ ...base, filename: 'a.pdf', content_type: 'application/pdf' })).toMatchObject({ canOpen: false, canUpload: false })
    expect(officeEditState({ ...base, storage_backend: 'local', provider_object_id: null })).toMatchObject({ canOpen: false, canUpload: true })
    expect(officeEditState({ ...base, document_status: 'approved' })).toMatchObject({ canOpen: false, canUpload: false, canBringBack: true })
    expect(officeEditState({ ...base, generated_artifact_revision_id: 'rev' })).toMatchObject({ canOpen: false, canUpload: false, canBringBack: false })
    expect(officeEditState({ ...base, document_category: 'assistant_revision' }).canOpen).toBe(false)
  })
})

describe('isBeingEdited', () => {
  it('shows the marker for twelve hours after opening', () => {
    const started = Date.parse('2026-09-25T08:00:00Z')
    const doc = { external_edit_started_at: '2026-09-25T08:00:00Z' }
    expect(isBeingEdited(doc, started + 60_000)).toBe(true)
    expect(isBeingEdited(doc, started + 13 * 60 * 60 * 1000)).toBe(false)
    expect(isBeingEdited({}, started)).toBe(false)
  })
})

describe('OfficeEditControls', () => {
  it('opens Word for the web in a tab opened within the click', async () => {
    const popup = { location: { href: '' }, close: vi.fn(), opener: 'x' }
    vi.spyOn(window, 'open').mockReturnValue(popup)
    const updated = { ...base, external_edit_started_at: RECENT, external_edit_app: 'word_web', external_edit_started_by_name: 'Ada Lovelace' }
    startMatterDocumentCloudEdit.mockResolvedValue({ document: updated, links: { word_web: 'https://firm.sharepoint.com/doc' }, app: 'word_web' })
    const { onDocumentChange } = renderControls()
    fireEvent.click(screen.getByRole('button', { name: 'Open Engagement letter.docx in Word' }))
    expect(window.open).toHaveBeenCalledWith('', '_blank')
    await waitFor(() => expect(popup.location.href).toBe('https://firm.sharepoint.com/doc'))
    expect(popup.opener).toBeNull()
    expect(startMatterDocumentCloudEdit).toHaveBeenCalledWith('m-1', 'doc-1', 'word_web')
    expect(onDocumentChange).toHaveBeenCalledWith(updated)
  })

  it('opens Google Docs for a Drive file and shows no Word app button', async () => {
    const popup = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(popup)
    startMatterDocumentCloudEdit.mockResolvedValue({ document: base, links: { google_docs: 'https://docs.google.com/document/d/1/edit' }, app: 'google_docs' })
    renderControls({ ...base, storage_backend: 'google_drive' })
    expect(screen.queryByRole('button', { name: /Word app/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open Engagement letter.docx in Google Docs' }))
    await waitFor(() => expect(popup.location.href).toBe('https://docs.google.com/document/d/1/edit'))
  })

  it('closes the waiting tab and explains when opening fails', async () => {
    const popup = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(popup)
    startMatterDocumentCloudEdit.mockRejectedValue({ response: { data: { detail: { code: 'reconnect_required', message: 'Reconnect Microsoft 365.' } } } })
    renderControls()
    fireEvent.click(screen.getByRole('button', { name: 'Open Engagement letter.docx in Word' }))
    await waitFor(() => expect(popup.close).toHaveBeenCalled())
    expect(toast.error).toHaveBeenCalledWith('Could not open the document', { message: 'Reconnect Microsoft 365.' })
  })

  it('falls back to a new tab when the browser blocked the early one', async () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    startMatterDocumentCloudEdit.mockResolvedValue({ document: base, links: { word_web: 'https://firm.sharepoint.com/doc' }, app: 'word_web' })
    renderControls()
    fireEvent.click(screen.getByRole('button', { name: 'Open Engagement letter.docx in Word' }))
    await waitFor(() => expect(openSpy).toHaveBeenLastCalledWith('https://firm.sharepoint.com/doc', '_blank', 'noopener,noreferrer'))
  })

  it('shows who is editing and brings the changes back on request', async () => {
    const editing = { ...base, external_edit_started_at: RECENT, external_edit_app: 'word_desktop', external_edit_started_by_name: 'Ada Lovelace' }
    reconcileMatterDocument.mockResolvedValue({ document: base, outcome: 'adopted', message: 'The edits are now this document\'s current version.' })
    const { onDocumentChange } = renderControls(editing)
    expect(screen.getByRole('status')).toHaveTextContent(/Being edited in the Word app by Ada Lovelace since/)
    fireEvent.click(screen.getByRole('button', { name: 'Bring back changes to Engagement letter.docx' }))
    await waitFor(() => expect(onDocumentChange).toHaveBeenCalledWith(base))
    expect(toast.success).toHaveBeenCalledWith('Edits brought back', expect.objectContaining({ message: expect.stringContaining('current version') }))
  })

  it('reports blocked and unchanged results', async () => {
    const editing = { ...base, external_edit_started_at: RECENT }
    reconcileMatterDocument.mockResolvedValueOnce({ document: base, outcome: 'blocked', message: 'The edits were not brought back.' })
    renderControls(editing)
    fireEvent.click(screen.getByRole('button', { name: /Bring back changes/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Edits were not brought back', { message: 'The edits were not brought back.' }))
    reconcileMatterDocument.mockResolvedValueOnce({ document: base, outcome: 'unchanged', message: 'No changes.' })
    fireEvent.click(screen.getByRole('button', { name: /Bring back changes/ }))
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('No changes to bring back', { message: 'No changes.' }))
    reconcileMatterDocument.mockRejectedValueOnce(new Error('network'))
    fireEvent.click(screen.getByRole('button', { name: /Bring back changes/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Could not bring back changes', { message: 'Please try again.' }))
  })

  it('offers only Bring back changes for an approved document that changed', () => {
    renderControls({ ...base, document_status: 'approved', storage_state: 'conflict', storage_error: 'Changed outside LawHand. This document is approved.' })
    expect(screen.getByRole('status')).toHaveTextContent('This document is approved.')
    expect(screen.getByRole('button', { name: /Bring back changes/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Open .* in Word/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Upload a revised version/ })).not.toBeInTheDocument()
  })

  it('renders nothing for files it cannot handle', () => {
    const { container } = renderControls({ ...base, filename: 'Scan.pdf', content_type: 'application/pdf' })
    expect(container).toBeEmptyDOMElement()
  })

  it('brings changes back quietly when the person who opened it returns', async () => {
    const popup = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(popup)
    const editing = { ...base, external_edit_started_at: RECENT, external_edit_app: 'word_web' }
    startMatterDocumentCloudEdit.mockResolvedValue({ document: editing, links: { word_web: 'https://firm.sharepoint.com/doc' }, app: 'word_web' })
    reconcileMatterDocument.mockResolvedValue({ document: base, outcome: 'unchanged', message: 'No changes.' })
    const onDocumentChange = vi.fn()
    const { rerender } = render(<OfficeEditControls matterId="m-1" doc={base} onDocumentChange={onDocumentChange} />)
    let now = 1_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    fireEvent.click(screen.getByRole('button', { name: /in Word$/ }))
    await waitFor(() => expect(onDocumentChange).toHaveBeenCalledWith(editing))
    rerender(<OfficeEditControls matterId="m-1" doc={editing} onDocumentChange={onDocumentChange} />)
    act(() => { window.dispatchEvent(new Event('focus')) })
    expect(reconcileMatterDocument).not.toHaveBeenCalled()
    now += 20_000
    act(() => { window.dispatchEvent(new Event('focus')) })
    await waitFor(() => expect(reconcileMatterDocument).toHaveBeenCalledWith('m-1', 'doc-1'))
    expect(toast.info).not.toHaveBeenCalled()
  })

  it('does not bring changes back on focus for someone else\'s edit', () => {
    renderControls({ ...base, external_edit_started_at: RECENT })
    act(() => { window.dispatchEvent(new Event('focus')) })
    expect(reconcileMatterDocument).not.toHaveBeenCalled()
  })

  it('uploads a revised version after confirmation', async () => {
    uploadRevisedMatterDocument.mockResolvedValue({ document: base, outcome: 'adopted', message: 'Saved.' })
    const { onDocumentChange } = renderControls({ ...base, storage_backend: 'local', provider_object_id: null })
    expect(screen.queryByRole('button', { name: /in Word$/ })).not.toBeInTheDocument()
    const file = new File(['docx'], 'Revised.docx')
    fireEvent.change(screen.getByTestId('revised-input-doc-1'), { target: { files: [file] } })
    await waitFor(() => expect(uploadRevisedMatterDocument).toHaveBeenCalledWith('m-1', 'doc-1', file))
    expect(onDocumentChange).toHaveBeenCalledWith(base)
    expect(toast.success).toHaveBeenCalledWith('Revised version saved', { message: 'Saved.' })
  })

  it('keeps the document when the upload is cancelled or refused', async () => {
    confirm.answer = false
    renderControls()
    const input = screen.getByTestId('revised-input-doc-1')
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.docx')] } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(uploadRevisedMatterDocument).not.toHaveBeenCalled()
    confirm.answer = true
    uploadRevisedMatterDocument.mockRejectedValue({ response: { data: { detail: { code: 'changed_in_office', message: 'Bring back those changes first.' } } } })
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.docx')] } })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Revised version was not saved', { message: 'Bring back those changes first.' }))
    uploadRevisedMatterDocument.mockResolvedValue({ document: base, outcome: 'unchanged', message: 'Identical.' })
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.docx')] } })
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('Nothing changed', { message: 'Identical.' }))
  })

  it('opens the Word desktop app through the Office link', async () => {
    const assign = vi.fn()
    const original = window.location
    Object.defineProperty(window, 'location', { configurable: true, value: { set href(value) { assign(value) } } })
    try {
      startMatterDocumentCloudEdit.mockResolvedValue({ document: base, links: { word_web: 'https://a', word_desktop: 'ms-word:ofe|u|https://firm.sharepoint.com/a.docx' }, app: 'word_desktop' })
      const openSpy = vi.spyOn(window, 'open')
      renderControls()
      fireEvent.click(screen.getByRole('button', { name: 'Open Engagement letter.docx in the Word app' }))
      await waitFor(() => expect(assign).toHaveBeenCalledWith('ms-word:ofe|u|https://firm.sharepoint.com/a.docx'))
      expect(openSpy).not.toHaveBeenCalled()
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: original })
    }
  })
})
