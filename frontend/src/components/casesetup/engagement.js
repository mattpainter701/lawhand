// Shared model for recording an existing engagement.
//
// A client who arrives with live matters has usually already signed a fee
// agreement, and a few legacy arrangements have none. The new-matter form and
// the matter's paperwork card both offer the same three answers; these helpers
// keep them describing the record the same way and building the same request.

export const ENGAGEMENT_CHOICES = [
  {
    value: 'signed_on_file',
    label: 'Upload the signed fee agreement',
    description: 'The signed copy is filed on the matter. Nothing is sent to the client.',
  },
  {
    value: 'signed_no_copy',
    label: 'Signed, no copy on hand',
    description: 'Record where and when it was signed. Add the copy later if it turns up.',
  },
  {
    value: 'no_agreement',
    label: 'No fee agreement',
    description: 'A legacy or unusual arrangement. Record the reason so it stays visible.',
  },
]

export const ENGAGEMENT_STATUS_LABELS = {
  signed_on_file: 'Fee agreement on file',
  signed_no_copy: 'Signed, no copy on hand',
  no_agreement: 'No fee agreement',
  pending_copy: 'Signed copy pending',
}

export const emptyEngagement = {
  status: 'signed_on_file',
  signedOn: '',
  documentId: '',
  file: null,
  note: '',
}

// What is still missing before the record can be sent, or '' when complete.
export function engagementProblem(state) {
  if (state.status === 'signed_on_file' && !state.file && !state.documentId) {
    return 'Upload the signed fee agreement or choose it from the matter documents.'
  }
  if (state.status === 'signed_no_copy' && !state.note.trim()) {
    return 'Say where the agreement was signed.'
  }
  if (state.status === 'no_agreement' && !state.note.trim()) {
    return 'Say why this matter has no fee agreement.'
  }
  return ''
}

// The multipart body the engagement endpoint reads: an options JSON part and,
// for an uploaded signed copy, the PDF itself.
export function engagementFormData(state, { replace = false } = {}) {
  const options = {
    status: state.status,
    signed_on: state.status !== 'no_agreement' && state.signedOn ? state.signedOn : null,
    document_id: state.status === 'signed_on_file' && state.documentId ? state.documentId : null,
    note: state.note.trim() || null,
    replace,
    confirm: true,
  }
  const form = new FormData()
  form.append('options', JSON.stringify(options))
  if (state.status === 'signed_on_file' && state.file && !state.documentId) {
    form.append('agreement', state.file)
  }
  return form
}

function formatDay(value) {
  if (!value) return ''
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

// One line for a card header: the status, and the signing date when known.
export function engagementSummary(engagement) {
  if (!engagement?.status) return ''
  const label = ENGAGEMENT_STATUS_LABELS[engagement.status] || engagement.status
  const signed = engagement.signed_on ? ` · signed ${formatDay(engagement.signed_on)}` : ''
  return `${label}${signed}`
}
