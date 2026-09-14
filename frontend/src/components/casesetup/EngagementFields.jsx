import { ENGAGEMENT_CHOICES } from './engagement'

const field = 'block w-full rounded-lg border border-brand-line bg-brand-surface px-3 py-2 text-sm text-brand-ink focus:border-brand-accent focus:outline-none focus:ring-1 focus:ring-brand-accent'
const label = 'block text-[12px] font-semibold uppercase tracking-wider text-brand-muted mb-1.5'

// The three ways an existing engagement is recorded, as one radio group with
// the inputs each answer needs. `documents` lists matter PDFs already on file
// so a scanned copy uploaded earlier can be chosen instead of uploaded twice.
export default function EngagementFields({ value, onChange, documents = [], idPrefix = 'engagement', disabled = false }) {
  const set = (key, next) => onChange({ ...value, [key]: next })
  const pdfs = documents.filter(document => document.content_type === 'application/pdf' || document.filename?.toLowerCase().endsWith('.pdf'))
  return (
    <fieldset disabled={disabled} className="space-y-3">
      <legend className={label}>How was this matter engaged?</legend>
      {ENGAGEMENT_CHOICES.map(choice => (
        <label key={choice.value} className="flex items-start gap-2 text-[13px] text-brand-ink">
          <input
            type="radio"
            name={`${idPrefix}-status`}
            value={choice.value}
            checked={value.status === choice.value}
            onChange={() => set('status', choice.value)}
            className="mt-0.5"
          />
          <span>
            <span className="font-semibold">{choice.label}</span>
            <span className="block text-[12px] text-brand-muted">{choice.description}</span>
          </span>
        </label>
      ))}

      {value.status === 'signed_on_file' && (
        <div className="space-y-3 rounded-lg border border-brand-line bg-brand-bg-soft/40 p-3">
          {pdfs.length > 0 && (
            <label className="block">
              <span className={label}>Signed copy already on the matter</span>
              <select className={field} value={value.documentId} onChange={event => set('documentId', event.target.value)}>
                <option value="">Upload a new file instead</option>
                {pdfs.map(document => <option key={document.id} value={document.id}>{document.filename}</option>)}
              </select>
            </label>
          )}
          {!value.documentId && (
            <label className="block">
              <span className={label}>Signed fee agreement (PDF)</span>
              <input
                type="file"
                accept=".pdf,application/pdf"
                className={field}
                onChange={event => set('file', event.target.files?.[0] || null)}
              />
              {value.file && <span className="mt-1 block text-[12px] text-brand-muted">{value.file.name}</span>}
            </label>
          )}
        </div>
      )}

      {value.status !== 'no_agreement' && (
        <label className="block">
          <span className={label}>Date signed (optional)</span>
          <input
            id={`${idPrefix}-signed-on`}
            type="date"
            className={field}
            value={value.signedOn}
            max={new Date().toISOString().slice(0, 10)}
            onChange={event => set('signedOn', event.target.value)}
          />
        </label>
      )}

      <label className="block">
        <span className={label}>
          {value.status === 'no_agreement' ? 'Why there is no fee agreement' : value.status === 'signed_no_copy' ? 'Where it was signed' : 'Note (optional)'}
        </span>
        <textarea
          id={`${idPrefix}-note`}
          className={field}
          rows={2}
          maxLength={1000}
          value={value.note}
          onChange={event => set('note', event.target.value)}
          placeholder={value.status === 'no_agreement' ? 'For example: long-standing client billed under the 2019 retainer letter' : ''}
        />
      </label>
    </fieldset>
  )
}
