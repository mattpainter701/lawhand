import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import MatterCsvImport from './MatterCsvImport'

const mocks = vi.hoisted(() => ({
  getMatterCsvTemplate: vi.fn(), previewMatterCsvImport: vi.fn(), confirmMatterCsvImport: vi.fn(),
}))
vi.mock('../api', () => ({
  getMatterCsvTemplate: mocks.getMatterCsvTemplate,
  previewMatterCsvImport: mocks.previewMatterCsvImport,
  confirmMatterCsvImport: mocks.confirmMatterCsvImport,
}))

const preview = {
  id: 'run-1',
  status: 'review',
  summary: { total: 2, valid: 1, invalid: 1, contacts_matched: 1, contacts_to_create: 1 },
  rows: [
    {
      row: 2, values: { matter_name: 'Smith v. Jones', opened_on: '2025-01-15', engagement: 'existing', agreement: 'pending_copy' },
      contact: { action: 'match', contact_id: 'c1', display_name: 'Jane Smith' }, attorney: { user_id: 'u1', name: 'Ann Attorney' }, errors: [],
    },
    {
      row: 3, values: { matter_name: 'Bad row', opened_on: '', engagement: 'review' },
      contact: { action: 'create', display_name: 'New Person' }, attorney: null, errors: ['opened_on: not a date'],
    },
  ],
}

beforeEach(() => { vi.clearAllMocks() })
afterEach(cleanup)

describe('bulk create from CSV', () => {
  it('previews the uploaded CSV, blocks on included problems, and creates the rest', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    mocks.previewMatterCsvImport.mockResolvedValue(preview)
    mocks.confirmMatterCsvImport.mockResolvedValue({
      id: 'run-1', status: 'complete',
      results: [{ row: 2, matter_id: 'm1', matter_number: 'SMIT0001', matter_name: 'Smith v. Jones', contact_id: 'c1', contact_created: false }],
    })
    render(<MemoryRouter><MatterCsvImport onComplete={onComplete} /></MemoryRouter>)

    const file = new File(['matter_name\nSmith v. Jones'], 'matters.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Choose CSV'), { target: { files: [file] } })
    await waitFor(() => expect(mocks.previewMatterCsvImport).toHaveBeenCalledWith(expect.any(FormData)))
    expect(mocks.previewMatterCsvImport.mock.calls[0][0].get('file')).toBe(file)

    expect(await screen.findByText('Smith v. Jones')).toBeInTheDocument()
    expect(screen.getByText('existing client')).toBeInTheDocument()
    expect(screen.getByText('new client')).toBeInTheDocument()
    expect(screen.getByText('opened_on: not a date')).toBeInTheDocument()
    const create = screen.getByRole('button', { name: 'Create 2 matters' })
    expect(create).toBeDisabled()

    await user.click(screen.getByRole('checkbox', { name: 'Include row 3' }))
    await user.click(screen.getByRole('button', { name: 'Create 1 matter' }))

    await waitFor(() => expect(mocks.confirmMatterCsvImport).toHaveBeenCalledWith('run-1', { confirm: true, include_rows: [2] }))
    expect(await screen.findByRole('link', { name: 'SMIT0001 · Smith v. Jones' })).toHaveAttribute('href', '/matters/m1')
    expect(screen.getByText(/Import files & emails/)).toBeInTheDocument()
    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ status: 'complete' }))
  })

  it('reports a rejected file', async () => {
    mocks.previewMatterCsvImport.mockRejectedValue({ response: { data: { detail: 'A .csv file is required' } } })
    render(<MemoryRouter><MatterCsvImport /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Choose CSV'), { target: { files: [new File(['x'], 'x.txt')] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('A .csv file is required')
  })

  it('downloads the template as a file', async () => {
    const user = userEvent.setup()
    mocks.getMatterCsvTemplate.mockResolvedValue(new Blob(['matter_name\n'], { type: 'text/csv' }))
    const createObjectURL = vi.fn(() => 'blob:template')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(<MemoryRouter><MatterCsvImport /></MemoryRouter>)
    await user.click(screen.getByRole('button', { name: 'Download template' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:template')
    click.mockRestore()
  })
})
