# Staff invitations and sign-in refusals

How a new person joins an existing firm, what an administrator controls, and how
Google/Microsoft sign-in explains a refusal. Public signup is separate and stays
off (`PUBLIC_SIGNUP_ENABLED=false`); brand-new firms are still provisioned by an
operator.

## How a person joins

1. A firm administrator invites an email address from **Admin → Users → Invite
   user**. LawHand creates the person as an inactive user with **no credential**
   and emails a link to `/accept-invite?token=…`.
2. The accept page names the firm and a masked address (`j•••@firm.com`). The
   person either:
   - chooses a password (12–128 characters, common passwords refused), or
   - continues with Google or Microsoft. The provider account must report the
     address the invitation was sent to: Google's verified email, or Microsoft's
     `email`/`preferred_username`.
3. Acceptance activates the account and signs the person in.

An invitation link works **once** and expires after **7 days**.

## What an administrator sees and can do

The Users list shows invited people in the everyday view, not under
**Show inactive**, with one of:

| State | Meaning | Actions |
|---|---|---|
| Invited · link expires … | Open, unused link | Resend invite, Revoke |
| Invitation expired | Link is past its 7 days | Resend invite, Revoke |
| Invitation revoked | Every link was revoked; never accepted | Resend invite |

- **Resend** issues a new link and invalidates the previous one.
- **Revoke** makes the link stop working immediately.
- **Deactivating** an invited person also revokes their link.
- **Reactivate is refused (409)** for someone who never accepted. Before this
  change it activated an account with no credential of its own, which Google
  verified-email matching would then sign in. Resend the invitation instead.

## Security model

- Only the sha256 of the token is stored (`user_invitations.token_hash`). The
  raw token exists in the email and the person's browser only; the accept page
  removes it from the address bar after reading it.
- The token is how the firm is discovered, so lookup runs before any tenant
  context. Migration `192_user_invitations` adds a SELECT-only RLS policy that
  matches exactly one presented hash (`app.invite_token_hash`); the invitation's
  own tenant is bound before anything else is read or written. There is no use
  of `app.rls_bypass` on this table. `test_user_invitations_rls.py` proves this
  under the NOSUPERUSER/NOBYPASSRLS runtime role.
- Acceptance is claimed with a conditional update
  (`WHERE accepted_at IS NULL AND revoked_at IS NULL AND expires_at > now()`),
  so two concurrent requests with the same link cannot both succeed.
- Provider linking needs **both** the valid token **and** the invited address,
  so a forwarded link cannot bind someone else's account. The provider identity
  must not already belong to another user in any firm. Every check runs before
  the invitation is claimed, so a wrong-account attempt leaves the link usable.
- **Without an invitation nothing changes**: Microsoft sign-in still never links
  an account by email; Google still matches only existing users.
- Password reset never activates anyone. `forgot-password` sends nothing (same
  generic response) for invited or inactive accounts, and `reset-password`
  refuses them before any change.

## Sign-in refusals

Google and Microsoft sign-in are full-page navigations, so a JSON error body is
exactly what a person would see. The four browser routes
(`/api/auth/{google,microsoft}/{login,callback}`) now redirect expected
refusals to `/login?error=<code>`, and the login page shows plain wording for
the code. Codes are allowlisted; anything else becomes `oauth_failed`. Server
errors (5xx) are not converted and still reach error logging. Only the code is
logged, never the address.

| Code | When |
|---|---|
| `not_invited` | A firm exists for the domain but this address has no user |
| `microsoft_not_linked` | The Microsoft account is not linked to any user |
| `account_inactive` | The matched user is inactive |
| `tenant_inactive` | The firm is inactive or its access has expired |
| `signup_disabled` | Self-serve signup was requested while it is off |
| `identity_conflict` | The identity matches more than one account |
| `identity_already_linked` | Invitation acceptance with an identity another user holds |
| `invite_email_mismatch` | Invitation acceptance with a different account |
| `invite_invalid` / `invite_expired` / `invite_accepted` | Invitation link problems |
| `google_email_unverified` | Google has not verified the address |
| `provider_unavailable` | The provider is not configured |
| `oauth_state_expired` | The sign-in took too long or was replayed |
| `oauth_failed` | Any other client-side failure |

JSON endpoints (`/api/auth/register`, `/api/auth/signup/plan`,
`/api/auth/oauth/exchange`, `/api/auth/office/exchange`) keep their JSON
responses with the same status and detail as before.

## Operator notes

- **Legacy links.** Invitations created before migration 192 stored
  `invite:<token>` in `users.password_hash`. The migration backfills a hashed,
  7-day invitation for each such inactive user, and old
  `/reset-password?token=…&invite=1` links redirect to the accept page. Their
  7 days start at deploy. `users.password_hash` is left as is; a later contract
  migration clears the `invite:` placeholders once this has run for a week.
- **Grants.** The table is created by the migrator role and reaches the
  `clarity_app` runtime role through the default privileges in
  `scripts/init_clarity_app_role.sh`, like every other migrated table.
- **Downgrade** of 192 drops `user_invitations`. Invitations issued after
  upgrade are lost and those users stay inactive until re-invited.
