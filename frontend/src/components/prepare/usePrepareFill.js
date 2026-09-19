import { useState, useEffect, useMemo, useRef } from 'react'
import { applyFillSuggestions, discoverySuggestions, fillReview, initialFillValues, isSigningField } from '../templates/templateFillReview'
import { discoverTemplateVariables, renderTemplate, renderTemplateFile } from '../../api'
import { getErrorMessage, getTemplateVariables } from './prepareHelpers'

// The fill state machine behind both the Generate dialog and the Prepare
// route: values, their sources and review state, the once-per-matter Smart
// Fill, the preview and its evidence, and the save. Moved verbatim from the
// dialog so a route and a dialog cannot drift apart on what "reviewed" means.
const templateIsDocx = (template) => String(template?.format || '').toLowerCase() === 'docx' && Boolean(template?.source_sha256)
export const templateHasSigningFields = (template) => (template?.variable_schema?.fields || [])
  .some((field) => field?.included !== false && isSigningField(field))

export default function usePrepareFill({ template, initialMatterId, folderId, onSaved }) {
  const [variables, setVariables] = useState({})
  const [matterId, setMatterId] = useState(initialMatterId || '')
  const [rendered, setRendered] = useState(null)
  const [matterDocId, setMatterDocId] = useState(null)
  const [savedDownloadUrl, setSavedDownloadUrl] = useState('')
  const [outputFilename, setOutputFilename] = useState('')
  const [outputFormat, setOutputFormat] = useState('')
  const [storageBackend, setStorageBackend] = useState('')
  const [storageWarning, setStorageWarning] = useState('')
  const [filePreview, setFilePreview] = useState(null)
  const [filePreviewUrl, setFilePreviewUrl] = useState('')
  const [previewId, setPreviewId] = useState('')
  const [previewPurpose, setPreviewPurpose] = useState('')
  // A Word template that carries signature fields is generated as PDF unless
  // the user says otherwise: only a PDF can be sent for signature, and the
  // Send step that follows the save would otherwise be a dead end.
  const [convertDocxToPdf, setConvertDocxToPdf] = useState(() => templateHasSigningFields(template) && templateIsDocx(template))
  const [rendering, setRendering] = useState(false)
  const [renderPurpose, setRenderPurpose] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)
  const [smartFillState, setSmartFillState] = useState('idle')
  const [smartFillMessage, setSmartFillMessage] = useState('')
  const [fieldSources, setFieldSources] = useState({})
  const [latestSuggestions, setLatestSuggestions] = useState({})
  const [reviewedValues, setReviewedValues] = useState({})
  const [fieldFilter, setFieldFilter] = useState('all')
  const [focusedFillName, setFocusedFillName] = useState(null)
  const pendingFocus = useRef(null)
  const previewRequestGenerationRef = useRef(0)
  const smartFillRequestGenerationRef = useRef(0)
  const formRevisionRef = useRef(0)
  const smartFillRef = useRef(null)
  const smartFillAutoKeyRef = useRef('')

  const names = useMemo(() => getTemplateVariables(template), [template])
  const fieldDefinitions = useMemo(() => Object.fromEntries(
    (template?.variable_schema?.fields || [])
      .filter((field) => field?.name && field?.included !== false)
      .map((field) => [field.name, field]),
  ), [template])
  const isPdfTemplate = String(template?.format || '').toLowerCase() === 'pdf'
  const isDocxTemplate = templateIsDocx(template)
  const hasSigningFields = useMemo(() => templateHasSigningFields(template), [template])
  const isFileTemplate = isPdfTemplate || isDocxTemplate
  const isPdfOutput = isPdfTemplate || (isDocxTemplate && convertDocxToPdf)
  const canSaveToMatter = Boolean(template?.is_active)
  const fillableNames = useMemo(
    () => names.filter((name) => !isSigningField(fieldDefinitions[name]) && !fieldDefinitions[name]?.value_from),
    [names, fieldDefinitions],
  )
  const progress = fillReview(names, fieldDefinitions, variables, fieldSources, reviewedValues)
  const hasFirmFields = fillableNames.some(name => fieldDefinitions[name]?.binding?.startsWith('firm.'))
  const filteredNames = fieldFilter === 'all' ? names : (fieldFilter === 'remaining' ? progress.remaining : progress.review).map(row => row.name)
  // Keep the current input mounted until the reviewer moves on; typing the
  // first character must not remove it from a missing-only queue.
  const visibleNames = focusedFillName && !filteredNames.includes(focusedFillName) ? [...filteredNames, focusedFillName] : filteredNames
  const lastAttentionField = useRef(null)
  const nextField = () => {
    const missing = [...progress.remaining].sort((a, b) => Number(Boolean(fieldDefinitions[b.name]?.required)) - Number(Boolean(fieldDefinitions[a.name]?.required)))
    const queue = fieldFilter === 'review' ? progress.review : fieldFilter === 'remaining' ? missing : [...missing, ...progress.review]
    const index = queue.findIndex(row => row.name === lastAttentionField.current)
    const name = queue[(index + 1) % queue.length]?.name
    if (!name) return
    lastAttentionField.current = name
    const input = document.getElementById(`template-variable-${name}`)
    input?.scrollIntoView?.({ block: 'center' })
    input?.focus({ preventScroll: true })
  }
  useEffect(() => {
    if (pendingFocus.current) {
      document.getElementById(`template-variable-${pendingFocus.current}`)?.focus()
      pendingFocus.current = null
    }
  }, [fieldFilter])
  const requiredUnresolvedNames = fillableNames.filter((name) => {
    const field = fieldDefinitions[name]
    if (!field?.required) return false
    if (field.field_type === 'checkbox') return variables[name] !== 'true'
    return !String(variables[name] || '').trim()
  })
  const optionalUnfilledNames = fillableNames.filter((name) => {
    const field = fieldDefinitions[name]
    if (field?.required) return false
    if (field?.field_type === 'checkbox') return variables[name] === ''
    return !String(variables[name] || '').trim()
  })
  const activationUnresolvedNames = fillableNames.filter((name) => (
    fieldDefinitions[name]?.field_type !== 'checkbox'
    && !String(variables[name] || '').trim()
  ))

  useEffect(() => {
    setVariables(initialFillValues(fillableNames, fieldDefinitions))
    setFieldSources({})
    setLatestSuggestions({})
    setReviewedValues({})
    setFieldFilter('all')
    setFocusedFillName(null)
    lastAttentionField.current = null
    setSaved(false)
    setRendered(null)
    setMatterDocId(null)
    setSavedDownloadUrl('')
    setOutputFilename('')
    setOutputFormat('')
    setStorageBackend('')
    setStorageWarning('')
    setFilePreview(null)
    setFilePreviewUrl('')
    setPreviewId('')
    setPreviewPurpose('')
    previewRequestGenerationRef.current += 1
    smartFillRequestGenerationRef.current += 1
    formRevisionRef.current += 1
  }, [fillableNames, fieldDefinitions])

  useEffect(() => () => {
    if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl)
  }, [filePreviewUrl])

  useEffect(() => () => {
    previewRequestGenerationRef.current += 1
    smartFillRequestGenerationRef.current += 1
  }, [])

  const invalidatePreview = () => {
    previewRequestGenerationRef.current += 1
    smartFillRequestGenerationRef.current += 1
    formRevisionRef.current += 1
    setRendered(null)
    setFilePreview(null)
    setFilePreviewUrl('')
    setPreviewId('')
    setPreviewPurpose('')
    setRendering(false)
    setOutputFilename('')
    setOutputFormat('')
  }

  const setVariable = (name, value) => {
    setSaved(false)
    invalidatePreview()
    setFieldSources(prev => { const next = { ...prev }; delete next[name]; return next })
    setVariables((prev) => {
      const next = { ...prev, [name]: value }
      const choice = fieldDefinitions[name]?.docx_choice
      if (choice?.exclusive && value === 'true') {
        for (const [other, field] of Object.entries(fieldDefinitions)) {
          if (other !== name && field.docx_choice?.group === choice.group) next[other] = 'false'
        }
      }
      for (const [other, field] of Object.entries(fieldDefinitions)) {
        if (field.value_from) next[other] = next[field.value_from] || ''
      }
      return next
    })
  }

  const selectMatter = (id) => {
    setFocusedFillName(null)
    lastAttentionField.current = null
    if (id === matterId) return
    setMatterId(id)
    setVariables(initialFillValues(fillableNames, fieldDefinitions))
    setFieldSources({})
    setLatestSuggestions({})
    setReviewedValues({})
    setSmartFillState('idle')
    setSmartFillMessage('')
    setSaved(false)
    setMatterDocId(null)
    setSavedDownloadUrl('')
    invalidatePreview()
  }

  const handleSmartFill = async () => {
    if (!matterId.trim() && !hasFirmFields) {
      setSmartFillState('error')
      setSmartFillMessage('Choose a matter before smart fill.')
      return
    }
    const requestGeneration = smartFillRequestGenerationRef.current + 1
    smartFillRequestGenerationRef.current = requestGeneration
    const requestRevision = formRevisionRef.current
    const requestMatterId = matterId.trim() || null
    setSmartFillState('loading')
    setSmartFillMessage('')
    try {
      const res = await discoverTemplateVariables(template.id, {
        matter_id: requestMatterId,
        published: Boolean(template.is_active),
        variables: fillableNames,
      })
      if (
        smartFillRequestGenerationRef.current !== requestGeneration
        || formRevisionRef.current !== requestRevision
      ) {
        setSmartFillState('idle')
        setSmartFillMessage('Smart-fill results were not applied because the matter or fields changed. Run Smart Fill again if needed.')
        return
      }
      const discovered = discoverySuggestions(res)
      if (Object.keys(discovered).length === 0) {
        setSmartFillState('empty')
        setSmartFillMessage('No smart-fill values were returned for this template yet.')
        return
      }
      const applied = applyFillSuggestions(fillableNames, fieldDefinitions, variables, fieldSources, discovered)
      setLatestSuggestions(discovered)
      setFieldSources(applied.sources)
      setVariables(applied.values)
      invalidatePreview()
      setSaved(false)
      setSmartFillState('ready')
      setSmartFillMessage('Available values refreshed. Your entries were kept.')
    } catch (err) {
      if (smartFillRequestGenerationRef.current !== requestGeneration) return
      if ([404, 405, 501].includes(err?.response?.status)) {
        setSmartFillState('unavailable')
        setSmartFillMessage('Smart fill is not enabled on this server yet. Manual fields are ready for review.')
      } else {
        setSmartFillState('error')
        setSmartFillMessage(getErrorMessage(err, 'Smart fill failed.'))
      }
    }
  }

  // Keep the latest closure for the auto-fill effect without making it a
  // dependency that would re-run it on every keystroke.
  useEffect(() => { smartFillRef.current = handleSmartFill })

  // Auto-fill the moment there is a record to fill from: a template opened
  // from inside a matter (initialMatterId) arrives already populated, and
  // choosing a matter in this dialog fills it without a second click. The
  // manual button stays as the explicit refresh. One pass per matter keeps a
  // late response from clobbering edits the reviewer has since typed.
  useEffect(() => {
    if (saving || !fillableNames.length) return
    const hasMatter = Boolean(matterId.trim())
    if (!hasMatter && !hasFirmFields) {
      smartFillAutoKeyRef.current = ''
      return
    }
    const key = `${template?.id || ''}:${matterId.trim()}`
    if (smartFillAutoKeyRef.current === key) return
    smartFillAutoKeyRef.current = key
    smartFillRef.current?.()
  }, [matterId, template?.id, fillableNames.length, hasFirmFields, saving])

  const handleRender = async (requestedPdfPurpose = null) => {
    const previewPurpose = requestedPdfPurpose || (canSaveToMatter ? 'generation' : 'draft')
    if (isPdfOutput && canSaveToMatter && !matterId.trim()) {
      setError('Choose the destination matter before previewing the exact PDF values for save.')
      return
    }
    if (isPdfTemplate && previewPurpose === 'activation' && activationUnresolvedNames.length > 0) {
      setError(`Enter representative values for every non-signature PDF field before the activation preview. Missing: ${activationUnresolvedNames.join(', ')}.`)
      return
    }
    const requestGeneration = previewRequestGenerationRef.current + 1
    previewRequestGenerationRef.current = requestGeneration
    const requestVariables = { ...variables }
    const requestMatterId = isPdfOutput && canSaveToMatter ? matterId.trim() : null
    setRendering(true)
    setRenderPurpose(previewPurpose)
    setError(null)
    try {
      const payload = {
        variables: requestVariables,
        matter_id: requestMatterId,
        preview_purpose: previewPurpose,
        ...(isDocxTemplate ? { convert_to_pdf: convertDocxToPdf } : {}),
      }
      if (isFileTemplate) {
        const result = await renderTemplateFile(template.id, payload)
        const nextUrl = URL.createObjectURL(result.blob)
        if (previewRequestGenerationRef.current !== requestGeneration) {
          URL.revokeObjectURL(nextUrl)
          return
        }
        if (isPdfOutput && !result.previewId) {
          URL.revokeObjectURL(nextUrl)
          throw new Error('The server did not return PDF preview evidence. Preview again before saving or activating.')
        }
        if (isPdfOutput && result.previewPurpose !== previewPurpose) {
          URL.revokeObjectURL(nextUrl)
          throw new Error('The server returned preview evidence for a different review purpose. Preview again.')
        }
        setFilePreview({ blob: result.blob, filename: result.filename, contentType: result.contentType })
        setFilePreviewUrl(nextUrl)
        setPreviewId(result.previewId)
        setPreviewPurpose(result.previewPurpose)
        setOutputFilename(result.filename)
        setOutputFormat(isPdfOutput ? 'pdf' : 'docx')
        setRendered(null)
      } else {
        const res = await renderTemplate(template.id, payload)
        if (previewRequestGenerationRef.current !== requestGeneration) return
        setRendered(res.rendered)
        setFilePreview(null)
        setFilePreviewUrl('')
      }
      setMatterDocId(null)
      setSaved(false)
    } catch (err) {
      if (previewRequestGenerationRef.current === requestGeneration) {
        setError(getErrorMessage(err, 'Render failed.'))
      }
    } finally {
      if (previewRequestGenerationRef.current === requestGeneration) {
        setRendering(false)
      }
    }
  }

  const handleSave = async () => {
    if (!matterId.trim()) return
    if (!canSaveToMatter) {
      setError('Activate this template after verifying its preview before saving a generated document to a matter.')
      return
    }
    if (requiredUnresolvedNames.length > 0) {
      setError(`Complete ${requiredUnresolvedNames.length} required field${requiredUnresolvedNames.length === 1 ? '' : 's'} before saving.`)
      return
    }
    if (isPdfOutput && !previewId) {
      setError('Preview the exact current PDF values for this matter before saving.')
      return
    }
    if (isDocxTemplate && !filePreview) {
      setError('Download and review the current Word preview before saving it to the matter.')
      return
    }
    if (smartFillState === 'loading') {
      setError('Wait for Smart Fill to finish, or change a field to discard it, before saving.')
      return
    }
    const saveRevision = formRevisionRef.current
    const saveVariables = { ...variables }
    const saveMatterId = matterId.trim()
    const savePreviewId = previewId
    smartFillRequestGenerationRef.current += 1
    setSaving(true)
    setError(null)
    setStorageWarning('')
    try {
      const res = await renderTemplate(template.id, {
        variables: saveVariables,
        matter_id: saveMatterId,
        ...(folderId ? { folder_id: folderId } : {}),
        ...(isDocxTemplate ? { convert_to_pdf: convertDocxToPdf } : {}),
        ...(isPdfOutput ? { preview_id: savePreviewId } : {}),
      })
      if (formRevisionRef.current !== saveRevision) {
        setError('The form changed while the save was in flight, so this response was not marked Saved. Review the matter document before continuing.')
        return
      }
      setError(null)
      if (!isPdfOutput) setRendered(res.rendered || rendered)
      setSavedDownloadUrl(res.download_url || '')
      setOutputFilename(res.output_filename || res.filename || outputFilename || '')
      setOutputFormat(res.output_format || res.format || (isPdfOutput ? 'pdf' : 'markdown'))
      setStorageBackend(res.storage_backend || '')
      setStorageWarning(res.storage_warning || '')
      if (res.matter_document_id) {
        setMatterDocId(res.matter_document_id)
        setSaved(true)
        onSaved?.(res)
      } else {
        setError('The server rendered the text but did not return a saved matter document.')
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Save failed.'))
    } finally {
      setSaving(false)
    }
  }


  return {
    variables, setVariables, matterId, setMatterId, rendered, setRendered, matterDocId, setMatterDocId, savedDownloadUrl, setSavedDownloadUrl, outputFilename, setOutputFilename, outputFormat, setOutputFormat, storageBackend, setStorageBackend, storageWarning, setStorageWarning, filePreview, setFilePreview, filePreviewUrl, setFilePreviewUrl, previewId, setPreviewId, previewPurpose, setPreviewPurpose, convertDocxToPdf, setConvertDocxToPdf, rendering, setRendering, renderPurpose, setRenderPurpose, saving, setSaving, saved, setSaved, error, setError, smartFillState, setSmartFillState, smartFillMessage, setSmartFillMessage, fieldSources, setFieldSources, latestSuggestions, setLatestSuggestions, reviewedValues, setReviewedValues, fieldFilter, setFieldFilter, focusedFillName, setFocusedFillName, pendingFocus, previewRequestGenerationRef, smartFillRequestGenerationRef, formRevisionRef, smartFillRef, smartFillAutoKeyRef, names, fieldDefinitions, isPdfTemplate, isDocxTemplate, isFileTemplate, isPdfOutput, hasSigningFields, canSaveToMatter, fillableNames, progress, hasFirmFields, filteredNames, visibleNames, lastAttentionField, nextField, requiredUnresolvedNames, optionalUnfilledNames, activationUnresolvedNames, invalidatePreview, setVariable, selectMatter, handleSmartFill, handleRender, handleSave,
  }
}
