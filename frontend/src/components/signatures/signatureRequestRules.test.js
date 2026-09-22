import { describe, expect, it } from 'vitest'
import {
  buildSignatureRequestPayload, duplicateSignerRoles, freeSignerRole, parseReminderDays, placementRolesFor,
  prepareSigners, roleOptionsFor, signatureRequestProblem, signatureSendNotice,
} from './signatureRequestRules'
import { initialSignersForMatter } from './signerPrefill'

const block = () => 'Review signing positions first.'

describe('signature request rules', () => {
  it('refuses the request in the order staff can fix it', () => {
    const signers = prepareSigners([{ name: ' Ada ', email: 'ada@example.test ', role: 'client' }])
    expect(signers).toEqual([{ name: 'Ada', email: 'ada@example.test', role: 'client', sign_order: 0 }])
    expect(signatureRequestProblem({ document: null, preparedSigners: signers, positionedFields: [], requiredRoles: [], placementBlockMessage: block })).toBe('Choose a document to send for signature.')
    const document = { id: 'd', signing_placement_required: true }
    expect(signatureRequestProblem({ document, preparedSigners: [{ name: '', email: 'x', role: 'client' }], positionedFields: [], requiredRoles: [], placementBlockMessage: block })).toBe('Each signer needs a name and email.')
    expect(signatureRequestProblem({ document, preparedSigners: signers, positionedFields: [], requiredRoles: [], placementBlockMessage: block })).toBe('Review signing positions first.')
    const fields = [{ field_id: 'f', role: 'client' }]
    expect(signatureRequestProblem({ document, preparedSigners: signers, positionedFields: fields, requiredRoles: ['client', 'attorney'], placementBlockMessage: block })).toBe('Add signing fields for every role required by this document.')
    expect(signatureRequestProblem({ document, preparedSigners: [...signers, { ...signers[0], sign_order: 1 }], positionedFields: fields, requiredRoles: ['client'], placementBlockMessage: block })).toBe('Assign exactly one signer to each role used by a signing field.')
    expect(signatureRequestProblem({ document, preparedSigners: signers, positionedFields: fields, requiredRoles: ['client'], placementBlockMessage: block })).toBeNull()
  })

  it('builds the portal request with the dates the client is told', () => {
    const payload = buildSignatureRequestPayload({
      documentId: 'd', preparedSigners: [], positionedFields: [], dueOn: '2026-10-02', expiresOn: '', reminderDays: '7, 1 x 0', enforceSigningOrder: false,
    })
    expect(payload.provider).toBe('internal')
    expect(payload.due_at).toBe(new Date('2026-10-02T17:00:00').toISOString())
    expect(payload.expires_at).toBeNull()
    expect(payload.reminder_days).toEqual([7, 1])
    expect(parseReminderDays('')).toEqual([])
  })

  it('keeps roles distinct and offers a template role the list does not know', () => {
    expect(freeSignerRole([{ role: 'client' }, { role: 'co_client' }])).toBe('attorney_countersigner')
    expect(duplicateSignerRoles([{ role: 'client' }, { role: 'client' }, { role: 'witness' }])).toEqual(['client'])
    const roles = placementRolesFor({ requiredRoles: ['landlord'], fields: [{ role: 'client' }], signers: [{ role: 'witness' }] })
    expect(roles).toEqual(['landlord', 'client', 'witness'])
    expect(roleOptionsFor(roles).map((option) => option.value)).toContain('landlord')
  })

  it('reports an undelivered invitation by signer and reason', () => {
    expect(signatureSendNotice({ signers: [{ email: 'a@x', invitation_delivery_status: 'sent' }] }).delivered).toBe(true)
    const outcome = signatureSendNotice({ signers: [{ email: 'a@x', invitation_delivery_status: 'disabled', status: 'pending' }] })
    expect(outcome.delivered).toBe(false)
    expect(outcome.text).toContain('a@x')
    expect(outcome.text).toContain('outbound email is turned off')
  })
})

describe('signer prefill', () => {
  it('names the client from the matter and leaves other roles to be filled', () => {
    const rows = initialSignersForMatter({ client_name: 'Ada Smith', client_email: 'ada@example.test' }, ['attorney', 'client'])
    expect(rows).toEqual([
      { name: 'Ada Smith', email: 'ada@example.test', role: 'client' },
      { name: '', email: '', role: 'attorney' },
    ])
  })

  it('starts with one client row when the document names no role', () => {
    expect(initialSignersForMatter(null, [])).toEqual([{ name: '', email: '', role: 'client' }])
    expect(initialSignersForMatter({ client_name: 'Ada' }, ['witness'])).toEqual([{ name: '', email: '', role: 'witness' }])
  })
})
