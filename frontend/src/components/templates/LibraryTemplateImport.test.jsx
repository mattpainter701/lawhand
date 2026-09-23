import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LibraryTemplateImport from './LibraryTemplateImport'

const harness = vi.hoisted(() => ({
  getSampleTemplate: vi.fn(),
  getSampleTemplateSource: vi.fn(),
}))
vi.mock('../../api', () => harness)

const SAMPLE_ID = '6b30c225-7c44-4d82-a832-e9a871f23102'
const SAMPLE_ID_UPPER = SAMPLE_ID.toUpperCase()
const pdfBytes = new Uint8Array([37, 80, 68, 70, 45, 49, 46, 55])
const digestBytes = new Uint8Array(32).fill(0xab)
const digestHex = [...digestBytes].map(value => value.toString(16).padStart(2, '0')).join('')
const sample = (overrides = {}) => ({
  id: SAMPLE_ID,
  title: 'Civil complaint',
  source_filename: 'C:\\catalog\\2025\\civil-complaint.pdf',
  source_sha256: digestHex.toUpperCase(),
  provenance: { source_name: 'Court forms', edition: '2025' },
  jurisdictions: ['California'],
  ...overrides,
})
const pdf = () => new Blob([pdfBytes], { type: 'application/pdf' })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const renderImport = (sampleId = SAMPLE_ID) => render(
  <LibraryTemplateImport sampleId={sampleId}>
    {({ sample: loadedSample, file }) => (
      <div data-testid="intake-source">{loadedSample.title}|{file.name}|{file.type}</div>
    )}
  </LibraryTemplateImport>,
)

beforeEach(() => {
  harness.getSampleTemplate.mockResolvedValue(sample())
  harness.getSampleTemplateSource.mockResolvedValue(pdf())
  vi.stubGlobal('crypto', {
    subtle: {
      digest: vi.fn(async (algorithm, buffer) => {
        expect(algorithm).toBe('SHA-256')
        expect([...new Uint8Array(buffer)]).toEqual([...pdfBytes])
        return digestBytes.buffer.slice(0)
      }),
    },
  })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('global library template intake source', () => {
  it('loads matching metadata and PDF bytes, verifies the source, and passes a basename File to intake', async () => {
    renderImport(SAMPLE_ID_UPPER)

    expect(await screen.findByTestId('intake-source')).toHaveTextContent('Civil complaint|civil-complaint.pdf|application/pdf')
    expect(harness.getSampleTemplate).toHaveBeenCalledWith(SAMPLE_ID)
    expect(harness.getSampleTemplateSource).toHaveBeenCalledWith(SAMPLE_ID)
    expect(crypto.subtle.digest).toHaveBeenCalledTimes(1)
  })

  it('does not expose a source to intake when the PDF digest does not match metadata', async () => {
    harness.getSampleTemplate.mockResolvedValue(sample({ source_sha256: '00'.repeat(32) }))
    renderImport()

    expect(await screen.findByRole('alert')).toHaveTextContent('The library form changed while loading')
    expect(screen.queryByTestId('intake-source')).not.toBeInTheDocument()
  })

  it('offers retry after a load error and then passes the loaded source to intake', async () => {
    harness.getSampleTemplate.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(sample())
    renderImport()

    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
    fireEvent.click(screen.getByRole('button', { name: 'Retry global template' }))

    expect(await screen.findByTestId('intake-source')).toHaveTextContent('Civil complaint|civil-complaint.pdf|application/pdf')
    expect(harness.getSampleTemplate).toHaveBeenCalledTimes(2)
    expect(harness.getSampleTemplateSource).toHaveBeenCalledTimes(2)
  })

  it('ignores an earlier sample response after a newer sample has loaded', async () => {
    const oldDetails = deferred()
    harness.getSampleTemplate.mockImplementation(id => id === SAMPLE_ID ? oldDetails.promise : Promise.resolve(sample({ id: '6b30c225-7c44-4d82-a832-e9a871f23103', title: 'Newer complaint', source_filename: 'newer.pdf' })))
    const view = renderImport(SAMPLE_ID)
    view.rerender(
      <LibraryTemplateImport sampleId="6b30c225-7c44-4d82-a832-e9a871f23103">
        {({ sample: loadedSample, file }) => <div data-testid="intake-source">{loadedSample.title}|{file.name}</div>}
      </LibraryTemplateImport>,
    )

    expect(await screen.findByTestId('intake-source')).toHaveTextContent('Newer complaint|newer.pdf')
    oldDetails.resolve(sample({ title: 'Stale complaint' }))
    await waitFor(() => expect(screen.getByTestId('intake-source')).toHaveTextContent('Newer complaint|newer.pdf'))
    expect(screen.queryByText(/Stale complaint/)).not.toBeInTheDocument()
  })

  it('rejects a malformed sample id without making catalog requests', async () => {
    renderImport('not-a-server-id')

    expect(await screen.findByRole('alert')).toHaveTextContent('global template link is invalid')
    expect(harness.getSampleTemplate).not.toHaveBeenCalled()
    expect(harness.getSampleTemplateSource).not.toHaveBeenCalled()
  })
})
