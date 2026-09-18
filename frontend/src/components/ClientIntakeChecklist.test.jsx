import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { axe } from 'jest-axe'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ClientIntakeChecklist, { DONT_KNOW, readDraft, writeDraft } from './ClientIntakeChecklist'
import { getClientIntake, submitClientIntake } from '../api'

vi.mock('../api', () => ({
  default: { post: vi.fn() },
  getClientIntake: vi.fn(),
  submitClientIntake: vi.fn(),
  uploadClientPortalDocument: vi.fn(),
  downloadClientPortalDocumentUrl: vi.fn(() => '#'),
}))
afterEach(() => { cleanup(); window.localStorage.clear() })
beforeEach(() => vi.resetAllMocks())

const packet = {
  id: 'packet-1',
  status: 'awaiting_documents',
  requirements: { questionnaire: { completed: false, required: true, kind: 'questionnaire' } },
  answers: {},
  questions: [
    { key: 'date_of_death', label: 'Date of death', required: true, kind: 'date' },
    { key: 'will_exists', label: 'Did they leave a will?', required: true, kind: 'yes_no', help: 'Answer no if you are not aware of one.' },
    { key: 'domicile_state', label: 'Which state did they live in?', required: true, kind: 'select', options: ['North Dakota', 'Minnesota'] },
    { key: 'probate_property_value', label: 'Rough value', required: false, kind: 'money' },
    { key: 'assets_summary', label: 'What did they own?', required: false },
  ],
}

it('renders typed controls, keeps a draft on this device, and sends the answers', async () => {
  getClientIntake.mockResolvedValue(packet)
  submitClientIntake.mockResolvedValue({ ...packet, requirements: { questionnaire: { completed: true, required: true, kind: 'questionnaire' } } })
  const { container } = render(<ClientIntakeChecklist onSign={() => {}} />)
  const dateInput = await screen.findByLabelText('Date of death *')
  expect(dateInput).toHaveAttribute('type', 'date')
  expect(screen.getByText('Answer no if you are not aware of one.')).toBeInTheDocument()
  fireEvent.change(dateInput, { target: { value: '2025-01-15' } })
  fireEvent.click(screen.getByLabelText('Yes'))
  fireEvent.change(screen.getByLabelText('Which state did they live in? *'), { target: { value: 'North Dakota' } })
  expect(screen.getByLabelText('Rough value')).toHaveAttribute('inputmode', 'decimal')
  fireEvent.click(screen.getAllByLabelText(new RegExp(DONT_KNOW))[1])
  expect(readDraft('packet-1')).toEqual({ date_of_death: '2025-01-15', will_exists: 'yes', domicile_state: 'North Dakota', assets_summary: DONT_KNOW })
  fireEvent.click(screen.getByRole('button', { name: 'Save and finish later' }))
  expect(screen.getByRole('status')).toHaveTextContent('Saved on this device')
  expect(await axe(container)).toHaveNoViolations()

  fireEvent.click(screen.getByRole('button', { name: 'Send my answers' }))
  await waitFor(() => expect(submitClientIntake).toHaveBeenCalledWith({ date_of_death: '2025-01-15', will_exists: 'yes', domicile_state: 'North Dakota', assets_summary: DONT_KNOW }))
  await waitFor(() => expect(readDraft('packet-1')).toBeNull())
})

it('restores a saved draft when the client comes back', async () => {
  writeDraft('packet-1', { date_of_death: '2025-02-02' })
  getClientIntake.mockResolvedValue(packet)
  render(<ClientIntakeChecklist onSign={() => {}} />)
  expect(await screen.findByLabelText('Date of death *')).toHaveValue('2025-02-02')
})

it('shows the server message when an answer is refused', async () => {
  getClientIntake.mockResolvedValue(packet)
  submitClientIntake.mockRejectedValue({ response: { status: 422, data: { detail: 'Enter a date as YYYY-MM-DD for: Date of death' } } })
  render(<ClientIntakeChecklist onSign={() => {}} />)
  await screen.findByLabelText('Date of death *')
  fireEvent.submit(screen.getByRole('button', { name: 'Send my answers' }).closest('form'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Enter a date as YYYY-MM-DD')
})
