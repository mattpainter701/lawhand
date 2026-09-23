import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSampleTemplateSource, getSampleTemplates, getTemplate, getTemplates } from '../../api'
import PdfPreviewDialog from './PdfPreviewDialog'

const RenderModal = lazy(() => import('../../pages/TemplatesPage').then(module => ({ default: module.RenderModal })))
const PAGE_SIZE = 20
const PREPARATION_CONTEXT = (matterId, folderId) => ({
  preparationContext: {
    matterId,
    folderId: folderId || null,
    returnTo: `/matters/${encodeURIComponent(matterId)}?tab=documents`,
  },
})

function sampleSearchText(sample) {
  const provenance = sample.provenance || {}
  return [sample.title, sample.category, ...(sample.jurisdictions || []), provenance.source_name, provenance.edition, provenance.source, sample.source_name, sample.edition]
    .filter(Boolean).join(' ').toLowerCase()
}

export default function MatterTemplatePicker({ matterId, folderId, onClose, onSaved, initialTemplateId }) {
  const dialog = useRef(null)
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(0)
  const [globalPage, setGlobalPage] = useState(0)
  const [firmRetry, setFirmRetry] = useState(0)
  const [globalRetry, setGlobalRetry] = useState(0)
  const [firm, setFirm] = useState({ items: [], total: 0, loading: true, error: '' })
  const [global, setGlobal] = useState({ items: [], loading: true, error: '' })
  const [selected, setSelected] = useState(null)
  const [directOpenFailed, setDirectOpenFailed] = useState(false)
  const [selecting, setSelecting] = useState(false)
  const [preview, setPreview] = useState(null)
  const previewRequest = useRef(0)

  useEffect(() => { const previous = document.activeElement; return () => previous?.focus?.() }, [])

  useEffect(() => {
    if (initialTemplateId && !directOpenFailed) return undefined
    let cancelled = false
    setFirm({ items: [], total: 0, loading: true, error: '' })
    const timer = setTimeout(() => {
      getTemplates({ query: query.trim() || undefined, include_inactive: true, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
        .then(data => { if (!cancelled) setFirm({ items: data.items || [], total: data.total || 0, loading: false, error: '' }) })
        .catch(() => { if (!cancelled) setFirm(current => ({ ...current, loading: false, error: 'Firm templates could not be loaded. Try again.' })) })
    }, 150)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [query, page, firmRetry, initialTemplateId, directOpenFailed])

  useEffect(() => {
    if (initialTemplateId && !directOpenFailed) return undefined
    let cancelled = false
    getSampleTemplates()
      .then(data => { if (!cancelled) setGlobal({ items: data.items || [], loading: false, error: '' }) })
      .catch(() => { if (!cancelled) setGlobal({ items: [], loading: false, error: 'The global library could not be loaded. Try again.' }) })
    return () => { cancelled = true }
  }, [initialTemplateId, directOpenFailed, globalRetry])

  function reviewInStudio(templateId) {
    navigate(`/templates/${encodeURIComponent(templateId)}/studio`, { state: PREPARATION_CONTEXT(matterId, folderId) })
  }

  async function choose(template, isDirectOpen = false) {
    setSelecting(true)
    try {
      const current = await getTemplate(template.id)
      if (!current?.is_active) {
        reviewInStudio(template.id)
        return
      }
      const publishedIsOlder = current.published_version_no != null && current.published_version_no !== current.current_version_no
      setSelected(publishedIsOlder ? await getTemplate(template.id, { published: true }) : current)
    } catch {
      if (isDirectOpen) setDirectOpenFailed(true)
      setFirm(current => ({ ...current, error: 'Could not open this firm template. Try again.' }))
    } finally { setSelecting(false) }
  }

  useEffect(() => { if (initialTemplateId) choose({ id: initialTemplateId }, true) }, [initialTemplateId])

  async function loadPreview(sample) {
    const request = previewRequest.current
    setPreview(current => current?.sample.id === sample.id ? { ...current, loading: true, error: '', source: null } : current)
    try {
      const source = await getSampleTemplateSource(sample.id)
      if (previewRequest.current === request) setPreview(current => current?.sample.id === sample.id ? { ...current, source, loading: false, error: '' } : current)
    } catch {
      if (previewRequest.current === request) setPreview(current => current?.sample.id === sample.id ? { ...current, loading: false, error: `The preview for “${sample.title}” could not be loaded.` } : current)
    }
  }
  function openPreview(sample) {
    previewRequest.current += 1
    setPreview({ sample, source: null, loading: true, error: '' })
    loadPreview(sample)
  }
  function closePreview() { previewRequest.current += 1; setPreview(null) }

  const visibleGlobal = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return global.items.filter(sample => !needle || sampleSearchText(sample).includes(needle))
  }, [global.items, query])
  const globalPages = Math.ceil(visibleGlobal.length / PAGE_SIZE)
  const pagedGlobal = visibleGlobal.slice(globalPage * PAGE_SIZE, (globalPage + 1) * PAGE_SIZE)
  const showFirm = filter !== 'global'
  const showGlobal = filter !== 'firm'
  const hasMatches = (showFirm && firm.items.length) || (showGlobal && visibleGlobal.length)

  function handleKey(event) {
    if (preview) return
    if (event.key === 'Escape' && !selecting) { event.stopPropagation(); onClose() }
    if (event.key !== 'Tab') return
    const focusable = [...dialog.current.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href]')]
    const first = focusable[0], last = focusable.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }

  if (selected) return <Suspense fallback={<p role="status">Opening document editor…</p>}><RenderModal key={`${matterId}:${selected.id}`} template={selected} fixedMatterId={matterId} folderId={folderId} onSaved={onSaved} onClose={onClose} /></Suspense>

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
    <section ref={dialog} onKeyDown={handleKey} role="dialog" aria-modal="true" aria-label="Attach template" className="max-h-[85vh] w-full max-w-3xl overflow-auto rounded-xl bg-brand-surface p-5 shadow-xl">
      <div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Attach template</h2><button type="button" onClick={onClose} disabled={selecting}>Close</button></div>
      <p className="my-2 text-sm text-brand-muted">Search your firm’s templates and the global library. Firm templates must be published before they can be used on a matter. Global samples need firm review before use.</p>
      <label className="block text-sm">Search templates<input autoFocus value={query} onChange={event => { setQuery(event.target.value); setPage(0); setGlobalPage(0) }} className="my-2 w-full rounded border border-brand-line p-2" /></label>
      <div role="group" aria-label="Template source" className="mb-4 flex flex-wrap gap-2">
        {[['all', 'All'], ['firm', 'Firm templates'], ['global', 'Global library']].map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className="rounded border px-3 py-1.5">{label}</button>)}
      </div>
      {showFirm && <section aria-labelledby="firm-templates-heading" className="mb-5">
        <h3 id="firm-templates-heading" className="mb-2 font-semibold">Firm templates <span className="text-xs font-normal text-brand-muted">Your workspace</span></h3>
        {firm.error && <div><p role="alert">{firm.error}</p><button type="button" onClick={() => setFirmRetry(value => value + 1)} className="mt-2 rounded border px-3 py-1.5">Retry firm templates</button></div>}
        {firm.loading ? <p role="status">Loading firm templates…</p> : firm.items.length ? <ul className="divide-y divide-brand-line">{firm.items.map(template => <li key={template.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div><strong>{template.title}</strong><p className="text-xs text-brand-muted">{template.format || 'Text'} · {template.category || 'General'} · <span className="rounded bg-brand-bg px-1.5 py-0.5">{template.is_active ? `Published${template.published_version_no ? ` v${template.published_version_no}` : ''}` : (template.status === 'paused' ? 'Paused' : 'Draft')}</span></p></div>
          {template.is_active ? <button type="button" disabled={selecting} onClick={() => choose(template)} className="rounded border px-3 py-2">Use template</button> : <button type="button" onClick={() => reviewInStudio(template.id)} className="rounded border px-3 py-2">Review in Studio</button>}
        </li>)}</ul> : !firm.error && <p className="text-sm text-brand-muted">No matching firm templates.</p>}
        {!firm.loading && !firm.error && firm.total > PAGE_SIZE && <div className="mt-2 flex justify-between"><button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous firm templates</button><span aria-live="polite">Page {page + 1} of {Math.ceil(firm.total / PAGE_SIZE)}</span><button type="button" disabled={(page + 1) * PAGE_SIZE >= firm.total} onClick={() => setPage(page + 1)}>Next firm templates</button></div>}
      </section>}
      {showGlobal && <section aria-labelledby="global-library-heading" className="mb-2 border-t border-brand-line pt-4">
        <h3 id="global-library-heading" className="mb-2 font-semibold">Global library <span className="text-xs font-normal text-brand-muted">Shared reference forms</span></h3>
        <p className="mb-2 text-xs text-brand-muted">Global library items are read-only references. Review jurisdiction, source, and wording before bringing one into your firm templates.</p>
        {global.error && <div><p role="alert">{global.error}</p><button type="button" onClick={() => setGlobalRetry(value => value + 1)} className="mt-2 rounded border px-3 py-1.5">Retry global library</button></div>}
        {global.loading ? <p role="status">Loading global library…</p> : visibleGlobal.length ? <ul className="divide-y divide-brand-line">{pagedGlobal.map(sample => <li key={sample.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div className="min-w-0"><strong>{sample.title}</strong><p className="text-xs text-brand-muted">{sample.category || 'General'} · {(sample.jurisdictions || []).join(', ') || 'Jurisdiction not specified'} · {sample.provenance?.source_name || sample.source_name || 'Source not recorded'}{(sample.provenance?.edition || sample.edition) ? ` · ${sample.provenance?.edition || sample.edition}` : ''}</p><p className="mt-1 text-xs"><span className="rounded bg-brand-bg px-1.5 py-0.5">Global library</span> <span className="text-brand-muted">Needs firm review</span></p></div>
          <div className="flex shrink-0 gap-2"><button type="button" onClick={() => openPreview(sample)} className="rounded border px-3 py-2">Preview</button><button type="button" onClick={() => navigate(`/templates/new?sample=${encodeURIComponent(sample.id)}`, { state: PREPARATION_CONTEXT(matterId, folderId) })} className="rounded border px-3 py-2">Add to firm</button></div>
        </li>)}</ul> : !global.error && <p className="text-sm text-brand-muted">No matching global library items.</p>}
        {!global.loading && globalPages > 1 && <div className="mt-2 flex justify-between"><button type="button" disabled={globalPage === 0} onClick={() => setGlobalPage(value => value - 1)}>Previous global results</button><span aria-live="polite">Page {globalPage + 1} of {globalPages} · {visibleGlobal.length} matches</span><button type="button" disabled={globalPage + 1 >= globalPages} onClick={() => setGlobalPage(value => value + 1)}>Next global results</button></div>}
      </section>}
      {!hasMatches && !firm.loading && !global.loading && !firm.error && !global.error && <p>No matching templates.</p>}
    </section>
    {preview && <PdfPreviewDialog title={preview.sample.title} source={preview.source} loading={preview.loading} error={preview.error} onClose={closePreview} onRetry={() => loadPreview(preview.sample)} filename={preview.sample.source_filename || `${preview.sample.slug || preview.sample.id}.pdf`} />}
  </div>
}
