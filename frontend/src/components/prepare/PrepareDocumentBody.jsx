import { Check, Download, Eye, Send, Wand2 } from 'lucide-react'
import MatterPicker from './MatterPicker'
import TemplateFactReview from '../templates/TemplateFactReview'
import TemplateFillProgress from '../templates/TemplateFillProgress'
import TemplateFillSource from '../templates/TemplateFillSource'
import TemplateTestSummary from '../templates/TemplateTestSummary'
import GeneratedPdfPreview from '../templates/GeneratedPdfPreview'
import { fillValue, isSigningField, suggestionConfidenceLabel } from '../templates/templateFillReview'
import { getMatterDocumentDownloadUrl, triggerBlobDownload } from '../../api'
import { downloadRenderedText, friendlyVariableLabel } from './prepareHelpers'

// The two-pane fill surface: fields and actions on the left, the document
// reference or generated preview on the right. Rendered inside the Generate
// dialog (`layout="modal"`) and as the body of the Prepare route
// (`layout="page"`). Every control keeps its accessible name in both.
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
    convertDocxToPdf,
    hasSigningFields,
    setConvertDocxToPdf,
    rendering,
    renderPurpose,
    saving,
    saved,
    setSaved,
    error,
    smartFillState,
    smartFillMessage,
    fieldSources,
    setFieldSources,
    latestSuggestions,
    setReviewedValues,
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
  const scrollClass = layout === 'modal' ? 'lg:max-h-[78vh] lg:overflow-y-auto' : ''
  return (
      <div className="grid gap-5 lg:grid-cols-[minmax(300px,380px)_minmax(0,1fr)]"><div className={`space-y-4 lg:pr-2 ${scrollClass}`}>
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
            value={matterId}
            onChange={(e) => selectMatter(e.target.value)}
            disabled={saving}
            className="w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent font-mono"
            placeholder="Paste matter UUID if the matter is not listed"
          />
        </details>

        </>}

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

        {(matterId.trim() || hasFirmFields) && <div className="rounded border border-brand-line bg-brand-bg p-3 text-xs">
          <p className="font-semibold">Correct the source once</p>
          <div className="mt-2 flex flex-wrap gap-3">
            {matterId.trim() && <a href={`/matters/${encodeURIComponent(matterId.trim())}`} target="_blank" rel="noreferrer" className="underline">Open matter details (new tab)</a>}
            {hasFirmFields && <a href="/admin?tab=firm" target="_blank" rel="noreferrer" className="underline">Open firm settings (new tab)</a>}
          </div>
          <p className="mt-2 text-brand-muted">Keep this document open. After saving changes to the source, return and refresh values. Your entries stay intact; changed suggestions are yours to accept. Firm changes require an administrator.</p>
        </div>}

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

        {names.length > 0 && (
          <div>
            <div className="sticky top-0 z-20 bg-brand-surface pb-2">
              <TemplateFillProgress progress={progress} requiredMissing={requiredUnresolvedNames.length} filter={fieldFilter} onFilter={value => { lastAttentionField.current = null; setFocusedFillName(null); setFieldFilter(value) }} onNext={nextField} />
            </div>
            <h3 className="text-sm font-medium text-brand-ink mb-2">
              Fields
            </h3>
            <div className="space-y-2">
              {visibleNames.map((name) => {
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
                  {fieldSources[name] && <p className="mb-1 text-xs text-brand-muted">{fieldSources[name].suggested_value == null ? 'Missing: review or enter a value' : `From ${fieldSources[name].provenance?.binding_label || fieldSources[name].source_type || 'record'} · verify current accuracy`}{fieldSources[name].provenance?.updated_at ? ` · Updated ${new Date(fieldSources[name].provenance.updated_at).toLocaleDateString()}` : ''}</p>}
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
                        onChange={(e) => setVariable(name, e.target.checked ? 'true' : 'false')}
                        disabled={saving}
                        className="h-4 w-4 rounded border-brand-line text-brand-accent focus:ring-brand-accent"
                      />
                      Checked
                    </label>
                  ) : (fieldType === 'choice' || fieldType === 'radio') && options.length > 0 ? (
                    <select
                      id={inputId}
                      value={variables[name] || ''}
                      onChange={(e) => setVariable(name, e.target.value)}
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
                      onChange={(e) => setVariable(name, e.target.value)}
                      disabled={saving}
                      className="w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent"
                      placeholder={`Enter ${label}`}
                    />
                  ) : (
                    <input
                      id={inputId}
                      type="text"
                      value={variables[name] || ''}
                      onChange={(e) => setVariable(name, e.target.value)}
                      disabled={saving}
                      className="w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent"
                      placeholder={`Enter ${label}`}
                    />
                  )}
                  {field.pdf_field_name && !signingField && (
                    <p className="mt-1 text-[11px] text-brand-muted">PDF field: {field.pdf_field_name}{field.page ? ` · Page ${field.page}` : ''}</p>
                  )}
                </div>
                )
              })}
            </div>
            {visibleNames.length === 0 && <p role="status" className="py-3 text-sm text-brand-muted">{fieldFilter === 'remaining' ? 'No missing fields.' : 'No suggestions waiting for review.'}</p>}
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

        {names.length === 0 && (
          <p className="text-sm text-brand-muted italic">
            This template has no variables. Preview or save it directly.
          </p>
        )}

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


        <div className="flex flex-col sm:flex-row gap-3">
          {!canSaveToMatter ? (
            <>
              <button
                onClick={() => handleRender('draft')}
                disabled={rendering || saving}
                className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-brand-ink border border-brand-line bg-brand-surface hover:bg-brand-surface-2 rounded disabled:opacity-50"
              >
                <Eye size={16} />
                {rendering && renderPurpose === 'draft' ? 'Preparing preview…' : 'Preview draft'}
              </button>
              <button
                onClick={() => handleRender('activation')}
                disabled={rendering || saving}
                className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white bg-brand-ink hover:bg-brand-ink-2 rounded disabled:opacity-50"
              >
                <Check size={16} />
                {rendering && renderPurpose === 'activation' ? 'Testing this draft…' : 'Test this draft'}
              </button>
            </>
          ) : (
            <button
              onClick={() => handleRender()}
              disabled={rendering || saving}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white bg-brand-ink hover:bg-brand-ink-2 rounded disabled:opacity-50"
            >
              <Eye size={16} />
              {rendering ? 'Rendering...' : 'Preview'}
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving || smartFillState === 'loading' || saved || !matterId.trim() || !canSaveToMatter || (isPdfOutput && !previewId) || (isDocxTemplate && !filePreview)}
            title={!canSaveToMatter
              ? 'Activate this verified template before saving to a matter'
              : (isPdfOutput && !previewId)
                ? 'Preview the exact current PDF values before saving'
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
                <Send size={16} />
                {saving ? 'Saving...' : 'Render & Save to Matter'}
              </>
            )}
          </button>
        </div>

        {!canSaveToMatter && <TemplateTestSummary template={template} error={error} rendering={rendering} outputReady={Boolean(filePreview || rendered)} missing={requiredUnresolvedNames} diagnostic={renderPurpose !== 'activation'} />}

        </div><section aria-label="Document preview" className={`min-w-0 rounded-xl border border-brand-line bg-brand-bg p-4 ${layout === 'modal' ? 'lg:max-h-[78vh] lg:overflow-auto' : ''}`}>
        {!filePreview && !rendered && <><div className="mb-3"><h3 className="text-sm font-semibold text-brand-ink">Document reference</h3><p className="mt-1 text-xs text-brand-muted">Click a highlighted field to complete it. Choose Preview to check the generated document with your current values.</p></div><TemplateFillSource template={template} fields={Object.values(fieldDefinitions).filter(field => field.included !== false)} values={variables} onSelectField={name => { pendingFocus.current = name; setFieldFilter('all'); requestAnimationFrame(() => document.getElementById(`template-variable-${name}`)?.focus()) }} /></>}
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
              <button type="button" onClick={() => triggerBlobDownload(filePreview.blob, filePreview.filename)} className="inline-flex items-center gap-1.5 rounded border border-brand-line px-3 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand-surface-2">
                <Download size={14} /> Download preview
              </button>
            </div>
            {isPdfOutput ? (
              <>
                <GeneratedPdfPreview key={filePreviewUrl} source={filePreview.blob} title={template.title} />
                <p className="mt-2 text-xs font-medium text-brand-green" role="status">
                  {previewPurpose === 'generation'
                    ? 'These exact values and this matter are previewed. Inspect every page, then save without changing the fields.'
                    : previewPurpose === 'activation'
                      ? 'Representative activation preview recorded. Inspect every page, then activate this unchanged template.'
                      : 'Draft preview only. To record a publication test, choose Test this draft after entering representative values. Review every generated page before publishing.'}
                </p>
              </>
            ) : (
              <div className="rounded border border-brand-green/30 bg-brand-green/10 px-4 py-3 text-sm text-brand-ink">
                Word formatting was preserved. Download and open this generated DOCX to inspect its exact pagination, tables, headers, and footers.
              </div>
            )}
          </div>
        )}

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
      </section></div>
  )
}
