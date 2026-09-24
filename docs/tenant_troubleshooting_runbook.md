# Tenant Troubleshooting Runbook

How to investigate one tenant's problem without borrowing their login.

Every route here requires the `platform:debug` scope. See
[credential_security_operations.md](credential_security_operations.md) for how
to obtain a credential that carries it. Every call is written to
`operator_audit_logs` and is readable back via `GET /api/platform/audit`.

Set up a session first:

```bash
HOST=https://getlawhand.com
TOKEN=$(curl -sX POST "$HOST/api/platform/auth/token" \
  -H "X-Platform-Key: $PLATFORM_BOOTSTRAP_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"scopes":["platform:read","platform:debug"]}' | jq -r .access_token)
auth=(-H "Authorization: Bearer $TOKEN")
```

## 1. The customer sent you an error id

Every 5xx response body carries `error_id` and `request_id`, and the
`X-Request-ID` header repeats the latter. Either one is enough to start.

```bash
curl -s "${auth[@]}" "$HOST/api/platform/logs/$ERROR_ID" | jq
```

Returns the full record including `stack_trace`, `request_id`,
`conversation_id`, `query_text`, `ip_address` and `user_agent`. Pass
`?tenant_id=…` when you already know the tenant — it skips the scan and
answers immediately.

`query_text` is null unless `GATEWAY_RAW_TEXT_RETENTION_ENABLED` was on when
the error was captured. That is expected, not a bug.

## 2. The customer sent you a request id

```bash
curl -s "${auth[@]}" "$HOST/api/platform/trace/$REQUEST_ID" | jq
```

Assembles everything recorded about that one request: the error rows and the
access-log rows, ordered by time, across whichever tenant they belong to.

Access-log rows only carry `request_id` from migration
`108_access_log_request_correlation` onward. Older rows return under the error
half of the response but not the access half.

## 3. "Something is wrong with this tenant"

```bash
curl -s "${auth[@]}" "$HOST/api/platform/tenants/$TENANT_ID/diagnostics?hours=24" | jq
```

One call, and the fields map to the usual causes:

| Field | What it tells you |
|---|---|
| `error_rate`, `requests` | Whether the tenant is failing broadly or not at all |
| `top_failing_endpoints` | Which feature is broken |
| `errors_by_severity`, `unresolved_errors` | Severity and whether anyone has triaged it |
| `failed_sync_runs` | Integration breakage — `invalid_grant` here means re-consent |
| `stuck_jobs` | Background work not completing; a hung feature to the user |
| `last_activity_at`, `active_users` | Whether anyone is actually using it |
| `is_active`, `billing_tier` | Whether the account is entitled to what they are trying |

`stuck_jobs` deliberately includes `pending`/`running` rows untouched for 15
minutes, not just `failed` — work that keeps retrying looks identical to a hang
from the user's side.

## 4. You only have an email address

```bash
curl -s "${auth[@]}" "$HOST/api/platform/users?email=someone@firm.com" | jq
```

Substring match, case-insensitive, across all tenants. Use it to get the
`tenant_id` that every other route wants.

## 5. Record what you found

```bash
curl -sX PATCH "${auth[@]}" -H 'Content-Type: application/json' \
  "$HOST/api/platform/logs/$ERROR_ID/resolve" \
  -d '{"is_resolved":true,"resolution_notes":"Upstream gateway restarted"}'
```

Without this the same error resurfaces in every triage pass, because tenant
admins are the only other party who can close one out.

## 6. Review what operators did

```bash
curl -s "${auth[@]}" "$HOST/api/platform/audit?days=7&actor_id=ops@example.com" | jq
```

Filters: `action`, `actor_id`, `resource_id`, `days`. This is also the answer to
"what did we touch in this tenant, and when".

## Retention

Both tables these routes read are pruned nightly by the `log-retention`
scheduler job: `error_logs` after `ERROR_LOG_RETENTION_DAYS` (default 90) and
`api_access_logs` after `API_ACCESS_LOG_RETENTION_DAYS` (default 30). So an
error id from four months ago returns 404, and a trace older than a month
returns its error half with no access half — that is retention, not a lost
record. Widen the window on the host before an investigation that needs to
reach further back, or set it to `0` to retain that table indefinitely under a
litigation hold. The sweep is age-based only: resolving an error does not
shorten its life, and leaving one unresolved does not extend it.

## 7. Retire an unused trial so its address can re-onboard

An abandoned or test trial keeps its login address registered, so the same
person cannot start a fresh onboarding with it. Revoke releases the address
without deleting the tenant:

```bash
curl -sX POST "${auth[@]}" -H 'Content-Type: application/json' \
  "$HOST/api/platform/tenants/$TENANT_ID/revoke" \
  -d '{"confirm_email":"owner@firm.com","reason":"abandoned test trial"}' | jq
```

`confirm_email` must name a login in that tenant; it is the confirmation token
that stops a stale console from revoking the wrong firm.

What it does:

- deactivates every human login and moves each address to a non-deliverable
  tombstone (`revoked+<user-id>@revoked.invalid`) so the original can register
  again;
- removes the stored Google / Microsoft credential so the old grant cannot be
  replayed;
- marks the tenant inactive and clears the trial marker; and
- records a `trial.revoked` operator audit entry.

What it deliberately does **not** do: delete the tenant, its append-only
agreement evidence, or any connected Drive/OneDrive content. Revocation is
refused with `409` when the tenant holds work product (matters, documents,
billing, imports, and similar), so it can only reach a genuinely unused trial.
Hard deletion of an expired disposable **demo** is a different operation and
belongs to the demo workspace panel.

## Repair Microsoft sign-in links after an Entra app registration change

A new Microsoft app registration changes the pairwise `sub` claim. Existing
LawHand users without saved Entra `tid` and `oid` then get
`microsoft_not_linked`, even though they still appear in the tenant roster.
The `/api/auth/me` and `/api/auth/refresh` 401s follow from the failed login.

For the Bismarck Law incident, target LawHand tenant
`9ff4a695-826c-422c-bb7f-6037495a2c4e`. Obtain the **Microsoft Entra
directory (tenant) ID** independently from Entra admin center. It is different
from the LawHand tenant ID. Run this from `backend` on the production host with
application database configuration. First review the dry-run mapping:

```bash
python -m scripts.repair_microsoft_entra_links \
  --tenant-id 9ff4a695-826c-422c-bb7f-6037495a2c4e \
  --entra-tenant-id "$BISMARCK_ENTRA_TENANT_ID" > /secure/bismarck-link-plan.json
```

The script uses the tenant's stored Microsoft Graph connection and checks its
token's `tid` against the supplied Entra directory ID. Graph validates that
access token. If the old app's refresh token is unusable, use a trusted export
from **that Entra directory** instead. The JSON format is
`{"entra_tenant_id":"<directory UUID>","users":[{"id":"<object UUID>","mail":"services@bismarcklaw.com","userPrincipalName":"services@bismarcklaw.com","accountEnabled":true,"userType":"Member"}]}`;
include the complete paginated `/users` result with those fields. Keep the
export in a restricted location and remove it after the repair.

```bash
python -m scripts.repair_microsoft_entra_links \
  --tenant-id 9ff4a695-826c-422c-bb7f-6037495a2c4e \
  --entra-tenant-id "$BISMARCK_ENTRA_TENANT_ID" \
  --graph-export /secure/bismarck-entra-users.json > /secure/bismarck-link-plan.json
```

Check that `services@bismarcklaw.com` and the expected staff appear under
`links` or `already_linked`. Inspect every mapping and all `skipped` rows.
The script only links active, human LawHand users at the tenant's domain to
enabled, non-guest Entra users with a unique exact `mail` or UPN match. It
refuses conflicting existing links or ambiguous identities. Users with other
email domains, such as guest addresses and `.onmicrosoft.com` accounts, need
separate review. It never changes LawHand roles, seats, or existing subjects.

Apply the reviewed mapping by repeating the same command and adding
`--confirm-plan-sha256 <plan_sha256 from dry run>`. A changed mapping fails
instead of applying. Re-run a dry run after applying: repaired users should
appear under `already_linked`. On their next Microsoft sign-in, the callback
matches `(tid, oid)` and records the new pairwise `sub`; future successful
sign-ins keep the stable IDs. The script may refresh the stored Graph token
during a dry run, but never writes user links without the digest.

## Performance note

Postgres RLS stays on for operator reads: the registry is enumerated and each
tenant's scope entered one at a time, rather than granting a cross-tenant
bypass. Lookups by id stop at the first match, but an unfiltered scan costs one
query per tenant. Pass `tenant_id` whenever you know it.
