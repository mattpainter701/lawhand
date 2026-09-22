import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getSampleTemplateSource, previewSampleTemplateSmartFill, renderSampleTemplateFile } from '../../api'
import SampleFillDialog from './SampleFillDialog'

vi.mock('../../api', () => ({
  getSampleTemplateSource: vi.fn(),
  previewSampleTemplateSmartFill: vi.fn(),
  renderSampleTemplateFile: vi.fn(),
}))

vi.mock('../prepare/MatterPicker', () => ({
  default: ({ onSelect }) => <div>
    <button type="button" onClick={() => onSelect('matter-1')}>Choose matter</button>
    <button type="button" onClick={() => onSelect('matter-2')}>Choose another matter</button>
    <button type="button" onClick={() => onSelect('')}>Clear matter</button>
  </div>,
}))

vi.mock('./GeneratedPdfPreview', () => ({
  default: ({ title }) => <section aria-label={`Preview of ${title}`}>PDF preview</section>,
}))

const sample = {
  id: 'sample-1',
  title: 'Sample intake',
  description: 'Review this form before use.',
  jurisdictions: ['North Dakota'],
  variable_schema: { fields: [
    { name: 'client_name', label: 'Client name', field_type: 'text', page: 1 },
    { name: 'safe_contact', label: 'Safe contact', field_type: 'radio', options: ['yes', 'no'], page: 1 },
  ] },
}

afterEach(() => { cleanup(); vi.clearAllMocks() })
beforeEach(() => { getSampleTemplateSource.mockResolvedValue(new Blob(['source'], { type: 'application/pdf' })) })

describe('SampleFillDialog Smart Fill', () => {
  it('loads matter suggestions and shows filled and attention counts', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'client_name', suggested_value: 'Ada Example' }] })
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose matter' }))
    expect(await screen.findByDisplayValue('Ada Example')).toBeInTheDocument()
    expect(screen.getByText(/1 filled from this matter · 1 need attention/)).toBeInTheDocument()
  })

  it('keeps a manual edit when a same-matter refresh resolves', async () => {
    let resolve
    previewSampleTemplateSmartFill.mockImplementation(() => new Promise((r) => { resolve = r }))
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose matter' }))
    const field = screen.getByLabelText('Client name')
    fireEvent.change(field, { target: { value: 'Manual value' } })
    resolve({ variables: [{ variable: 'client_name', suggested_value: 'Matter value' }] })
    await waitFor(() => expect(field).toHaveValue('Manual value'))
  })

  it('shows source and filled previews and leaves the dialog open after preview', async () => {
    getSampleTemplateSource.mockResolvedValue(new Blob(['source'], { type: 'application/pdf' }))
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    expect(await screen.findByRole('region', { name: /Preview of Source: Sample intake/ })).toBeInTheDocument()
    renderSampleTemplateFile.mockResolvedValue({ blob: new Blob(['filled'], { type: 'application/pdf' }), filename: 'filled.pdf' })
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('region', { name: /Preview of Filled: Sample intake/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close fill dialog' })).toBeInTheDocument()
  })

  it('keeps fields editable when preview fails', async () => {
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    renderSampleTemplateFile.mockRejectedValue(new Error('preview failed'))
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('preview failed')
    expect(screen.getByLabelText('Client name')).toBeInTheDocument()
  })

  it('clears prior matter values before a failed matter switch', async () => {
    previewSampleTemplateSmartFill
      .mockResolvedValueOnce({ variables: [{ variable: 'client_name', suggested_value: 'First matter' }] })
      .mockRejectedValueOnce(new Error('denied'))
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose matter' }))
    expect(await screen.findByDisplayValue('First matter')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Choose another matter' }))
    await waitFor(() => expect(screen.getByLabelText('Client name')).toHaveValue(''))
    expect(await screen.findByRole('alert')).toHaveTextContent('matter could not be used')
  })

  it('clears matter suggestions when the selection is cleared', async () => {
    previewSampleTemplateSmartFill.mockResolvedValue({ variables: [{ variable: 'client_name', suggested_value: 'Matter value' }] })
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose matter' }))
    expect(await screen.findByDisplayValue('Matter value')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear matter' }))
    expect(screen.getByLabelText('Client name')).toHaveValue('')
    expect(screen.queryByText(/filled from this matter/)).not.toBeInTheDocument()
  })

  it('clears a filled preview when an answer is edited', async () => {
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    renderSampleTemplateFile.mockResolvedValue({ blob: new Blob(['filled']), filename: 'filled.pdf' })
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('region', { name: /Preview of Filled/ })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Changed' } })
    expect(screen.queryByRole('region', { name: /Preview of Filled/ })).not.toBeInTheDocument()
  })

  it('ignores a stale render result after an answer changes', async () => {
    let resolveFirst
    renderSampleTemplateFile.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    render(<SampleFillDialog sample={sample} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'New value' } })
    renderSampleTemplateFile.mockResolvedValueOnce({ blob: new Blob(['second']), filename: 'second.pdf' })
    fireEvent.click(screen.getByRole('button', { name: 'Preview filled PDF' }))
    expect(await screen.findByRole('region', { name: /Preview of Filled/ })).toBeInTheDocument()
    resolveFirst({ blob: new Blob(['first']), filename: 'first.pdf' })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.getByRole('region', { name: /Preview of Filled/ })).toBeInTheDocument()
  })
})
