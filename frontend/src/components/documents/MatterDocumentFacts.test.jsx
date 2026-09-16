import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import MatterDocumentFacts from './MatterDocumentFacts'
import { getMatterDocuments, proposeMatterDocumentFacts, acceptMatterDocumentFact } from '../../api'
vi.mock('../../api', () => ({
  getMatterDocuments: vi.fn(),
  getMatterDocumentDownloadUrl: () => 'https://api.example.test/source',
  proposeMatterDocumentFacts: vi.fn(),
  acceptMatterDocumentFact: vi.fn(),
}))
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  getMatterDocuments.mockResolvedValue([{ id: 'source', filename: 'intake.pdf' }])
  acceptMatterDocumentFact.mockResolvedValue({ status: 'accepted' })
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
