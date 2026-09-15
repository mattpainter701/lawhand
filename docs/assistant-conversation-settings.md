# Assistant conversation settings — storage and precedence

Two settings change what an assistant answer costs and what sources it may
draw on: the response **tier** (Standard or Premium) and the **public case law**
preference. Both used to be per-message request fields with nowhere to live, so
closing and reopening a conversation reverted them to Standard with public case
law on, and a user could believe they were still in the configuration they
picked ([#487](https://github.com/mattpainter701/lawhand/issues/487)).

## Scope: per conversation

`conversations.use_premium_llm` and `conversations.include_public` (migration
`190_conversation_ai_preferences`) store what the user chose **for that
conversation**. Both carry the previous in-memory defaults as server defaults,
so every existing conversation behaves exactly as it did before the release.

| Surface | Behaviour |
| --- | --- |
| `POST /api/conversations` | Accepts `use_premium_llm` and `include_public`; the browser sends the settings currently on screen so a conversation starts where the user is. |
| `GET /api/conversations`, `GET /api/conversations/{id}` | Return both, plus `public_case_law_restricted`. |
| `PATCH /api/conversations/{id}` | Accepts either field on its own; the chat page saves a toggle the moment it changes. |
| Sending a message | Records the requested settings on the conversation, so the stored value tracks the last turn even if a `PATCH` was lost. |

A per-user default was considered and not taken: the issue is about a
conversation losing its own configuration, and a global default would still
lose a deliberate per-conversation choice.

## Precedence: firm policy narrows, never widens

The tenant Case Law setting (`TenantSettings.custom_config.include_public_case_law`,
written in the admin UI) was never read by the chat path. It now is, through the
single reader in `app/services/public_case_law_policy.py`:

1. **A stored preference is a request, not an entitlement.** Every turn resolves
   it against policy before retrieval runs.
2. **Policy can only narrow it.** A conversation that asked for public case law
   in a firm that forbids it runs without it. A conversation that asked to stay
   private stays private whatever the firm permits.
3. **The stored value is the user's own choice.** Policy narrows the request in
   flight; it does not overwrite the preference. If the firm re-enables public
   case law, the conversation returns to what its user picked.
4. **Absent or malformed configuration means allowed.** Public authority has
   been on by default since before the setting existed, and silently disabling
   retrieval on a config read error would change answers without telling anyone.

### What the UI shows

`GET /api/auth/me` returns `public_case_law_allowed`. When it is false the chat
settings popover shows the Public case law switch **off and disabled**, with
"Your firm has turned off public case law, so the assistant answers from firm
and matter sources only." The switch never displays an on state that retrieval
ignores.

### Tier is unchanged and still fails closed

A stored `use_premium_llm = true` remains a request. `reject_demo_premium`,
`_premium_for_user` (which requires `user.premium_ai_enabled`), and
`resolve_llm_route` all still apply, in that order, on every turn — and a
`PATCH` that tries to store a premium preference in a demo workspace is
rejected the same way a send is.

## Known boundary

The MCP `search_caselaw` tool (`app/routers/mcp.py`) still passes
`include_public=True` unconditionally. It is not a conversation and has no
stored preference, so it is out of this change's scope; a firm that turns public
case law off restricts the assistant, not that tool. Wiring the same policy into
the MCP surface needs its own decision about what the tool should return when
public authority is forbidden.
