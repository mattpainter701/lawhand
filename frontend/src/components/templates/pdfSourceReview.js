/**
 * Which scanned fields a person still has to check against the original.
 *
 * Mirrors `backend/app/services/pdf_source_review.py` field for field. It has
 * to: the server refuses to publish a template whose uncertain fields nobody
 * confirmed, so an editor working from a different rule would tell a firm
 * there is nothing to review and then watch publish refuse them.
 *
 * Deliberately *not* the same as the editors' "N need review" count, which
 * also counts AI proposals. That one is an authoring prompt — look at this.
 * This one is a publish gate — a person attested to this.
 */

/** Below this the scan is not confident enough to publish unconfirmed. */
export const CONFIDENCE_FLOOR = 0.75

const OCR = 'ocr'

const overlaysOf = (field) => {
  const overlays = field?.pdf_overlays
  if (Array.isArray(overlays) && overlays.length) return overlays.filter(Boolean)
  return field?.pdf_overlay ? [field.pdf_overlay] : []
}

/**
 * Whether a person has to check this one field against the original.
 *
 * Every field a PDF scan produces is born `review_required`, including an
 * AcroForm field read with full confidence — the flag means "nobody has looked
 * at this yet", not "the scan struggled". So on a freshly uploaded form this is
 * true of everything, which is the correct answer: nobody has.
 */
export const fieldNeedsReview = (field) => {
  if (field?.review_required === true) return true
  if (field?.confidence != null) {
    const confidence = Number(field.confidence)
    // An unreadable confidence is not a confident one.
    if (!Number.isFinite(confidence) || confidence < CONFIDENCE_FLOOR) return true
  }
  return overlaysOf(field).some((overlay) => overlay?.source_kind === OCR)
}

/**
 * The included fields a person must confirm before this template can publish.
 *
 * A scan whose detection method was OCR is uncertain as a whole, not only
 * where it happened to score a field low, so every field on one counts.
 */
export function fieldsNeedingReview(fields = [], variableSchema = null) {
  const included = fields.filter((field) => field?.included !== false)
  const method = String(variableSchema?.detection?.method || '').toLowerCase()
  if (method.includes(OCR)) return included
  return included.filter(fieldNeedsReview)
}
