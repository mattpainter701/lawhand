import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { getFillSession, getMattersV2, getTemplate } from '../api'
import useFillDraft from '../components/prepare/useFillDraft'
import usePrepareFill, { templateHasSigningFields } from '../components/prepare/usePrepareFill'
import SendStep, { renderIsSendable, savedDocumentFromRender } from '../components/prepare/SendStep'
import usePrepareSet from '../components/prepare/usePrepareSet'
import PrepareSetBody from '../components/prepare/PrepareSetBody'
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
  const navigate = useNavigate()
  const location = useLocation()
  const sessionRef = useRef(null)
  const [restored, setRestored] = useState(!query.sessionId)
  const [restoreError, setRestoreError] = useState('')
  const [restoreAttempt, setRestoreAttempt] = useState(0)
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
    autoFillEnabled: restored,
    onSaved: (res) => {
      const matterId = matterRef.current
      if (renderIsSendable(res)) setSendable({ matterId, document: savedDocumentFromRender(res) })
      else onSaved(res, matterId)
    },
  })
  matterRef.current = fill.matterId
  const signing = templateHasSigningFields(template) ? { pdf: fill.isPdfOutput, sent } : null
  // The values typed here are kept server-side (encrypted) so the page can
  // be closed and resumed from the matter's Documents tab; created on the
  // first value, updated a moment after each change, resumed from `?session=`.
  const { setVariables, setVerifiedNames, setMatterId } = fill
  useEffect(() => {
    if (!query.sessionId || query.sessionId === sessionRef.current?.id) return undefined
    let active = true
    setRestored(false)
    setRestoreError('')
    getFillSession(query.sessionId)
      .then((value) => {
        if (!active) return
        if (value.template_id !== template.id) throw new Error('This draft belongs to a different template. Open it from the matter’s Documents tab.')
        sessionRef.current = value
        if (value.answers && Object.keys(value.answers).length) setVariables((prev) => ({ ...prev, ...value.answers }))
        setVerifiedNames(Object.fromEntries((value.verified || []).map((name) => [name, true])))
        if (value.matter_id) setMatterId(value.matter_id)
        setRestored(true)
      })
      .catch(() => { if (active) setRestoreError('We couldn’t restore your saved answers. Retry before continuing; your draft has not been replaced.') })
    return () => { active = false }
  }, [query.sessionId, restoreAttempt, template.id, setVariables, setVerifiedNames, setMatterId])
  const { variables, verifiedNames, matterId, saved } = fill
  const draftPayload = useMemo(() => {
    if (!restored || saved) return null
    const answers = Object.fromEntries(Object.entries(variables).filter(([, value]) => String(value ?? '').trim()))
    if (!Object.keys(answers).length && !sessionRef.current) return null
    return {
        matter_id: matterId.trim() || null,
        template_id: template.id,
        title: template.title || '',
        versions: { [template.id]: template.published_version_no ?? null },
        answers,
        verified: Object.keys(verifiedNames).filter((name) => verifiedNames[name] && String(variables[name] ?? '').trim()),
    }
  }, [restored, template, variables, verifiedNames, matterId, saved])
  const onDraftCreated = useCallback((id) => {
    const params = new URLSearchParams(location.search)
    if (params.get('session') === id) return
    params.set('session', id)
    navigate({ pathname: location.pathname, search: params.toString() }, { replace: true })
  }, [navigate, location.pathname, location.search])
  const draft = useFillDraft({ payload: draftPayload, sessionRef, onCreated: onDraftCreated })
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
      {!restored ? (
        restoreError ? <div role="alert" className="rounded border border-brand-rose/30 p-3 text-sm"><p>{restoreError}</p><button type="button" onClick={() => setRestoreAttempt(value => value + 1)} className="mt-2 rounded border border-brand-line px-3 py-2">Retry restoring answers</button></div>
          : <p role="status">Restoring your answers…</p>
      ) : sendable ? (
        <SendStep
          matterId={sendable.matterId}
          document={sendable.document}
          savedTarget={buildSavedTarget({ matterId: sendable.matterId, documentId: sendable.document.id, returnTo: query.returnTo })}
          onSent={() => setSent(true)}
        />
      ) : (
        <>
          {draft.status === 'error' ? <div role="alert" className="rounded border border-brand-rose/30 p-3 text-sm">Your latest answers haven’t been saved. Keep this page open. <button type="button" className="underline" onClick={draft.retry}>Retry saving answers</button></div>
            : draft.status !== 'idle' && <p role="status" className="text-xs text-brand-muted">{draft.status === 'saved' ? 'Answers saved · available from this matter for 14 days' : 'Saving answers…'}</p>}
          <PrepareDocumentBody fill={fill} template={template} matters={matters} matterLoading={matterLoading} layout="page" />
        </>
      )}
    </>
  )
}

// A set: one interview, many documents, saved one at a time from here.
function PrepareSet({ query, matters, matterLoading, onSessionCreated }) {
  const prep = usePrepareSet({ setId: query.setId, initialMatterId: query.matterId || '', folderId: query.folderId || null, sessionId: query.sessionId || null, onSessionCreated })
  const anyPdfSigning = prep.availableMembers.some((member) => member.output?.format === 'pdf')
  const steps = prepareSteps({
    template: prep.set ? { title: prep.set.title } : null,
    matterId: prep.matterId,
    progress: prep.progress,
    requiredMissing: prep.requiredUnresolvedNames.length,
    previewReady: prep.allPreviewed,
    saved: prep.allSaved,
    signing: anyPdfSigning ? { pdf: true, sent: false } : null,
  })
  if (prep.loading) return <p role="status" className="text-sm text-brand-muted">Loading the set…</p>
  if (!prep.set) return <p role="alert" className="text-sm text-brand-rose">{prep.error || 'This set could not be loaded.'}</p>
  return (
    <>
      <PrepareStepper steps={steps} />
      <PrepareSetBody prep={prep} matters={matters} matterLoading={matterLoading} fixedMatterId={query.matterId && query.returnTo ? query.matterId : ''} returnTo={query.returnTo} />
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
  const onPacketSessionCreated = useCallback((id) => {
    const params = new URLSearchParams(location.search)
    if (params.get('session') === id) return
    params.set('session', id)
    navigate({ pathname: location.pathname, search: params.toString() }, { replace: true })
  }, [navigate, location.pathname, location.search])

  const backTarget = query.returnTo || (template ? `/templates/${encodeURIComponent(template.id)}/studio` : query.setId ? '/templates/sets' : '/templates')

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to={backTarget} className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-muted hover:text-brand-ink">
          <ArrowLeft size={16} aria-hidden="true" /> Back
        </Link>
        <h1 className="text-lg font-semibold text-brand-ink">{template ? `Prepare: ${template.title}` : query.setId ? 'Prepare a packet' : 'Prepare a document'}</h1>
      </div>
      {loading && <p role="status" className="text-sm text-brand-muted">Loading the template…</p>}
      {templateError && <p role="alert" className="text-sm text-brand-rose">{templateError}</p>}
      {query.setId && (
        <PrepareSet key={`${query.setId}:${query.matterId || ''}`} query={query} matters={matters} matterLoading={matterLoading} onSessionCreated={onPacketSessionCreated} />
      )}
      {!loading && !query.templateId && !query.setId && (
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
