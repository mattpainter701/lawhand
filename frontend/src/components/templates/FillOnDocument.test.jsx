import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import FillOnDocument, { orderFieldsForDocument } from './FillOnDocument'

const pdfState = vi.hoisted(() => ({ result: null }))

vi.mock('./PdfDocumentCanvas', () => ({
  useTemplatePdfDocument: () => pdfState.result,
  PdfPageCanvas: ({ pageNumber }) => <canvas aria-label={`PDF page ${pageNumber}`} />,
}))

const loaded = { document: { numPages: 2 }, pages: [{ page: 1, width: 612, height: 792, rotation: 0 }, { page: 2, width: 612, height: 792, rotation: 0 }], error: '' }

const fields = [
  { name: 'city', label: 'City', field_type: 'text', page: 1, rect: [300, 700, 400, 716] },
  { name: 'client_name', label: 'Client name', field_type: 'text', required: true, page: 1, rect: [40, 740, 280, 756] },
  { name: 'consent', label: 'Consent', field_type: 'checkbox', page: 2, rect: [40, 500, 52, 512] },
  { name: 'role', label: 'Role', field_type: 'radio', options: ['Buyer', 'Seller'], page: 2, rect: [60, 500, 72, 512] },
  { name: 'notes', label: 'Notes', field_type: 'text', multiline: true, page: 2, rect: [40, 300, 500, 400] },
  { name: 'signer', label: 'Client signature', field_type: 'signature', page: 2, rect: [40, 100, 240, 130] },
  { name: 'reference', label: 'Reference', field_type: 'text', required: true },
]

const renderInput = (field, value, onChange) => (
  <input aria-label={`Bar: ${field.label}`} value={value ?? ''} onChange={(event) => onChange(event.target.value)} />
)

function Harness({ initial = {}, suggested = new Set() }) {
  const [values, setValues] = useState(initial)
  return (
    <FillOnDocument
      source={new Blob(['pdf'])}
      fields={fields}
      values={values}
      suggestedNames={suggested}
      onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))}
      renderInput={renderInput}
    />
  )
}

afterEach(() => { cleanup(); pdfState.result = null })

describe('orderFieldsForDocument', () => {
  it('reads by page, then top to bottom, then left to right, with unplaced fields last', () => {
    expect(orderFieldsForDocument(fields).map((field) => field.name)).toEqual(['client_name', 'city', 'consent', 'role', 'notes', 'signer', 'reference'])
  })
})

describe('FillOnDocument', () => {
  it('shows every page with an input on each placed field', () => {
    pdfState.result = loaded
    render(<Harness />)
    const page1 = screen.getByRole('group', { name: 'Page 1' })
    const page2 = screen.getByRole('group', { name: 'Page 2' })
    expect(within(page1).getByLabelText('Client name')).toBeInTheDocument()
    expect(within(page1).getByLabelText('City')).toBeInTheDocument()
    expect(within(page2).getByRole('checkbox', { name: 'Consent' })).toHaveAttribute('aria-checked', 'false')
    expect(within(page2).getByLabelText('Role').tagName).toBe('SELECT')
    expect(within(page2).getByLabelText('Notes').tagName).toBe('TEXTAREA')
    expect(within(page2).getByRole('note', { name: 'Client signature: Signed later' })).toBeInTheDocument()
    expect(screen.getByText(/1 field has no box on the page/)).toBeInTheDocument()
  })

  it('places a field box from PDF points using the page height', () => {
    pdfState.result = loaded
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Document zoom'), { target: { value: '1' } })
    const name = within(screen.getByRole('group', { name: 'Page 1' })).getByLabelText('Client name')
    expect(name.style.left).toBe('40px')
    expect(name.style.top).toBe('36px')
    expect(name.style.width).toBe('240px')
  })

  it('keeps the page and the guided bar on one shared value', () => {
    pdfState.result = loaded
    render(<Harness />)
    expect(screen.getByText('Field 1 of 7')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Bar: Client name'), { target: { value: 'Ada Example' } })
    expect(within(screen.getByRole('group', { name: 'Page 1' })).getByLabelText('Client name')).toHaveValue('Ada Example')
    fireEvent.focus(within(screen.getByRole('group', { name: 'Page 1' })).getByLabelText('City'))
    expect(screen.getByText('Field 2 of 7')).toBeInTheDocument()
    fireEvent.change(within(screen.getByRole('group', { name: 'Page 1' })).getByLabelText('City'), { target: { value: 'Boulder' } })
    expect(screen.getByLabelText('Bar: City')).toHaveValue('Boulder')
  })

  it('toggles checkboxes on the page', () => {
    pdfState.result = loaded
    render(<Harness />)
    const box = screen.getByRole('checkbox', { name: 'Consent' })
    fireEvent.click(box)
    expect(box).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('Field 3 of 7')).toBeInTheDocument()
    fireEvent.click(box)
    expect(box).toHaveAttribute('aria-checked', 'false')
  })

  it('steps through fields and jumps to the next unanswered required field, including unplaced ones', () => {
    pdfState.result = loaded
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Next field' }))
    expect(screen.getByText('Field 2 of 7')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Previous field' }))
    fireEvent.click(screen.getByRole('button', { name: 'Previous field' }))
    expect(screen.getByText('Field 7 of 7')).toBeInTheDocument()
    expect(screen.getByText(/Not placed on the page/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next required (2)' }))
    expect(screen.getByText('Field 1 of 7')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Bar: Client name'), { target: { value: 'Ada' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next required (1)' }))
    expect(screen.getByLabelText('Bar: Reference')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Bar: Reference'), { target: { value: 'R-1' } })
    expect(screen.getByRole('button', { name: 'All required answered' })).toBeDisabled()
  })

  it('marks matter suggestions and unanswered required boxes differently', () => {
    pdfState.result = loaded
    render(<Harness initial={{ city: 'Boulder' }} suggested={new Set(['city'])} />)
    fireEvent.click(screen.getByRole('button', { name: 'Next field' }))
    const page1 = screen.getByRole('group', { name: 'Page 1' })
    expect(within(page1).getByLabelText('Client name').className).toContain('bg-amber-100')
    fireEvent.click(screen.getByRole('button', { name: 'Previous field' }))
    expect(within(page1).getByLabelText('City').className).toContain('bg-blue-50')
  })

  it('reports an unreadable document so the caller can fall back to questions', () => {
    pdfState.result = { document: null, pages: [], error: 'bad pdf' }
    const onUnavailable = vi.fn()
    render(<FillOnDocument source={new Blob(['x'])} fields={fields} values={{}} onChange={vi.fn()} renderInput={renderInput} onUnavailable={onUnavailable} />)
    expect(screen.getByRole('alert')).toHaveTextContent('could not be opened')
    expect(onUnavailable).toHaveBeenCalledWith('bad pdf')
  })

  it('shows a loading state while the document opens', () => {
    pdfState.result = { document: null, pages: [], error: '' }
    render(<FillOnDocument source={null} fields={fields} values={{}} onChange={vi.fn()} renderInput={renderInput} />)
    expect(screen.getByRole('status')).toHaveTextContent('Opening the original document')
  })
})

describe('FillOnDocument packet hooks', () => {
  it('marks shared boxes and lets the host drive "Next required"', () => {
    pdfState.result = loaded
    const onNextRequired = vi.fn()
    render(
      <FillOnDocument
        source={new Blob(['pdf'])}
        fields={fields}
        values={{}}
        onChange={() => {}}
        renderInput={renderInput}
        isShared={(field) => field.name === 'client_name'}
        onNextRequired={onNextRequired}
        requiredMissing={5}
      />,
    )
    const page1 = screen.getByRole('group', { name: 'Page 1' })
    expect(page1.querySelector('[data-fill-shared="client_name"]')).not.toBeNull()
    expect(page1.querySelector('[data-fill-shared="city"]')).toBeNull()
    expect(within(page1).getByLabelText('Client name')).toHaveAttribute('title', 'Client name (required) · also fills other documents')
    fireEvent.click(screen.getByRole('button', { name: 'Next required (5)' }))
    expect(onNextRequired).toHaveBeenCalledTimes(1)
  })

  it('brings the opening field into view when the host asks for it', () => {
    pdfState.result = loaded
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    try {
      render(<FillOnDocument source={new Blob(['pdf'])} fields={fields} values={{}} onChange={() => {}} renderInput={renderInput} activeName="notes" onActiveChange={() => {}} scrollToActiveOnOpen />)
      expect(scrollIntoView).toHaveBeenCalled()
      expect(scrollIntoView.mock.contexts.at(-1)).toHaveAttribute('data-fill-field', 'notes')
    } finally {
      delete Element.prototype.scrollIntoView
    }
  })
})
