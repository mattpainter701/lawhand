import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getTemplate, getTemplateSet, getTemplateSetDocumentsVariables, getTemplateSetInterview, renderTemplate, renderTemplateFile } from '../../api'
import { fillValue, interviewReview, isSigningField } from '../templates/templateFillReview'
import { getErrorMessage } from './prepareHelpers'
import { renderIsSendable, savedDocumentFromRender } from './SendStep'

const PREVIEW_CONCURRENCY = 3

// A member's output: a PDF template renders PDF; a Word template with
// signature fields renders PDF (only a PDF can be sent); other Word
// templates stay Word; anything else is text.
export function memberOutput(template) {
  const format = String(template?.format || '').toLowerCase()
  if (format === 'pdf' || format === 'image') return { format: 'pdf', file: true, convertToPdf: false }
  const signing = (template?.variable_schema?.fields || []).some((field) => field?.included !== false && isSigningField(field))
  if (format === 'docx' && template?.source_sha256) return signing ? { format: 'pdf', file: true, convertToPdf: true } : { format: 'docx', file: true, convertToPdf: false }
  return { format: 'markdown', file: false, convertToPdf: false }
}

// Run `work` over `items` with at most `limit` in flight, preserving order.
export async function pooled(items, limit, work) {
  const results = new Array(items.length)
  let next = 0
  const runners = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
    while (next < items.length) {
      const index = next
      next += 1
      results[index] = await work(items[index], index)
    }
  })
  await Promise.all(runners)
  return results
}

const memberState = (status, extra = {}) => ({ status, ...extra })

// The Prepare route for a set: one interview, many documents. Answers are
// fanned out by the server; every member renders through the per-template
// routes, so the preview evidence gate and the save path are exactly what
// they are for one document. Save-all runs from the browser, one member at a
// time, because preview evidence is per user.
export default function usePrepareSet({ setId, initialMatterId = '', folderId = null }) {
  const [set, setSet] = useState(null)
  const [members, setMembers] = useState([])
  const [interview, setInterview] = useState(null)
  const [matterId, setMatterId] = useState(initialMatterId || '')
  const [answers, setAnswers] = useState({})
  const [reviewedValues, setReviewedValues] = useState({})
  const [verifiedNames, setVerifiedNames] = useState({})
  const [fieldFilter, setFieldFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [smartFillState, setSmartFillState] = useState('idle')
  const [smartFillMessage, setSmartFillMessage] = useState('')
  const [previews, setPreviews] = useState({})
  const [saves, setSaves] = useState({})
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const generationRef = useRef(0)
  const mountedRef = useRef(true)
  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false } }, [])

  // The set and each available member's release, once per set.
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    ;(async () => {
      try {
        const record = await getTemplateSet(setId)
        const loaded = await Promise.all((record.items || []).map(async (item) => {
          if (item.unavailable_reason) return { ...item, template: null, output: null }
          try {
            const template = await getTemplate(item.template_id, { published: true })
            return { ...item, template, output: memberOutput(template) }
          } catch (err) {
            return { ...item, template: null, output: null, unavailable_reason: getErrorMessage(err, 'This template could not be loaded.') }
          }
        }))
        if (!active) return
        setSet(record)
        setMembers(loaded.sort((a, b) => (a.position ?? 0) - (b.position ?? 0)))
      } catch (err) {
        if (active) setError(getErrorMessage(err, 'This set could not be loaded.'))
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => { active = false }
  }, [setId])

  const questions = useMemo(() => interview?.questions || [], [interview])
  const unavailable = useMemo(() => interview?.unavailable || [], [interview])

  // The interview, and the matter's suggestions applied to unanswered
  // questions. Running it again is the refresh: typed answers are kept.
  const loadInterview = useCallback(async (nextMatterId) => {
    const generation = generationRef.current + 1
    generationRef.current = generation
    setSmartFillState('loading'); setSmartFillMessage('')
    try {
      const response = await getTemplateSetInterview(setId, nextMatterId || undefined)
      if (!mountedRef.current || generationRef.current !== generation) return
      setInterview(response)
      const suggested = {}
      for (const question of response.questions || []) {
        if (question.suggested_value != null && String(question.suggested_value) !== '') suggested[question.key] = fillValue(question.suggested_value)
      }
      setAnswers((prev) => {
        const next = { ...prev }
        for (const [key, value] of Object.entries(suggested)) if (!fillValue(next[key]).trim()) next[key] = value
        return next
      })
      setVerifiedNames((prev) => {
        const next = { ...prev }
        for (const key of Object.keys(next)) if (suggested[key] != null && suggested[key] !== fillValue(answers[key])) delete next[key]
        return next
      })
      setSmartFillState(nextMatterId ? 'ready' : 'idle')
      setSmartFillMessage(nextMatterId ? 'Available values refreshed. Your entries were kept.' : '')
    } catch (err) {
      if (!mountedRef.current) return
      setSmartFillState('error'); setSmartFillMessage(getErrorMessage(err, 'The interview could not be loaded.'))
    }
  }, [setId])

  useEffect(() => { if (set) loadInterview(matterId.trim()) }, [set, matterId, loadInterview])

  const invalidatePreviews = useCallback(() => {
    setPreviews((prev) => Object.fromEntries(Object.entries(prev).map(([id, entry]) => [id, entry.status === 'saved' ? entry : memberState('idle')])))
  }, [])

  const setAnswer = (key, value) => {
    setAnswers((prev) => ({ ...prev, [key]: value }))
    setVerifiedNames((prev) => { const next = { ...prev }; if (String(value ?? '').trim()) next[key] = true; else delete next[key]; return next })
    invalidatePreviews()
  }
  const toggleVerified = (key) => setVerifiedNames((prev) => { const next = { ...prev }; if (next[key]) delete next[key]; else next[key] = true; return next })
  const selectMatter = (id) => {
    if (id === matterId) return
    setMatterId(id)
    setPreviews({}); setSaves({})
  }

  const progress = interviewReview(questions, answers, reviewedValues, verifiedNames)
  const requiredUnresolvedNames = progress.rows.filter((row) => row.required && !row.present).map((row) => row.name)
  const filteredKeys = fieldFilter === 'all' ? questions.map((q) => q.key) : (fieldFilter === 'remaining' ? progress.remaining : fieldFilter === 'unverified' ? progress.unverified : progress.review).map((row) => row.name)
  const nextField = () => {
    const target = (progress.remaining[0] || progress.review[0])?.name
    if (!target) return
    const input = document.getElementById(`set-answer-${target}`)
    input?.scrollIntoView?.({ block: 'center' })
    input?.focus({ preventScroll: true })
  }

  const availableMembers = members.filter((member) => member.template && member.output)
  const previewOf = (member) => previews[member.template_id] || memberState('idle')
  const saveOf = (member) => saves[member.template_id] || null
  const allPreviewed = availableMembers.length > 0 && availableMembers.every((member) => previewOf(member).status === 'ready' || saveOf(member)?.status === 'saved')
  const allSaved = availableMembers.length > 0 && availableMembers.every((member) => saveOf(member)?.status === 'saved')
  const savedDocuments = availableMembers.map((member) => saveOf(member)).filter((entry) => entry?.status === 'saved').map((entry) => entry.response)

  // Every available member's variables from the server, then one preview
  // per member, three at a time. `only` limits a retry to the named members.
  const generateAll = async (only = null) => {
    if (!matterId.trim()) { setError('Choose the destination matter before generating the packet.'); return }
    if (requiredUnresolvedNames.length) { setError(`Answer ${requiredUnresolvedNames.length} required question${requiredUnresolvedNames.length === 1 ? '' : 's'} before generating.`); return }
    const targets = availableMembers.filter((member) => !only || only.includes(member.template_id))
    setError(''); setGenerating(true)
    setPreviews((prev) => ({ ...prev, ...Object.fromEntries(targets.map((member) => [member.template_id, memberState('loading')])) }))
    try {
      const fan = await getTemplateSetDocumentsVariables(setId, { matter_id: matterId.trim(), answers })
      await pooled(targets, PREVIEW_CONCURRENCY, async (member) => {
        const variables = fan.documents?.[member.template_id] || {}
        try {
          let entry
          if (member.output.file) {
            const result = await renderTemplateFile(member.template_id, {
              variables, matter_id: matterId.trim(), preview_purpose: 'generation',
              ...(member.output.convertToPdf ? { convert_to_pdf: true } : {}),
            })
            entry = memberState('ready', { previewId: result.previewId || '', filename: result.filename, blob: result.blob, variables })
          } else {
            const result = await renderTemplate(member.template_id, { variables })
            entry = memberState('ready', { rendered: result.rendered || '', filename: result.output_filename || `${member.title}.md`, variables })
          }
          if (mountedRef.current) setPreviews((prev) => ({ ...prev, [member.template_id]: entry }))
        } catch (err) {
          if (mountedRef.current) setPreviews((prev) => ({ ...prev, [member.template_id]: memberState('failed', { error: getErrorMessage(err, 'The preview failed.'), variables }) }))
        }
      })
    } catch (err) {
      if (mountedRef.current) {
        setError(getErrorMessage(err, 'The packet could not be prepared.'))
        setPreviews((prev) => ({ ...prev, ...Object.fromEntries(targets.map((member) => [member.template_id, memberState('idle')])) }))
      }
    } finally {
      if (mountedRef.current) setGenerating(false)
    }
  }

  // One save per ready member, in set order, one at a time. A failure is
  // recorded on its row and the rest continue; Retry re-runs only the failed.
  const saveAll = async (only = null) => {
    if (!matterId.trim()) return
    const targets = availableMembers.filter((member) => (!only || only.includes(member.template_id)) && saveOf(member)?.status !== 'saved')
    if (targets.some((member) => previewOf(member).status !== 'ready')) { setError('Preview every document before saving the packet.'); return }
    setError(''); setSaving(true)
    const verified = questions.filter((question) => verifiedNames[question.key] && fillValue(answers[question.key]).trim())
    try {
      for (const member of targets) {
        const preview = previewOf(member)
        const verifiedFields = verified.flatMap((question) => question.appears_in.filter((ref) => ref.template_id === member.template_id).map((ref) => ref.field_name)).filter((name) => name in (preview.variables || {}))
        setSaves((prev) => ({ ...prev, [member.template_id]: memberState('saving') }))
        try {
          const response = await renderTemplate(member.template_id, {
            variables: preview.variables || {},
            matter_id: matterId.trim(),
            ...(folderId ? { folder_id: folderId } : {}),
            ...(member.output.convertToPdf ? { convert_to_pdf: true } : {}),
            ...(member.output.format === 'pdf' ? { preview_id: preview.previewId } : {}),
            ...(verifiedFields.length ? { verified_fields: verifiedFields } : {}),
          })
          if (!mountedRef.current) return
          if (!response?.matter_document_id) throw new Error('The server did not return a saved matter document.')
          setSaves((prev) => ({ ...prev, [member.template_id]: memberState('saved', { response }) }))
        } catch (err) {
          if (!mountedRef.current) return
          const status = err?.response?.status
          setSaves((prev) => ({ ...prev, [member.template_id]: memberState('failed', { error: getErrorMessage(err, 'The save failed.') }) }))
          // Evidence that no longer binds sends the member back to Review.
          if (status === 409) setPreviews((prev) => ({ ...prev, [member.template_id]: memberState('idle') }))
        }
      }
    } finally {
      if (mountedRef.current) setSaving(false)
    }
  }

  return {
    set, members, availableMembers, unavailable, interview, questions, loading, error, setError,
    matterId, selectMatter, answers, setAnswer, reviewedValues, setReviewedValues, verifiedNames, toggleVerified,
    fieldFilter, setFieldFilter, filteredKeys, nextField, progress, requiredUnresolvedNames,
    smartFillState, smartFillMessage, refresh: () => loadInterview(matterId.trim()),
    previews, previewOf, saves, saveOf, generating, saving, generateAll, saveAll, allPreviewed, allSaved,
    savedDocuments, sendable: savedDocuments.filter(renderIsSendable).map(savedDocumentFromRender),
  }
}
