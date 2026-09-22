import { useEffect, useId, useRef, useState } from 'react'
import { Download, Loader2, X } from 'lucide-react'
import GeneratedPdfPreview from './GeneratedPdfPreview'

/** Accessible in-app PDF preview that never relies on the browser PDF plug-in. */
export default function PdfPreviewDialog({ title, source, loading = false, error = '', onClose, onRetry, filename = 'preview.pdf' }) {
  const dialogRef = useRef(null)
  const closeRef = useRef(null)
  const previousFocus = useRef(null)
  const [downloadUrl, setDownloadUrl] = useState('')

  useEffect(() => {
    previousFocus.current = document.activeElement
    closeRef.current?.focus()
    return () => previousFocus.current?.focus?.()
  }, [])

  useEffect(() => {
    if (!dialogRef.current?.contains(document.activeElement)) closeRef.current?.focus()
  }, [loading, error, source])

  useEffect(() => {
    if (!source) {
      setDownloadUrl('')
      return undefined
    }
    const url = URL.createObjectURL(source)
    setDownloadUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [source])

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll('button:not([disabled]), a[href], select:not([disabled]), input:not([disabled]), textarea:not([disabled])')
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!dialogRef.current.contains(document.activeElement)) {
        event.preventDefault()
        first.focus()
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const headingId = useId()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 sm:p-6" role="presentation">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={headingId} className="flex max-h-[calc(100vh-1.5rem)] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-brand-line bg-brand-surface shadow-xl sm:max-h-[calc(100vh-3rem)]">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-brand-line bg-brand-surface-2 px-4 py-3">
          <h2 id={headingId} className="min-w-0 truncate text-sm font-semibold text-brand-ink">Preview: {title}</h2>
          <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-1.5 text-brand-muted hover:bg-brand-bg hover:text-brand-ink" aria-label="Close PDF preview">
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="min-h-0 overflow-auto p-3 sm:p-5">
          {loading && <p role="status" className="flex items-center gap-2 rounded-lg border border-dashed border-brand-line px-3 py-6 text-sm text-brand-muted"><Loader2 size={16} className="animate-spin" aria-hidden="true" /> Loading PDF preview…</p>}
          {error && !loading && (
            <div className="rounded-lg border border-dashed border-brand-line px-3 py-6 text-sm text-brand-muted">
              <p role="alert">{error}</p>
              {onRetry && <button type="button" onClick={onRetry} className="mt-3 rounded-lg bg-brand-ink px-3 py-2 text-xs font-semibold text-white">Retry preview</button>}
            </div>
          )}
          {source && !loading && !error && <GeneratedPdfPreview source={source} title={title} />}
        </div>
        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-brand-line px-4 py-3 text-xs text-brand-muted">
          <span>Review every page before saving or using this document.</span>
          {downloadUrl && <a href={downloadUrl} download={filename} className="inline-flex items-center gap-1.5 rounded-lg border border-brand-line px-3 py-2 font-semibold text-brand-ink hover:bg-brand-bg"><Download size={14} aria-hidden="true" /> Download PDF</a>}
        </footer>
      </div>
    </div>
  )
}
