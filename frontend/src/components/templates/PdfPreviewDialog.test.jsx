import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PdfPreviewDialog from './PdfPreviewDialog'

const generated = vi.fn(({ source }) => <output aria-label="generated-preview">{source.type}</output>)
vi.mock('./GeneratedPdfPreview', () => ({ default: (props) => generated(props) }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('PdfPreviewDialog', () => {
  it('shows loading immediately, then forwards the exact source blob and download name', () => {
    const source = new Blob(['pdf'], { type: 'application/pdf' })
    const createObjectURL = vi.fn(() => 'blob:download')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const onClose = vi.fn()
    const { rerender, unmount } = render(<PdfPreviewDialog title="Source form" loading onClose={onClose} filename="source.pdf" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading PDF preview')
    rerender(<PdfPreviewDialog title="Source form" source={source} onClose={onClose} filename="source.pdf" />)
    expect(generated).toHaveBeenCalledWith(expect.objectContaining({ source }))
    expect(screen.getByRole('link', { name: /Download PDF/ })).toHaveAttribute('href', 'blob:download')
    expect(screen.getByRole('link', { name: /Download PDF/ })).toHaveAttribute('download', 'source.pdf')
    unmount()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:download')
  })

  it('closes on Escape and restores focus', () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    const onClose = vi.fn()
    const { unmount } = render(<PdfPreviewDialog title="Source form" onClose={onClose} />)
    expect(screen.getByRole('button', { name: 'Close PDF preview' })).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    unmount()
    expect(trigger).toHaveFocus()
    trigger.remove()
  })

  it('keeps the dialog editable on errors and retries', () => {
    const onRetry = vi.fn()
    const onClose = vi.fn()
    const { rerender } = render(<PdfPreviewDialog title="Source form" error="Network error" onRetry={onRetry} onClose={onClose} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Network error')
    screen.getByRole('button', { name: 'Retry preview' }).focus()
    fireEvent.click(screen.getByRole('button', { name: 'Retry preview' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
    rerender(<PdfPreviewDialog title="Source form" loading onClose={onClose} />)
    expect(screen.getByRole('button', { name: 'Close PDF preview' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Close PDF preview' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('traps focus within the dialog', () => {
    render(<PdfPreviewDialog title="Source form" source={new Blob(['pdf'])} onClose={vi.fn()} />)
    const close = screen.getByRole('button', { name: 'Close PDF preview' })
    const download = screen.getByRole('link', { name: /Download PDF/ })
    download.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(close).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(download).toHaveFocus()
  })
})
