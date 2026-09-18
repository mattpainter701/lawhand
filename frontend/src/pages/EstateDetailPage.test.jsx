import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import EstateDetailPage from './EstateDetailPage'
import { getEstate, updateEstate } from '../api'

vi.mock('../api', () => ({
  getEstate: vi.fn(), updateEstate: vi.fn(), addEstateEvent: vi.fn(),
  listEstateChildren: vi.fn(), getEstateAccountingSummary: vi.fn(), getEstateReport: vi.fn(), verifyEstateAsset: vi.fn(),
  getProbate: vi.fn(), saveProbateFacts: vi.fn(), pullProbateFactsFromIntake: vi.fn(), recomputeProbate: vi.fn(),
  saveProbateAnchors: vi.fn(), syncProbateDeadlines: vi.fn(), listProbateForms: vi.fn(), installProbateForms: vi.fn(), getTemplate: vi.fn(),
}))
vi.mock('../components/estate/ProbateTab', () => ({ default: ({ estate }) => <div>probate workbench for {estate.id}</div> }))
afterEach(cleanup)

it('saves corrected estate details with unknown dates and values while retaining known zero', async () => {
  const estate = { id: 'estate-1', estate_name: 'Estate of Example', date_of_death: '2026-01-02', gross_estate_value: 12000, net_estate_value: 0, status: 'active' }
  getEstate.mockResolvedValue(estate)
  updateEstate.mockImplementation(async (_, payload) => payload)
  render(<MemoryRouter initialEntries={['/estates/estate-1']}><Routes><Route path='/estates/:id' element={<EstateDetailPage />} /></Routes></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(screen.getByLabelText('Date of Death'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Gross Estate Value'), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  await waitFor(() => expect(updateEstate).toHaveBeenCalledWith('estate-1', expect.objectContaining({ date_of_death: null, gross_estate_value: null, net_estate_value: 0 })))
  expect(await screen.findByRole('button', { name: 'Edit', exact: true })).toBeInTheDocument()
})

it('offers a Probate tab that opens the workbench for this estate', async () => {
  getEstate.mockResolvedValue({ id: 'estate-2', estate_name: 'Estate of Olson', estate_type: 'probate', status: 'active', probate_track: 'informal_testate', domicile_county: 'Cass' })
  render(<MemoryRouter initialEntries={['/estates/estate-2']}><Routes><Route path='/estates/:id' element={<EstateDetailPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Cass')).toBeInTheDocument()
  expect(screen.getByText('informal testate')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Probate' }))
  expect(await screen.findByText('probate workbench for estate-2')).toBeInTheDocument()
})
