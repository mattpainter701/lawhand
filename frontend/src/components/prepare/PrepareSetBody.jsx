import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link2, Wand2 } from 'lucide-react'
import MatterPicker from './MatterPicker'
import TemplateFillProgress from '../templates/TemplateFillProgress'
import TemplateFillSource from '../templates/TemplateFillSource'
import GeneratedPdfPreview from '../templates/GeneratedPdfPreview'
import FillOnDocument, { GuidedFieldBar, useGuidedFields } from '../templates/FillOnDocument'
import { placementsFor } from '../templates/pdfFieldGeometry'
import { readFillViewPreference, writeFillViewPreference } from '../templates/fillViewPreference'
import { fillValue, suggestionOriginLabel } from '../templates/templateFillReview'
import { getTemplateSource } from '../../api'
import FieldEditor from './FieldEditor'
import SendStep from './SendStep'
import { buildSavedTarget } from './prepareRouting'
import StorageReadinessNotice from './StorageReadinessNotice'
import { alsoFills, memberDocumentFields, memberFieldMarker, memberMissingCount, memberValues, nextRequiredStop } from './packetFill'

// The Prepare route for a set (a packet of documents). Three views share one
// set of answers, each question asked once:
// - Document (default): one tab per member document. PDF members are typed on
//   their own pages; Word and text members show the page reference above the
//   guided bar. Typing on any document writes the shared answer, so every
//   member using it updates; "Next required" walks the whole packet. Each
//   member has a Preview sub-tab with its generated document.
// - Questions: the single interview, grouped by card, beside the packet.
// - Packet: the member list with Generate all, Save all and Send.
// The Document/Questions choice is remembered per browser.
const VIEW_TABS = [['document', 'Document'], ['questions', 'Questions'], ['packet', 'Packet']]
const LEGEND = ['missing', 'review', 'verified', 'open']
const CHECKBOX_VALUES = { on: 'true', off: 'false' }

const groupLabel = (question) => {
  if (question.card) return question.card.replace(/[_.]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return `${question.appears_in?.[0]?.template_title || 'This document'} only`
}

const sourceKey = (template) => (template?.id ? `${template.id}:${template.source_sha256 || ''}:${template.source_filename || ''}` : '')

// Each PDF member's stored source, loaded the first time its tab is opened
// and kept while the page is open, so moving between documents does not
// download them again.
function usePacketSources() {
  const [sources, setSources] = useState({})
  const requested = useRef(new Set())
  const request = useCallback((template) => {
    const key = sourceKey(template)
    if (!key || requested.current.has(key)) return
    requested.current.add(key)
    getTemplateSource(template.id, template.source_filename)
      .then((blob) => setSources((prev) => ({ ...prev, [key]: { blob, failed: false } })))
      .catch(() => setSources((prev) => ({ ...prev, [key]: { blob: null, failed: true } })))
  }, [])
  const sourceFor = (template) => sources[sourceKey(template)] || { blob: null, failed: false }
  return { request, sourceFor }
}

function WordPreviewDownload({ preview }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    const nextUrl = URL.createObjectURL(preview.blob)
    setUrl(nextUrl)
    return () => URL.revokeObjectURL(nextUrl)
  }, [preview.blob])
  return url ? <a href={url} download={preview.filename || 'document-preview.docx'} className="text-xs underline">Download Word preview</a> : null
}

// A Word or text member: the page reference, with the guided bar under it.
function ReferenceFill({ template, fields, values, activeName, onActiveChange, isMissing, renderInput, onNextRequired, requiredMissing }) {
  const guided = useGuidedFields(fields, { values, activeName, onActiveChange, isMissing })
  const field = guided.activeField
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-brand-line bg-brand-bg-soft">
      <div className="min-h-0 flex-1 overflow-auto p-4">
        <TemplateFillSource template={template} fields={fields.filter((item) => item.included !== false)} values={values} onSelectField={onActiveChange} />
      </div>
      <GuidedFieldBar
        field={field}
        position={guided.index + 1}
        total={fields.length}
        onPrevious={() => guided.step(-1)}
        onNext={() => guided.step(1)}
        onNextRequired={onNextRequired}
        requiredMissing={requiredMissing}
      >
        {field && renderInput(field)}
      </GuidedFieldBar>
    </div>
  )
}

// One member's generated document, in place. It prepares itself when opened
// with every answer it needs, and again after answers change, so it reads
// like the live preview of a single document.
function MemberPreview({ member, preview, save, missing, matterReady, busy, locked, onGenerate }) {
  const generate = useRef(onGenerate)
  useEffect(() => { generate.current = onGenerate }, [onGenerate])
  const canGenerate = preview.status === 'idle' && matterReady && !missing && !busy && !locked
  useEffect(() => {
    if (!canGenerate) return undefined
    const timer = setTimeout(() => generate.current(), 600)
    return () => clearTimeout(timer)
  }, [canGenerate])
  const format = member.output.format
  return (
    <section aria-label={`Preview of ${member.title}`} className="min-w-0 rounded-xl border border-brand-line bg-brand-bg p-4">
      {save?.status === 'saved' && <p role="status" className="mb-3 rounded border border-brand-green/30 bg-brand-green/10 px-3 py-2 text-xs text-brand-green">Saved to the matter{save.response?.output_filename ? ` as ${save.response.output_filename}` : ''}.</p>}
      {preview.status === 'ready' ? (
        format === 'pdf' && preview.blob ? <GeneratedPdfPreview source={preview.blob} title={member.title} />
          : preview.blob ? (
            <div className="rounded border border-brand-green/30 bg-brand-green/10 px-4 py-3 text-sm text-brand-ink">
              <p className="mb-2">Word formatting was preserved. Download and open this generated DOCX to inspect its exact pagination, tables, headers, and footers.</p>
              <WordPreviewDownload preview={preview} />
            </div>
          ) : <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded bg-brand-surface p-4 font-mono text-sm text-brand-ink">{preview.rendered}</pre>
      ) : preview.status === 'loading' ? (
        <p role="status" className="p-6 text-center text-sm text-brand-muted">Preparing the preview with your answers…</p>
      ) : preview.status === 'failed' ? (
        <div role="alert" className="p-6 text-center text-sm text-brand-rose">
          <p>Preview failed: {preview.error}</p>
          <button type="button" onClick={onGenerate} disabled={busy || locked} className="mt-2 rounded border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink disabled:opacity-50">Retry preview</button>
        </div>
      ) : save?.status === 'saved' ? null : (
        <p role="status" className="p-6 text-center text-sm text-brand-muted">
          {!matterReady ? 'Choose a matter to preview this document.'
            : missing ? `Answer ${missing} required question${missing === 1 ? '' : 's'} in this document to preview it.`
              : 'Preparing the preview with your answers…'}
        </p>
      )}
    </section>
  )
}

export default function PrepareSetBody({ prep, matters, matterLoading, fixedMatterId, returnTo }) {
  const {
    questions, unavailable, availableMembers, error, matterId, selectMatter, answers, setAnswer, setReviewedValues,
    toggleVerified, fieldFilter, setFieldFilter, filteredKeys, nextField, progress, requiredUnresolvedNames,
    smartFillState, smartFillMessage, refresh, previewOf, saveOf, generating, saving, generateAll, saveAll, allPreviewed, allSaved, sendable,
    session, background, sessionRestoreError, retrySessionRestore, sessionRestored, persistError, persistStatus, retrySave,
  } = prep

  // --- Views ---------------------------------------------------------------
  const [view, setView] = useState(readFillViewPreference)
  const chooseView = (next) => {
    setView(next)
    writeFillViewPreference(next)
  }
  // A finished packet opens on its Send step.
  useEffect(() => { if (allSaved) setView((current) => (current === 'document' ? 'packet' : current)) }, [allSaved])
  const [activeMemberId, setActiveMemberId] = useState('')
  const [memberViews, setMemberViews] = useState({})
  const [activeFields, setActiveFields] = useState({})
  const [walkedTo, setWalkedTo] = useState('')
  const pendingFocus = useRef('')
  const { request: requestSource, sourceFor } = usePacketSources()

  // --- Shared answers ------------------------------------------------------
  const clearReviewedValue = (key) => setReviewedValues((prev) => ({ ...prev, [key]: undefined }))
  const updateValue = (key, value) => {
    clearReviewedValue(key)
    setAnswer(key, value)
  }
  const verifyCurrentValue = (key, value) => {
    setReviewedValues((prev) => ({ ...prev, [key]: fillValue(value) }))
    toggleVerified(key)
  }
  const toggleValueVerified = (key, value, currentlyVerified) => {
    if (currentlyVerified) clearReviewedValue(key)
    else verifyCurrentValue(key, value)
    if (currentlyVerified) toggleVerified(key)
  }
  const questionByKey = useMemo(() => Object.fromEntries(questions.map((question) => [question.key, question])), [questions])
  const rowByKey = useMemo(() => Object.fromEntries((progress.rows || []).map((row) => [row.name, row])), [progress.rows])
  const missingKeys = useMemo(() => new Set(requiredUnresolvedNames), [requiredUnresolvedNames])
  const locked = saving || allSaved

  // --- Documents -----------------------------------------------------------
  const membersKey = availableMembers.map((member) => `${member.template_id}:${member.template?.id || ''}:${member.template?.source_sha256 || ''}`).join(',')
  const documents = useMemo(() => availableMembers.map((member) => ({ member, memberId: member.template_id, fields: memberDocumentFields(member, questions) })), [membersKey, questions])
  const activeDoc = documents.find((doc) => String(doc.memberId) === String(activeMemberId)) || documents[0] || null
  const activeId = activeDoc?.memberId || ''
  const activeTemplate = activeDoc?.member.template || null
  const newerDraft = Boolean(activeTemplate?.is_active && activeTemplate.published_version_no && activeTemplate.published_version_no !== activeTemplate.current_version_no)
  const activeOnPage = Boolean(activeTemplate && String(activeTemplate.format || '').toLowerCase() === 'pdf' && !newerDraft && activeDoc.fields.some((field) => placementsFor(field).length))
  const memberView = memberViews[activeId] || 'fill'
  const [unreadable, setUnreadable] = useState({})
  const onPdfUnavailable = useCallback(() => setUnreadable((prev) => ({ ...prev, [activeId]: true })), [activeId])
  useEffect(() => {
    if (view === 'document' && memberView === 'fill' && activeOnPage) requestSource(activeTemplate)
  }, [view, memberView, activeOnPage, activeTemplate, requestSource])
  const activeSource = activeTemplate ? sourceFor(activeTemplate) : { blob: null, failed: false }
  const fillOnPage = activeOnPage && !activeSource.failed && !unreadable[activeId]

  const currentFieldOf = (doc) => activeFields[doc.memberId] || doc.fields[0]?.name || ''
  const openMember = (memberId, sub = null) => {
    setWalkedTo('')
    setActiveMemberId(memberId)
    if (sub) setMemberViews((prev) => ({ ...prev, [memberId]: sub }))
  }
  const setActiveField = (memberId, name) => setActiveFields((prev) => ({ ...prev, [memberId]: name }))
  // "Next required" walks the packet: later in this document, then the next
  // document's first missing box. A shared answer is asked once.
  const walkNextRequired = () => {
    if (!activeDoc) return
    const stop = nextRequiredStop(documents, missingKeys, { memberId: activeId, fieldName: currentFieldOf(activeDoc) })
    if (!stop) return
    if (String(stop.memberId) !== String(activeId)) {
      setWalkedTo(stop.memberId)
      setActiveMemberId(stop.memberId)
      setMemberViews((prev) => ({ ...prev, [stop.memberId]: 'fill' }))
    }
    pendingFocus.current = `set-answer-${stop.key}`
    setActiveField(stop.memberId, stop.fieldName)
  }
  // Enter confirms the answer and moves to the next box in this document.
  const advanceFrom = (doc, fieldName, key) => {
    const row = rowByKey[key]
    if (row?.present && !row.verified) verifyCurrentValue(key, answers[key])
    const index = doc.fields.findIndex((field) => field.name === fieldName)
    const next = doc.fields[(index + 1) % doc.fields.length]
    if (!next) return
    if (next.question_key) pendingFocus.current = `set-answer-${next.question_key}`
    setActiveField(doc.memberId, next.name)
  }
  useEffect(() => {
    const id = pendingFocus.current
    if (!id) return
    const input = document.getElementById(id)
    if (!input) return
    pendingFocus.current = ''
    input.focus({ preventScroll: true })
  })

  // --- Editors -------------------------------------------------------------
  const renderQuestionEditor = (question, doc = null, fieldName = '') => {
    const review = rowByKey[question.key]
    const count = review?.documents || 1
    const value = fillValue(answers[question.key])
    const others = doc ? alsoFills(question, doc.memberId) : []
    return (
      <FieldEditor
        key={question.key}
        inputId={`set-answer-${question.key}`}
        label={question.label}
        required={Boolean(question.required)}
        fieldType={question.value_kind}
        options={question.options}
        value={value}
        disabled={saving}
        inputDisabled={locked}
        review={review}
        choicePlaceholder={`Choose ${question.label}`}
        onChange={(next) => updateValue(question.key, next)}
        onConfirm={() => setReviewedValues((prev) => ({ ...prev, [question.key]: value }))}
        onToggleVerified={() => toggleValueVerified(question.key, value, review?.verified)}
        onEnter={doc ? () => advanceFrom(doc, fieldName, question.key) : undefined}
        labelNote={!doc && count > 1 ? <span className="ml-2 font-normal">· Appears in {count} documents</span> : null}
        notes={review?.source ? <p className="mb-1 text-xs text-brand-muted">{suggestionOriginLabel(review.source)}</p> : null}
        footer={others.length > 0 ? (
          <p className="mt-1 flex items-center gap-1 text-xs text-brand-accent-2"><Link2 size={12} aria-hidden="true" />Also fills: {others.join(', ')}</p>
        ) : null}
      />
    )
  }
  const renderDocumentEditor = (doc, field) => {
    const question = field.question_key ? questionByKey[field.question_key] : null
    const marker = memberFieldMarker(field, doc.fields)
    if (question && !marker) return renderQuestionEditor(question, doc, field.name)
    return (
      <FieldEditor
        label={field.label}
        asHeading
        readOnly={<p className="text-sm text-brand-muted">{marker === 'Filled automatically' ? 'This box is filled from the rest of the packet when the document is generated.' : marker === 'Signed later' ? 'Signature area is left blank for signing; it is not populated during document generation.' : marker === 'Dated at signing' ? 'The signing date is completed during e-signing.' : `${marker}; it fills itself from that answer.`}</p>}
      />
    )
  }
  const statusFor = (field) => {
    const row = field.question_key ? rowByKey[field.question_key] : null
    if (!row) return 'open'
    if (!row.present) return field.required ? 'missing' : 'open'
    if (row.verified) return 'verified'
    if (row.needsReview) return 'review'
    if (row.source) return 'suggested'
    return 'filled'
  }
  const isMissing = (field) => Boolean(field.question_key && missingKeys.has(field.question_key))
  const isShared = (field) => new Set((questionByKey[field.question_key]?.appears_in || []).map((ref) => String(ref.template_id))).size > 1

  // --- Packet --------------------------------------------------------------
  const visible = questions.filter((question) => filteredKeys.includes(question.key))
  const groups = []
  for (const question of visible) {
    const label = groupLabel(question)
    const group = groups.find((entry) => entry.label === label)
    if (group) group.questions.push(question)
    else groups.push({ label, questions: [question] })
  }
  const failedPreviews = availableMembers.filter((member) => previewOf(member).status === 'failed').map((member) => member.template_id)
  const failedSaves = availableMembers.filter((member) => saveOf(member)?.status === 'failed').map((member) => member.template_id)
  const memberState = (member, missing) => {
    const preview = previewOf(member)
    const save = saveOf(member)
    if (save?.status === 'saved') return { label: 'Saved', tone: 'text-brand-green' }
    if (save?.status === 'saving') return { label: 'Saving…', tone: 'text-brand-muted' }
    if (save?.status === 'failed') return { label: 'Save failed', tone: 'text-brand-rose' }
    if (missing) return { label: `${missing} missing`, tone: 'text-amber-800' }
    if (preview.status === 'ready') return { label: 'Previewed', tone: 'text-brand-green' }
    if (preview.status === 'loading') return { label: 'Previewing…', tone: 'text-brand-muted' }
    if (preview.status === 'failed') return { label: 'Preview failed', tone: 'text-brand-rose' }
    return { label: 'Ready to preview', tone: 'text-brand-muted' }
  }

  if (sessionRestored === false) return (
    <div className="space-y-4">
      {sessionRestoreError ? (
        <div role="alert" className="text-sm text-brand-rose bg-brand-rose/10 border border-brand-rose/30 px-3 py-2 flex items-center justify-between gap-2">
          <span>{sessionRestoreError}</span><button type="button" onClick={retrySessionRestore} className="underline font-semibold">Retry</button>
        </div>
      ) : <p role="status" className="text-sm text-brand-muted">Restoring your packet answers…</p>}
    </div>
  )

  const noticeSection = <>
    {sessionRestoreError && <div role="alert" className="text-sm text-brand-rose bg-brand-rose/10 border border-brand-rose/30 px-3 py-2 flex items-center justify-between gap-2"><span>{sessionRestoreError}</span><button type="button" onClick={retrySessionRestore} className="underline font-semibold">Retry</button></div>}
    {persistError && <div role="alert" className="text-sm text-brand-rose bg-brand-rose/10 border border-brand-rose/30 px-3 py-2 flex items-center justify-between gap-2"><span>{persistError}</span><button type="button" onClick={retrySave} className="underline font-semibold">Retry save</button></div>}
    {!persistError && ['pending', 'saving'].includes(persistStatus) && <p role="status" className="text-xs text-brand-muted">Saving answers…</p>}
    {!persistError && persistStatus === 'saved' && <p role="status" className="text-xs text-brand-muted">Answers saved · available from this matter for 14 days</p>}
    {error && <div role="alert" className="text-sm text-brand-rose bg-brand-rose/10 border border-brand-rose/30 px-3 py-2">{error}</div>}
  </>
  const matterSection = fixedMatterId ? <p className="text-sm font-semibold">Saving to this matter</p> : <MatterPicker matters={matters} selectedMatterId={matterId} onSelect={selectMatter} loading={matterLoading} disabled={saving || generating} />
  const smartFillSection = <>
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border border-brand-line rounded bg-brand-bg px-3 py-2">
      <div>
        <p className="text-sm font-medium text-brand-ink">Smart fill</p>
        <p className="text-xs text-brand-muted">Asks each question once for the whole packet. Your entries are kept on refresh.</p>
      </div>
      <button type="button" onClick={refresh} disabled={saving || generating || smartFillState === 'loading' || !matterId.trim()} className="flex shrink-0 items-center justify-center gap-2 whitespace-nowrap px-3 py-2 text-sm text-brand-ink border border-brand-line rounded hover:bg-brand-surface-2 disabled:opacity-50">
        <Wand2 size={15} />
        {smartFillState === 'loading' ? 'Filling...' : smartFillState === 'ready' ? 'Refresh matter values' : 'Smart Fill'}
      </button>
    </div>
    {smartFillMessage && <p role="status" className="text-xs text-brand-muted">{smartFillMessage}</p>}
  </>

  const packetSection = (
    <div className="min-w-0 space-y-4">
      <section aria-label="Packet" className="rounded-xl border border-brand-line bg-brand-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-brand-ink">Packet</h2>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => generateAll()} disabled={generating || saving || !matterId.trim() || !availableMembers.length || allSaved} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-semibold disabled:opacity-50">{generating ? 'Generating…' : allPreviewed ? 'Generate all again' : 'Generate all'}</button>
            {failedPreviews.length > 0 && !generating && <button type="button" onClick={() => generateAll(failedPreviews)} className="rounded-lg border border-brand-amber px-3 py-2 text-xs font-semibold">Retry failed previews</button>}
            <button type="button" onClick={() => saveAll()} disabled={saving || generating || !allPreviewed || allSaved || background === 'saving'} className="rounded-lg bg-brand-ink px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{saving ? 'Saving…' : 'Save all to matter'}</button>
            {failedSaves.length > 0 && !saving && <button type="button" onClick={() => saveAll(failedSaves)} className="rounded-lg border border-brand-amber px-3 py-2 text-xs font-semibold">Retry failed saves</button>}
          </div>
        </div>
        {background === 'saving' && <p role="status" className="mt-2 text-xs text-brand-muted">Saving in the background. You can leave this page; the matter's Documents tab shows the packet under "in progress" until every document is saved.</p>}
        {background === 'failed' && session?.last_error && <p role="alert" className="mt-2 text-xs text-brand-rose">{session.last_error}</p>}
        {session?.id && background !== 'saving' && <p className="mt-2 text-xs text-brand-muted">Your answers are available for 14 days; resume from the matter's Documents tab.</p>}
        <ul className="mt-3 space-y-2">
          {availableMembers.map((member) => {
            const preview = previewOf(member)
            const save = saveOf(member)
            const state = save?.status === 'saved' ? 'Saved' : save?.status === 'saving' ? 'Saving…' : save?.status === 'failed' ? `Save failed: ${save.error}` : preview.status === 'ready' ? 'Preview ready' : preview.status === 'loading' ? 'Previewing…' : preview.status === 'failed' ? `Preview failed: ${preview.error}` : 'Not previewed yet'
            return (
              <li key={member.template_id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-brand-line px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate"><strong>{member.title}</strong> <span className="text-xs text-brand-muted">· {member.output.format.toUpperCase()}{member.resolved_version_no ? ` · v${member.resolved_version_no}` : ''}</span></span>
                <span role="status" className={`text-xs ${save?.status === 'saved' ? 'text-brand-green' : preview.status === 'failed' || save?.status === 'failed' ? 'text-brand-rose' : 'text-brand-muted'}`}>{state}</span>
                {preview.status === 'ready' && preview.blob && (member.output.format === 'pdf'
                  ? <button type="button" onClick={() => { setView('document'); openMember(member.template_id, 'preview') }} className="text-xs underline" aria-label={`Open preview of ${member.title}`}>Open preview</button>
                  : <WordPreviewDownload preview={preview} />)}
                {preview.status === 'ready' && preview.rendered && <details className="basis-full mt-1"><summary className="cursor-pointer text-xs underline">Review Markdown preview</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-brand-bg p-2 text-xs">{preview.rendered}</pre></details>}
              </li>
            )
          })}
          {unavailable.map((item) => (
            <li key={item.template_id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-dashed border-brand-line px-3 py-2 text-sm text-brand-muted">
              <span><strong>{item.title}</strong> · skipped</span>
              <span role="alert" className="text-xs">{item.unavailable_reason}</span>
            </li>
          ))}
        </ul>
      </section>
      {allSaved && (
        <section aria-label="Saved packet" className="rounded-xl border border-brand-line bg-brand-surface p-4 text-sm">
          <p className="font-semibold text-brand-ink">Every document is saved to the matter.</p>
          <a className="text-brand-accent underline" href={buildSavedTarget({ matterId, documentId: sendable[0]?.id || null, returnTo })}>Open the matter's documents</a>
          {sendable.length === 0 && <p className="mt-1 text-brand-muted">No document in this packet has signature fields, so there is nothing to send for signature.</p>}
        </section>
      )}
      {allSaved && sendable.map((document) => (
        <SendStep key={document.id} matterId={matterId} document={document} savedTarget={buildSavedTarget({ matterId, documentId: document.id, returnTo })} />
      ))}
    </div>
  )

  const viewTabs = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div role="tablist" aria-label="Fill view" className="inline-flex rounded-lg border border-brand-line bg-brand-bg p-0.5">
        {VIEW_TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={view === id}
            onClick={() => (id === 'packet' ? setView('packet') : chooseView(id))}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${view === id ? 'bg-brand-surface text-brand-ink shadow-sm' : 'text-brand-muted hover:text-brand-ink'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {questions.length > 0 && view !== 'questions' && (
        <p className="text-xs text-brand-muted" role="status">
          {progress.percent}% complete · {progress.completed} of {progress.total} answered · {progress.verified || 0} verified · {requiredUnresolvedNames.length} required missing
        </p>
      )}
    </div>
  )

  if (view === 'questions') {
    return (
      <div className="flex min-w-0 flex-col gap-3">
        {viewTabs}
        <div className="grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-[minmax(300px,420px)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-4">
            {noticeSection}
            {matterSection}
            <StorageReadinessNotice enabled={Boolean(matterId.trim())} />
            {smartFillSection}
            {questions.length > 0 && (
              <div>
                <div className="sticky top-0 z-20 bg-brand-surface pb-2">
                  <TemplateFillProgress progress={progress} requiredMissing={requiredUnresolvedNames.length} filter={fieldFilter} onFilter={setFieldFilter} onNext={nextField} />
                </div>
                {groups.map((group) => (
                  <section key={group.label} aria-label={group.label} className="mb-3">
                    <h3 className="text-sm font-medium text-brand-ink mb-2">{group.label}</h3>
                    <div className="space-y-2">{group.questions.map((question) => renderQuestionEditor(question))}</div>
                  </section>
                ))}
                {visible.length === 0 && <p role="status" className="py-3 text-sm text-brand-muted">{fieldFilter === 'remaining' ? 'No missing answers.' : fieldFilter === 'unverified' ? 'Every answer is verified.' : 'No suggestions waiting for review.'}</p>}
              </div>
            )}
          </div>
          {packetSection}
        </div>
      </div>
    )
  }

  const setupSection = (
    <div className="space-y-3">
      {noticeSection}
      <div className="grid gap-3 lg:grid-cols-2 lg:items-start">
        <div className="min-w-0 space-y-2">{matterSection}<StorageReadinessNotice enabled={Boolean(matterId.trim())} /></div>
        <div className="min-w-0 space-y-2">{smartFillSection}</div>
      </div>
    </div>
  )

  if (view === 'packet') {
    return (
      <div className="flex min-w-0 flex-col gap-3">
        {viewTabs}
        {setupSection}
        {packetSection}
      </div>
    )
  }

  // Document view.
  const docHeight = 'h-[calc(100vh-15rem)] min-h-[520px]'
  const renderMemberFill = (doc) => {
    const values = memberValues(doc.fields, answers)
    const onChange = (name, value) => {
      const key = doc.fields.find((field) => field.name === name)?.question_key
      if (key) updateValue(key, value)
    }
    if (!doc.fields.length) return <p role="status" className="rounded-lg border border-brand-line bg-brand-bg p-6 text-center text-sm text-brand-muted">This document has nothing to fill. Preview it, or save it with the packet.</p>
    const common = {
      fields: doc.fields,
      values,
      activeName: activeFields[doc.memberId] || '',
      onActiveChange: (name) => setActiveField(doc.memberId, name),
      isMissing,
      onNextRequired: walkNextRequired,
      requiredMissing: requiredUnresolvedNames.length,
    }
    if (fillOnPage) {
      return (
        <FillOnDocument
          key={doc.memberId}
          {...common}
          source={activeSource.blob}
          onChange={onChange}
          renderInput={(field) => renderDocumentEditor(doc, field)}
          onUnavailable={onPdfUnavailable}
          statusFor={statusFor}
          markerFor={(field) => memberFieldMarker(field, doc.fields)}
          isShared={isShared}
          legend={LEGEND}
          checkboxValues={CHECKBOX_VALUES}
          disabled={locked}
          scrollToActiveOnOpen={String(walkedTo) === String(doc.memberId)}
        />
      )
    }
    if (activeOnPage && !activeSource.blob && !activeSource.failed && !unreadable[doc.memberId]) {
      return <p role="status" className="rounded-lg border border-brand-line bg-brand-bg-soft p-6 text-center text-sm text-brand-muted">Opening the original document…</p>
    }
    return (
      <>
        {activeOnPage && <p role="status" className="mb-2 text-xs text-brand-muted">The original PDF could not be opened for typing on the page. Use the bar below or Questions.</p>}
        <ReferenceFill key={doc.memberId} {...common} template={doc.member.template} renderInput={(field) => renderDocumentEditor(doc, field)} />
      </>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {viewTabs}
      {setupSection}
      {!documents.length ? (
        <p role="status" className="text-sm text-brand-muted">No document in this packet can be prepared yet.</p>
      ) : (
        <>
          <div role="tablist" aria-label="Packet documents" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
            {documents.map((doc) => {
              const missing = memberMissingCount(doc.fields, missingKeys)
              const state = memberState(doc.member, missing)
              const selected = String(doc.memberId) === String(activeId)
              return (
                <button
                  key={doc.memberId}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-label={`${doc.member.title}, ${state.label}`}
                  onClick={() => openMember(doc.memberId)}
                  className={`flex min-w-[9rem] max-w-[16rem] shrink-0 flex-col items-start rounded-lg border px-3 py-1.5 text-left transition ${selected ? 'border-brand-accent bg-brand-surface shadow-sm' : 'border-brand-line bg-brand-bg hover:bg-brand-surface'}`}
                >
                  <span className="w-full truncate text-sm font-semibold text-brand-ink">{doc.member.title}</span>
                  <span className={`text-xs ${state.tone}`}>{state.label}</span>
                </button>
              )
            })}
          </div>
          {unavailable.length > 0 && <p className="text-xs text-brand-muted">Skipped: {unavailable.map((item) => item.title).join(', ')}. See Packet for why.</p>}
          {activeDoc && (
            <div className="flex min-w-0 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <div role="tablist" aria-label={`${activeDoc.member.title} view`} className="inline-flex rounded-lg border border-brand-line bg-brand-bg p-0.5">
                  {[['fill', 'Fill'], ['preview', 'Preview']].map(([id, label]) => (
                    <button key={id} type="button" role="tab" aria-selected={memberView === id} onClick={() => setMemberViews((prev) => ({ ...prev, [activeId]: id }))} className={`rounded-md px-3 py-1 text-xs font-semibold transition ${memberView === id ? 'bg-brand-surface text-brand-ink shadow-sm' : 'text-brand-muted hover:text-brand-ink'}`}>{label}</button>
                  ))}
                </div>
                <span className="text-xs text-brand-muted">{activeDoc.member.output.format.toUpperCase()}{activeDoc.member.resolved_version_no ? ` · v${activeDoc.member.resolved_version_no}` : ''} · <Link2 size={11} className="inline" aria-hidden="true" /> marks an answer that also fills another document.</span>
              </div>
              {memberView === 'preview' ? (
                <MemberPreview
                  key={activeId}
                  member={activeDoc.member}
                  preview={previewOf(activeDoc.member)}
                  save={saveOf(activeDoc.member)}
                  missing={memberMissingCount(activeDoc.fields, missingKeys)}
                  matterReady={Boolean(matterId.trim())}
                  busy={generating || saving}
                  locked={allSaved}
                  onGenerate={() => generateAll([activeId])}
                />
              ) : (
                <div className={`flex min-w-0 flex-col ${docHeight}`}>{renderMemberFill(activeDoc)}</div>
              )}
            </div>
          )}
        </>
      )}
      <div className="flex flex-col gap-2 border-t border-brand-line pt-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-brand-muted" role="status">
          {requiredUnresolvedNames.length
            ? `${requiredUnresolvedNames.length} required answer${requiredUnresolvedNames.length === 1 ? '' : 's'} left across the packet.`
            : 'Every required answer is in. Generate and save the packet from Packet.'}
        </p>
        <button type="button" onClick={() => setView('packet')} className="rounded-lg bg-brand-ink px-3 py-2 text-xs font-semibold text-white">Review the packet</button>
      </div>
    </div>
  )
}
