import GeneratedSigningPlacementReview from '../templates/GeneratedSigningPlacementReview'
import { formatSignerRole, signingFieldKind, signingFieldOrigin } from './signatureRequestRules'

const inputClass = 'w-full border border-brand-line rounded-lg px-3 py-2 text-sm font-sans focus:outline-none focus:ring-2 focus:ring-brand-accent/40'
const signerInputClass = 'border border-brand-line rounded-lg px-3 py-2 text-sm font-sans focus:outline-none focus:ring-2 focus:ring-brand-accent/40'

// One signature request, from signers to "Send for signature". `draft` is the
// state from useSignatureRequestDraft; `document` is the matter document it
// is for; `picker` is whatever chooses that document (the matter panel's
// select and upload; nothing on the Prepare route, where the document was
// generated a moment ago). `submitDisabled` lets the host hold the submit
// while it is busy with something else, such as an upload.
export default function SignatureSendCard({ draft, document, picker = null, heading = 'New request', description = 'Choose a matter document and the portal signers who should sign it.', submitDisabled = false, children = null }) {
  const {
    signers, updateSigner, addSigner, removeSigner,
    positionedFields, setPositionedFields, initialFields, roleOptions, placementSigners, duplicateRoles,
    reviewOpen, setReviewOpen, signingSource, reviewPossible, placementLines,
    dueOn, setDueOn, expiresOn, setExpiresOn, reminderDays, setReminderDays, enforceSigningOrder, setEnforceSigningOrder,
    busy, error, notice, noticeDelivered, prepare, sendDraft, discardDraft, setAcknowledged, openDraft, draftError,
  } = draft
  const pending = draft.draft
  return (
    <>
      <form onSubmit={prepare} className="rounded-2xl border border-brand-line bg-white p-4 space-y-4">
        <div>
          <h3 className="text-sm font-sans font-semibold text-brand-ink">{heading}</h3>
          {description && <p className="text-xs text-brand-muted mt-0.5">{description}</p>}
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {picker}
          <label className="text-sm text-brand-ink">
            <span className="mb-1 block text-[12px] font-semibold uppercase tracking-wider text-brand-muted">Due from client</span>
            <input type="date" aria-label="Due from client" value={dueOn} onChange={(e) => setDueOn(e.target.value)} className={inputClass} />
            <span className="mt-1 block text-[12px] text-brand-muted">Creates an assigned follow-up task. Optional.</span>
          </label>
          <label className="text-sm text-brand-ink">
            <span className="mb-1 block text-[12px] font-semibold uppercase tracking-wider text-brand-muted">Expires</span>
            <input type="date" aria-label="Expires" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} className={inputClass} />
            <span className="mt-1 block text-[12px] text-brand-muted">After this date the request can no longer be signed.</span>
          </label>
          <label className="text-sm text-brand-ink">
            <span className="mb-1 block text-[12px] font-semibold uppercase tracking-wider text-brand-muted">Reminders</span>
            <input aria-label="Reminders" value={reminderDays} onChange={(e) => setReminderDays(e.target.value)} placeholder="7,1" className={inputClass} />
            <span className="mt-1 block text-[12px] text-brand-muted">Days before expiry to remind the signer.</span>
          </label>
        </div>
        {document && (
          <div className="flex flex-wrap items-center gap-3">
            {reviewPossible && <button type="button" onClick={() => setReviewOpen(true)} className="rounded border border-brand-line px-3 py-2 text-sm">Review PDF signing positions</button>}
            {reviewPossible && <span className="text-xs text-brand-muted">Place a signature, initials, or date block per signer on the PDF (optional — fields in the PDF and printed signature lines are detected automatically)</span>}
            {positionedFields.length > 0 && <span className="text-xs">{positionedFields.length} positioned signing fields</span>}
          </div>
        )}
        {/* The template defect behind an unsendable document, shown before
            staff fill the form rather than after they press Send. */}
        {document && !positionedFields.length && placementLines.length > 0 && (
          <ul role="alert" className="space-y-1 rounded-lg border border-brand-amber/40 bg-brand-amber/5 p-3 text-xs text-brand-ink">
            {placementLines.map((line) => <li key={line}>{line}</li>)}
          </ul>
        )}
        {reviewOpen && (signingSource
          ? <GeneratedSigningPlacementReview key={String(document?.id || '')} source={signingSource} initialFields={initialFields} signerRoles={placementSigners} onChange={setPositionedFields} />
          : <p role="status">Loading final PDF for placement review…</p>)}
        <label className="inline-flex items-center gap-2 text-xs text-brand-muted">
          <input type="checkbox" checked={enforceSigningOrder} onChange={(e) => setEnforceSigningOrder(e.target.checked)} />
          <span>Require signers to complete in listed order</span>
        </label>
        <div className="space-y-2">
          {signers.map((signer, index) => (
            <div key={index} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_190px_auto] gap-2 rounded-xl bg-brand-bg-soft p-3">
              <input value={signer.name} onChange={(e) => updateSigner(index, 'name', e.target.value)} placeholder={`Signer ${index + 1} full name`} className={signerInputClass} />
              <input type="email" value={signer.email} onChange={(e) => updateSigner(index, 'email', e.target.value)} placeholder="Signer email" className={signerInputClass} />
              <select value={signer.role} aria-label={`Signer ${index + 1} role`} onChange={(e) => updateSigner(index, 'role', e.target.value)} className={signerInputClass}>
                {roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <button type="button" onClick={() => removeSigner(index)} disabled={signers.length === 1} className="px-3 py-2 text-xs font-semibold text-brand-rose disabled:text-brand-muted disabled:cursor-not-allowed">Remove</button>
            </div>
          ))}
          {duplicateRoles.length > 0 && (
            <p role="alert" className="text-xs font-semibold text-brand-amber">
              {duplicateRoles.map(formatSignerRole).join(', ')} is used by more than one signer. Give each signer their own role so they get their own signature fields.
            </p>
          )}
          <button type="button" onClick={addSigner} className="text-xs font-semibold text-brand-accent hover:text-brand-ink">Add signer</button>
          <p className="text-[11px] text-brand-muted">Each signer signs the fields placed for their role. Add the signer first, then place their blocks in the PDF review above.</p>
        </div>
        {children}
        <button type="submit" disabled={busy || submitDisabled || Boolean(pending)} className="px-4 py-2 bg-brand-ink text-white text-sm font-sans font-semibold rounded-lg hover:bg-brand-ink-2 transition-all disabled:opacity-50">
          {busy ? 'Preparing…' : 'Prepare for signature'}
        </button>
        {pending && (
          <p className="text-xs text-brand-muted">
            A draft request is waiting below. Send or discard it before preparing another; later edits above are not applied to it.
          </p>
        )}
      </form>
      {pending && (() => {
        const request = pending.request || {}
        const roles = [...new Set((request.signers || []).map((signer) => signer.role || 'signer'))]
        const signing = pending.fields.filter((item) => ['signature', 'initials', 'date'].includes(item.kind))
        const review = Array.isArray(request.plan_review) ? request.plan_review : []
        const mustAcknowledge = Boolean(request.plan_review_required)
        return (
          <section aria-label="Where each signer will sign" className="rounded-2xl border border-brand-line bg-white p-4 space-y-3">
            <div>
              <h3 className="text-sm font-sans font-semibold text-brand-ink">Where each signer will sign</h3>
              <p className="text-xs text-brand-muted mt-0.5">{request.document_name || 'Document'} — check this before it reaches the client.</p>
            </div>
            <ul className="space-y-2">
              {roles.map((role) => {
                const mine = signing.filter((item) => (item.role || 'signer') === role)
                return (
                  <li key={role} className="text-sm">
                    <span className="font-semibold text-brand-ink">{formatSignerRole(role)}</span>
                    <ul className="ml-4 mt-1 space-y-0.5 text-xs text-brand-muted">
                      {mine.length === 0 && <li>No field</li>}
                      {mine.map((item) => (
                        <li key={item.field_id}>
                          Page {item.page} · {signingFieldKind(item.kind)}{item.label && !['Signature', signingFieldKind(item.kind)].includes(item.label) ? ` “${item.label}”` : ''} · {signingFieldOrigin(item.source)}
                        </li>
                      ))}
                    </ul>
                  </li>
                )
              })}
            </ul>
            {review.map((item, index) => (
              <p key={index} role={item.level === 'warn' ? 'alert' : 'status'} className={`text-xs ${item.level === 'warn' ? 'font-semibold text-brand-amber' : 'text-brand-muted'}`}>{item.detail}</p>
            ))}
            {mustAcknowledge && (
              <label className="inline-flex items-center gap-2 text-xs text-brand-ink">
                <input type="checkbox" checked={pending.acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
                <span>I have checked where each signer will sign</span>
              </label>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={sendDraft} disabled={busy || Boolean(draftError) || (mustAcknowledge && !pending.acknowledged)} className="rounded-lg bg-brand-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">Send for signature</button>
              <button type="button" onClick={discardDraft} disabled={busy} className="rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-rose disabled:opacity-50">Discard draft</button>
            </div>
            {draftError && (
              <p role="alert" className="text-xs font-semibold text-brand-rose">
                {draftError}{' '}
                <button type="button" onClick={() => openDraft(pending.request)} className="underline">Reload the plan</button>
              </p>
            )}
          </section>
        )
      })()}
      {error && <p className="text-sm text-brand-rose">{error}</p>}
      {notice && <p role="status" className={`text-sm ${noticeDelivered ? 'text-brand-green' : 'text-brand-amber font-semibold'}`}>{notice}</p>}
    </>
  )
}
