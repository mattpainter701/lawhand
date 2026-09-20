import { useCallback, useEffect, useRef, useState } from 'react'
import { createSignatureRequest, getMatterDocumentSigningSource, getSignatureRequestFields, sendSignatureRequest, voidSignatureRequest } from '../../api'
import { placementBlockMessage, placementProblemLines, placementReviewPossible } from '../templates/signingPlacementProblems'
import {
  EMPTY_SIGNING_FIELDS, buildSignatureRequestPayload, duplicateSignerRoles, freeSignerRole, newSignerRow,
  placementRolesFor, prepareSigners, roleOptionsFor, signatureRequestProblem, signatureSendNotice,
} from './signatureRequestRules'

// The lifecycle of one signature request against one matter document: signers
// and dates, an optional placement review of the final PDF, a draft the server
// returns with where each signer will sign, then send or discard. The panel on
// the matter and the Send step of the Prepare route share it, so a document
// generated a moment ago is sent under the same rules as one chosen later.
export default function useSignatureRequestDraft({ matterId, document, initialSigners, onSent, onDraftCreated }) {
  const [signers, setSigners] = useState(() => (initialSigners?.length ? initialSigners : [newSignerRow()]))
  const [positionedFields, setPositionedFields] = useState(() => document?.positioned_fields || EMPTY_SIGNING_FIELDS)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [signingSource, setSigningSource] = useState(null)
  // A created request waits here, with where each signer will sign, until
  // staff have looked. A plan the server guessed at cannot be sent unread.
  const [draft, setDraft] = useState(null)
  const [expiresOn, setExpiresOn] = useState('')
  const [dueOn, setDueOn] = useState('')
  const [reminderDays, setReminderDays] = useState('7,1')
  const [enforceSigningOrder, setEnforceSigningOrder] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [noticeDelivered, setNoticeDelivered] = useState(true)

  const documentId = document?.id ? String(document.id) : ''
  // False once the host unmounts, so a create/send/discard that finishes after
  // the user has navigated away cannot set state or run a caller callback.
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])
  // Choosing another document starts its placement over: the fields belong
  // to the document's bytes, not to the form.
  useEffect(() => {
    setPositionedFields(document?.positioned_fields || EMPTY_SIGNING_FIELDS)
    setReviewOpen(false)
    setSigningSource(null)
  }, [documentId])

  useEffect(() => {
    let cancelled = false
    setSigningSource(null)
    if (reviewOpen && documentId) {
      getMatterDocumentSigningSource(matterId, documentId)
        .then((source) => { if (!cancelled) setSigningSource(source) })
        .catch(() => { if (!cancelled) setError('The final PDF could not be loaded for placement review.') })
    }
    return () => { cancelled = true }
  }, [reviewOpen, documentId, matterId])

  const initialFields = document?.positioned_fields || EMPTY_SIGNING_FIELDS
  const requiredRoles = document?.signing_roles || EMPTY_SIGNING_FIELDS
  const placementRoles = placementRolesFor({ requiredRoles, fields: initialFields, signers })
  const roleOptions = roleOptionsFor(placementRoles)
  // The placement review groups its fields by role, so it needs the signer
  // behind each role to label them.
  const placementSigners = placementRoles.map((role) => ({
    role,
    name: signers.find((signer) => signer.role === role && signer.name.trim())?.name.trim() || '',
  }))
  const duplicateRoles = duplicateSignerRoles(signers)
  // A Word document has no page the review can render, so offering the button
  // would send staff to a screen that cannot clear the block.
  const reviewPossible = Boolean(document) && placementReviewPossible(document)
  const placementLines = document ? placementProblemLines(document) : []

  const updateSigner = (index, key, value) => setSigners((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)))
  const addSigner = () => setSigners((prev) => [...prev, { ...newSignerRow(), role: freeSignerRole(prev) }])
  const removeSigner = (index) => setSigners((prev) => (prev.length === 1 ? prev : prev.filter((_, i) => i !== index)))

  const resetForm = useCallback(() => {
    setSigners(initialSigners?.length ? initialSigners : [newSignerRow()])
    setReviewOpen(false); setSigningSource(null); setPositionedFields(EMPTY_SIGNING_FIELDS)
    setExpiresOn(''); setDueOn(''); setReminderDays('7,1'); setEnforceSigningOrder(true)
  }, [initialSigners])

  // The request exists as a draft; show where the server put each signer
  // before anything reaches the client.
  const openDraft = async (request) => {
    let manifest = null
    try { manifest = await getSignatureRequestFields(matterId, request.id) } catch { manifest = null }
    if (!mountedRef.current) return
    setDraft({ request, fields: Array.isArray(manifest?.fields) ? manifest.fields : [], acknowledged: false })
  }

  const prepare = async (event) => {
    event?.preventDefault?.()
    setError(''); setNotice(''); setNoticeDelivered(true)
    const preparedSigners = prepareSigners(signers)
    const problem = signatureRequestProblem({ document, preparedSigners, positionedFields, requiredRoles, placementBlockMessage })
    if (problem) { setError(problem); return false }
    setBusy(true)
    try {
      const request = await createSignatureRequest(matterId, buildSignatureRequestPayload({
        documentId, preparedSigners, positionedFields, dueOn, expiresOn, reminderDays, enforceSigningOrder,
      }))
      await openDraft(request)
      // The request now exists and is pending, so the queue that lists it is
      // stale until it is reloaded.
      if (mountedRef.current) onDraftCreated?.(request)
      return true
    } catch (err) {
      if (mountedRef.current) setError(err?.response?.data?.detail || 'Failed to create signature request.')
      return false
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  const setAcknowledged = (acknowledged) => setDraft((prev) => (prev ? { ...prev, acknowledged } : prev))

  const sendDraft = async () => {
    if (!draft) return null
    setError(''); setNotice(''); setNoticeDelivered(true)
    setBusy(true)
    try {
      const sent = draft.acknowledged
        ? await sendSignatureRequest(matterId, draft.request.id, { acknowledge_review: true })
        : await sendSignatureRequest(matterId, draft.request.id)
      if (!mountedRef.current) return sent
      setDraft(null)
      resetForm()
      const outcome = signatureSendNotice(sent)
      setNoticeDelivered(outcome.delivered)
      setNotice(outcome.text)
      onSent?.(sent, outcome)
      return sent
    } catch (err) {
      if (mountedRef.current) setError(err?.response?.data?.detail || 'Failed to send the signature request.')
      return null
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  const discardDraft = async () => {
    if (!draft) return
    setError('')
    setBusy(true)
    try {
      await voidSignatureRequest(matterId, draft.request.id, { reason: 'Discarded before sending' })
      if (!mountedRef.current) return
      setDraft(null)
      onSent?.(null, null)
    } catch (err) {
      if (mountedRef.current) setError(err?.response?.data?.detail || 'Failed to discard the draft.')
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  return {
    signers, updateSigner, addSigner, removeSigner,
    positionedFields, setPositionedFields, initialFields, requiredRoles, placementRoles, roleOptions, placementSigners, duplicateRoles,
    reviewOpen, setReviewOpen, signingSource, reviewPossible, placementLines,
    draft, setAcknowledged,
    dueOn, setDueOn, expiresOn, setExpiresOn, reminderDays, setReminderDays, enforceSigningOrder, setEnforceSigningOrder,
    busy, error, setError, notice, setNotice, noticeDelivered, setNoticeDelivered,
    prepare, openDraft, sendDraft, discardDraft, resetForm,
  }
}
