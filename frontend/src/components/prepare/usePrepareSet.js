import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getFillSession, getTemplate, getTemplateSet, getTemplateSetDocumentsVariables, getTemplateSetInterview, renderFillSession, renderTemplate, renderTemplateFile, writeFillSession } from '../../api'
import { fillValue, interviewReview, isSigningField } from '../templates/templateFillReview'
import { getErrorMessage } from './prepareHelpers'
import { renderIsSendable, savedDocumentFromRender } from './SendStep'

const PREVIEW_CONCURRENCY = 3

const US_STATE_NAMES = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming', PR: 'Puerto Rico', GU: 'Guam', VI: 'U.S. Virgin Islands',
}

const choiceForms = (value) => {
  const text = fillValue(value).trim()
  const forms = new Set([text.toLocaleLowerCase()])
  const stateName = US_STATE_NAMES[text.toUpperCase()]
  if (stateName) forms.add(stateName.toLocaleLowerCase())
  const stateCode = Object.entries(US_STATE_NAMES).find(([, name]) => name.toLocaleLowerCase() === text.toLocaleLowerCase())?.[0]
  if (stateCode) forms.add(stateCode.toLocaleLowerCase())
  return forms
}

const normalizeChoiceSuggestion = (question) => {
  const raw = question?.suggested_value
  if (raw == null || fillValue(raw).trim() === '') return question
  const kind = fillValue(question.value_kind).toLocaleLowerCase()
  if (!['choice', 'radio', 'select'].includes(kind) || !Array.isArray(question.options) || !question.options.length) return question
  const options = question.options.map((option) => {
    if (option && typeof option === 'object') return { value: fillValue(option.value ?? option.label), label: fillValue(option.label ?? option.value) }
    return { value: fillValue(option), label: fillValue(option) }
  }).filter((option) => option.value)
  const rawForms = choiceForms(raw)
  const selected = options.find((option) => [...choiceForms(option.value)].some((form) => rawForms.has(form)) || [...choiceForms(option.label)].some((form) => rawForms.has(form)))
  return { ...question, suggested_value: selected?.value ?? null }
}

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

// The saved/failed rows to show for a session's recorded members, including
// the signing descriptor a background-saved PDF needs to stay sendable after
// the page is reopened.
const savesFromMembers = (members) => Object.fromEntries((members || [])
  .filter((member) => member.status !== 'queued')
  .map((member) => [member.template_id, member.status === 'saved'
    ? memberState('saved', { response: {
        matter_document_id: member.matter_document_id,
        output_filename: member.output_filename,
        output_format: member.output_format || 'pdf',
        signing_roles: member.signing_roles || [],
        positioned_fields: member.positioned_fields || [],
        signing_placement_required: Boolean(member.signing_placement_required),
      } })
    : memberState('failed', { error: member.detail || 'Not saved' })]))

// The Prepare route for a set: one interview, many documents. Answers are
// fanned out by the server; every member renders through the per-template
// routes, so the preview evidence gate and the save path are exactly what
// they are for one document. Save-all runs from the browser, one member at a
// time, because preview evidence is per user.
export default function usePrepareSet({ setId, initialMatterId = '', folderId = null, sessionId = null, onSessionCreated = null }) {
  const [set, setSet] = useState(null)
  const [members, setMembers] = useState([])
  const [interview, setInterview] = useState(null)
  const availableMembersKey = members.filter((member) => member.template && member.output).map((member) => `${member.template_id}:${member.resolved_version_no ?? ''}`).join(',')
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
  const revisionRef = useRef(0)
  const mountedRef = useRef(true)
  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false } }, [])
  // The server-side session: created on the first answer, updated a moment
  // after each change, resumed from `?session=`, and what a background save
  // runs from.
  const [session, setSession] = useState(null)
  const [sessionRestored, setSessionRestored] = useState(!sessionId)
  const [background, setBackground] = useState(null) // null | 'saving' | 'saved' | 'failed'
  const sessionRef = useRef(null)
  const saveTimer = useRef(null)
  const restoredAnswers = useRef(null)
  const answersRef = useRef({})
  const persistInFlight = useRef(null)
  const persistEpoch = useRef(0)
  const restoreEpoch = useRef(0)
  const persistDirty = useRef(false)
  const persistRevision = useRef(0)
  const flushRef = useRef(null)
  const latestPersist = useRef(null)
  const lastPersistedKey = useRef('')
  const onSessionCreatedRef = useRef(onSessionCreated)
  useEffect(() => { onSessionCreatedRef.current = onSessionCreated }, [onSessionCreated])
  const [restoreAttempt, setRestoreAttempt] = useState(0)
  const [sessionRestoreError, setSessionRestoreError] = useState('')
  const [persistError, setPersistError] = useState('')
  const [persistStatus, setPersistStatus] = useState('idle')
  useEffect(() => {
    if (!sessionId) return undefined
    if (sessionRef.current?.id === sessionId) return undefined
    const requestEpoch = restoreEpoch.current
    let active = true
    getFillSession(sessionId)
      .then((value) => {
        if (!active || restoreEpoch.current !== requestEpoch) return
        if (String(value.set_id) !== String(setId)) throw new Error('This saved packet belongs to a different template set.')
        sessionRef.current = value
        setSession(value)
        restoredAnswers.current = value.answers || {}
        answersRef.current = value.answers || {}
        setAnswers(value.answers || {})
        setVerifiedNames(Object.fromEntries((value.verified || []).map((key) => [key, true])))
        setReviewedValues(Object.fromEntries((value.verified || [])
          .filter((key) => fillValue(value.answers?.[key]).trim())
          .map((key) => [key, fillValue(value.answers[key])])))
        persistDirty.current = false
        if (value.matter_id) setMatterId(value.matter_id)
        if (value.status === 'saving') setBackground('saving')
        else if (value.status === 'saved' || value.status === 'failed') {
          setBackground(value.status === 'saved' ? 'saved' : 'failed')
        }
        // Show whatever the session already recorded — including a partial
        // background save that left it open — so a reopened packet is not
        // "not previewed" and its Send card is not lost. Queued members are
        // skipped by the helper.
        setSaves(savesFromMembers(value.members))
        if ((value.members || []).some((member) => member.status === 'preview_expired')) {
          setPreviews((prev) => Object.fromEntries(Object.entries(prev).map(([id, entry]) => [id, (value.members || []).find((member) => member.template_id === id && member.status === 'preview_expired') ? memberState('idle') : entry])))
        }
        setSessionRestored(true)
      })
      .catch((err) => { if (active && restoreEpoch.current === requestEpoch) setSessionRestoreError(getErrorMessage(err, 'The saved packet could not be restored.')) })
    return () => { active = false }
  }, [sessionId, setId, restoreAttempt])

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
      const normalizedResponse = {
        ...response,
        questions: (response.questions || []).map(normalizeChoiceSuggestion),
      }
      setInterview(normalizedResponse)
      const suggested = {}
      for (const question of normalizedResponse.questions) {
        if (question.suggested_value != null && String(question.suggested_value) !== '') suggested[question.key] = fillValue(question.suggested_value)
      }
      const previousAnswers = answersRef.current
      setAnswers((prev) => {
        const next = { ...prev }
        for (const [key, value] of Object.entries(suggested)) if (!fillValue(next[key]).trim()) next[key] = value
        answersRef.current = next
        return next
      })
      setVerifiedNames((prev) => {
        const next = { ...prev }
        for (const key of Object.keys(next)) {
          if (suggested[key] == null) continue
          if (fillValue(previousAnswers[key]) !== fillValue(answersRef.current[key])) delete next[key]
        }
        return next
      })
      setSmartFillState(nextMatterId ? 'ready' : 'idle')
      setSmartFillMessage(nextMatterId ? 'Available values refreshed. Your entries were kept.' : '')
      if (Object.keys(suggested).length) {
        persistDirty.current = true
        persistRevision.current += 1
        setPersistStatus('pending')
      }
    } catch (err) {
      if (!mountedRef.current || generationRef.current !== generation) return
      setSmartFillState('error'); setSmartFillMessage(getErrorMessage(err, 'The interview could not be loaded.'))
    }
  }, [setId])

  useEffect(() => { if (set && sessionRestored) loadInterview(matterId.trim()) }, [set, matterId, sessionRestored, loadInterview])

  // Persist answers, verified names and the matter a moment after they
  // change. Creating the session lazily means an untouched page leaves no row.
  const flushLatest = useCallback(async () => {
    // Every caller records a complete snapshot. If a write is already in
    // flight, wait for it and then drain the newest snapshot instead of
    // replaying the closure that happened to start the first write.
    if (!set || !sessionRestored || background === 'saving' || background === 'saved') return sessionRef.current
    const epoch = persistEpoch.current
    const keys = Object.keys(answers).filter((key) => fillValue(answers[key]).trim())
    if (!keys.length && !sessionRef.current) return sessionRef.current
    const payload = {
      matter_id: matterId.trim() || null,
      set_id: setId,
      title: set.title || '',
      versions: Object.fromEntries(availableMembers.map((member) => [member.template_id, member.resolved_version_no ?? null])),
      answers: Object.fromEntries(keys.map((key) => [key, fillValue(answers[key])])),
      verified: Object.keys(verifiedNames).filter((key) => verifiedNames[key]),
    }
    const snapshot = { epoch, revision: persistRevision.current, key: JSON.stringify(payload), payload }
    latestPersist.current = snapshot
    if (persistInFlight.current) return persistInFlight.current
    if (snapshot.key === lastPersistedKey.current) {
      persistDirty.current = false
      return sessionRef.current
    }
    const operation = (async () => {
      while (latestPersist.current && latestPersist.current.key !== lastPersistedKey.current) {
        const currentSnapshot = latestPersist.current
        if (currentSnapshot.epoch !== persistEpoch.current) break
        const current = sessionRef.current
        let saved
        try {
          saved = await writeFillSession({ ...(current?.id ? { id: current.id } : {}), ...currentSnapshot.payload })
        } catch (err) {
          if (currentSnapshot.epoch !== persistEpoch.current) continue
          throw err
        }
        // A matter switch invalidates the response from the old session. The
        // request may finish, but it must not resurrect that session in state.
        if (persistEpoch.current !== currentSnapshot.epoch) continue
        const wasNew = !sessionRef.current?.id
        sessionRef.current = saved
        lastPersistedKey.current = currentSnapshot.key
        if (persistRevision.current === currentSnapshot.revision) persistDirty.current = false
        setPersistError('')
        if (mountedRef.current) setSession(saved)
        if (wasNew && saved?.id) onSessionCreatedRef.current?.(saved.id)
      }
      return sessionRef.current
    })()
    persistInFlight.current = operation
    try { return await operation } finally {
      if (persistInFlight.current === operation) persistInFlight.current = null
    }
  }, [set, sessionRestored, background, answers, matterId, setId, verifiedNames, availableMembersKey])
  const persistSession = useCallback(async () => {
    if (mountedRef.current) setPersistStatus('saving')
    try {
      const saved = await flushLatest()
      if (mountedRef.current) setPersistStatus(persistDirty.current ? 'pending' : saved ? 'saved' : 'idle')
      return saved
    } catch {
      if (mountedRef.current) {
        setPersistStatus('error')
        setPersistError('Your packet answers could not be saved. Retry to keep the latest changes.')
      }
      return null
    }
  }, [flushLatest])
  useEffect(() => { flushRef.current = flushLatest }, [flushLatest])
  useEffect(() => {
    if (!set || !sessionRestored) return undefined
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(persistSession, 800)
    return () => clearTimeout(saveTimer.current)
  }, [persistSession, set, sessionRestored])
  useEffect(() => {
    const beforeUnload = (event) => {
      if (!persistDirty.current && !persistInFlight.current && !(latestPersist.current && latestPersist.current.key !== lastPersistedKey.current)) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      window.removeEventListener('beforeunload', beforeUnload)
      void flushRef.current?.().catch(() => {})
    }
  }, [])

  // While a background save runs, follow the session until it settles.
  useEffect(() => {
    if (background !== 'saving' || !sessionRef.current?.id) return undefined
    let active = true
    const tick = async () => {
      try {
        const value = await getFillSession(sessionRef.current.id)
        if (!active) return
        sessionRef.current = value
        setSession(value)
        if (value.status !== 'saving') {
          setBackground(value.status === 'saved' ? 'saved' : 'failed')
          setSaves(savesFromMembers(value.members))
          if ((value.members || []).some((member) => member.status === 'preview_expired')) {
            setPreviews((prev) => Object.fromEntries(Object.entries(prev).map(([id, entry]) => [id, (value.members || []).find((member) => member.template_id === id && member.status === 'preview_expired') ? memberState('idle') : entry])))
          }
        }
      } catch { /* keep polling */ }
    }
    tick()
    const timer = setInterval(tick, 3000)
    return () => { active = false; clearInterval(timer) }
  }, [background])

  // The interview verifies a shared question once, but each document spells the
  // value under its own field name. Map the verified interview keys to one
  // member's field names so the background save records the same verified
  // fields the browser save does.
  const verifiedFieldNames = (member, variables) => questions
    .filter((question) => verifiedNames[question.key] && fillValue(answers[question.key]).trim())
    .flatMap((question) => (question.appears_in || [])
      .filter((ref) => String(ref.template_id) === String(member.template_id))
      .map((ref) => ref.field_name))
    .filter((name) => name in (variables || {}))

  // Save the packet in the background from the previews reviewed here. The
  // server saves each member as this user with that user's own evidence;
  // only then does the copy say "Saving in the background".
  const saveAllInBackground = async () => {
    if (!matterId.trim()) return
    const ready = availableMembers.filter((member) => previewOf(member).status === 'ready' && saveOf(member)?.status !== 'saved')
    if (ready.length !== availableMembers.filter((member) => saveOf(member)?.status !== 'saved').length) { setError('Preview every document before saving the packet.'); return }
    setError('')
    // Hold the button through the two round trips below so a second click
    // cannot queue the packet twice.
    setSaving(true)
    try {
      await flushLatest()
      const current = sessionRef.current
      if (!current?.id) { setError('The session could not be saved; try again.'); return }
      const queued = await renderFillSession(current.id, {
        ...(folderId ? { folder_id: folderId } : {}),
        members: ready.map((member) => {
          const preview = previewOf(member)
          const verifiedFields = verifiedFieldNames(member, preview.variables)
          return { template_id: member.template_id, variables: preview.variables || {}, preview_id: member.output.format === 'pdf' ? (preview.previewId || null) : null, convert_to_pdf: Boolean(member.output.convertToPdf), output_format: member.output.format, ...(verifiedFields.length ? { verified_fields: verifiedFields } : {}) }
        }),
      })
      sessionRef.current = queued
      setSession(queued)
      setBackground('saving')
    } catch (err) {
      setError(getErrorMessage(err, 'The packet could not be queued.'))
    } finally {
      if (mountedRef.current) setSaving(false)
    }
  }

  const invalidatePreviews = useCallback(() => {
    setPreviews((prev) => Object.fromEntries(Object.entries(prev).map(([id, entry]) => [id, entry.status === 'saved' ? entry : memberState('idle')])))
  }, [])

  const setAnswer = (key, value) => {
    persistRevision.current += 1
    persistDirty.current = true
    setPersistStatus('pending')
    revisionRef.current += 1
    setGenerating(false)
    setAnswers((prev) => {
      const next = { ...prev, [key]: value }
      answersRef.current = next
      return next
    })
    setVerifiedNames((prev) => { const next = { ...prev }; if (String(value ?? '').trim()) next[key] = true; else delete next[key]; return next })
    invalidatePreviews()
  }
  const toggleVerified = (key) => {
    persistRevision.current += 1
    persistDirty.current = true
    setPersistStatus('pending')
    setVerifiedNames((prev) => { const next = { ...prev }; if (next[key]) delete next[key]; else next[key] = true; return next })
  }
  const selectMatter = (id) => {
    if (id === matterId) return
    revisionRef.current += 1
    generationRef.current += 1
    persistEpoch.current += 1
    persistRevision.current += 1
    restoreEpoch.current += 1
    persistDirty.current = false
    setPersistStatus('idle')
    latestPersist.current = null
    lastPersistedKey.current = ''
    setGenerating(false)
    setMatterId(id)
    answersRef.current = {}
    sessionRef.current = null
    setSession(null); setBackground(null); setPersistError('')
    setAnswers({}); setVerifiedNames({}); setReviewedValues({})
    setPreviews({}); setSaves({}); setError('')
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
    const revision = revisionRef.current
    const targetMatterId = matterId.trim()
    setError(''); setGenerating(true)
    setPreviews((prev) => ({ ...prev, ...Object.fromEntries(targets.map((member) => [member.template_id, memberState('loading')])) }))
    try {
      const fan = await getTemplateSetDocumentsVariables(setId, { matter_id: targetMatterId, answers })
      if (revisionRef.current !== revision) return
      await pooled(targets, PREVIEW_CONCURRENCY, async (member) => {
        const variables = fan.documents?.[member.template_id] || {}
        try {
          let entry
          if (member.output.file) {
            const result = await renderTemplateFile(member.template_id, {
              variables, matter_id: targetMatterId, preview_purpose: 'generation',
              ...(member.output.convertToPdf ? { convert_to_pdf: true } : {}),
            })
            entry = memberState('ready', { previewId: result.previewId || '', filename: result.filename, blob: result.blob, variables })
          } else {
            const result = await renderTemplate(member.template_id, { variables })
            entry = memberState('ready', { rendered: result.rendered || '', filename: result.output_filename || `${member.title}.md`, variables })
          }
          if (mountedRef.current && revisionRef.current === revision) setPreviews((prev) => ({ ...prev, [member.template_id]: entry }))
        } catch (err) {
          if (mountedRef.current && revisionRef.current === revision) setPreviews((prev) => ({ ...prev, [member.template_id]: memberState('failed', { error: getErrorMessage(err, 'The preview failed.'), variables }) }))
        }
      })
    } catch (err) {
      if (mountedRef.current && revisionRef.current === revision) {
        setError(getErrorMessage(err, 'The packet could not be prepared.'))
        setPreviews((prev) => ({ ...prev, ...Object.fromEntries(targets.map((member) => [member.template_id, memberState('idle')])) }))
      }
    } finally {
      if (mountedRef.current && revisionRef.current === revision) setGenerating(false)
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

  const retrySessionRestore = () => {
    setSessionRestoreError('')
    setSessionRestored(false)
    setRestoreAttempt((value) => value + 1)
  }

  return {
    set, members, availableMembers, unavailable, interview, questions, loading, error, setError,
    matterId, selectMatter, answers, setAnswer, reviewedValues, setReviewedValues, verifiedNames, toggleVerified,
    fieldFilter, setFieldFilter, filteredKeys, nextField, progress, requiredUnresolvedNames,
    smartFillState, smartFillMessage, refresh: () => loadInterview(matterId.trim()),
    previews, previewOf, saves, saveOf, generating, saving, generateAll, saveAll, allPreviewed, allSaved,
    savedDocuments, sendable: savedDocuments.filter(renderIsSendable).map(savedDocumentFromRender),
    session, background, sessionRestored, saveAllInBackground,
    sessionRestoreError, retrySessionRestore, persistError, persistStatus, retrySave: persistSession,
    flushLatest,
  }
}
