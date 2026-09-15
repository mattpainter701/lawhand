import { format } from 'date-fns'

// An invited person is inactive until they accept, yet they are not a
// deactivated colleague: they come in through a new link, never a toggle.
export const isInvitee = (user) => user?.is_active === false && Boolean(user?.invitation_status)

// Split the admin user list so invitees show in the everyday view instead of
// being hidden under "Show inactive", where a sent invitation looked lost.
export const partitionUsers = (users = []) => ({
  active: users.filter((user) => user.is_active !== false),
  invited: users.filter((user) => isInvitee(user)),
  inactive: users.filter((user) => user.is_active === false && !isInvitee(user)),
})

export const invitationLabel = (user) => {
  if (!isInvitee(user)) return null
  if (user.invitation_status === 'pending') {
    return user.invitation_expires_at
      ? `Invited · link expires ${format(new Date(user.invitation_expires_at), 'MMM d')}`
      : 'Invited'
  }
  return user.invitation_status === 'expired' ? 'Invitation expired' : 'Invitation revoked'
}
