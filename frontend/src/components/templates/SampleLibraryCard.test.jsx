import { StrictMode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getSampleTemplates, getSampleTemplateSource } from '../../api'
import SampleLibraryCard from './SampleLibraryCard'

vi.mock('../../api', () => ({
  getSampleTemplates: vi.fn(),
  getSampleTemplateSource: vi.fn(),
}))

const samples = [
  {
    id: 'will-1',
    title: 'Last Will and Testament',
    category: 'will',
    jurisdictions: ['North Dakota'],
    field_count: 26,
    variable_schema: { version: 1, fields: [{ name: 'client_name', label: 'Client Name', field_type: 'text' }] },
  },
  {
    id: 'poa-1',
    title: 'Durable Power of Attorney',
    category: 'power_of_attorney',
    jurisdictions: ['Arizona'],
    field_count: 42,
    variable_schema: { version: 1, fields: [] },
  },
  {
    id: 'will-2',
    title: 'Alaska Last Will and Testament',
    category: 'will',
    jurisdictions: ['Alaska'],
    field_count: 57,
    variable_schema: { version: 1, fields: [] },
  },
  {
    id: 'lease-1',
    title: 'Alabama Residential Lease Agreement',
    category: 'lease',
    jurisdictions: ['Alabama'],
    field_count: 42,
    variable_schema: { version: 1, fields: [] },
  },
  {
    id: 'contract-1',
    title: 'Independent Contractor Agreement',
    category: 'contract',
    jurisdictions: [],
    field_count: 18,
    variable_schema: { version: 1, fields: [] },
  },
]

function rowFor(title) {
  return screen.getByText(title).closest('li')
}

describe('SampleLibraryCard', () => {
  beforeEach(() => {
    getSampleTemplates.mockResolvedValue({ items: samples, total: 2 })
  })
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('loads samples grouped by type and ordered by jurisdiction', async () => {
    render(<SampleLibraryCard />)
    await waitFor(() => expect(getSampleTemplates).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('Last Will and Testament')).toBeInTheDocument()
    const headings = screen.getAllByRole('heading', { level: 3 }).map((node) => node.textContent)
    expect(headings).toEqual(['Contract', 'Lease', 'Power of Attorney', 'Will'])
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    const willSection = screen.getByRole('heading', { name: 'Will' }).closest('section')
    const willRows = within(willSection).getAllByRole('listitem')
    expect(willRows[0]).toHaveTextContent('Alaska Last Will and Testament')
    expect(willRows[1]).toHaveTextContent('North Dakota · 26 fields')
    expect(screen.getByText('Alabama · 42 fields')).toBeInTheDocument()
    expect(rowFor('Independent Contractor Agreement')).toHaveTextContent('General')
  })

  it('collapses each type by default and toggles it open', async () => {
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    // Collapsed by default: rows are not in the accessibility tree yet.
    expect(screen.queryByRole('button', { name: 'Preview' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Will' })).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Will' }))
    expect(screen.getByRole('button', { name: 'Will' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('button', { name: 'Preview' })).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }))
    expect(screen.queryByRole('button', { name: 'Preview' })).not.toBeInTheDocument()
  })

  it('searches by title and opens only the matching groups', async () => {
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'alaska' } })
    expect(screen.getByText('Alaska Last Will and Testament')).toBeInTheDocument()
    expect(screen.queryByText('Alabama Residential Lease Agreement')).not.toBeInTheDocument()
    // The matching group is forced open while searching.
    expect(screen.getByRole('button', { name: 'Preview' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: '' } })
    expect(screen.queryByRole('button', { name: 'Preview' })).not.toBeInTheDocument()
  })

  it('exposes the full title as a tooltip on truncated rows', async () => {
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    expect(screen.getByText('Alabama Residential Lease Agreement')).toHaveAttribute(
      'title',
      'Alabama Residential Lease Agreement',
    )
  })

  it('filters the list by category and jurisdiction', async () => {
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'power_of_attorney' } })
    expect(screen.queryByText('Last Will and Testament')).not.toBeInTheDocument()
    expect(screen.getByText('Durable Power of Attorney')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'all' } })
    fireEvent.change(screen.getByLabelText('Jurisdiction'), { target: { value: 'North Dakota' } })
    expect(screen.getByText('Last Will and Testament')).toBeInTheDocument()
    expect(screen.queryByText('Durable Power of Attorney')).not.toBeInTheDocument()
  })

  it('opens a source preview in StrictMode without requiring a popup', async () => {
    const popup = vi.spyOn(window, 'open').mockReturnValue(null)
    const source = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    let resolveSource
    getSampleTemplateSource.mockImplementation(() => new Promise((resolve) => { resolveSource = resolve }))
    render(<StrictMode><SampleLibraryCard /></StrictMode>)
    await screen.findByText('Durable Power of Attorney')
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    fireEvent.click(within(rowFor('Last Will and Testament')).getByRole('button', { name: 'Preview' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Loading PDF preview')
    await waitFor(() => expect(getSampleTemplateSource).toHaveBeenCalledWith('will-1'))
    resolveSource(source)
    expect(await screen.findByRole('region', { name: 'Preview of Last Will and Testament' })).toBeInTheDocument()
    expect(popup).not.toHaveBeenCalled()
  })

  it('shows a retryable alert when the preview cannot be loaded', async () => {
    getSampleTemplateSource.mockRejectedValue(new Error('offline'))
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    fireEvent.click(within(rowFor('Last Will and Testament')).getByRole('button', { name: 'Preview' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
    expect(screen.getByRole('button', { name: 'Retry preview' })).toBeInTheDocument()
  })

  it('ignores a source response after the preview is closed', async () => {
    let resolveSource
    getSampleTemplateSource.mockImplementation(() => new Promise((resolve) => { resolveSource = resolve }))
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    fireEvent.click(within(rowFor('Last Will and Testament')).getByRole('button', { name: 'Preview' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close PDF preview' }))
    resolveSource(new Blob(['late']))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.queryByRole('region', { name: 'Preview of Last Will and Testament' })).not.toBeInTheDocument()
  })

  it('opens the fill dialog and closes it again', async () => {
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    fireEvent.click(within(rowFor('Last Will and Testament')).getByRole('button', { name: 'Fill' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Fill “Last Will and Testament”' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('lists the firm paperwork first, under its own labels', async () => {
    // The fee agreement and the two intake forms are what a firm opens a matter
    // with, so they lead the catalog rather than sorting alphabetically into it.
    getSampleTemplates.mockResolvedValue({
      items: [
        ...samples,
        {
          id: 'fee-1',
          title: 'Fee Agreement — Legal Services (All Matter Types)',
          category: 'engagement_letter',
          jurisdictions: [],
          field_count: 100,
          variable_schema: { version: 1, fields: [] },
        },
        {
          id: 'intake-1',
          title: 'Prospective Client Intake Form',
          category: 'intake',
          jurisdictions: [],
          field_count: 71,
          variable_schema: { version: 1, fields: [] },
        },
      ],
      total: 7,
    })
    render(<SampleLibraryCard />)
    await screen.findByText('Durable Power of Attorney')
    const headings = screen.getAllByRole('heading', { level: 3 }).map((node) => node.textContent)
    expect(headings.slice(0, 2)).toEqual(['Fee Agreement', 'Client Intake'])
  })

  it('shows a load error when the catalog fails', async () => {
    getSampleTemplates.mockRejectedValue(new Error('offline'))
    render(<SampleLibraryCard />)
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
  })
})

describe('SampleLibraryCard duplicate-titled variants', () => {
  // #504: four titles repeat across the catalog and the files behind them are
  // genuinely different. The list has to make that visible without inventing a
  // label for forms whose source was never recorded.
  const variants = [
    {
      id: 'nd-divorce',
      title: 'ND Divorce',
      category: 'court_form',
      jurisdictions: ['North Dakota'],
      field_count: 9,
      variable_schema: { version: 1, fields: [] },
    },
    {
      id: 'nd-divorce-2',
      title: 'ND Divorce',
      category: 'court_form',
      jurisdictions: ['North Dakota'],
      field_count: 91,
      variable_schema: { version: 1, fields: [] },
    },
    {
      id: 'nd-general',
      title: 'ND General',
      category: 'court_form',
      jurisdictions: ['North Dakota'],
      field_count: 10,
      variable_schema: { version: 1, fields: [] },
      provenance: { source_name: 'ND Supreme Court', edition: 'Rev. 03/2024' },
    },
    {
      id: 'nd-general-2',
      title: 'ND General',
      category: 'court_form',
      jurisdictions: ['North Dakota'],
      field_count: 74,
      variable_schema: { version: 1, fields: [] },
      provenance: { source_name: 'ND Supreme Court', edition: 'Rev. 11/2019' },
    },
    {
      id: 'unique-1',
      title: 'Arizona Living Will',
      category: 'advance_directive',
      jurisdictions: ['Arizona'],
      field_count: 30,
      variable_schema: { version: 1, fields: [] },
    },
  ]

  beforeEach(() => {
    getSampleTemplates.mockResolvedValue({ items: variants, total: variants.length })
  })
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('numbers same-titled forms and leaves unique titles alone', async () => {
    render(<SampleLibraryCard />)
    fireEvent.click(await screen.findByRole('button', { name: 'Expand all' }))

    const rows = screen.getAllByText('ND Divorce').map((node) => node.closest('li'))
    expect(rows).toHaveLength(2)
    // Ordered by field count, so the numbering reads as a series.
    expect(within(rows[0]).getByText('Version 1 of 2')).toBeInTheDocument()
    expect(within(rows[0]).getByText(/9 fields/)).toBeInTheDocument()
    expect(within(rows[1]).getByText('Version 2 of 2')).toBeInTheDocument()

    const unique = screen.getByText('Arizona Living Will').closest('li')
    expect(within(unique).queryByText(/Version \d of/)).not.toBeInTheDocument()
  })

  it('warns that the source was not recorded, and stops warning once it is', async () => {
    render(<SampleLibraryCard />)
    fireEvent.click(await screen.findByRole('button', { name: 'Expand all' }))

    const unrecorded = screen.getAllByText('ND Divorce')[0].closest('li')
    expect(
      within(unrecorded).getByText(/Source file: .*preview before filing/i),
    ).toBeInTheDocument()

    const recorded = screen.getAllByText('ND General')[0].closest('li')
    expect(
      within(recorded).queryByText(/was not recorded/i),
    ).not.toBeInTheDocument()
    expect(
      within(recorded).getByText(/ND Supreme Court · Rev\. 03\/2024/),
    ).toBeInTheDocument()
  })

  it('searches provenance so an edition finds its form', async () => {
    render(<SampleLibraryCard />)
    await screen.findByRole('button', { name: 'Expand all' })

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'Rev. 11/2019' } })

    expect(screen.getByText('ND General')).toBeInTheDocument()
    expect(screen.queryByText('ND Divorce')).not.toBeInTheDocument()
  })
})
