import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TemplateStudioHome from './TemplateStudioHome'

vi.mock('./StarterPaperworkCard', () => ({ default: () => null }))
vi.mock('./SampleLibraryCard', () => ({ default: () => null }))

afterEach(cleanup)

const queue = (items) => ({ total: items.length, items })
const renderHome = (items) => render(
  <MemoryRouter>
    <TemplateStudioHome
      templates={[]}
      summary={{ total: 0, active: 0, inactive: 0, ready: 0, source_missing: 0 }}
      queues={{
        needs_attention: queue([]),
        continue_setup: queue(items),
        awaiting_publish: queue([]),
        published: queue([]),
      }}
      onRefresh={vi.fn()}
    />
  </MemoryRouter>,
)

describe('fill coverage in the library', () => {
  it('does not put paused published templates in the draft queue fallback', () => {
    render(
      <MemoryRouter>
        <TemplateStudioHome
          templates={[
            { id: 'paused', title: 'Paused', is_active: false, status: 'paused' },
            { id: 'draft', title: 'Draft', is_active: false, status: 'draft' },
          ]}
          summary={{ total: 2, active: 0, inactive: 2, ready: 0, source_missing: 0 }}
          onRefresh={vi.fn()}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Continue setup' }).parentElement).toHaveTextContent('1')
    expect(screen.getByText('Draft')).toBeInTheDocument()
    expect(screen.queryByText('Paused')).not.toBeInTheDocument()
  })

  // The number that decides whether a template is worth having was previously
  // reachable only by opening each one in an editor, which is no way to
  // compare them.
  it('says how much of each template fills from the matter', () => {
    renderHome([
      { id: '1', title: 'Client questionnaire', format: 'pdf', fill_coverage: { total: 41, fills: 13 } },
    ])

    expect(screen.getByText('13 of 41 fields fill from the matter')).toBeInTheDocument()
  })

  it('stays quiet about a template that has no fields yet', () => {
    // "0 of 0" on a template nobody has set up is noise, not information.
    renderHome([{ id: '2', title: 'Empty draft', format: 'markdown', fill_coverage: { total: 0, fills: 0 } }])

    expect(screen.getByText('Empty draft')).toBeInTheDocument()
    expect(screen.queryByText(/fill from the matter/)).not.toBeInTheDocument()
  })

  it('renders a template from a server that does not report coverage', () => {
    renderHome([{ id: '3', title: 'Older response', format: 'docx' }])

    expect(screen.getByText('Older response')).toBeInTheDocument()
  })
})
