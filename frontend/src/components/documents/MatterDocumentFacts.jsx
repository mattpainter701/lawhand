import { useCallback, useEffect, useRef, useState } from 'react'
import {
  acceptMatterDocumentFact,
  getMatterDocumentDownloadUrl,
  getMatterDocumentFormSources,
  getMatterDocuments,
  proposeMatterDocumentFacts,
  readMatterDocumentAgainstForm,
} from '../../api'

const READABLE = /\.(pdf|docx|txt|png|jpe?g|tiff?)$/i

const formKey = (source) => `${source.template_id}:${source.version_no ?? ''}`

// Where a proposed value came from, and how sure the reader was when it was
// read from a scan rather than typed into a form.
export function sourceLabel(entry) {
  const percent = typeof entry.confidence === 'number' ? Math.round(entry.confidence * 100) : null
  if (entry.source_kind === 'ocr_field') return `Read from the scan, field by field${percent == null ? '' : ` · ${percent}% OCR confidence`}`
  if (entry.source_kind === 'ocr') return `From the scan${percent == null ? '' : ` · ${percent}% OCR confidence`}`
  if (entry.source_kind === 'acroform') return 'From the form'
  if (entry.source_kind === 'regex') return 'From the text'
  if (entry.source_kind === 'ai') return 'Proposed by AI'
  return 'From the document'
}

function rowId(entry) {
  return entry.target_key
}

export default function MatterDocumentFacts({ matterId, documentId: providedDocumentId, documents: providedDocuments, onAccepted }) {
  const requestVersion = useRef(0)
  const [fetched, setFetched] = useState([])
  const [pickedId, setPickedId] = useState('')
  const [proposal, setProposal] = useState(null)
  const [values, setValues] = useState({})
  const [replace, setReplace] = useState({})
  const [done, setDone] = useState({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [useAi, setUseAi] = useState(false)
  const [formSources, setFormSources] = useState([])
  const [formChoice, setFormChoice] = useState('')
  const documents = providedDocuments || fetched
  const documentId = providedDocumentId || pickedId

  // The forms this matter generated; a scan of one can be read against it.
  useEffect(() => {
    let current = true
    setFormSources([])
    setFormChoice('')
    if (!matterId || !documentId) return undefined
    getMatterDocumentFormSources(matterId, documentId)
      .then(result => {
        if (!current) return
        const sources = Array.isArray(result?.sources) ? result.sources : []
        setFormSources(sources)
        setFormChoice(sources.length ? formKey(sources[0]) : '')
      })
      .catch(() => { if (current) setFormSources([]) })
    return () => { current = false }
  }, [matterId, documentId])

  useEffect(() => {
    let current = true
    requestVersion.current += 1
    setFetched([])
    setPickedId('')
    setProposal(null)
    setValues({})
    setDone({})
    setMessage('')
    // When the parent already holds the matter's document list, reuse it rather
    // than issuing a second read of the same documents.
    if (matterId && !providedDocuments && !providedDocumentId) {
      getMatterDocuments(matterId)
        .then(result => {
          if (current) setFetched((result.items || result.documents || result || []).filter(doc => READABLE.test(doc.filename)))
        })
        .catch(() => { if (current) setMessage('Matter source documents could not be loaded.') })
    }
    return () => { current = false; requestVersion.current += 1 }
  }, [matterId, providedDocuments, providedDocumentId])

  const applyResult = useCallback((version, result) => {
    if (version !== requestVersion.current) return
    setProposal(result)
    setValues(Object.fromEntries((result.candidates || []).map(entry => [rowId(entry), entry.value == null ? '' : String(entry.value)])))
    if (!(result.candidates || []).length) setMessage((result.warnings || [])[0] || 'No supported details were found in this document.')
  }, [])

  const readAgainstForm = useCallback(async () => {
    const source = formSources.find(item => formKey(item) === formChoice)
    if (!source) return
    const version = ++requestVersion.current
    setBusy(true)
    setProposal(null)
    setValues({})
    setReplace({})
    setDone({})
    setMessage('')
    try {
      const result = await readMatterDocumentAgainstForm(matterId, documentId, {
        template_id: source.template_id,
        ...(source.version_no ? { version_no: source.version_no } : {}),
      })
      applyResult(version, result)
    } catch (error) {
      if (version === requestVersion.current) setMessage(error?.response?.data?.detail || 'The scan could not be read against the form.')
    } finally {
      if (version === requestVersion.current) setBusy(false)
    }
  }, [matterId, documentId, formSources, formChoice, applyResult])

  const read = useCallback(async () => {
    const version = ++requestVersion.current
    setBusy(true)
    setProposal(null)
    setValues({})
    setReplace({})
    setDone({})
    setMessage('')
    try {
      const result = await proposeMatterDocumentFacts(matterId, documentId, useAi)
      if (version !== requestVersion.current) return
      setProposal(result)
      setValues(Object.fromEntries((result.candidates || []).map(entry => [rowId(entry), entry.value == null ? '' : String(entry.value)])))
      if (!(result.candidates || []).length) setMessage((result.warnings || [])[0] || 'No supported details were found in this document.')
    } catch (error) {
      if (version === requestVersion.current) setMessage(error?.response?.data?.detail || 'The source could not be read.')
    } finally {
      if (version === requestVersion.current) setBusy(false)
    }
  }, [matterId, documentId, useAi])

  const accept = async entry => {
    const id = rowId(entry)
    setBusy(true)
    setMessage('')
    try {
      await acceptMatterDocumentFact(matterId, documentId, {
        target_key: entry.target_key,
        value: values[id],
        replace_existing: Boolean(replace[id]),
      })
      setDone(previous => ({ ...previous, [id]: true }))
      setMessage(`${entry.label} saved to the matter.`)
      onAccepted?.()
    } catch (error) {
      setMessage(error?.response?.data?.detail || 'The detail could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  if (!matterId) return null
  const pending = (proposal?.candidates || []).filter(entry => !done[rowId(entry)])

  return (
    <details className="rounded border border-brand-line p-3">
      <summary className="cursor-pointer font-semibold text-sm">Read details from a document</summary>
      <p className="my-2 text-xs text-brand-muted">
        Reads a filled PDF form or exact “Label: value” lines and proposes matter and client details.
        Nothing is saved until you accept it.
      </p>
      {!providedDocumentId && (
        <label className="block text-xs">
          Source document
          <select
            aria-label="Source document"
            value={pickedId}
            disabled={busy}
            onChange={event => { setPickedId(event.target.value); setProposal(null); setDone({}); setMessage('') }}
            className="block w-full border rounded p-2 text-brand-ink bg-brand-bg"
          >
            <option value="">Choose a source</option>
            {documents.map(doc => <option key={doc.id} value={doc.id}>{doc.filename}</option>)}
          </select>
        </label>
      )}
      <label className="mt-2 flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={useAi}
          disabled={busy}
          onChange={event => setUseAi(event.target.checked)}
        />
        Also read with AI for scans and prose (document text is sent to the AI provider)
      </label>
      <button type="button" onClick={read} disabled={busy || !documentId} className="mt-2 border rounded p-2 text-sm">
        {busy ? 'Reading…' : 'Find details'}
      </button>
      {formSources.length > 0 && (
        <div className="mt-3 rounded border border-brand-line p-2 text-xs">
          <p className="font-semibold">Printed and filled in by hand?</p>
          <p className="my-1 text-brand-muted">Read the scan field by field against the form this matter printed. Each value shows a clip of the handwriting and how sure the reader was.</p>
          <label className="block">
            Printed form
            <select aria-label="Printed form" value={formChoice} disabled={busy} onChange={event => setFormChoice(event.target.value)} className="block w-full border rounded p-2 text-brand-ink bg-brand-bg">
              {formSources.map(source => <option key={formKey(source)} value={formKey(source)}>{source.template_title || source.template_id}{source.version_no ? ` v${source.version_no}` : ''}{source.output_filename ? ` — ${source.output_filename}` : ''}</option>)}
            </select>
          </label>
          <button type="button" onClick={readAgainstForm} disabled={busy || !documentId || !formChoice} className="mt-2 border rounded p-2 text-sm">
            {busy ? 'Reading…' : 'Read against the printed form'}
          </button>
        </div>
      )}
      {proposal && pending.length > 0 && (proposal.warnings || []).length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-brand-muted">
          {(proposal.warnings || []).map(warning => <li key={warning}>{warning}</li>)}
        </ul>
      )}
      {proposal && pending.length > 0 && (
        <ul className="mt-3 space-y-3 text-sm">
          {pending.map(entry => (
            <li key={rowId(entry)} className="rounded border border-brand-line p-2">
              <div className="flex items-center justify-between gap-2">
                <strong>{entry.label}</strong>
                {entry.status === 'conflicting_sources'
                  ? <span className="text-xs text-brand-danger">Conflicting values in the document</span>
                  : <span className="text-xs text-brand-muted">{sourceLabel(entry)}</span>}
              </div>
              {entry.thumbnail_png_b64 && (
                <img alt={`Scan of ${entry.label}`} src={`data:image/png;base64,${entry.thumbnail_png_b64}`} className="mt-1 max-h-16 rounded border border-brand-line" />
              )}
              <label className="block text-xs mt-1">
                Value
                <input
                  aria-label={`${entry.label} value`}
                  value={values[rowId(entry)] ?? ''}
                  onChange={event => setValues(previous => ({ ...previous, [rowId(entry)]: event.target.value }))}
                  className="block w-full border rounded p-2 text-brand-ink bg-brand-bg"
                />
              </label>
              {entry.current_value != null && String(entry.current_value) !== '' && (
                <label className="flex items-center gap-2 text-xs mt-1">
                  <input
                    type="checkbox"
                    checked={Boolean(replace[rowId(entry)])}
                    onChange={event => setReplace(previous => ({ ...previous, [rowId(entry)]: event.target.checked }))}
                  />
                  Replace the current value “{String(entry.current_value)}”
                </label>
              )}
              <button type="button" disabled={busy || !String(values[rowId(entry)] ?? '').trim()} onClick={() => accept(entry)} className="mt-2 border rounded p-2 text-sm font-semibold">
                Accept {entry.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {proposal?.source_document_id && (
        <a className="mt-2 inline-block text-xs underline" href={getMatterDocumentDownloadUrl(matterId, documentId)} target="_blank" rel="noreferrer">
          Open {proposal.source_filename}
        </a>
      )}
      {message && <p role="status" className="mt-2 text-sm">{message}</p>}
    </details>
  )
}
