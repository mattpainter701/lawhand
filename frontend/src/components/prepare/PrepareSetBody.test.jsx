import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PrepareSetBody from './PrepareSetBody'

vi.mock('./MatterPicker', () => ({ default: () => null }))
vi.mock('../templates/TemplateFillProgress', () => ({ default: () => null }))
vi.mock('./SendStep', () => ({ default: () => null }))
vi.mock('./prepareRouting', () => ({ buildSavedTarget: () => '/matters/m' }))

const prep = {
  questions: [{
    key: 'manual:markdown:venue', label: 'Venue', value_kind: 'choice', options: ['Court', 'Remote'],
    required: true, card: '', appears_in: [{ template_id: 'md', template_title: 'Notice', field_name: 'venue' }],
  }],
  unavailable: [],
  availableMembers: [{ template_id: 'md', title: 'Notice', output: { format: 'markdown', file: false }, resolved_version_no: 1 }],
  error: '', matterId: 'm', selectMatter: vi.fn(), answers: {}, setAnswer: vi.fn(), setReviewedValues: vi.fn(),
  toggleVerified: vi.fn(), fieldFilter: 'all', setFieldFilter: vi.fn(), filteredKeys: ['manual:markdown:venue'],
  nextField: vi.fn(), progress: { rows: [{ name: 'manual:markdown:venue', present: false, documents: 1 }], remaining: [], review: [], completed: 0, total: 1 },
  requiredUnresolvedNames: [], smartFillState: 'ready', smartFillMessage: '', refresh: vi.fn(),
  previewOf: () => ({ status: 'ready', rendered: 'Ada Lovelace — Remote' }), saveOf: () => null,
  generating: false, saving: false, generateAll: vi.fn(), saveAll: vi.fn(), allPreviewed: true, allSaved: false,
  sendable: [], session: null, background: null, saveAllInBackground: vi.fn(),
}

describe('PrepareSetBody packet controls', () => {
  it('keeps choice fields selectable and exposes Markdown output for review', () => {
    render(<PrepareSetBody prep={prep} matters={[]} matterLoading={false} fixedMatterId="m" returnTo="/templates/prepare" />)

    expect(screen.getByRole('combobox', { name: /Venue/ })).toHaveDisplayValue('Choose Venue')
    expect(screen.getByRole('option', { name: 'Court' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Remote' })).toBeInTheDocument()
    expect(screen.getByText('Review Markdown preview')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace — Remote')).toBeInTheDocument()
  })
})
