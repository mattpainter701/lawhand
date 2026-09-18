import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { axe } from 'jest-axe'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ClientPortalEstateTab, { statusLabel } from './ClientPortalEstateTab'
import { addClientPortalEstateAsset, updateClientPortalEstateAsset, uploadClientPortalDocument } from '../../api'

vi.mock('../../api', () => ({
  addClientPortalEstateAsset: vi.fn(),
  updateClientPortalEstateAsset: vi.fn(),
  uploadClientPortalDocument: vi.fn(),
}))
afterEach(cleanup)
beforeEach(() => vi.resetAllMocks())

const estate = {
  estate_id: 'estate-1',
  decedent_name: 'Ole Olson',
  inventory_open: true,
  appointment_date: '2025-03-31',
  assets: [
    { id: 'a1', name: 'Checking at Gate City Bank', category: 'bank_account', ownership_type: 'sole', approximate_value: '12,500.00', institution: 'Gate City Bank', notes: null, artifact_document_id: null, verification_status: 'unverified', editable: true, submitted_at: null },
    { id: 'a2', name: 'Farmland', category: 'real_property', ownership_type: 'joint', approximate_value: null, institution: null, notes: null, artifact_document_id: null, verification_status: 'verified', editable: false, submitted_at: null },
  ],
  categories: [{ key: 'bank_account', label: 'Bank or credit union account' }, { key: 'real_property', label: 'House, land, farmland, or minerals' }, { key: 'other', label: 'Something else' }],
  ownership_options: [{ key: 'sole', label: 'In their name only' }, { key: 'joint', label: 'Jointly with someone still living' }, { key: 'unknown', label: 'Not sure' }],
}

it('lists what the client entered in plain language and lets them add an item', async () => {
  addClientPortalEstateAsset.mockResolvedValue({ ...estate, assets: [...estate.assets, { id: 'a3', name: 'Pickup', category: 'other', verification_status: 'unverified', editable: true }] })
  const onChange = vi.fn()
  const { container } = render(<ClientPortalEstateTab estate={estate} onChange={onChange} />)
  expect(screen.getByText(/Please list what Ole Olson owned/)).toBeInTheDocument()
  expect(screen.getByText('Sent — the office will review it')).toBeInTheDocument()
  expect(screen.getByText('Checked by the office')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'Change' })).toHaveLength(1)
  expect(await axe(container)).toHaveNoViolations()

  fireEvent.click(screen.getByRole('button', { name: /Add an item/ }))
  fireEvent.change(screen.getByLabelText('What is it?'), { target: { value: 'Pickup' } })
  fireEvent.change(screen.getByLabelText('Whose name is it in?'), { target: { value: 'sole' } })
  fireEvent.change(screen.getByLabelText(/Roughly what is it worth/), { target: { value: '8,000' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add this item' }))
  await waitFor(() => expect(addClientPortalEstateAsset).toHaveBeenCalledWith(expect.objectContaining({ name: 'Pickup', ownership_type: 'sole', approximate_value: '8,000', category: 'other' })))
  await waitFor(() => expect(onChange).toHaveBeenCalled())
})

it('edits an unreviewed item and attaches a statement', async () => {
  uploadClientPortalDocument.mockResolvedValue({ id: 'doc-9' })
  updateClientPortalEstateAsset.mockResolvedValue(estate)
  render(<ClientPortalEstateTab estate={estate} onChange={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: 'Change' }))
  const file = new File(['%PDF-1.4'], 'statement.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText(/Attach a statement or photo/), { target: { files: [file] } })
  await screen.findByText('Attached: statement.pdf')
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await waitFor(() => expect(updateClientPortalEstateAsset).toHaveBeenCalledWith('a1', expect.objectContaining({ name: 'Checking at Gate City Bank', artifact_document_id: 'doc-9' })))
})

it('explains the wait when the inventory is not open yet', () => {
  render(<ClientPortalEstateTab estate={{ ...estate, inventory_open: false, assets: [] }} onChange={() => {}} />)
  expect(screen.getByText(/opens once the court has appointed the personal representative/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Add an item/ })).not.toBeInTheDocument()
  expect(statusLabel('rejected')).toBe('The office will follow up')
})

it('shows the server message when an item is refused', async () => {
  addClientPortalEstateAsset.mockRejectedValue({ response: { data: { detail: 'Enter the value as a number, for example 12,500.' } } })
  render(<ClientPortalEstateTab estate={estate} onChange={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: /Add an item/ }))
  fireEvent.change(screen.getByLabelText('What is it?'), { target: { value: 'Boat' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add this item' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Enter the value as a number')
})
