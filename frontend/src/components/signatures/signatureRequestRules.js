// The rules behind a firm-side signature request, with no React in them, so
// the matter's E-Signature panel and the Prepare route's Send step build the
// same request from the same document and are refused by the same checks.

export function formatSignatureDate(value) {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return '—'
  }
}

export const SIGNER_ROLE_OPTIONS = [
  { value: 'client', label: 'Client' },
  { value: 'co_client', label: 'Co-client' },
  { value: 'attorney_countersigner', label: 'Attorney countersigner' },
  { value: 'witness', label: 'Witness' },
  { value: 'signer', label: 'Signer' },
]

export const newSignerRow = () => ({ name: '', email: '', role: 'client' })

export const signingFieldKind = (kind) => ({ signature: 'Signature', initials: 'Initials', date: 'Date signed' }[kind] || kind)

// Where a field came from decides how much to trust it: a widget in the PDF,
// a block staff placed, or a Word template's declared caption is certain; a
// printed line the server read is a good guess; a fallback block is the server
// admitting it found nothing.
export const signingFieldOrigin = (source) => ({
  acroform: 'a field in the PDF form',
  placed: 'placed by you',
  anchored: 'the caption the template prints beside it',
  detected: 'a signature line found on the page',
  fallback: 'no line found — a block at the foot of the last page',
}[source] || source || 'unknown')

export function formatSignerRole(role) {
  const match = SIGNER_ROLE_OPTIONS.find((option) => option.value === role)
  return match ? match.label : (role || 'Signer').replace(/_/g, ' ')
}

export function signerStatusLabel(signer) {
  if (signer.status === 'signed') return `Signed ${formatSignatureDate(signer.signed_at)}`
  if (signer.status === 'declined') return `Declined ${formatSignatureDate(signer.declined_at)}`
  return 'Pending signature'
}

// Why an invitation email never left the server. The API reports a per-signer
// delivery result; a configuration problem must never be shown as "sent".
export const EMAIL_DELIVERY_REASONS = {
  disabled: 'outbound email is turned off for this environment',
  unconfigured: 'the outbound email settings are incomplete',
  reauthorization_required: 'the sending mailbox needs to be reconnected',
  invalid_recipient: 'the signer address was rejected',
  failed: 'the mail server rejected the message',
}

export const SENT_NOTICE = 'Signature request sent. Signers will see it in their client portal Signatures tab when it is their turn.'

// The request is created and visible in the portal either way, so an
// undelivered invitation is a warning rather than a failure — but it has to be
// said, and it has to name the signer whose email did not go out.
export function signatureSendNotice(request) {
  const undelivered = (request?.signers || []).filter((signer) => (
    signer.invitation_delivery_status
    && !['sent', 'not_required'].includes(signer.invitation_delivery_status)
    // A signer who already acted is not waiting on an invitation.
    && !['signed', 'declined'].includes(signer.status)
  ))
  if (!undelivered.length) return { text: SENT_NOTICE, delivered: true }
  const reasons = [...new Set(undelivered.map((signer) => (
    EMAIL_DELIVERY_REASONS[signer.invitation_delivery_status]
    || String(signer.invitation_delivery_status).replace(/_/g, ' ')
  )))]
  const recipients = undelivered.map((signer) => signer.email).filter(Boolean).join(', ')
  return {
    text: `Signature request created, but the email invitation${recipients ? ` to ${recipients}` : ''} was not delivered — ${reasons.join('; ')}. The request is waiting in the signer's client portal; fix email delivery and use Resend, or tell the signer directly.`,
    delivered: false,
  }
}

export const EMPTY_SIGNING_FIELDS = Object.freeze([])

// Every signer needs their own role: signing fields are bound to a role, and
// the request is rejected when two signers claim the same one. A new row
// takes the first role nobody has taken.
export const freeSignerRole = (signers) => {
  const taken = new Set(signers.map((signer) => signer.role))
  const free = SIGNER_ROLE_OPTIONS.find((option) => !taken.has(option.value))
  return free ? free.value : 'signer'
}

export const duplicateSignerRoles = (signers) => [...new Set(
  signers.map((signer) => signer.role).filter((role) => signers.filter((other) => other.role === role).length > 1),
)]

// The roles the request has to cover: those the document requires, those its
// placed fields already use, and those the signers claim.
export const placementRolesFor = ({ requiredRoles = [], fields = [], signers = [] }) => [...new Set([
  ...requiredRoles,
  ...fields.map((field) => field.role),
  ...signers.map((signer) => signer.role).filter(Boolean),
])]

// A template can declare a role the options above do not list (a Word
// template's "landlord"); it is offered as itself rather than dropped.
export const roleOptionsFor = (placementRoles) => [
  ...SIGNER_ROLE_OPTIONS,
  ...placementRoles
    .filter((role) => !SIGNER_ROLE_OPTIONS.some((option) => option.value === role))
    .map((role) => ({ value: role, label: role })),
]

export const prepareSigners = (signers) => signers.map((signer, index) => ({
  name: signer.name.trim(),
  email: signer.email.trim(),
  role: signer.role || 'signer',
  sign_order: index,
}))

export const parseReminderDays = (text) => String(text || '')
  .split(/[\s,]+/)
  .map((value) => Number.parseInt(value, 10))
  .filter((value) => Number.isInteger(value) && value > 0)

// The first reason the request cannot be created, or null. Order matters: the
// document first, then the people, then whether the two line up.
export function signatureRequestProblem({ document, preparedSigners, positionedFields, requiredRoles, placementBlockMessage }) {
  if (!document?.id) return 'Choose a document to send for signature.'
  if (preparedSigners.some((signer) => !signer.name || !signer.email)) return 'Each signer needs a name and email.'
  if (document.signing_placement_required && !positionedFields.length) return placementBlockMessage(document)
  if (requiredRoles.some((role) => !positionedFields.some((field) => field.role === role))) return 'Add signing fields for every role required by this document.'
  if (positionedFields.some((field) => preparedSigners.filter((signer) => signer.role === field.role).length !== 1)) return 'Assign exactly one signer to each role used by a signing field.'
  return null
}

export function buildSignatureRequestPayload({ documentId, preparedSigners, positionedFields, dueOn, expiresOn, reminderDays, enforceSigningOrder }) {
  return {
    document_id: documentId,
    signers: preparedSigners,
    // The portal is the only signing provider; the server detects signature
    // lines itself when none were placed here.
    provider: 'internal',
    // Generated-PDF placement metadata is attached by the final-PDF
    // generation flow. Never derive this from a DOCX preview here.
    positioned_fields: positionedFields,
    // 5pm, matching the deadline wording a client is given at intake.
    due_at: dueOn ? new Date(`${dueOn}T17:00:00`).toISOString() : null,
    expires_at: expiresOn ? new Date(`${expiresOn}T23:59:59`).toISOString() : null,
    reminder_days: parseReminderDays(reminderDays),
    enforce_signing_order: enforceSigningOrder,
  }
}
