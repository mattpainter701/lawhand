import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PrepareSetBody from './PrepareSetBody'
import PdfPreviewDialog from '../templates/PdfPreviewDialog'

vi.mock('./MatterPicker', () => ({ default: () => null }))
vi.mock('../templates/TemplateFillProgress', () => ({ default: () => null }))
vi.mock('./SendStep', () => ({ default: () => null }))
vi.mock('./StorageReadinessNotice', () => ({ default: () => null }))
vi.mock('./prepareRouting', () => ({ buildSavedTarget: () => '/matters/m' }))
vi.mock('../templates/PdfPreviewDialog', () => ({ default: vi.fn(({ title, onClose }) => <div role="dialog" aria-label={title}><button onClick={onClose}>Close PDF</button></div>) }))

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks() })

const prep = {
  questions: [{
    key: 'manual:markdown:venue', label: 'Venue', value_kind: 'choice', options: ['Court', 'Remote'],
    required: true, card: '', appears_in: [{ template_id: 'md', template_title: 'Notice', field_name: 'venue' }],
  }],
  unavailable: [],
  availableMembers: [{ template_id: 'md', title: 'Notice', output: { format: 'markdown', file: false }, resolved_version_no: 1 }],
  error: '', matterId: 'm', selectMatter: vi.fn(), answers: {}, setAnswer: vi.fn(), setReviewedValues: vi.fn(),
  toggleVerified: vi.fn(), fieldFilter: 'all', setFieldFilter: vi.fn(), filteredKeys: ['manual:markdown:venue'],
  nextField: vi.fn(), progress: { rows: [{ name: 'manual:markdown:venue', present: false, documents: 1 }], remaining: [], review: [], completed: 0, total: 1 },
  requiredUnresolvedNames: [], smartFillState: 'ready', smartFillMessage: '', refresh: vi.fn(),
  previewOf: () => ({ status: 'ready', rendered: 'Ada Lovelace — Remote' }), saveOf: () => null,
  generating: false, saving: false, generateAll: vi.fn(), saveAll: vi.fn(), allPreviewed: true, allSaved: false,
  sendable: [], session: null, background: null, saveAllInBackground: vi.fn(),
}

describe('PrepareSetBody packet controls', () => {
  it('keeps choice fields selectable and exposes Markdown output for review', () => {
    render(<PrepareSetBody prep={prep} matters={[]} matterLoading={false} fixedMatterId="m" returnTo="/templates/prepare" />)

    expect(screen.getByRole('combobox', { name: /Venue/ })).toHaveDisplayValue('Choose Venue')
    expect(screen.getByRole('option', { name: 'Court' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Remote' })).toBeInTheDocument()
    expect(screen.getByText('Review Markdown preview')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace — Remote')).toBeInTheDocument()
  })

  it('treats checking a suggested answer as reviewed and clears it when edited', () => {
    const setReviewedValues = vi.fn()
    const toggleVerified = vi.fn()
    const packet = {
      ...prep,
      answers: { 'manual:markdown:venue': 'Remote' },
      setReviewedValues,
      toggleVerified,
      progress: {
        rows: [{ name: 'manual:markdown:venue', present: true, documents: 1, source: { suggested_value: 'Remote' }, needsReview: true, verified: false }],
        remaining: [], review: [{ name: 'manual:markdown:venue' }], unverified: [{ name: 'manual:markdown:venue' }], completed: 1, total: 1, verified: 0,
      },
    }
    const view = render(<PrepareSetBody prep={packet} matters={[]} fixedMatterId="m" />)
    const checkbox = screen.getByRole('checkbox', { name: 'Verified: Venue' })
    fireEvent.click(checkbox)
    expect(toggleVerified).toHaveBeenCalledWith('manual:markdown:venue')
    expect(setReviewedValues.mock.calls.at(-1)[0]({})).toEqual({ 'manual:markdown:venue': 'Remote' })

    fireEvent.change(screen.getByRole('combobox', { name: /Venue/ }), { target: { value: 'Court' } })
    expect(setReviewedValues.mock.calls.at(-1)[0]({ 'manual:markdown:venue': 'Remote' })).toEqual({ 'manual:markdown:venue': undefined })
    view.unmount()
  })

  it('opens the exact generated PDF in the page and closes without a popup or save', () => {
    const popup = vi.spyOn(window, 'open').mockReturnValue(null)
    const blob = new Blob(['generated PDF'], { type: 'application/pdf' })
    const packet = { ...prep, availableMembers: [{ template_id: 'pdf', title: 'Cover sheet', output: { format: 'pdf', file: true } }], previewOf: () => ({ status: 'ready', blob, filename: 'cover.pdf' }) }
    render(<PrepareSetBody prep={packet} matters={[]} fixedMatterId="m" />)
    fireEvent.click(screen.getByRole('button', { name: 'Open preview' }))
    expect(screen.getByRole('dialog', { name: 'Cover sheet' })).toBeVisible()
    expect(PdfPreviewDialog.mock.calls.at(-1)[0]).toMatchObject({ source: blob, title: 'Cover sheet', filename: 'cover.pdf' })
    expect(popup).not.toHaveBeenCalled()
    expect(prep.saveAll).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Close PDF' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('removes the open preview when answers invalidate or replace its generated bytes', () => {
    const blob = new Blob(['first'])
    const member = { template_id: 'pdf', title: 'Cover sheet', output: { format: 'pdf', file: true } }
    const packet = { ...prep, availableMembers: [member], previewOf: () => ({ status: 'ready', blob }) }
    const view = render(<PrepareSetBody prep={packet} matters={[]} fixedMatterId="m" />)
    fireEvent.click(screen.getByRole('button', { name: 'Open preview' }))
    view.rerender(<PrepareSetBody prep={{ ...packet, previewOf: () => ({ status: 'idle' }) }} matters={[]} fixedMatterId="m" />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    view.rerender(<PrepareSetBody prep={{ ...packet, previewOf: () => ({ status: 'ready', blob: new Blob(['replacement']) }) }} matters={[]} fixedMatterId="m" />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('offers an explicit Word download and releases its URL after preview invalidation', () => {
    const blob = new Blob(['Word bytes'])
    const create = vi.fn(() => 'blob:word-preview')
    const revoke = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke })
    const packet = { ...prep, availableMembers: [{ template_id: 'word', title: 'Letter', output: { format: 'docx', file: true } }], previewOf: () => ({ status: 'ready', blob, filename: 'letter.docx' }) }
    const view = render(<PrepareSetBody prep={packet} matters={[]} fixedMatterId="m" />)
    const link = screen.getByRole('link', { name: 'Download Word preview' })
    expect(link).toHaveAttribute('href', 'blob:word-preview')
    expect(link).toHaveAttribute('download', 'letter.docx')
    expect(create).toHaveBeenCalledWith(blob)
    expect(screen.queryByRole('button', { name: 'Open preview' })).not.toBeInTheDocument()
    view.rerender(<PrepareSetBody prep={{ ...packet, previewOf: () => ({ status: 'idle' }) }} matters={[]} fixedMatterId="m" />)
    expect(screen.queryByRole('link', { name: 'Download Word preview' })).not.toBeInTheDocument()
    expect(revoke).toHaveBeenCalledWith('blob:word-preview')
  })
})
