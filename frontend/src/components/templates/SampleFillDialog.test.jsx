import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getSampleTemplateSource, previewSampleTemplateSmartFill, renderSampleTemplateFile, saveSampleTemplateToMatter, updateMatterDocument } from '../../api'
import SampleFillDialog from './SampleFillDialog'

vi.mock('../../api', () => ({
  getSampleTemplateSource: vi.fn(),
  previewSampleTemplateSmartFill: vi.fn(),
  renderSampleTemplateFile: vi.fn(),
  saveSampleTemplateToMatter: vi.fn(),
  updateMatterDocument: vi.fn(),
}))

vi.mock('../prepare/MatterPicker', () => ({
  default: ({ onSelect }) => <div>
    <button type="button" onClick={() => onSelect('matter-1')}>Choose matter</button>
    <button type="button" onClick={() => onSelect('matter-2')}>Choose another matter</button>
    <button type="button" onClick={() => onSelect('')}>Clear matter</button>
  </div>,
}))

vi.mock('./FillOnDocument', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    default: ({ onChange, suggestedNames, onUnavailable }) => <div data-testid="fill-on-document">
      {[...suggestedNames].map((name) => <span key={name}>suggested: {name}</span>)}
      <button type="button" onClick={() => onChange('client_name', 'Typed on page')}>Doc: type client</button>
      <button type="button" onClick={() => onChange('city', 'Denver')}>Doc: edit city</button>
      <button type="button" onClick={() => onUnavailable('bad pdf')}>Doc: unreadable</button>
    </div>,
  }
})

vi.mock('./GeneratedPdfPreview', () => ({
  default: ({ title }) => <section aria-label={`Preview of ${title}`}>PDF preview</section>,
}))

const sample = {
  id: 'sample-1',
  title: 'Sample intake',
  description: 'Review this form before use.',
  jurisdictions: ['North Dakota'],
  variable_schema: { fields: [
    { name: 'client_name', label: 'Client name', source_label: 'undefined', field_type: 'text', required: true, page: 1 },
    { name: 'safe_contact', label: 'Safe contact', field_type: 'radio', options: ['yes', 'no'], page: 1 },
    { name: 'safe_contact_details', label: 'If yes, explain', field_type: 'text', page: 1 },
    { name: 'source_required', label: 'Source required field', field_type: 'text', source_required: true, page: 1 },
    { name: 'explicit_optional', label: 'Explicit optional field', field_type: 'text', required: false, source_required: true, page: 1 },
  ] },
}

const pickMatter = () => {
  fireEvent.click(screen.getByRole('button', { name: 'Fill from a matter' }))
  fireEvent.click(screen.getByRole('button', { name: 'Choose matter' }))
}

afterEach(() => { cleanup(); vi.clearAllMocks(); localStorage.clear() })
beforeEach(() => { getSampleTemplateSource.mockResolvedValue(new Blob(['source'], { type: 'application/pdf' })) })

describe('SampleFillDialog Smart Fill', () => {
  it('trusts a curated label over a placeholder source label', () => {
    const curated = { ...sample, variable_schema: { fields: [
      { name: 'landlord_name', label: 'Landlord name', label_source: 'curated', source_label: 'undefined 2', field_type: 'text', page: 1 },
    ] } }
    render(<SampleFillDialog sample={curated} onClose={vi.fn()} />)
    expect(screen.getByText('Landlord name')).toBeInTheDocument()
    expect(screen.queryByText(/Source label unavailable/)).not.toBeInTheDocument()
  })

  it('loads matter suggestions and shows filled and attention counts', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'client_name', suggested_value: 'Ada Example' }] })
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    pickMatter()
    expect(await screen.findByDisplayValue('Ada Example')).toBeInTheDocument()
    expect(screen.getByText(/1 filled · 1 required answers missing · 3 optional unanswered/)).toBeInTheDocument()
    expect(screen.getByText(/Source label unavailable; check this field in the source PDF/)).toBeInTheDocument()
    expect(screen.getByText('Source required field *')).toBeInTheDocument()
    expect(screen.getByText('Explicit optional field')).toBeInTheDocument()
    expect(screen.queryByText('Explicit optional field *')).not.toBeInTheDocument()
  })

  it('updates counts from live edits and clears', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'client_name', suggested_value: 'Ada Example' }] })
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    pickMatter()
    expect(await screen.findByText(/1 filled · 1 required answers missing · 3 optional unanswered/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('If yes, explain'), { target: { value: 'Details' } })
    expect(screen.getByText(/2 filled · 1 required answers missing · 2 optional unanswered/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('If yes, explain'), { target: { value: '' } })
    expect(screen.getByText(/1 filled · 1 required answers missing · 3 optional unanswered/)).toBeInTheDocument()
  })

  it('treats unchecked required checkboxes as missing and keeps text zero as answered', async () => {
    const checkboxSample = {
      ...sample,
      variable_schema: { fields: [
        { name: 'consent', label: 'Consent', field_type: 'checkbox', required: true, page: 1 },
        { name: 'count', label: 'Count', field_type: 'text', default: 0, page: 1 },
      ] },
    }
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [] })
    render(<SampleFillDialog sample={checkboxSample} onClose={vi.fn()} />)
    expect(screen.getByLabelText('Count')).toHaveValue('0')
    pickMatter()
    expect(await screen.findByText(/1 filled · 1 required answers missing · 0 optional unanswered/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/Consent/))
    expect(screen.getByText(/2 filled · 0 required answers missing · 0 optional unanswered/)).toBeInTheDocument()
  })

  it('filters optional blanks separately and keeps follow-up fields visible', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [] })
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    expect(screen.getByLabelText('If yes, explain')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/no/i))
    expect(screen.getByLabelText('If yes, explain')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Optional' }))
    expect(screen.getByLabelText('If yes, explain')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Client name/)).not.toBeInTheDocument()
  })

  it('keeps a manual edit when a same-matter refresh resolves', async () => {
    let resolve
    previewSampleTemplateSmartFill.mockImplementation(() => new Promise((r) => { resolve = r }))
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    pickMatter()
    const field = screen.getByLabelText(/Client name/)
    fireEvent.change(field, { target: { value: 'Manual value' } })
    resolve({ variables: [{ variable: 'client_name', suggested_value: 'Matter value' }] })
    await waitFor(() => expect(field).toHaveValue('Manual value'))
  })

  it('opens the final PDF tab after preview and leaves the dialog open', async () => {
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    renderSampleTemplateFile.mockResolvedValue({ blob: new Blob(['filled'], { type: 'application/pdf' }), filename: 'filled.pdf' })
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('region', { name: /Preview of Filled: Sample intake/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Final PDF' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: 'Download filled PDF' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close fill dialog' })).toBeInTheDocument()
  })

  it('keeps fields editable when preview fails', async () => {
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    renderSampleTemplateFile.mockRejectedValue(new Error('preview failed'))
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('preview failed')
    expect(screen.getByLabelText(/Client name/)).toBeInTheDocument()
  })

  it('clears prior matter values before a failed matter switch', async () => {
    previewSampleTemplateSmartFill
      .mockResolvedValueOnce({ variables: [{ variable: 'client_name', suggested_value: 'First matter' }] })
      .mockRejectedValueOnce(new Error('denied'))
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    pickMatter()
    expect(await screen.findByDisplayValue('First matter')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Choose another matter' }))
    await waitFor(() => expect(screen.getByLabelText(/Client name/)).toHaveValue(''))
    expect(await screen.findByRole('alert')).toHaveTextContent('matter could not be used')
  })

  it('clears matter suggestions when the selection is cleared', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'client_name', suggested_value: 'Matter value' }] })
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    pickMatter()
    expect(await screen.findByDisplayValue('Matter value')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear matter' }))
    expect(screen.getByLabelText(/Client name/)).toHaveValue('')
    expect(screen.queryByText(/filled from this matter/)).not.toBeInTheDocument()
  })

  it('clears a filled preview when an answer is edited', async () => {
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    renderSampleTemplateFile.mockResolvedValue({ blob: new Blob(['filled']), filename: 'filled.pdf' })
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('region', { name: /Preview of Filled/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Questions' }))
    fireEvent.change(screen.getByLabelText(/Client name/), { target: { value: 'Changed' } })
    expect(screen.queryByRole('tab', { name: 'Final PDF' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Download filled PDF' })).not.toBeInTheDocument()
  })

  it('ignores a stale render result after an answer changes', async () => {
    let resolveFirst
    renderSampleTemplateFile.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    fireEvent.change(screen.getByLabelText(/Client name/), { target: { value: 'New value' } })
    renderSampleTemplateFile.mockResolvedValueOnce({ blob: new Blob(['second']), filename: 'second.pdf' })
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('region', { name: /Preview of Filled/ })).toBeInTheDocument()
    resolveFirst({ blob: new Blob(['first']), filename: 'first.pdf' })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.getByRole('region', { name: /Preview of Filled/ })).toBeInTheDocument()
  })
})

describe('SampleFillDialog document view', () => {
  const placedSample = {
    ...sample,
    variable_schema: { fields: [
      { name: 'client_name', label: 'Client name', field_type: 'text', required: true, page: 1, rect: [40, 740, 280, 756] },
      { name: 'city', label: 'City', field_type: 'text', page: 1, rect: [300, 740, 400, 756] },
    ] },
  }

  it('opens on the original document and shares answers with the Questions view', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'city', suggested_value: 'Boulder' }] })
    render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Document' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByTestId('fill-on-document')).toBeInTheDocument()
    pickMatter()
    expect(await screen.findByText('suggested: city')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Doc: type client' }))
    expect(screen.queryByText('suggested: city')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Questions' }))
    expect(screen.getByLabelText(/Client name/)).toHaveValue('Typed on page')
    expect(screen.getByLabelText('City')).toHaveValue('Boulder')
    expect(screen.getByText(/2 filled · 0 required answers missing · 0 optional unanswered/)).toBeInTheDocument()
  })

  it('drops the matter mark once a suggested answer is edited on the page', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'city', suggested_value: 'Boulder' }] })
    render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    pickMatter()
    expect(await screen.findByText('suggested: city')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Doc: edit city' }))
    expect(screen.queryByText('suggested: city')).not.toBeInTheDocument()
  })

  it('falls back to Questions when the source PDF cannot be loaded', async () => {
    getSampleTemplateSource.mockRejectedValue(new Error('missing'))
    render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    expect(await screen.findByText(/original document could not be opened here/)).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Document' })).not.toBeInTheDocument()
    expect(screen.getByLabelText(/Client name/)).toBeInTheDocument()
  })

  it('falls back to Questions when the document viewer reports the PDF is unreadable', async () => {
    render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Doc: unreadable' }))
    expect(screen.getByRole('tab', { name: 'Questions' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('tab', { name: 'Document' })).not.toBeInTheDocument()
  })

  it('returns to the document after a final PDF is invalidated', async () => {
    render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    renderSampleTemplateFile.mockResolvedValue({ blob: new Blob(['filled']), filename: 'filled.pdf' })
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('tab', { name: 'Final PDF' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Document' }))
    fireEvent.click(screen.getByRole('button', { name: 'Doc: type client' }))
    expect(screen.queryByRole('tab', { name: 'Final PDF' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Document' })).toHaveAttribute('aria-selected', 'true')
  })

  it('remembers the chosen view for the next fill', () => {
    const { unmount } = render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Questions' }))
    unmount()
    render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Questions' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps matter search folded away until asked for', () => {
    render(<SampleFillDialog sample={placedSample} onClose={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Choose matter' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Fill from a matter' }))
    expect(screen.getByRole('button', { name: 'Choose matter' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }))
    expect(screen.queryByRole('button', { name: 'Choose matter' })).not.toBeInTheDocument()
  })

  it('closes on Escape', () => {
    const onClose = vi.fn()
    render(<SampleFillDialog sample={placedSample} onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})

describe('SampleFillDialog on a matter', () => {
  const fillable = { ...sample, variable_schema: { fields: [
    { name: 'client_name', label: 'Client name', field_type: 'text', required: true, page: 1 },
    { name: 'city', label: 'City', field_type: 'text', page: 1 },
  ] } }
  const renderOnMatter = (props = {}) => render(<SampleFillDialog sample={fillable} fixedMatterId="matter-9" folderId="folder-2" onClose={vi.fn()} onSaved={vi.fn()} {...props} />)
  beforeEach(() => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'client_name', suggested_value: 'Ada Example' }] })
    renderSampleTemplateFile.mockResolvedValue({ blob: new Blob(['filled'], { type: 'application/pdf' }), filename: 'filled.pdf' })
  })

  it('fills from the matter on open without asking for a matter', async () => {
    renderOnMatter()
    expect(screen.getByRole('heading', { name: 'Fill “Sample intake” for this matter' })).toBeInTheDocument()
    expect(await screen.findByDisplayValue('Ada Example')).toBeInTheDocument()
    expect(previewSampleTemplateSmartFill).toHaveBeenCalledWith('sample-1', { matter_id: 'matter-9', variables: ['client_name', 'city'] })
    expect(screen.queryByRole('button', { name: 'Fill from a matter' })).not.toBeInTheDocument()
    expect(screen.getByText(/Filled from this matter — review every value before saving/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save to matter' })).not.toBeInTheDocument()
  })

  it('reviews the final PDF, saves it to the matter folder, and shares it with the client', async () => {
    const onSaved = vi.fn()
    const onClose = vi.fn()
    saveSampleTemplateToMatter.mockResolvedValue({ matter_document_id: 'doc-1', output_filename: 'Sample intake.pdf', matter_document: { id: 'doc-1', filename: 'Sample intake.pdf', portal_visible: false } })
    updateMatterDocument.mockResolvedValue({ id: 'doc-1', filename: 'Sample intake.pdf', portal_visible: true })
    renderOnMatter({ onSaved, onClose })
    await screen.findByDisplayValue('Ada Example')
    fireEvent.click(screen.getByRole('button', { name: 'Review final PDF' }))
    expect(await screen.findByRole('region', { name: /Preview of Filled: Sample intake/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save to matter' }))
    expect(await screen.findByText(/Saved to this matter’s documents/)).toBeInTheDocument()
    expect(saveSampleTemplateToMatter).toHaveBeenCalledWith('sample-1', { matter_id: 'matter-9', variables: { client_name: 'Ada Example', city: '' }, folder_id: 'folder-2' })
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ matter_document_id: 'doc-1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Share with client' }))
    expect(await screen.findByText(/Shared with the client/)).toBeInTheDocument()
    expect(updateMatterDocument).toHaveBeenCalledWith('matter-9', 'doc-1', { portal_visible: true })
    expect(screen.queryByRole('button', { name: 'Share with client' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('blocks saving while a required answer is missing', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [] })
    renderOnMatter()
    await waitFor(() => expect(previewSampleTemplateSmartFill).toHaveBeenCalled())
    fireEvent.click(await screen.findByRole('button', { name: 'Review final PDF' }))
    expect(await screen.findByRole('button', { name: 'Save to matter' })).toBeDisabled()
    expect(screen.getByText('Answer the required questions to finish.')).toBeInTheDocument()
  })

  it('keeps the filled form open with the reason when saving fails', async () => {
    saveSampleTemplateToMatter.mockRejectedValue({ response: { data: { detail: 'Matter not found' } } })
    renderOnMatter()
    await screen.findByDisplayValue('Ada Example')
    fireEvent.click(screen.getByRole('button', { name: 'Review final PDF' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save to matter' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Matter not found')
    expect(screen.getByRole('button', { name: 'Save to matter' })).toBeEnabled()
  })

  it('reports a failed share without losing the saved document', async () => {
    saveSampleTemplateToMatter.mockResolvedValue({ matter_document_id: 'doc-1', output_filename: 'Sample intake.pdf' })
    updateMatterDocument.mockRejectedValue(new Error('offline'))
    renderOnMatter()
    await screen.findByDisplayValue('Ada Example')
    fireEvent.click(screen.getByRole('button', { name: 'Review final PDF' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Save to matter' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Share with client' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('saved but could not be shared')
    expect(screen.getByText(/Saved to this matter’s documents/)).toBeInTheDocument()
  })
})
