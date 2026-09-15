import { describe, expect, it } from 'vitest'
import { invitationLabel, isInvitee, partitionUsers } from './invitations'

const active = { id: 'a', is_active: true, invitation_status: null }
const deactivated = { id: 'd', is_active: false, invitation_status: null }
const pending = {
  id: 'p',
  is_active: false,
  invitation_status: 'pending',
  invitation_expires_at: '2026-09-22T12:00:00Z',
}
const expired = { id: 'e', is_active: false, invitation_status: 'expired' }
const revoked = { id: 'r', is_active: false, invitation_status: 'revoked' }

describe('admin invitation helpers', () => {
  it('keeps invitees out of the inactive bucket', () => {
    const { active: on, invited, inactive } = partitionUsers([active, deactivated, pending, expired, revoked])

    expect(on.map((u) => u.id)).toEqual(['a'])
    expect(invited.map((u) => u.id)).toEqual(['p', 'e', 'r'])
    expect(inactive.map((u) => u.id)).toEqual(['d'])
  })

  it('never treats an active person as an invitee, whatever the status field says', () => {
    expect(isInvitee({ is_active: true, invitation_status: 'pending' })).toBe(false)
  })

  it('labels each invitation state in plain words', () => {
    expect(invitationLabel(pending)).toBe('Invited · link expires Sep 22')
    expect(invitationLabel({ ...pending, invitation_expires_at: null })).toBe('Invited')
    expect(invitationLabel(expired)).toBe('Invitation expired')
    expect(invitationLabel(revoked)).toBe('Invitation revoked')
    expect(invitationLabel(deactivated)).toBeNull()
  })
})
