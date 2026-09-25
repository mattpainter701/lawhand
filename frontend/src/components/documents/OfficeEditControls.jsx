import { useCallback, useEffect, useRef, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { AlertTriangle, ExternalLink, Loader2, MonitorUp, RefreshCw, Upload } from 'lucide-react'
import {
  reconcileMatterDocument,
  startMatterDocumentCloudEdit,
  uploadRevisedMatterDocument,
} from '../../api'
import { useConfirm } from '../dialog/ConfirmProvider'
import { useToast } from '../toast/useToast'

// Edit a matter's Word document in the firm's own Word or Google Docs, then
// bring the edits back as the same document's next version. LawHand never
// hosts an editor: it hands out a fresh link to the exact cloud file, marks
// who is editing, and adopts the edited bytes when the person returns (or on
// "Bring back changes"). "Upload revised version" covers anyone who edited a
// downloaded copy instead.

const CLOUD_BACKENDS = ['onedrive', 'sharepoint', 'google_drive']
const LOCKED_STATUSES = ['approved', 'filed', 'superseded', 'archived']
const DOCX_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const APP_LABELS = { word_web: 'Word', word_desktop: 'the Word app', google_docs: 'Google Docs' }
// A person coming back to this tab is the natural moment to bring edits back,
// but not on every flicker of focus.
const RETURN_RECONCILE_INTERVAL_MS = 15000
// Matches the server: the "being edited" marker lasts 12 hours from opening.
const EDIT_MARKER_TTL_MS = 12 * 60 * 60 * 1000

export function isBeingEdited(doc, now = Date.now()) {
  const started = Date.parse(doc?.external_edit_started_at || '')
  return Number.isFinite(started) && now - started < EDIT_MARKER_TTL_MS
}

function isWordDocument(doc) {
  const filename = String(doc?.filename || '').toLowerCase()
  const contentType = String(doc?.content_type || '').toLowerCase()
  return filename.endsWith('.docx') || contentType === DOCX_MIME_TYPE
}

/** What the office round trip can do for this document. */
export function officeEditState(doc) {
  const word = isWordDocument(doc)
  // Assistant drafts and their approved derivatives keep their own review
  // and release flows.
  const assistantDraft = Boolean(doc?.generated_artifact_revision_id)
    || String(doc?.document_category || '').toLowerCase() === 'assistant_revision'
  const locked = LOCKED_STATUSES.includes(doc?.document_status)
  const cloud = CLOUD_BACKENDS.includes(doc?.storage_backend) && Boolean(doc?.provider_object_id)
  const usable = word && !assistantDraft && !locked
  return {
    canOpen: usable && cloud,
    canBringBack: word && !assistantDraft && cloud,
    canUpload: usable,
    suite: doc?.storage_backend === 'google_drive' ? 'google' : 'microsoft',
  }
}

function errorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (typeof detail?.message === 'string') return detail.message
  return fallback
}

function sinceLabel(value) {
  if (!value) return ''
  try { return format(parseISO(value), 'MMM d, h:mm a') } catch { return '' }
}

export default function OfficeEditControls({ matterId, doc, onDocumentChange, layout = 'row' }) {
  const state = officeEditState(doc)
  const toast = useToast()
  const confirmAction = useConfirm()
  const [busy, setBusy] = useState('')
  const openedHere = useRef(false)
  const lastReturnCheck = useRef(0)
  const fileInput = useRef(null)
  const card = layout === 'card'

  const bringBack = useCallback(async ({ quiet = false } = {}) => {
    setBusy('reconcile')
    try {
      const result = await reconcileMatterDocument(matterId, doc.id)
      onDocumentChange?.(result.document)
      if (result.outcome === 'adopted') {
        toast.success('Edits brought back', { message: `${doc.filename}: ${result.message}` })
      } else if (result.outcome === 'blocked') {
        toast.error('Edits were not brought back', { message: result.message })
      } else if (!quiet) {
        toast.info('No changes to bring back', { message: result.message })
      }
    } catch (error) {
      if (!quiet) toast.error('Could not bring back changes', { message: errorMessage(error, 'Please try again.') })
    } finally {
      setBusy('')
    }
  }, [doc.filename, doc.id, matterId, onDocumentChange, toast])

  // Bring edits back when the person who opened the file here returns to
  // LawHand. Others see the marker and can bring changes back themselves.
  const markerActive = isBeingEdited(doc)
  useEffect(() => {
    if (!markerActive || !openedHere.current) return undefined
    const onReturn = () => {
      if (globalThis.document?.visibilityState === 'hidden') return
      const now = Date.now()
      if (now - lastReturnCheck.current < RETURN_RECONCILE_INTERVAL_MS) return
      lastReturnCheck.current = now
      void bringBack({ quiet: true })
    }
    window.addEventListener('focus', onReturn)
    globalThis.document?.addEventListener('visibilitychange', onReturn)
    return () => {
      window.removeEventListener('focus', onReturn)
      globalThis.document?.removeEventListener('visibilitychange', onReturn)
    }
  }, [bringBack, markerActive])

  const open = async (app) => {
    // Open the tab inside the click so pop-up blockers allow it, then point it
    // at the fresh link once LawHand has it.
    const popup = app === 'word_desktop' ? null : window.open('', '_blank')
    setBusy(app)
    try {
      const result = await startMatterDocumentCloudEdit(matterId, doc.id, app)
      // Set before the parent re-renders with the marker, so the return
      // listener arms for this person.
      openedHere.current = true
      lastReturnCheck.current = Date.now()
      onDocumentChange?.(result.document)
      const url = result.links?.[app] || result.links?.[result.app]
      if (!url) throw new Error('No link was returned for this file.')
      if (app === 'word_desktop') {
        window.location.href = url
      } else if (popup) {
        popup.opener = null
        popup.location.href = url
      } else {
        window.open(url, '_blank', 'noopener,noreferrer')
      }
    } catch (error) {
      popup?.close()
      toast.error('Could not open the document', { message: errorMessage(error, error?.message || 'Please try again.') })
    } finally {
      setBusy('')
    }
  }

  const chooseRevised = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const confirmed = await confirmAction({
      title: 'Replace with your revised version?',
      message: `${file.name} becomes the current version of ${doc.filename}. The change is recorded on the matter timeline.`,
      confirmLabel: 'Replace document',
    })
    if (!confirmed) return
    setBusy('upload')
    try {
      const result = await uploadRevisedMatterDocument(matterId, doc.id, file)
      onDocumentChange?.(result.document)
      if (result.outcome === 'adopted') toast.success('Revised version saved', { message: result.message })
      else toast.info('Nothing changed', { message: result.message })
    } catch (error) {
      toast.error('Revised version was not saved', { message: errorMessage(error, 'Please try again.') })
    } finally {
      setBusy('')
    }
  }

  if (!state.canOpen && !state.canUpload && !(state.canBringBack && doc.storage_state === 'conflict')) return null

  const editing = markerActive
  const conflict = doc.storage_state === 'conflict'
  const suiteLabel = state.suite === 'google' ? 'Google Docs' : 'Word'
  const button = card
    ? 'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-brand-line px-3 text-xs font-bold text-brand-ink hover:bg-brand-bg-soft disabled:opacity-50'
    : 'inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg border border-brand-line px-2.5 text-xs font-bold text-brand-ink hover:border-brand-accent hover:bg-brand-bg-soft disabled:opacity-50'
  const spinner = <Loader2 size={14} className="animate-spin" aria-hidden="true" />

  return (
    <div className={card ? 'mt-3 space-y-2 border-t border-brand-line pt-3' : 'mt-1.5 space-y-1.5'} data-testid={`office-edit-${doc.id}`}>
      {(editing || conflict) && (
        <p role="status" className={`flex items-start gap-1.5 text-[11px] leading-snug ${conflict ? 'text-brand-rose' : 'text-brand-accent-2'}`}>
          {conflict ? <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden="true" /> : <ExternalLink size={12} className="mt-0.5 shrink-0" aria-hidden="true" />}
          <span>
            {conflict
              ? (doc.storage_error || 'Changed outside LawHand. Bring back the changes to keep working with it.')
              : `Being edited in ${APP_LABELS[doc.external_edit_app] || suiteLabel}${doc.external_edit_started_by_name ? ` by ${doc.external_edit_started_by_name}` : ''}${sinceLabel(doc.external_edit_started_at) ? ` since ${sinceLabel(doc.external_edit_started_at)}` : ''}.`}
          </span>
        </p>
      )}
      <div className={card ? 'grid grid-cols-2 gap-2' : 'flex flex-wrap items-center gap-1.5'}>
        {state.canOpen && (
          <button type="button" onClick={() => open(state.suite === 'google' ? 'google_docs' : 'word_web')} disabled={Boolean(busy)} aria-label={`Open ${doc.filename} in ${suiteLabel}`} className={button}>
            {busy === 'word_web' || busy === 'google_docs' ? spinner : <ExternalLink size={14} aria-hidden="true" />} Open in {suiteLabel}
          </button>
        )}
        {state.canOpen && state.suite === 'microsoft' && (
          <button type="button" onClick={() => open('word_desktop')} disabled={Boolean(busy)} aria-label={`Open ${doc.filename} in the Word app`} title="Open in the Word desktop app" className={button}>
            {busy === 'word_desktop' ? spinner : <MonitorUp size={14} aria-hidden="true" />} Word app
          </button>
        )}
        {state.canBringBack && (editing || conflict) && (
          <button type="button" onClick={() => bringBack()} disabled={Boolean(busy)} aria-label={`Bring back changes to ${doc.filename}`} className={`${button} ${conflict ? 'border-brand-rose/40' : 'border-brand-accent/50'}`}>
            {busy === 'reconcile' ? spinner : <RefreshCw size={14} aria-hidden="true" />} Bring back changes
          </button>
        )}
        {state.canUpload && (
          <>
            <button type="button" onClick={() => fileInput.current?.click()} disabled={Boolean(busy)} aria-label={`Upload a revised version of ${doc.filename}`} title="Edited a downloaded copy? Upload it as the new version." className={button}>
              {busy === 'upload' ? spinner : <Upload size={14} aria-hidden="true" />} Upload revised
            </button>
            <input ref={fileInput} type="file" tabIndex={-1} aria-label={`Revised version of ${doc.filename}`} accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="hidden" onChange={chooseRevised} data-testid={`revised-input-${doc.id}`} />
          </>
        )}
      </div>
    </div>
  )
}
