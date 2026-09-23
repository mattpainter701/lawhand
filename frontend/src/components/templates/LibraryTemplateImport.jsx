import { useEffect, useState } from 'react'
import { getSampleTemplate, getSampleTemplateSource } from '../../api'
import { canonicalStudioServerId } from './studioRouting'

// The catalog stays read-only. Its verified source enters the same analysis,
// review and inactive-draft creation workflow as an uploaded document.
export default function LibraryTemplateImport({ sampleId, children }) {
  const [loaded, setLoaded] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let cancelled = false
    setLoaded(null)
    setError('')
    const id = canonicalStudioServerId(sampleId)
    if (!id) {
      setError('This global template link is invalid. Return to the library and choose a form.')
      return undefined
    }
    async function load() {
      try {
        const [sample, blob] = await Promise.all([getSampleTemplate(id), getSampleTemplateSource(id)])
        const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
        const sha256 = [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('')
        if (sha256 !== String(sample.source_sha256 || '').toLowerCase()) {
          throw new Error('The library form changed while loading. Retry to load its current source and fields together.')
        }
        const filename = String(sample.source_filename || 'library-template.pdf').split(/[\\/]/).at(-1)
        const file = new File([blob], filename, { type: 'application/pdf' })
        if (!cancelled) setLoaded({ sample, file })
      } catch (failure) {
        if (!cancelled) setError(failure?.message?.startsWith('The library form changed')
          ? failure.message : 'This global template could not be loaded. Retry or return to the library.')
      }
    }
    void load()
    return () => { cancelled = true }
  }, [sampleId, attempt])
  if (error) return <div role="alert" className="space-y-3"><p>{error}</p><button type="button" onClick={() => setAttempt(value => value + 1)} className="rounded border border-brand-line px-3 py-2">Retry global template</button></div>
  if (!loaded) return <p role="status">Loading global template…</p>
  const { sample } = loaded
  const provenance = sample.provenance || {}
  const sourceLabel = [provenance.source_name, provenance.edition].filter(value => typeof value === 'string' && value).join(' · ')
  return <div className="space-y-4">
    <div className="rounded-lg border border-brand-line bg-brand-bg p-3 text-sm">
      <p className="font-semibold">Global library · {sample.title}</p>
      {sourceLabel && <p className="text-brand-muted">{sourceLabel}</p>}
      {sample.jurisdictions?.length > 0 && <p className="text-brand-muted">{sample.jurisdictions.join(', ')}</p>}
      <p className="mt-1 text-brand-muted">Create a firm draft from this source. Review its wording and suggested field mappings, then test and publish it before saving documents to a matter.</p>
    </div>
    {children(loaded)}
  </div>
}
