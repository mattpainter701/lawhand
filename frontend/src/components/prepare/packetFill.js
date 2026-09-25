import { orderFieldsForDocument } from '../templates/FillOnDocument'
import { isSigningField } from '../templates/templateFillReview'
import { friendlyVariableLabel, getTemplateVariables } from './prepareHelpers'

// Pure helpers for filling a packet on its documents. A packet asks each
// question once; each interview question lists where it lands
// (`appears_in: [{ template_id, field_name }]`). These map a member's own
// field names to those shared question keys, so typing on any document reads
// and writes the one packet answer, and so "Next required" can walk every
// document in one pass without asking a shared answer twice.

const sameId = (a, b) => String(a) === String(b)

/** `{ fieldName: question }` for one member. */
export function questionsByField(questions, templateId) {
  const map = {}
  for (const question of questions || []) {
    for (const ref of question.appears_in || []) {
      if (sameId(ref.template_id, templateId) && ref.field_name && !map[ref.field_name]) map[ref.field_name] = question
    }
  }
  return map
}

/**
 * One member's fields in reading order, each carrying the packet question
 * it answers (`question_key`, empty when the interview does not ask it: a
 * signature, a linked field, or one resolved per repeating item).
 */
export function memberDocumentFields(member, questions) {
  const template = member?.template || {}
  const byField = questionsByField(questions, member?.template_id)
  const schema = Object.fromEntries((template.variable_schema?.fields || [])
    .filter((field) => field?.name)
    .map((field) => [field.name, field]))
  const fields = getTemplateVariables(template).map((name) => {
    const definition = schema[name] || {}
    const question = byField[name]
    return {
      ...definition,
      name,
      label: question?.label || definition.label || friendlyVariableLabel(name),
      field_type: definition.field_type || question?.value_kind || 'text',
      options: definition.options?.length ? definition.options : (question?.options || []),
      required: Boolean(question?.required),
      question_key: question?.key || '',
    }
  })
  return orderFieldsForDocument(fields)
}

/** Member field values read from the shared packet answers. */
export function memberValues(fields, answers) {
  const values = {}
  for (const field of fields) if (field.question_key) values[field.name] = answers?.[field.question_key] ?? ''
  return values
}

/** Why a box on the page is not typed here, or null when it is. */
export function memberFieldMarker(field, fields = []) {
  if (isSigningField(field)) return field.field_type === 'date' ? 'Dated at signing' : 'Signed later'
  if (field.value_from) {
    const source = fields.find((item) => item.name === field.value_from)
    return `Uses ${source?.label || field.value_from}`
  }
  if (!field.question_key) return 'Filled automatically'
  return null
}

/** The other documents one question fills, by title, from `memberId`'s point of view. */
export function alsoFills(question, memberId) {
  const titles = []
  for (const ref of question?.appears_in || []) {
    if (sameId(ref.template_id, memberId)) continue
    const title = ref.template_title || 'Another document'
    if (!titles.includes(title)) titles.push(title)
  }
  return titles
}

/** Required answers still missing in one member, counting each question once. */
export function memberMissingCount(fields, missingKeys) {
  return new Set(fields.filter((field) => field.question_key && missingKeys.has(field.question_key)).map((field) => field.question_key)).size
}

/**
 * Every missing required answer across the packet, in member order and then
 * reading order, each question listed once: at the first document it
 * appears in.
 */
export function packetRequiredWalk(documents, missingKeys) {
  const seen = new Set()
  const stops = []
  documents.forEach(({ memberId, fields }, memberIndex) => {
    fields.forEach((field, fieldIndex) => {
      const key = field.question_key
      if (!key || !missingKeys.has(key) || seen.has(key)) return
      seen.add(key)
      stops.push({ memberId, fieldName: field.name, key, memberIndex, fieldIndex })
    })
  })
  return stops
}

/**
 * The stop after the current field: later in this document, else the first
 * one in a following document, wrapping to the start of the packet.
 */
export function nextRequiredStop(documents, missingKeys, current = {}) {
  const stops = packetRequiredWalk(documents, missingKeys)
  if (!stops.length) return null
  const memberIndex = documents.findIndex((doc) => sameId(doc.memberId, current.memberId))
  const fieldIndex = memberIndex >= 0 ? documents[memberIndex].fields.findIndex((field) => field.name === current.fieldName) : -1
  return stops.find((stop) => stop.memberIndex > memberIndex || (stop.memberIndex === memberIndex && stop.fieldIndex > fieldIndex)) || stops[0]
}
