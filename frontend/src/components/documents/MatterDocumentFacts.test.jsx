import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import MatterDocumentFacts from './MatterDocumentFacts'
import { getMatterDocuments, proposeMatterDocumentFacts, acceptMatterDocumentFact, getMatterDocumentFormSources, readMatterDocumentAgainstForm } from '../../api'
vi.mock('../../api', () => ({
  getMatterDocuments: vi.fn(),
  getMatterDocumentDownloadUrl: () => 'https://api.example.test/source',
  proposeMatterDocumentFacts: vi.fn(),
  acceptMatterDocumentFact: vi.fn(),
  getMatterDocumentFormSources: vi.fn(),
  readMatterDocumentAgainstForm: vi.fn(),
}))
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  getMatterDocuments.mockResolvedValue([{ id: 'source', filename: 'intake.pdf' }])
  acceptMatterDocumentFact.mockResolvedValue({ status: 'accepted' })
  getMatterDocumentFormSources.mockResolvedValue({ sources: [] })
})

it('proposes document details and saves one only after acceptance', async () => {
  proposeMatterDocumentFacts.mockResolvedValue({
    source_document_id: 'source',
    source_filename: 'intake.pdf',
    candidates: [
      { target_key: 'client.name', label: 'Client name', source_kind: 'label_value', value: 'John Smith', current_value: null, status: 'suggested' },
      { target_key: 'matter.case_number', label: 'Case number', source_kind: 'acroform', value: '2024-CV-001', current_value: '2020-CV-9', status: 'suggested' },
    ],
    warnings: [],
  })
  render(<MatterDocumentFacts matterId="matter" />)
  fireEvent.click(screen.getByText('Read details from a document'))
  await screen.findByText('intake.pdf')
  fireEvent.change(screen.getByLabelText('Source document'), { target: { value: 'source' } })
  fireEvent.click(screen.getByText('Find details'))
  await screen.findByText('Client name')
  expect(acceptMatterDocumentFact).not.toHaveBeenCalled()

  fireEvent.click(screen.getByText('Accept Client name'))
  await waitFor(() => expect(acceptMatterDocumentFact).toHaveBeenCalledWith('matter', 'source', {
    target_key: 'client.name',
    value: 'John Smith',
    replace_existing: false,
  }))
  await screen.findByText('Client name saved to the matter.')

  fireEvent.click(screen.getByLabelText(/Replace the current value/))
  fireEvent.click(screen.getByText('Accept Case number'))
  await waitFor(() => expect(acceptMatterDocumentFact).toHaveBeenLastCalledWith('matter', 'source', {
    target_key: 'matter.case_number',
    value: '2024-CV-001',
    replace_existing: true,
  }))
})

it('reports a document with no supported details', async () => {
  proposeMatterDocumentFacts.mockResolvedValue({ source_document_id: 'source', source_filename: 'intake.pdf', candidates: [], warnings: ['No text layer or form values were found.'] })
  render(<MatterDocumentFacts matterId="matter" />)
  fireEvent.click(screen.getByText('Read details from a document'))
  await screen.findByText('intake.pdf')
  fireEvent.change(screen.getByLabelText('Source document'), { target: { value: 'source' } })
  fireEvent.click(screen.getByText('Find details'))
  await screen.findByText('No text layer or form values were found.')
  expect(acceptMatterDocumentFact).not.toHaveBeenCalled()
})

it('does nothing without a matter', () => {
  const { container } = render(<MatterDocumentFacts matterId="" />)
  expect(container).toBeEmptyDOMElement()
  expect(getMatterDocuments).not.toHaveBeenCalled()
})

it('asks the server for AI reading only when the reviewer opts in', async () => {
  proposeMatterDocumentFacts.mockResolvedValue({ source_document_id: 'source', source_filename: 'intake.pdf', candidates: [], warnings: [] })
  render(<MatterDocumentFacts matterId="matter" />)
  fireEvent.click(screen.getByText('Read details from a document'))
  await screen.findByText('intake.pdf')
  fireEvent.change(screen.getByLabelText('Source document'), { target: { value: 'source' } })
  fireEvent.click(screen.getByText('Find details'))
  await waitFor(() => expect(proposeMatterDocumentFacts).toHaveBeenCalledWith('matter', 'source', false))
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByText('Find details'))
  await waitFor(() => expect(proposeMatterDocumentFacts).toHaveBeenLastCalledWith('matter', 'source', true))
})

it('shows how sure OCR was about a value read from a scan', async () => {
  proposeMatterDocumentFacts.mockResolvedValue({
    source_document_id: 'source',
    source_filename: 'scan.png',
    candidates: [
      { target_key: 'client.name', label: 'Client name', source_kind: 'ocr', confidence: 0.73, value: 'Ada Lovelace', current_value: null, status: 'suggested' },
    ],
    warnings: ['Some values were read by OCR from a scan.'],
  })
  getMatterDocuments.mockResolvedValue([{ id: 'source', filename: 'scan.png' }])
  render(<MatterDocumentFacts matterId="matter" />)
  fireEvent.click(screen.getByText('Read details from a document'))
  await screen.findByText('scan.png')
  fireEvent.change(screen.getByLabelText('Source document'), { target: { value: 'source' } })
  fireEvent.click(screen.getByText('Find details'))
  await screen.findByText('Client name')
  expect(screen.getByText('From the scan · 73% OCR confidence')).toBeInTheDocument()
  expect(screen.getByText('Some values were read by OCR from a scan.')).toBeInTheDocument()
})

it('reads a scan field by field against the form the matter printed', async () => {
  getMatterDocumentFormSources.mockResolvedValue({ sources: [
    { template_id: 't-1', template_title: 'Intake form', version_no: 3, output_filename: 'intake.pdf' },
    { template_id: 't-2', template_title: 'Fee agreement', version_no: 1, output_filename: 'fee.pdf' },
  ] })
  readMatterDocumentAgainstForm.mockResolvedValue({
    source_document_id: 'scan',
    template_id: 't-1',
    alignment: 'scaled',
    candidates: [
      { target_key: 'client.name', label: 'Client name', source_kind: 'ocr_field', source_locator: 'field:client_name', confidence: 0.66, value: 'Ada Lovelace', current_value: null, status: 'suggested', thumbnail_png_b64: 'iVBORw0KGgo=' },
    ],
    readings: [],
    warnings: ['Values were read from a scan, field by field.'],
  })
  render(<MatterDocumentFacts matterId="matter" documentId="scan" />)
  fireEvent.click(screen.getByText('Read details from a document'))
  const picker = await screen.findByLabelText('Printed form')
  await waitFor(() => expect(getMatterDocumentFormSources).toHaveBeenCalledWith('matter', 'scan'))
  expect(picker).toHaveValue('t-1:3')
  fireEvent.change(picker, { target: { value: 't-2:1' } })
  fireEvent.click(screen.getByText('Read against the printed form'))
  await screen.findByText('Client name')
  expect(readMatterDocumentAgainstForm).toHaveBeenCalledWith('matter', 'scan', { template_id: 't-2', version_no: 1 })
  expect(screen.getByText('Read from the scan, field by field · 66% OCR confidence')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: 'Scan of Client name' })).toHaveAttribute('src', 'data:image/png;base64,iVBORw0KGgo=')
  fireEvent.click(screen.getByText('Accept Client name'))
  await waitFor(() => expect(acceptMatterDocumentFact).toHaveBeenCalledWith('matter', 'scan', {
    target_key: 'client.name',
    value: 'Ada Lovelace',
    replace_existing: false,
  }))
})
