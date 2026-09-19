import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMatterV2 } from '../../api'
import SignatureSendCard from '../signatures/SignatureSendCard'
import useSignatureRequestDraft from '../signatures/useSignatureRequestDraft'
import { initialSignersForMatter } from '../signatures/signerPrefill'

// The document the render response describes, in the shape the signature
// request rules read (the same shape the matter's document list returns).
export function savedDocumentFromRender(res) {
  if (!res?.matter_document_id) return null
  return {
    id: res.matter_document_id,
    filename: res.output_filename || 'Generated document',
    positioned_fields: Array.isArray(res.positioned_fields) ? res.positioned_fields : [],
    signing_roles: Array.isArray(res.signing_roles) ? res.signing_roles : [],
    signing_placement_required: Boolean(res.signing_placement_required),
    signing_placement_problems: Array.isArray(res.signing_placement_problems) ? res.signing_placement_problems : [],
  }
}

// A saved PDF can be sent when the template gave it signing roles or fields.
// Anything else (Word, markdown, a PDF with no signature field) lands on the
// matter as before.
export const renderIsSendable = (res) => String(res?.output_format || '').toLowerCase() === 'pdf'
  && Boolean(res?.matter_document_id)
  && ((res?.signing_roles || []).length > 0 || (res?.positioned_fields || []).length > 0)

function SendForm({ matterId, document, matter, savedTarget, onSent }) {
  const initialSigners = useMemo(() => initialSignersForMatter(matter, document.signing_roles), [matter, document.signing_roles])
  const draft = useSignatureRequestDraft({ matterId, document, initialSigners, onSent: (sent, outcome) => { if (sent) onSent(outcome) } })
  return (
    <SignatureSendCard
      draft={draft}
      document={document}
      heading="Send for signature"
      description={`${document.filename} is saved to the matter. Check the signers, then prepare and send the request.`}
    >
      <p className="text-xs text-brand-muted">
        Not ready to send? <Link className="underline" to={savedTarget}>Open it in the matter's documents</Link> and send it from the E-Signature panel later.
      </p>
    </SignatureSendCard>
  )
}

// The Send step of the Prepare route: the document was just saved, so the
// request is built from the render response and the matter's client, under
// the same rules the matter's E-Signature panel applies.
export default function SendStep({ matterId, document, savedTarget, onSent }) {
  const [matter, setMatter] = useState(null)
  const [matterReady, setMatterReady] = useState(false)
  const [sent, setSent] = useState(null)
  useEffect(() => {
    let active = true
    setMatterReady(false)
    getMatterV2(matterId)
      .then((value) => { if (active) setMatter(value) })
      .catch(() => { if (active) setMatter(null) })
      .finally(() => { if (active) setMatterReady(true) })
    return () => { active = false }
  }, [matterId])
  if (sent) {
    return (
      <section aria-label="Sent for signature" className="rounded-2xl border border-brand-line bg-white p-4 space-y-2">
        <h3 className="text-sm font-sans font-semibold text-brand-ink">Sent for signature</h3>
        <p role="status" className={`text-sm ${sent.delivered ? 'text-brand-green' : 'text-brand-amber font-semibold'}`}>{sent.text}</p>
        <Link className="inline-block text-sm font-semibold text-brand-accent hover:text-brand-ink" to={savedTarget}>Open the matter's documents</Link>
      </section>
    )
  }
  if (!matterReady) return <p role="status" className="text-sm text-brand-muted">Preparing the signature request…</p>
  return (
    <SendForm
      matterId={matterId}
      document={document}
      matter={matter}
      savedTarget={savedTarget}
      onSent={(outcome) => { setSent(outcome); onSent?.(outcome) }}
    />
  )
}
