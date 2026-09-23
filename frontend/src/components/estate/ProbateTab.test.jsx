import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { axe } from 'jest-axe'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ProbateTab, { factsToForm, formToFacts, printHint } from './ProbateTab'
import {
  getProbate, installProbateForms, pullProbateFactsFromIntake, recomputeProbate,
  saveProbateAnchors, saveProbateFacts, syncProbateDeadlines,
} from '../../api'

vi.mock('../../api', () => ({
  getProbate: vi.fn(), saveProbateFacts: vi.fn(), pullProbateFactsFromIntake: vi.fn(),
  recomputeProbate: vi.fn(), saveProbateAnchors: vi.fn(), syncProbateDeadlines: vi.fn(),
  listProbateForms: vi.fn(), installProbateForms: vi.fn(), getTemplate: vi.fn(),
}))
vi.mock('../../pages/TemplatesPage', () => ({ RenderModal: () => <div>render modal</div> }))
afterEach(cleanup)
beforeEach(() => vi.resetAllMocks())

const forms = [
  { number: 2, key: 'form_02', title: 'Application for Informal Probate of Will', pages: [26, 28], required: true, slug: 'nd-informal-probate-guidebook', template_id: null, template_status: null, published: false, statute: '30.1-14-01' },
  { number: 6, key: 'form_06', title: 'Notice to Creditors', pages: [34, 34], required: false, slug: 'nd-informal-probate-guidebook', template_id: null, published: false, statute: '30.1-19-01' },
  { number: null, key: 'nd-probate-claim-against-estate', title: 'ND Probate — Claim Against Estate', pages: null, required: false, slug: 'nd-probate-claim-against-estate', template_id: null, published: false },
]

const state = {
  estate_id: 'estate-1', matter_id: 'matter-1',
  facts: { decedent_name: 'Ole Olson', date_of_death: '2025-01-15', will_exists: true, heirs: [{ name: 'Ann Olson', age: '70', relationship: 'spouse', address: 'Fargo' }], nd_property_counties: ['Cass'] },
  determination: {
    track: 'informal_testate', label: 'Informal probate of will and appointment of personal representative',
    forms: [2, 3, 4, 5, 7], optional_forms: [6, 10], checklist: [], reasons: ['A will exists and less than three years have passed.'],
    warnings: ['The original will is not in hand.'], missing_facts: ['domicile_county'], alternatives: [], waiver_required: true,
    venue_county: 'Cass', venue_basis: 'the decedent was domiciled in Cass County',
  },
  determined_at: '2026-09-18T10:00:00Z',
  anchors: { date_of_death: '2025-01-15', appointment_date: null, first_publication_date: null, letters_issued_date: null, closing_statement_filed_date: null },
  forms,
  deadlines_preview: { deadlines: [{ deadline_type: 'tax_706', title: 'Federal estate tax return', due_date: '2025-10-15', statute: 'IRC 6075(a)', note: '', anchor_used: 'date_of_death' }], waiting_on: { appointment_date: ['notice_heirs', 'inventory'] } },
  sources: [{ kind: 'portal_questionnaire' }],
}

function renderTab(estate = { id: 'estate-1', matter_id: 'matter-1' }) {
  return render(<MemoryRouter><ProbateTab estate={estate} onChanged={() => {}} /></MemoryRouter>)
}

it('shows the determination, the print pages for each form, and the clock', async () => {
  getProbate.mockResolvedValue(state)
  const { container } = renderTab()
  expect(await screen.findByText(/Informal probate of will/)).toBeInTheDocument()
  expect(screen.getByText(/A will exists and less than three years/)).toBeInTheDocument()
  expect(screen.getByText(/The original will is not in hand/)).toBeInTheDocument()
  expect(screen.getByText(/Waiver of Right to Appointment/)).toBeInTheDocument()
  expect(screen.getByText('print pages 26–28')).toBeInTheDocument()
  expect(screen.getByText('when needed')).toBeInTheDocument()
  expect(screen.getByText('2025-10-15')).toBeInTheDocument()
  expect(screen.getByText(/Waiting on: appointment date \(2\)/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Generate filled packet/ })).toBeDisabled()
  expect(screen.getByText(/Install the ND probate pack first/)).toBeInTheDocument()
  expect(await axe(container)).toHaveNoViolations()
})

it('saves the facts form as typed values and installs the pack on request', async () => {
  const user = userEvent.setup()
  getProbate.mockResolvedValue(state)
  saveProbateFacts.mockResolvedValue(state)
  installProbateForms.mockResolvedValue({ templates: [] })
  renderTab()
  await screen.findByText(/Informal probate of will/)
  await user.type(screen.getByLabelText('County they lived in'), 'Cass')
  await user.selectOptions(screen.getByLabelText('Did they leave a will?'), 'no')
  await user.click(screen.getByRole('button', { name: /Save facts and determine track/ }))
  await waitFor(() => expect(saveProbateFacts).toHaveBeenCalledWith('estate-1', expect.objectContaining({
    decedent_name: 'Ole Olson', domicile_county: 'Cass', will_exists: false, nd_property_counties: ['Cass'],
    heirs: [{ name: 'Ann Olson', age: '70', relationship: 'spouse', address: 'Fargo' }],
  })))
  await user.click(screen.getByRole('button', { name: /Install ND probate pack/ }))
  await waitFor(() => expect(installProbateForms).toHaveBeenCalled())
  expect(await screen.findByText(/installed as drafts/)).toBeInTheDocument()
})

it('pulls answers from the questionnaire, recomputes, saves anchors and builds deadlines', async () => {
  const user = userEvent.setup()
  getProbate.mockResolvedValue(state)
  pullProbateFactsFromIntake.mockResolvedValue(state)
  recomputeProbate.mockResolvedValue(state)
  saveProbateAnchors.mockResolvedValue(state)
  syncProbateDeadlines.mockResolvedValue({ created: ['notice_heirs'], updated: [], unchanged: [], waiting_on: {} })
  renderTab()
  await screen.findByText(/Informal probate of will/)
  await user.click(screen.getByRole('button', { name: /Pull from client questionnaire/ }))
  await waitFor(() => expect(pullProbateFactsFromIntake).toHaveBeenCalledWith('estate-1', { overwrite: false }))
  await user.click(screen.getByRole('button', { name: /Recompute/ }))
  await waitFor(() => expect(recomputeProbate).toHaveBeenCalledWith('estate-1'))
  const appointment = screen.getByLabelText('Appointment date')
  fireEvent.change(appointment, { target: { value: '2025-03-31' } })
  await waitFor(() => expect(appointment).toHaveValue('2025-03-31'))
  await user.click(screen.getByRole('button', { name: 'Save dates' }))
  await waitFor(() => expect(saveProbateAnchors).toHaveBeenCalledWith('estate-1', expect.objectContaining({ appointment_date: '2025-03-31', date_of_death: '2025-01-15' })))
  await user.click(screen.getByRole('button', { name: /Build deadlines/ }))
  await waitFor(() => expect(syncProbateDeadlines).toHaveBeenCalledWith('estate-1', { mirror_tasks: true }))
  expect(await screen.findByText(/1 deadline\(s\) created/)).toBeInTheDocument()
})

it('lists the firm-drafted pleadings for a formal track and explains why', async () => {
  getProbate.mockResolvedValue({
    ...state,
    determination: { ...state.determination, track: 'formal_intestate_late', label: 'Formal adjudication of intestacy', forms: [], optional_forms: [], checklist: ['Petition for adjudication of intestacy', 'Notice of hearing'], waiver_required: false },
  })
  renderTab()
  expect(await screen.findByText(/The court publishes no forms for this proceeding/)).toBeInTheDocument()
  expect(screen.getByText('Petition for adjudication of intestacy')).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: /Upload as template/ })).toHaveLength(2)
})

it('disables intake and generation without a linked matter', async () => {
  getProbate.mockResolvedValue({ ...state, matter_id: null, determination: null })
  renderTab({ id: 'estate-1', matter_id: null })
  expect(await screen.findByText(/No determination yet/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Send probate intake/ })).toBeDisabled()
  expect(screen.getByRole('button', { name: /Pull from client questionnaire/ })).toBeDisabled()
  expect(screen.getByText(/Link this estate to a matter to generate/)).toBeInTheDocument()
})

it('warns when the estate jurisdiction is not supported yet', async () => {
  getProbate.mockResolvedValue({ ...state, jurisdiction_supported: false, jurisdiction: null, jurisdiction_label: null, forms: [] })
  renderTab()
  expect(await screen.findByText(/does not yet support this estate's jurisdiction/)).toBeInTheDocument()
})

it('round-trips facts through the form helpers', () => {
  const form = factsToForm(state.facts)
  expect(form.will_exists).toBe('yes')
  expect(form.nd_property_counties).toBe('Cass')
  expect(form.heirs).toBe('Ann Olson; 70; spouse; Fargo')
  const facts = formToFacts({ ...form, heirs: 'Ann Olson; 70; spouse; Fargo\nBob; ; son', will_exists: '' })
  expect(facts.will_exists).toBeNull()
  expect(facts.heirs).toEqual([
    { name: 'Ann Olson', age: '70', relationship: 'spouse', address: 'Fargo' },
    { name: 'Bob', age: '', relationship: 'son', address: '' },
  ])
  expect(printHint({ pages: [31, 31] })).toBe('print page 31')
  expect(printHint({ pages: null })).toBe('')
})

it('sends a published packet to the Prepare route with the estate\'s matter chosen', async () => {
  const T = '11111111-1111-4111-8111-111111111111'
  const M = '22222222-2222-4222-8222-222222222222'
  const published = forms.map(row => row.number ? { ...row, template_id: T, template_status: 'published', published: true } : row)
  getProbate.mockResolvedValue({ ...state, matter_id: M, forms: published })
  function Location() { const loc = useLocation(); return <output aria-label="Location">{loc.pathname}{loc.search}</output> }
  render(<MemoryRouter><ProbateTab estate={{ id: 'estate-1', matter_id: M }} onChanged={() => {}} /><Location /></MemoryRouter>)
  const button = await screen.findByRole('button', { name: /Generate filled packet/ })
  expect(button).toBeEnabled()
  fireEvent.click(button)
  expect(screen.getByLabelText('Location')).toHaveTextContent(`/templates/prepare?template=${T}&matter=${M}&return=${encodeURIComponent(`/matters/${M}?tab=documents`)}`)
})
