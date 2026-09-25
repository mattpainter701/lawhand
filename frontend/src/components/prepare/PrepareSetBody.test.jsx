import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PrepareSetBody from './PrepareSetBody'
import { interviewReview } from '../templates/templateFillReview'

const api = vi.hoisted(() => ({ getTemplateSource: vi.fn() }))
vi.mock('../../api', () => api)
vi.mock('./MatterPicker', () => ({ default: () => null }))
vi.mock('../templates/TemplateFillProgress', () => ({ default: () => null }))
vi.mock('./SendStep', () => ({ default: () => null }))
vi.mock('./StorageReadinessNotice', () => ({ default: () => null }))
vi.mock('./prepareRouting', () => ({ buildSavedTarget: () => '/matters/m' }))
vi.mock('../templates/GeneratedPdfPreview', () => ({ default: vi.fn(({ title }) => <section aria-label={`Generated ${title}`} />) }))
vi.mock('../templates/TemplateFillSource', () => ({
  default: ({ fields, values, onSelectField }) => (
    <article aria-label="Page reference">
      {fields.map((field) => <button key={field.name} type="button" onClick={() => onSelectField(field.name)}>Fill {field.label}: {values[field.name] || '—'}</button>)}
    </article>
  ),
}))
const pdfState = vi.hoisted(() => ({ result: { document: null, pages: [], error: '' } }))
vi.mock('../templates/PdfDocumentCanvas', () => ({
  useTemplatePdfDocument: () => pdfState.result,
  PdfPageCanvas: ({ pageNumber }) => <canvas aria-label={`PDF page ${pageNumber}`} />,
}))

beforeEach(() => { localStorage.clear() })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); vi.useRealTimers(); localStorage.clear(); pdfState.result = { document: null, pages: [], error: '' } })

const prep = {
  questions: [{
    key: 'manual:markdown:venue', label: 'Venue', value_kind: 'choice', options: ['Court', 'Remote'],
    required: true, card: '', appears_in: [{ template_id: 'md', template_title: 'Notice', field_name: 'venue' }],
  }],
  unavailable: [],
  availableMembers: [{ template_id: 'md', title: 'Notice', output: { format: 'markdown', file: false }, resolved_version_no: 1, template: { id: 'md', format: 'markdown', body: '{{venue}}' } }],
  error: '', matterId: 'm', selectMatter: vi.fn(), answers: {}, setAnswer: vi.fn(), setReviewedValues: vi.fn(),
  toggleVerified: vi.fn(), fieldFilter: 'all', setFieldFilter: vi.fn(), filteredKeys: ['manual:markdown:venue'],
  nextField: vi.fn(), progress: { rows: [{ name: 'manual:markdown:venue', present: false, documents: 1 }], remaining: [], review: [], completed: 0, total: 1 },
  requiredUnresolvedNames: [], smartFillState: 'ready', smartFillMessage: '', refresh: vi.fn(),
  previewOf: () => ({ status: 'ready', rendered: 'Ada Lovelace — Remote' }), saveOf: () => null,
  generating: false, saving: false, generateAll: vi.fn(), saveAll: vi.fn(), allPreviewed: true, allSaved: false,
  sendable: [], session: null, background: null,
}

describe('PrepareSetBody Questions view', () => {
  beforeEach(() => { localStorage.setItem('lawhand.fill.view', 'questions') })

  it('keeps choice fields selectable and exposes Markdown output for review', () => {
    render(<PrepareSetBody prep={prep} matters={[]} matterLoading={false} fixedMatterId="m" returnTo="/templates/prepare" />)

    expect(screen.getByRole('tab', { name: 'Questions' })).toHaveAttribute('aria-selected', 'true')
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

    fireEvent.click(screen.getByRole('button', { name: 'Confirm Venue' }))
    expect(setReviewedValues.mock.calls.at(-1)[0]({})).toEqual({ 'manual:markdown:venue': 'Remote' })

    fireEvent.change(screen.getByRole('combobox', { name: /Venue/ }), { target: { value: 'Court' } })
    expect(setReviewedValues.mock.calls.at(-1)[0]({ 'manual:markdown:venue': 'Remote' })).toEqual({ 'manual:markdown:venue': undefined })
    view.unmount()
  })

  it('offers an explicit Word download and releases its URL after preview invalidation', () => {
    const blob = new Blob(['Word bytes'])
    const create = vi.fn(() => 'blob:word-preview')
    const revoke = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke })
    const packet = { ...prep, availableMembers: [{ template_id: 'word', title: 'Letter', output: { format: 'docx', file: true }, template: { id: 'word', format: 'docx' } }], previewOf: () => ({ status: 'ready', blob, filename: 'letter.docx' }) }
    const view = render(<PrepareSetBody prep={packet} matters={[]} fixedMatterId="m" />)
    const link = screen.getByRole('link', { name: 'Download Word preview' })
    expect(link).toHaveAttribute('href', 'blob:word-preview')
    expect(link).toHaveAttribute('download', 'letter.docx')
    expect(create).toHaveBeenCalledWith(blob)
    expect(screen.queryByRole('button', { name: /Open preview/ })).not.toBeInTheDocument()
    view.rerender(<PrepareSetBody prep={{ ...packet, previewOf: () => ({ status: 'idle' }) }} matters={[]} fixedMatterId="m" />)
    expect(screen.queryByRole('link', { name: 'Download Word preview' })).not.toBeInTheDocument()
    expect(revoke).toHaveBeenCalledWith('blob:word-preview')
  })
})

// A packet of a PDF engagement letter and a Markdown notice sharing the
// client's name, driven by real answer state so typing reaches every member.
const LETTER = 'letter'
const NOTICE = 'notice'
const QUESTIONS = [
  { key: 'client.full_name', label: 'Client name', value_kind: 'text', required: true, card: 'client', appears_in: [
    { template_id: LETTER, template_title: 'Engagement letter', field_name: 'client_name' },
    { template_id: NOTICE, template_title: 'Notice', field_name: 'CLIENT' },
  ] },
  { key: `manual:${LETTER}:fee`, label: 'Fee', value_kind: 'text', required: true, card: '', appears_in: [{ template_id: LETTER, template_title: 'Engagement letter', field_name: 'fee' }] },
  { key: `manual:${NOTICE}:venue`, label: 'Venue', value_kind: 'text', required: true, card: '', appears_in: [{ template_id: NOTICE, template_title: 'Notice', field_name: 'venue' }] },
]
const MEMBERS = [
  { template_id: LETTER, title: 'Engagement letter', output: { format: 'pdf', file: true }, resolved_version_no: 2, template: { id: LETTER, format: 'pdf', source_sha256: 'a', source_filename: 'letter.pdf', variable_schema: { fields: [
    { name: 'client_name', label: 'Client', page: 1, rect: [40, 700, 280, 716] },
    { name: 'fee', label: 'Fee', page: 1, rect: [40, 600, 280, 616] },
    { name: 'sig', label: 'Client signature', field_type: 'signature', signer_role: 'client', page: 1, rect: [40, 100, 240, 130] },
  ] } } },
  { template_id: NOTICE, title: 'Notice', output: { format: 'markdown', file: false }, resolved_version_no: 1, template: { id: NOTICE, format: 'markdown', body: '{{CLIENT}} at {{venue}}', variable_schema: { fields: [] } } },
]
const LOADED = { document: { numPages: 1 }, pages: [{ page: 1, width: 612, height: 792, rotation: 0 }], error: '' }

function Packet({ initial = {}, previews = {}, saves = {}, generateAll = vi.fn(), allSaved = false, onAnswer = () => {} }) {
  const [answers, setAnswers] = useState(initial)
  const progress = interviewReview(QUESTIONS, answers, {}, {})
  const packet = {
    ...prep,
    questions: QUESTIONS,
    availableMembers: MEMBERS,
    filteredKeys: QUESTIONS.map((question) => question.key),
    answers,
    setAnswer: (key, value) => { onAnswer(key, value); setAnswers((prev) => ({ ...prev, [key]: value })) },
    progress,
    requiredUnresolvedNames: progress.rows.filter((row) => row.required && !row.present).map((row) => row.name),
    previewOf: (member) => previews[member.template_id] || { status: 'idle' },
    saveOf: (member) => saves[member.template_id] || null,
    allPreviewed: false,
    allSaved,
    generateAll,
  }
  return <PrepareSetBody prep={packet} matters={[]} fixedMatterId="m" />
}

describe('PrepareSetBody Document view', () => {
  beforeEach(() => {
    pdfState.result = LOADED
    api.getTemplateSource.mockResolvedValue(new Blob(['%PDF']))
  })

  it('opens on the documents with one tab per member and its status', async () => {
    render(<Packet saves={{ [NOTICE]: { status: 'saved' } }} />)
    expect(screen.getByRole('tab', { name: 'Document' })).toHaveAttribute('aria-selected', 'true')
    const tabs = within(screen.getByRole('tablist', { name: 'Packet documents' })).getAllByRole('tab')
    expect(tabs.map((tab) => tab.getAttribute('aria-label'))).toEqual(['Engagement letter, 2 missing', 'Notice, Saved'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(api.getTemplateSource).toHaveBeenCalledWith(LETTER, 'letter.pdf'))
    expect(await screen.findByRole('group', { name: 'Page 1' })).toBeInTheDocument()
  })

  it('writes the shared answer from a box on the page, so every member using it updates', async () => {
    const onAnswer = vi.fn()
    render(<Packet onAnswer={onAnswer} />)
    const page = await screen.findByRole('group', { name: 'Page 1' })
    // Shared answers carry a link marker; document-only ones do not.
    expect(page.querySelector('[data-fill-shared="client_name"]')).not.toBeNull()
    expect(page.querySelector('[data-fill-shared="fee"]')).toBeNull()
    expect(within(page).getByRole('note', { name: 'Client signature: Signed later' })).toBeInTheDocument()
    fireEvent.change(within(page).getByLabelText('Client name'), { target: { value: 'Ada Lovelace' } })
    expect(onAnswer).toHaveBeenCalledWith('client.full_name', 'Ada Lovelace')
    // The guided bar edits the same answer and says where else it lands.
    const bar = screen.getByRole('region', { name: 'Current field' })
    expect(within(bar).getByRole('textbox', { name: /Client name/ })).toHaveValue('Ada Lovelace')
    expect(bar).toHaveTextContent('Also fills: Notice')
    fireEvent.click(screen.getByRole('tab', { name: /^Notice/ }))
    expect(screen.getByRole('button', { name: 'Fill Client name: Ada Lovelace' })).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Current field' })).getByRole('textbox', { name: /Client name/ })).toHaveValue('Ada Lovelace')
    expect(screen.getByRole('tab', { name: 'Notice, 1 missing' })).toBeInTheDocument()
  })

  it('walks "Next required" across documents, asking a shared answer once', async () => {
    render(<Packet />)
    await screen.findByRole('group', { name: 'Page 1' })
    const bar = () => screen.getByRole('region', { name: 'Current field' })
    expect(within(bar()).getByRole('textbox', { name: /Client name/ })).toBeInTheDocument()
    fireEvent.click(within(bar()).getByRole('button', { name: 'Next required (3)' }))
    expect(within(bar()).getByRole('textbox', { name: /Fee/ })).toHaveFocus()
    fireEvent.click(within(bar()).getByRole('button', { name: 'Next required (3)' }))
    // The end of the letter opens the notice at its first missing answer,
    // skipping the client's name, which the letter already asked.
    expect(screen.getByRole('tab', { name: 'Notice, 2 missing' })).toHaveAttribute('aria-selected', 'true')
    expect(within(bar()).getByRole('textbox', { name: /Venue/ })).toHaveFocus()
    fireEvent.change(within(bar()).getByRole('textbox', { name: /Venue/ }), { target: { value: 'Court' } })
    fireEvent.click(within(bar()).getByRole('button', { name: 'Next required (2)' }))
    expect(screen.getByRole('tab', { name: 'Engagement letter, 2 missing' })).toHaveAttribute('aria-selected', 'true')
    await screen.findByRole('group', { name: 'Page 1' })
    expect(within(bar()).getByRole('textbox', { name: /Client name/ })).toBeInTheDocument()
  })

  it('advances to the next box on Enter', async () => {
    render(<Packet initial={{ 'client.full_name': 'Ada' }} />)
    await screen.findByRole('group', { name: 'Page 1' })
    const bar = () => screen.getByRole('region', { name: 'Current field' })
    fireEvent.keyDown(within(bar()).getByRole('textbox', { name: /Client name/ }), { key: 'Enter' })
    expect(within(bar()).getByRole('textbox', { name: /Fee/ })).toHaveFocus()
  })

  it('previews each member in place and prepares it once its answers are in', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const generateAll = vi.fn()
    const blob = new Blob(['%PDF'])
    const view = render(<Packet generateAll={generateAll} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Preview' }))
    expect(screen.getByRole('region', { name: 'Preview of Engagement letter' })).toHaveTextContent('Answer 2 required questions in this document to preview it.')
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(generateAll).not.toHaveBeenCalled()
    view.unmount()

    render(<Packet generateAll={generateAll} initial={{ 'client.full_name': 'Ada', [`manual:${LETTER}:fee`]: '$300' }} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Preview' }))
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(generateAll).toHaveBeenCalledWith([LETTER])
    cleanup()

    render(<Packet initial={{ 'client.full_name': 'Ada', [`manual:${LETTER}:fee`]: '$300' }} previews={{ [LETTER]: { status: 'ready', blob } }} />)
    expect(screen.getByRole('tab', { name: 'Engagement letter, Previewed' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Preview' }))
    expect(screen.getByRole('region', { name: 'Generated Engagement letter' })).toBeInTheDocument()
  })

  it('offers a retry when a member preview fails', () => {
    const generateAll = vi.fn()
    render(<Packet generateAll={generateAll} previews={{ [LETTER]: { status: 'failed', error: 'Renderer busy' } }} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Preview' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Preview failed: Renderer busy')
    fireEvent.click(screen.getByRole('button', { name: 'Retry preview' }))
    expect(generateAll).toHaveBeenCalledWith([LETTER])
  })

  it('opens a ready preview from the packet list in its member tab, not a dialog', () => {
    render(<Packet previews={{ [LETTER]: { status: 'ready', blob: new Blob(['%PDF']) } }} />)
    fireEvent.click(screen.getByRole('button', { name: 'Review the packet' }))
    expect(screen.getByRole('tab', { name: 'Packet' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: 'Generate all' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open preview of Engagement letter' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Document' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('region', { name: 'Generated Engagement letter' })).toBeInTheDocument()
  })

  it('remembers Document or Questions, but not Packet', () => {
    render(<Packet />)
    fireEvent.click(screen.getByRole('tab', { name: 'Questions' }))
    expect(localStorage.getItem('lawhand.fill.view')).toBe('questions')
    expect(screen.getByText(/Appears in 2 documents/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Packet' }))
    expect(localStorage.getItem('lawhand.fill.view')).toBe('questions')
    fireEvent.click(screen.getByRole('tab', { name: 'Document' }))
    expect(localStorage.getItem('lawhand.fill.view')).toBe('document')
  })

  it('falls back to the page reference when the PDF cannot be opened', async () => {
    api.getTemplateSource.mockRejectedValue(new Error('gone'))
    render(<Packet />)
    expect(await screen.findByText(/could not be opened for typing on the page/)).toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Page reference' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Fill Fee/ }))
    expect(within(screen.getByRole('region', { name: 'Current field' })).getByRole('textbox', { name: /Fee/ })).toBeInTheDocument()
  })

  it('opens a finished packet on its Packet view', () => {
    render(<Packet allSaved saves={{ [LETTER]: { status: 'saved' }, [NOTICE]: { status: 'saved' } }} />)
    expect(screen.getByRole('tab', { name: 'Packet' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Every document is saved to the matter.')).toBeInTheDocument()
  })
})
