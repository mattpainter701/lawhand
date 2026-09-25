import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Download, Eye, Save, Wand2 } from 'lucide-react'
import MatterPicker from './MatterPicker'
import StorageReadinessNotice from './StorageReadinessNotice'
import TemplateFactReview from '../templates/TemplateFactReview'
import TemplateFillProgress from '../templates/TemplateFillProgress'
import TemplateFillSource from '../templates/TemplateFillSource'
import TemplateTestSummary from '../templates/TemplateTestSummary'
import GeneratedPdfPreview from '../templates/GeneratedPdfPreview'
import FillOnDocument, { GuidedFieldBar, useGuidedFields } from '../templates/FillOnDocument'
import { placementsFor } from '../templates/pdfFieldGeometry'
import { readFillViewPreference, writeFillViewPreference } from '../templates/fillViewPreference'
import useTemplateSourceBlob from './useTemplateSourceBlob'
import { fillValue, isSigningField, suggestionConfidenceLabel, suggestionOriginLabel } from '../templates/templateFillReview'
import { getMatterDocumentDownloadUrl, triggerBlobDownload } from '../../api'
import { downloadRenderedText, friendlyVariableLabel } from './prepareHelpers'

// The fill surface for a template on a matter. Rendered inside the Generate
// dialog (`layout="modal"`) and as the body of the Prepare route
// (`layout="page"`). Every control keeps its accessible name in both.
//
// Three views share one set of answers:
// - Document (default): the original document at full width. PDF answers are
//   typed on the page; Word and text templates show the page reference. A
//   guided bar edits the active field with its review controls.
// - Questions: the field list beside the document reference or preview.
// - Preview: the generated document at full width.
// The Document/Questions choice is remembered per browser.
const VIEW_TABS = [['document', 'Document'], ['questions', 'Questions'], ['preview', 'Preview']]
const LEGEND = ['missing', 'review', 'verified', 'open']
const CHECKBOX_VALUES = { on: 'true', off: 'false' }

export default function PrepareDocumentBody({ fill, template, matters = [], matterLoading = false, fixedMatterId, layout = 'modal' }) {
  const {
    variables,
    matterId,
    rendered,
    matterDocId,
    savedDownloadUrl,
    outputFilename,
    outputFormat,
    storageBackend,
    storageWarning,
    filePreview,
    filePreviewUrl,
    previewId,
    previewPurpose,
    autoPreviewEnabled,
    previewError,
    convertDocxToPdf,
    hasSigningFields,
    setConvertDocxToPdf,
    rendering,
    renderPurpose,
    saving: savingState,
    completionPending,
    saved,
    setSaved,
    error,
    smartFillState,
    smartFillMessage,
    fieldSources,
    setFieldSources,
    latestSuggestions,
    setReviewedValues,
    toggleVerified,
    verifyAndAdvance,
    fieldFilter,
    setFieldFilter,
    setFocusedFillName,
    pendingFocus,
    names,
    fieldDefinitions,
    isDocxTemplate,
    isPdfOutput,
    canSaveToMatter,
    progress,
    hasFirmFields,
    visibleNames,
    lastAttentionField,
    nextField,
    requiredUnresolvedNames,
    optionalUnfilledNames,
    invalidatePreview,
    setVariable,
    selectMatter,
    handleSmartFill,
    handleRender,
    handleSave,
  } = fill
  const clearReviewedValue = (name) => setReviewedValues(prev => ({ ...prev, [name]: undefined }))
  const updateValue = (name, value) => {
    clearReviewedValue(name)
    setVariable(name, value)
  }
  const verifyCurrentValue = (name, value) => {
    setReviewedValues(prev => ({ ...prev, [name]: fillValue(value) }))
    toggleVerified(name)
  }
  const verifyAndAdvanceCurrentValue = (name) => {
    setReviewedValues(prev => ({ ...prev, [name]: fillValue(variables[name]) }))
    return verifyAndAdvance(name)
  }
  const toggleValueVerified = (name, value, currentlyVerified) => {
    if (currentlyVerified) clearReviewedValue(name)
    else verifyCurrentValue(name, value)
    if (currentlyVerified) toggleVerified(name)
  }
  const saving = savingState || completionPending
  const livePreviewPending = autoPreviewEnabled && Boolean(matterId.trim()) && !previewId
  // The UUID fallback is committed on blur or Enter, not on every keystroke:
  // each character would otherwise change the matter and reset the form (and
  // fire a Smart Fill request) mid-paste.
  const [matterIdDraft, setMatterIdDraft] = useState(matterId || '')
  useEffect(() => { setMatterIdDraft(matterId || '') }, [matterId])
  const commitMatterIdDraft = () => {
    const next = matterIdDraft.trim()
    if (next !== matterId) selectMatter(next)
  }
  const scrollClass = layout === 'modal' ? 'lg:max-h-[78vh] lg:overflow-y-auto' : ''

  // --- Document view -------------------------------------------------------
  const [view, setView] = useState(readFillViewPreference)
  const chooseView = (next) => {
    setView(next)
    writeFillViewPreference(next)
  }
  const [docActive, setDocActive] = useState('')
  const focusBarField = useRef('')
  const newerDraft = Boolean(template.is_active && template.published_version_no && template.published_version_no !== template.current_version_no)
  const documentFields = useMemo(() => names.map((name) => ({ name, label: friendlyVariableLabel(name), ...(fieldDefinitions[name] || {}) })), [names, fieldDefinitions])
  const hasPlacedFields = useMemo(() => documentFields.some((field) => placementsFor(field).length), [documentFields])
  const pdfOnPage = String(template.format || '').toLowerCase() === 'pdf' && !newerDraft && hasPlacedFields
  const pdfSource = useTemplateSourceBlob(template, pdfOnPage && view === 'document')
  const [pdfUnreadable, setPdfUnreadable] = useState(false)
  const onPdfUnavailable = useCallback(() => setPdfUnreadable(true), [])
  useEffect(() => { setPdfUnreadable(false) }, [template.id])
  const fillOnPage = pdfOnPage && !pdfSource.failed && !pdfUnreadable
  const rowByName = useMemo(() => Object.fromEntries(progress.rows.map((row) => [row.name, row])), [progress.rows])
  const statusFor = (field) => {
    const row = rowByName[field.name]
    if (!row) return 'open'
    if (!row.present) return field.required ? 'missing' : 'open'
    if (row.verified) return 'verified'
    if (row.needsReview) return 'review'
    if (row.source) return 'suggested'
    return 'filled'
  }
  const isMissing = (field) => requiredUnresolvedNames.includes(field.name)
  const markerFor = (field) => {
    if (field.value_from) return `Uses ${fieldDefinitions[field.value_from]?.label || field.value_from}`
    if (isSigningField(field)) return field.field_type === 'date' ? 'Dated at signing' : 'Signed later'
    return null
  }
  // The active field on the page follows the host's own navigation (Enter to
  // verify and advance, "Next field needing attention"), and the bar's input
  // takes focus so keyboard review keeps flowing.
  const followField = (name) => {
    if (!name || view !== 'document') return
    focusBarField.current = name
    setDocActive(name)
    setFocusedFillName(name)
  }
  useEffect(() => {
    const name = focusBarField.current
    if (!name || name !== docActive) return
    focusBarField.current = ''
    document.getElementById(`template-variable-${name}`)?.focus({ preventScroll: true })
  }, [docActive])
  const activateDocField = (name) => { setDocActive(name); setFocusedFillName(name) }
  const referenceGuide = useGuidedFields(documentFields, { values: variables, activeName: docActive, onActiveChange: activateDocField, isMissing })
  const showPreview = () => { if (view === 'document') setView('preview') }
  const renderAndShow = (purpose) => { showPreview(); handleRender(purpose) }

  const renderFieldEditor = (name) => {
    const field = fieldDefinitions[name] || {}
    const review = progress.rows.find(row => row.name === name)
    const changedSuggestion = latestSuggestions[name]?.suggested_value != null && fillValue(latestSuggestions[name].suggested_value) !== fillValue(variables[name]) ? latestSuggestions[name] : null
    const fieldType = field.field_type || 'text'
    const signingField = isSigningField(field)
    const label = field.label || friendlyVariableLabel(name)
    const inputId = `template-variable-${name}`
    const options = (field.options || []).map((option) => (
      typeof option === 'object'
        ? { value: option.value ?? option.name ?? option.label ?? '', label: option.label ?? option.name ?? option.value ?? '' }
        : { value: option, label: option }
    ))
    return (
    <div key={name} onFocus={() => setFocusedFillName(name)} className={signingField ? 'border border-brand-line rounded bg-brand-bg px-3 py-2' : ''}>
      {signingField ? (
        <p className="block text-xs font-medium text-brand-muted mb-0.5">
          {label}
        </p>
      ) : (
        <label htmlFor={inputId} className="block text-xs font-medium text-brand-muted mb-0.5">
          {label}{field.required ? ' *' : ''}
        </label>
      )}
      {review && !review.present && <p className={`mb-1 text-xs font-semibold ${field.required ? 'text-brand-rose' : 'text-brand-amber'}`}>{field.required ? 'Required — missing' : 'Optional — not filled'}</p>}
      {fieldSources[name] && <p className="mb-1 text-xs text-brand-muted">{suggestionOriginLabel(fieldSources[name])}{fieldSources[name].provenance?.updated_at ? ` · Updated ${new Date(fieldSources[name].provenance.updated_at).toLocaleDateString()}` : ''}</p>}
      {field.binding?.startsWith('firm.') && <p className="mb-1 text-xs text-brand-muted">Shared firm profile. Missing or outdated details can be updated once by a firm administrator in Firm settings, then refreshed here with Smart Fill.</p>}
      {fieldSources[name]?.provenance?.source_document_id && <a className="block mb-1 text-xs underline" href={getMatterDocumentDownloadUrl(matterId, fieldSources[name].provenance.source_document_id)} target="_blank" rel="noreferrer">Open reviewed source document</a>}
      {review?.source && <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <span>{suggestionConfidenceLabel(review)}</span>
        {review.needsReview ? <button type="button" disabled={saving} className="rounded border border-brand-line px-2 py-1" onClick={() => setReviewedValues(prev => ({ ...prev, [name]: fillValue(variables[name]) }))}>Confirm {label}</button> : <span className="text-brand-green">Reviewed</span>}
      </div>}
      {changedSuggestion && <div className="mb-2 rounded border border-brand-amber/40 bg-brand-amber/10 p-2 text-xs">
        <p>{changedSuggestion.source_type === 'firm_profile' ? 'Firm profile now suggests' : 'Matter now suggests'}: {fillValue(changedSuggestion.suggested_value)}</p>
        <button type="button" disabled={saving} className="mt-1 rounded border border-brand-line px-2 py-1" onClick={() => { setVariable(name, fillValue(changedSuggestion.suggested_value)); setFieldSources(prev => ({ ...prev, [name]: changedSuggestion })); setReviewedValues(prev => ({ ...prev, [name]: undefined })) }}>Use updated {label}</button>
      </div>}
      {field.value_from ? <p id={inputId} className="text-sm text-brand-muted">Uses {fieldDefinitions[field.value_from]?.label || field.value_from}</p> : signingField ? (
        <p className="text-sm text-brand-muted">
          {fieldType === 'date' ? `Signing date is completed by ${field.signer_role} during e-signing.` : 'Signature area is left blank for signing; it is not populated during document generation.'}
          {field.pdf_field_name ? ` PDF field: ${field.pdf_field_name}.` : ''}
        </p>
      ) : fieldType === 'checkbox' ? (
        <label className="inline-flex items-center gap-2 text-sm text-brand-ink py-1">
          <input
            id={inputId}
            type="checkbox"
            checked={variables[name] === 'true'}
            onChange={(e) => updateValue(name, e.target.checked ? 'true' : 'false')}
            disabled={saving}
            className="h-4 w-4 rounded border-brand-line text-brand-accent focus:ring-brand-accent"
          />
          Checked
        </label>
      ) : (fieldType === 'choice' || fieldType === 'radio') && options.length > 0 ? (
        <select
          id={inputId}
          value={variables[name] || ''}
          onChange={(e) => updateValue(name, e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && String(variables[name] || '').trim()) { e.preventDefault(); followField(verifyAndAdvanceCurrentValue(name)) } }}
          disabled={saving}
          className="w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent"
        >
          <option value="">Select {label}</option>
          {options.map((option) => <option key={String(option.value)} value={option.value}>{option.label}</option>)}
        </select>
      ) : fieldType === 'multiline' || field.multiline ? (
        <textarea
          id={inputId}
          rows={3}
          value={variables[name] || ''}
          onChange={(e) => updateValue(name, e.target.value)}
          disabled={saving}
          className="w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent"
          placeholder={`Enter ${label}`}
        />
      ) : (
        <input
          id={inputId}
          type="text"
          value={variables[name] || ''}
          onChange={(e) => updateValue(name, e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && String(variables[name] || '').trim()) { e.preventDefault(); followField(verifyAndAdvanceCurrentValue(name)) } }}
          disabled={saving}
          className="w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent"
          placeholder={`Enter ${label}`}
        />
      )}
      {review?.present && !signingField && !field.value_from && (
        <label className={`mt-1 inline-flex items-center gap-2 text-xs ${review.verified ? 'text-brand-green' : 'text-brand-muted'}`}>
          <input
            id={`template-verified-${name}`}
            type="checkbox"
            aria-label={`Verified: ${label}`}
            checked={Boolean(review.verified)}
            onChange={() => toggleValueVerified(name, variables[name], review.verified)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); followField(verifyAndAdvanceCurrentValue(name)) } }}
            disabled={saving}
            className="h-3.5 w-3.5 rounded border-brand-line text-brand-green focus:ring-brand-green"
          />
          {review.verified ? 'Verified' : 'Verify'}
        </label>
      )}
      {field.pdf_field_name && !signingField && (
        <p className="mt-1 text-[11px] text-brand-muted">PDF field: {field.pdf_field_name}{field.page ? ` · Page ${field.page}` : ''}</p>
      )}
    </div>
    )
  }

  const noticeSection = <>
        <StorageReadinessNotice enabled={canSaveToMatter && Boolean(matterId.trim())} />
        {error && (
          <div className="text-sm text-brand-rose bg-brand-rose/10 border border-brand-rose/30 px-3 py-2">
            {canSaveToMatter ? error : 'The test needs attention. See the results below for the exact issue.'}
          </div>
        )}

        {!canSaveToMatter && (
          <div role="status" className="text-sm text-brand-amber bg-brand-amber/10 border border-brand-amber/30 px-3 py-2">
            Draft preview. Test and publish before saving to a matter.
          </div>
        )}
  </>
  const matterSection = <>
        {fixedMatterId ? <p className="text-sm font-semibold">Saving to this matter</p> : <><MatterPicker
          matters={matters}
          selectedMatterId={matterId}
          onSelect={selectMatter}
          loading={matterLoading}
          disabled={saving}
        />


        <details>
          <summary className="cursor-pointer text-xs text-brand-muted">Find a matter by ID</summary>
          <label htmlFor="templatespage-matter-uuid-fallback" className="block text-xs font-medium text-brand-muted mb-0.5">
            Matter UUID fallback
          </label>
          <input id="templatespage-matter-uuid-fallback"
            type="text"
            value={matterIdDraft}
            onChange={(e) => setMatterIdDraft(e.target.value)}
            onBlur={commitMatterIdDraft}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commitMatterIdDraft() } }}
            disabled={saving}
            className="w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent font-mono"
            placeholder="Paste matter UUID if the matter is not listed"
          />
        </details>

        </>}
  </>
  const smartFillSection = <>
        {names.length > 0 && (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border border-brand-line rounded bg-brand-bg px-3 py-2">
            <div>
              <p className="text-sm font-medium text-brand-ink">Smart fill</p>
              <p className="text-xs text-brand-muted">
                {hasFirmFields ? 'Uses shared firm details and the selected matter.' : 'Uses the selected matter.'} Your entries are kept on refresh.
              </p>
            </div>
            <button
              onClick={handleSmartFill}
              disabled={saving || smartFillState === 'loading' || (!matterId.trim() && !hasFirmFields)}
              className="flex shrink-0 items-center justify-center gap-2 whitespace-nowrap px-3 py-2 text-sm text-brand-ink border border-brand-line rounded hover:bg-brand-surface-2 disabled:opacity-50"
            >
              <Wand2 size={15} />
              {smartFillState === 'loading' ? 'Filling...' : smartFillState === 'ready' ? (matterId.trim() ? 'Refresh matter values' : 'Refresh firm values') : 'Smart Fill'}
            </button>
          </div>
        )}
  </>
  const correctSourceSection = <>
        {(matterId.trim() || hasFirmFields) && <details className="rounded border border-brand-line bg-brand-bg p-3 text-xs">
          <summary className="cursor-pointer font-semibold">Correct the source once</summary>
          <div className="mt-2 flex flex-wrap gap-3">
            {matterId.trim() && <a href={`/matters/${encodeURIComponent(matterId.trim())}`} target="_blank" rel="noreferrer" className="underline">Open matter details (new tab)</a>}
            {hasFirmFields && <a href="/admin?tab=firm" target="_blank" rel="noreferrer" className="underline">Open firm settings (new tab)</a>}
          </div>
          <p className="mt-2 text-brand-muted">Keep this document open. After saving changes to the source, return and refresh values. Your entries stay intact; changed suggestions are yours to accept. Firm changes require an administrator.</p>
        </details>}
  </>
  const factSection = <>
        <TemplateFactReview matterId={matterId.trim()} fields={Object.values(fieldDefinitions)} onAccepted={() => { setFieldSources({}); invalidatePreview() }} />
        {smartFillMessage && (
          <div className={`text-sm border px-3 py-2 ${
            smartFillState === 'ready'
              ? 'text-brand-green bg-brand-green/10 border-brand-green/30'
              : smartFillState === 'error'
                ? 'text-brand-rose bg-brand-rose/10 border-brand-rose/30'
                : 'text-brand-muted bg-brand-bg border-brand-line'
          }`}>
            {smartFillMessage}
          </div>
        )}
  </>
  const fieldListSection = <>
        {names.length > 0 && (
          <div>
            <div className="sticky top-0 z-20 bg-brand-surface pb-2">
              <TemplateFillProgress progress={progress} requiredMissing={requiredUnresolvedNames.length} filter={fieldFilter} onFilter={value => { lastAttentionField.current = null; setFocusedFillName(null); setFieldFilter(value) }} onNext={() => followField(nextField())} />
            </div>
            <h3 className="text-sm font-medium text-brand-ink mb-2">
              Fields
            </h3>
            <div className="space-y-2">
              {visibleNames.map((name) => renderFieldEditor(name))}
            </div>
            {visibleNames.length === 0 && <p role="status" className="py-3 text-sm text-brand-muted">{fieldFilter === 'remaining' ? 'No missing fields.' : fieldFilter === 'unverified' ? 'Every filled field is verified.' : 'No suggestions waiting for review.'}</p>}
            <p className={`mt-2 text-xs ${requiredUnresolvedNames.length ? 'text-brand-amber' : 'text-brand-green'}`} role="status">
              {requiredUnresolvedNames.length
                ? `${requiredUnresolvedNames.length} required field${requiredUnresolvedNames.length === 1 ? '' : 's'} still need review before saving.`
                : 'All required fields are ready.'}
            </p>
            {optionalUnfilledNames.length > 0 && (
              <p className="mt-1 text-xs text-brand-muted">
                {optionalUnfilledNames.length} optional field{optionalUnfilledNames.length === 1 ? '' : 's'} left unfilled; saving is still allowed.
              </p>
            )}
          </div>
        )}
  </>
  const noVariablesSection = <>
        {names.length === 0 && (
          <p className="text-sm text-brand-muted italic">
            This template has no variables. Preview or save it directly.
          </p>
        )}
  </>
  const outputFormatSection = <>
        {isDocxTemplate && (
          <fieldset className="rounded border border-brand-line bg-brand-bg px-3 py-2">
            <legend className="px-1 text-sm font-medium text-brand-ink">Output format</legend>
            <div className="flex flex-wrap gap-2">
              <label className={`cursor-pointer rounded border px-3 py-2 ${convertDocxToPdf ? 'border-brand-accent bg-brand-accent/5' : 'border-brand-line bg-brand-surface'}`}>
                <span className="flex items-start gap-2">
                  <input type="radio" name="template-output-format" checked={convertDocxToPdf} onChange={() => { setConvertDocxToPdf(true); setSaved(false); invalidatePreview() }} disabled={saving} className="mt-1" />
                  <span><span className="block text-sm font-semibold text-brand-ink">PDF for signature</span><span className="sr-only">Preserves the Word layout in a review-bound PDF ready for the e-signing workflow.</span></span>
                </span>
              </label>
              <label className={`cursor-pointer rounded border px-3 py-2 ${!convertDocxToPdf ? 'border-brand-accent bg-brand-accent/5' : 'border-brand-line bg-brand-surface'}`}>
                <span className="flex items-start gap-2">
                  <input type="radio" name="template-output-format" checked={!convertDocxToPdf} onChange={() => { setConvertDocxToPdf(false); setSaved(false); invalidatePreview() }} disabled={saving} className="mt-1" />
                  <span><span className="block text-sm font-semibold text-brand-ink">Editable Word document</span><span className="sr-only">Keep DOCX output when another editing pass is still required.</span></span>
                </span>
              </label>
            </div>
            {hasSigningFields && (
              <p className="mt-2 text-xs text-brand-muted">
                {convertDocxToPdf
                  ? 'PDF is preselected because this template has signature fields. Only a PDF can be sent for signature after it is saved.'
                  : 'This template has signature fields. A Word document cannot be sent for signature; choose PDF to send it from the matter.'}
              </p>
            )}
          </fieldset>
        )}
  </>
  const actionsSection = <>
        <div className="flex flex-col sm:flex-row gap-3">
          {!canSaveToMatter ? (
            <>
              <button
                onClick={() => renderAndShow('draft')}
                disabled={rendering || saving}
                className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-brand-ink border border-brand-line bg-brand-surface hover:bg-brand-surface-2 rounded disabled:opacity-50"
              >
                <Eye size={16} />
                {rendering && renderPurpose === 'draft' ? 'Preparing preview…' : 'Preview draft'}
              </button>
              <button
                onClick={() => renderAndShow('activation')}
                disabled={rendering || saving}
                className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white bg-brand-ink hover:bg-brand-ink-2 rounded disabled:opacity-50"
              >
                <Check size={16} />
                {rendering && renderPurpose === 'activation' ? 'Testing this draft…' : 'Test this draft'}
              </button>
            </>
          ) : !autoPreviewEnabled ? (
            <button
              onClick={() => renderAndShow()}
              disabled={rendering || saving}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white bg-brand-ink hover:bg-brand-ink-2 rounded disabled:opacity-50"
            >
              <Eye size={16} />
              {rendering ? 'Rendering...' : 'Preview'}
            </button>
          ) : previewError ? (
            <button type="button" onClick={() => renderAndShow()} disabled={rendering || saving} className="rounded border border-brand-line px-4 py-2 text-sm disabled:opacity-50">Retry preview</button>
          ) : null}
          <button
            onClick={handleSave}
            disabled={saving || rendering || smartFillState === 'loading' || saved || !matterId.trim() || !canSaveToMatter || requiredUnresolvedNames.length > 0 || (isPdfOutput && !previewId) || (isDocxTemplate && !filePreview)}
            title={!canSaveToMatter
              ? 'Activate this verified template before saving to a matter'
              : requiredUnresolvedNames.length > 0
                ? 'Complete the required fields before saving'
              : (isPdfOutput && !previewId)
                ? 'Wait for the preview to update before saving'
                : (isDocxTemplate && !filePreview)
                  ? 'Download and review the current Word preview before saving'
                : undefined}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white bg-brand-accent hover:opacity-90 rounded disabled:opacity-50"
          >
            {saved ? (
              <>
                <Check size={16} /> Saved
              </>
            ) : (
              <>
                <Save size={16} />
                {saving ? 'Saving...' : 'Save to matter'}
              </>
            )}
          </button>
        </div>
        {autoPreviewEnabled && <p role="status" className="text-xs text-brand-muted">
          {!matterId.trim() ? 'Choose a matter to fill and preview this document.' : previewError ? 'Preview could not update. Retry before saving.' : smartFillState === 'loading' ? 'Filling from your matter…' : livePreviewPending ? 'Updating preview… You can keep editing.' : 'Preview updates as you type. Review every page before saving.'}
        </p>}
  </>
  const testSummarySection = <>
        {!canSaveToMatter && <TemplateTestSummary template={template} error={error} rendering={rendering} outputReady={Boolean(filePreview || rendered)} missing={requiredUnresolvedNames} diagnostic={renderPurpose !== 'activation'} />}
  </>
  const referenceSection = <>
        {!filePreview && !rendered && <><div className="mb-3"><h3 className="text-sm font-semibold text-brand-ink">Document reference</h3><p className="mt-1 text-xs text-brand-muted">{autoPreviewEnabled ? 'Click a highlighted field to complete it. Your PDF preview updates automatically.' : 'Click a highlighted field to complete it. Choose Preview to check the generated document with your current values.'}</p></div><TemplateFillSource autoPreview={autoPreviewEnabled} template={template} fields={Object.values(fieldDefinitions).filter(field => field.included !== false)} values={variables} onSelectField={name => { pendingFocus.current = name; setFieldFilter('all'); requestAnimationFrame(() => document.getElementById(`template-variable-${name}`)?.focus()) }} /></>}
  </>
  const outputSection = <>
        {rendered && (
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-medium text-brand-ink">
              {outputFormat === 'pdf' ? 'PDF Preview' : 'Text Preview'}
            </h3>
              <button type="button" onClick={() => downloadRenderedText(rendered, template.title)} className="inline-flex items-center gap-1.5 rounded border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand-surface-2">
                <Download size={14} /> Download preview
              </button>
            </div>
            <div className="bg-brand-bg border border-brand-line rounded p-4 whitespace-pre-wrap font-mono text-sm text-brand-ink max-h-96 overflow-y-auto">
              {rendered}
            </div>
          </div>
        )}

        {filePreview && (
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-medium text-brand-ink">{isPdfOutput ? 'PDF Preview' : 'Generated Word Preview'}</h3>
                <p className="text-xs text-brand-muted">{filePreview.filename}</p>
              </div>
              <button type="button" disabled={livePreviewPending} onClick={() => triggerBlobDownload(filePreview.blob, filePreview.filename)} className="inline-flex items-center gap-1.5 rounded border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand-surface-2 disabled:opacity-50">
                <Download size={14} /> Download preview
              </button>
            </div>
            {isPdfOutput ? (
              <>
                {livePreviewPending && <p role="status" className="mb-2 rounded border border-brand-amber/40 bg-brand-amber/10 px-3 py-2 text-xs">{previewError ? 'This preview is out of date. Retry to see your latest answers.' : 'Updating preview. The document below shows your previous answers.'}</p>}
                <GeneratedPdfPreview key={autoPreviewEnabled ? `${template.id}:${matterId}` : filePreviewUrl} source={filePreview.blob} title={template.title} />
                {!livePreviewPending && <p className="mt-2 text-xs font-medium text-brand-green" role="status">
                  {previewPurpose === 'generation'
                    ? 'Preview is up to date. Review every page, then save to your matter.'
                    : previewPurpose === 'activation'
                      ? 'Representative activation preview recorded. Inspect every page, then activate this unchanged template.'
                      : 'Draft preview only. To record a publication test, choose Test this draft after entering representative values. Review every generated page before publishing.'}
                </p>}
              </>
            ) : (
              <div className="rounded border border-brand-green/30 bg-brand-green/10 px-4 py-3 text-sm text-brand-ink">
                Word formatting was preserved. Download and open this generated DOCX to inspect its exact pagination, tables, headers, and footers.
              </div>
            )}
          </div>
        )}
  </>
  const savedSection = <>
        {matterDocId && (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-brand-green/30 bg-brand-green/10 px-3 py-2">
              <p className="text-xs text-brand-green">
                Saved to the matter{outputFilename ? ` as ${outputFilename}` : ''}{outputFormat ? ` (${outputFormat.toUpperCase()})` : ''}{storageBackend ? ` in ${storageBackend.replaceAll('_', ' ')}` : ''}.
              </p>
              <a href={savedDownloadUrl || getMatterDocumentDownloadUrl(matterId.trim(), matterDocId)} className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-accent-2 underline">
                <Download size={14} /> Download saved document
              </a>
            </div>
            {storageWarning && (
              <div role="alert" className="rounded border border-brand-amber/40 bg-brand-amber/10 px-3 py-2 text-xs text-brand-ink">
                {storageWarning}
              </div>
            )}
          </div>
        )}
  </>

  const viewTabs = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div role="tablist" aria-label="Fill view" className="inline-flex rounded-lg border border-brand-line bg-brand-bg p-0.5">
        {VIEW_TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={view === id}
            onClick={() => (id === 'preview' ? setView('preview') : chooseView(id))}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${view === id ? 'bg-brand-surface text-brand-ink shadow-sm' : 'text-brand-muted hover:text-brand-ink'}`}
          >
            {label}
            {id === 'preview' && livePreviewPending && matterId.trim() ? <span className="ml-1.5 text-xs font-normal text-brand-muted">updating…</span> : null}
          </button>
        ))}
      </div>
      {names.length > 0 && view !== 'questions' && (
        <p className="text-xs text-brand-muted" role="status">
          {progress.percent}% complete · {progress.completed} of {progress.total} filled · {progress.verified || 0} verified · {requiredUnresolvedNames.length} required missing
        </p>
      )}
    </div>
  )

  const footer = (
    <div className="flex flex-col gap-3 border-t border-brand-line pt-3">
      {outputFormatSection}
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">{actionsSection}</div>
      </div>
      {testSummarySection}
      {savedSection}
    </div>
  )

  const docHeight = layout === 'modal' ? 'h-[62vh] min-h-[420px]' : 'h-[calc(100vh-15rem)] min-h-[520px]'

  if (view === 'questions') {
    return (
      <div className="flex min-w-0 flex-col gap-3">
        {viewTabs}
        <div className="grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-[minmax(300px,380px)_minmax(0,1fr)]"><div className={`min-w-0 space-y-4 lg:pr-2 ${scrollClass}`}>
          {noticeSection}
          {matterSection}
          {smartFillSection}
          {correctSourceSection}
          {factSection}
          {fieldListSection}
          {noVariablesSection}
          {outputFormatSection}
          {actionsSection}
          {testSummarySection}
        </div><section aria-label="Document preview" className={`min-w-0 rounded-xl border border-brand-line bg-brand-bg p-4 ${layout === 'modal' ? 'lg:max-h-[78vh] lg:overflow-auto' : ''}`}>
          {referenceSection}
          {outputSection}
          {savedSection}
        </section></div>
      </div>
    )
  }

  const setupSection = (
    <div className="space-y-3">
      {noticeSection}
      <div className="grid gap-3 lg:grid-cols-2 lg:items-start">
        <div className="min-w-0 space-y-2">{matterSection}</div>
        <div className="min-w-0 space-y-2">{smartFillSection}{correctSourceSection}</div>
      </div>
      {factSection}
    </div>
  )

  if (view === 'preview') {
    const hasOutput = Boolean(rendered || filePreview)
    return (
      <div className="flex min-w-0 flex-col gap-3">
        {viewTabs}
        {noticeSection}
        <section aria-label="Document preview" className="min-w-0 rounded-xl border border-brand-line bg-brand-bg p-4">
          {outputSection}
          {!hasOutput && (
            <p role="status" className="p-6 text-center text-sm text-brand-muted">
              {!matterId.trim() && canSaveToMatter
                ? 'Choose a matter to fill and preview this document.'
                : autoPreviewEnabled
                  ? (previewError ? 'Preview could not update. Retry before saving.' : 'Preparing the preview with your answers…')
                  : 'Choose Preview below to generate this document with your answers.'}
            </p>
          )}
        </section>
        {footer}
      </div>
    )
  }

  // Document view.
  const referenceField = referenceGuide.activeField
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {viewTabs}
      {setupSection}
      {names.length === 0 ? noVariablesSection : (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button type="button" onClick={() => followField(nextField())} disabled={!(progress.remaining.length + progress.review.length)} className="rounded border border-brand-line px-3 py-1.5 font-semibold disabled:opacity-40">Next field needing attention</button>
          {autoPreviewEnabled && matterId.trim() && <span className="text-brand-muted">The preview updates as you type; open Preview to check it.</span>}
        </div>
      )}
      {names.length > 0 && (
        <div className={`flex min-w-0 flex-col ${docHeight}`}>
          {fillOnPage ? (
            <FillOnDocument
              source={pdfSource.blob}
              fields={documentFields}
              values={variables}
              onChange={updateValue}
              renderInput={(field) => renderFieldEditor(field.name)}
              onUnavailable={onPdfUnavailable}
              activeName={docActive}
              onActiveChange={activateDocField}
              statusFor={statusFor}
              isMissing={isMissing}
              markerFor={markerFor}
              legend={LEGEND}
              checkboxValues={CHECKBOX_VALUES}
              disabled={saving}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-brand-line bg-brand-bg-soft">
              <div className="min-h-0 flex-1 overflow-auto p-4">
                {(pdfSource.failed || pdfUnreadable) && <p role="status" className="mb-3 text-xs text-brand-muted">The original PDF could not be opened for typing on the page. Use the bar below or Questions.</p>}
                <TemplateFillSource autoPreview={autoPreviewEnabled} template={template} fields={documentFields.filter(field => field.included !== false)} values={variables} onSelectField={activateDocField} />
              </div>
              <GuidedFieldBar
                field={referenceField}
                position={referenceGuide.index + 1}
                total={documentFields.length}
                onPrevious={() => referenceGuide.step(-1)}
                onNext={() => referenceGuide.step(1)}
                onNextRequired={referenceGuide.nextRequired}
                requiredMissing={referenceGuide.missing.length}
              >
                {referenceField && renderFieldEditor(referenceField.name)}
              </GuidedFieldBar>
            </div>
          )}
        </div>
      )}
      {footer}
    </div>
  )
}
