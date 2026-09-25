import { describe, expect, it } from 'vitest'
import { alsoFills, memberDocumentFields, memberFieldMarker, memberMissingCount, memberValues, nextRequiredStop, packetRequiredWalk, questionsByField } from './packetFill'

const LETTER = 'letter'
const NOTICE = 'notice'
const questions = [
  { key: 'client.full_name', label: 'Client name', value_kind: 'text', required: true, appears_in: [
    { template_id: LETTER, template_title: 'Engagement letter', field_name: 'client_name' },
    { template_id: NOTICE, template_title: 'Notice', field_name: 'CLIENT' },
  ] },
  { key: `manual:${LETTER}:fee`, label: 'Fee', value_kind: 'text', required: true, appears_in: [{ template_id: LETTER, template_title: 'Engagement letter', field_name: 'fee' }] },
  { key: `manual:${NOTICE}:venue`, label: 'Venue', value_kind: 'choice', options: ['Court', 'Remote'], required: true, appears_in: [{ template_id: NOTICE, template_title: 'Notice', field_name: 'venue' }] },
  { key: `manual:${NOTICE}:note`, label: 'Note', value_kind: 'text', required: false, appears_in: [{ template_id: NOTICE, template_title: 'Notice', field_name: 'note' }] },
]
const letter = {
  template_id: LETTER,
  template: { id: LETTER, format: 'pdf', variable_schema: { fields: [
    { name: 'fee', label: 'Hourly fee', page: 1, rect: [40, 500, 200, 516] },
    { name: 'client_name', label: 'Client', page: 1, rect: [40, 700, 200, 716] },
    { name: 'client_again', value_from: 'client_name', page: 2, rect: [40, 700, 200, 716] },
    { name: 'sig', field_type: 'signature', signer_role: 'client', page: 2, rect: [40, 100, 200, 130] },
    { name: 'off', included: false },
  ] } },
}
const notice = { template_id: NOTICE, template: { id: NOTICE, format: 'markdown', body: '{{CLIENT}} at {{venue}}. {{note}}', variable_schema: { fields: [] } } }

describe('packet answer mapping', () => {
  it('maps each member field to the shared question it answers, in reading order', () => {
    expect(Object.keys(questionsByField(questions, NOTICE))).toEqual(['CLIENT', 'venue', 'note'])
    const fields = memberDocumentFields(letter, questions)
    expect(fields.map((field) => field.name)).toEqual(['client_name', 'fee', 'client_again', 'sig'])
    expect(fields[0]).toMatchObject({ question_key: 'client.full_name', label: 'Client name', required: true })
    expect(fields[1]).toMatchObject({ question_key: `manual:${LETTER}:fee`, label: 'Fee' })
    expect(fields[2].question_key).toBe('')
    const noticeFields = memberDocumentFields(notice, questions)
    expect(noticeFields.map((field) => [field.name, field.question_key])).toEqual([['CLIENT', 'client.full_name'], ['venue', `manual:${NOTICE}:venue`], ['note', `manual:${NOTICE}:note`]])
    expect(noticeFields[1]).toMatchObject({ field_type: 'choice', options: ['Court', 'Remote'] })
  })

  it('reads every member from one set of answers', () => {
    const answers = { 'client.full_name': 'Ada Lovelace', [`manual:${NOTICE}:venue`]: 'Court' }
    expect(memberValues(memberDocumentFields(letter, questions), answers)).toEqual({ client_name: 'Ada Lovelace', fee: '' })
    expect(memberValues(memberDocumentFields(notice, questions), answers)).toEqual({ CLIENT: 'Ada Lovelace', venue: 'Court', note: '' })
  })

  it('explains boxes that are not typed here', () => {
    const fields = memberDocumentFields(letter, questions)
    expect(fields.map((field) => memberFieldMarker(field, fields))).toEqual([null, null, 'Uses Client name', 'Signed later'])
    expect(memberFieldMarker({ name: 'x', field_type: 'date', signer_role: 'client' })).toBe('Dated at signing')
    expect(memberFieldMarker({ name: 'loop', question_key: '' })).toBe('Filled automatically')
  })

  it('names the other documents a shared answer fills', () => {
    expect(alsoFills(questions[0], LETTER)).toEqual(['Notice'])
    expect(alsoFills(questions[0], NOTICE)).toEqual(['Engagement letter'])
    expect(alsoFills(questions[1], LETTER)).toEqual([])
  })
})

describe('Next required across the packet', () => {
  const documents = [
    { memberId: LETTER, fields: memberDocumentFields(letter, questions) },
    { memberId: NOTICE, fields: memberDocumentFields(notice, questions) },
  ]
  const missing = new Set(['client.full_name', `manual:${LETTER}:fee`, `manual:${NOTICE}:venue`])

  it('asks a shared answer once, at the first document it appears in', () => {
    expect(packetRequiredWalk(documents, missing).map((stop) => [stop.memberId, stop.fieldName])).toEqual([[LETTER, 'client_name'], [LETTER, 'fee'], [NOTICE, 'venue']])
    expect(memberMissingCount(documents[0].fields, missing)).toBe(2)
    expect(memberMissingCount(documents[1].fields, missing)).toBe(2)
  })

  it('moves on within a document, then opens the next document at its first missing box, then wraps', () => {
    expect(nextRequiredStop(documents, missing, { memberId: LETTER, fieldName: 'client_name' })).toMatchObject({ memberId: LETTER, fieldName: 'fee' })
    expect(nextRequiredStop(documents, missing, { memberId: LETTER, fieldName: 'fee' })).toMatchObject({ memberId: NOTICE, fieldName: 'venue', key: `manual:${NOTICE}:venue` })
    expect(nextRequiredStop(documents, missing, { memberId: NOTICE, fieldName: 'venue' })).toMatchObject({ memberId: LETTER, fieldName: 'client_name' })
    // From the start of the second document, its shared box is not asked again.
    expect(nextRequiredStop(documents, missing, { memberId: NOTICE, fieldName: '' })).toMatchObject({ memberId: NOTICE, fieldName: 'venue' })
    expect(nextRequiredStop(documents, new Set(), { memberId: LETTER, fieldName: 'fee' })).toBe(null)
  })
})
