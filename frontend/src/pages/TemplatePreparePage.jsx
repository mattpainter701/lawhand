import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { getMattersV2, getTemplate } from '../api'
import usePrepareFill, { templateHasSigningFields } from '../components/prepare/usePrepareFill'
import SendStep, { renderIsSendable, savedDocumentFromRender } from '../components/prepare/SendStep'
import PrepareDocumentBody from '../components/prepare/PrepareDocumentBody'
import PrepareStepper, { prepareSteps } from '../components/prepare/PrepareStepper'
import { buildSavedTarget, readPrepareQuery } from '../components/prepare/prepareRouting'
import { getErrorMessage } from '../components/prepare/prepareHelpers'

const normalizeItems = (data) => (Array.isArray(data) ? data : (data?.items || []))

// A template is filled from its published version. The workspace may hold a
// newer draft; the route reads the release the matter would actually get.
async function loadReleaseTemplate(templateId) {
  const template = await getTemplate(templateId)
  if (template?.is_active && template.published_version_no !== template.current_version_no) {
    return getTemplate(templateId, { published: true })
  }
  return template
}

function PrepareDocument({ template, matters, matterLoading, query, onSaved }) {
  // The hook reports the render response; the matter it was saved to is the
  // one chosen in the body, which the page cannot see until the hook returns.
  const matterRef = useRef(query.matterId || '')
  // A saved PDF with signing fields stays on the page for the Send step;
  // everything else hands over to the matter's documents.
  const [sendable, setSendable] = useState(null)
  const [sent, setSent] = useState(false)
  const fill = usePrepareFill({
    template,
    initialMatterId: query.matterId || '',
    folderId: query.folderId || null,
    onSaved: (res) => {
      const matterId = matterRef.current
      if (renderIsSendable(res)) setSendable({ matterId, document: savedDocumentFromRender(res) })
      else onSaved(res, matterId)
    },
  })
  matterRef.current = fill.matterId
  const signing = templateHasSigningFields(template) ? { pdf: fill.isPdfOutput, sent } : null
  const steps = prepareSteps({
    template,
    matterId: fill.matterId,
    progress: fill.progress,
    requiredMissing: fill.requiredUnresolvedNames.length,
    previewReady: Boolean(fill.previewId || fill.filePreview || fill.rendered),
    saved: fill.saved,
    signing,
  })
  return (
    <>
      <PrepareStepper steps={steps} />
      {sendable ? (
        <SendStep
          matterId={sendable.matterId}
          document={sendable.document}
          savedTarget={buildSavedTarget({ matterId: sendable.matterId, documentId: sendable.document.id, returnTo: query.returnTo })}
          onSent={() => setSent(true)}
        />
      ) : (
        <PrepareDocumentBody fill={fill} template={template} matters={matters} matterLoading={matterLoading} layout="page" />
      )}
    </>
  )
}

// The guided route: Template, Matter, Populate, Review, Save. It reuses the
// Generate dialog's hook and body, so a document prepared here is reviewed
// under exactly the same rules, and lands on the matter's Documents tab.
export default function TemplatePreparePage() {
  const location = useLocation()
  const navigate = useNavigate()
  const query = useMemo(() => readPrepareQuery(location.search), [location.search])
  const [template, setTemplate] = useState(null)
  const [templateError, setTemplateError] = useState('')
  const [loading, setLoading] = useState(Boolean(query.templateId))
  const [matters, setMatters] = useState([])
  const [matterLoading, setMatterLoading] = useState(false)

  useEffect(() => {
    let active = true
    if (!query.templateId) { setTemplate(null); setLoading(false); return undefined }
    setLoading(true); setTemplateError('')
    loadReleaseTemplate(query.templateId)
      .then((value) => { if (active) setTemplate(value) })
      .catch((err) => { if (active) { setTemplate(null); setTemplateError(getErrorMessage(err, 'This template could not be loaded.')) } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [query.templateId])

  useEffect(() => {
    let active = true
    setMatterLoading(true)
    getMattersV2({ page_size: 100, sort_by: 'updated_at', sort_dir: 'desc' })
      .then((res) => { if (active) setMatters(normalizeItems(res)) })
      .catch(() => { if (active) setMatters([]) })
      .finally(() => { if (active) setMatterLoading(false) })
    return () => { active = false }
  }, [])

  const onSaved = useCallback((res, matterId) => {
    navigate(buildSavedTarget({ matterId: String(matterId || query.matterId || '').trim(), documentId: res?.matter_document_id, returnTo: query.returnTo }))
  }, [navigate, query.matterId, query.returnTo])

  const backTarget = query.returnTo || (template ? `/templates/${encodeURIComponent(template.id)}/studio` : '/templates')

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to={backTarget} className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-muted hover:text-brand-ink">
          <ArrowLeft size={16} aria-hidden="true" /> Back
        </Link>
        <h1 className="text-lg font-semibold text-brand-ink">{template ? `Prepare: ${template.title}` : 'Prepare a document'}</h1>
      </div>
      {loading && <p role="status" className="text-sm text-brand-muted">Loading the template…</p>}
      {templateError && <p role="alert" className="text-sm text-brand-rose">{templateError}</p>}
      {!loading && !query.templateId && (
        <section className="rounded-xl border border-brand-line bg-brand-surface-2 p-4 text-sm">
          <p className="font-semibold text-brand-ink">Choose a template to prepare</p>
          <p className="mt-1 text-brand-muted">Open a published template in <Link className="underline" to="/templates">Template Studio</Link> and choose <strong>Use on a matter</strong>, or start from a matter's Case Documents.</p>
        </section>
      )}
      {template && !loading && (
        <PrepareDocument key={`${template.id}:${query.matterId || ''}`} template={template} matters={matters} matterLoading={matterLoading} query={query} onSaved={onSaved} />
      )}
    </div>
  )
}
