# MCP audit and review — 2026-09-19

Audit of both LawHand MCP products against the workflows operators asked for:
manage firm/matters from an external assistant (fetch a template, fill its
fields, submit the finished/reviewed document to a matter, update tasks), and
bill Research MCP RAG queries at a defined rate.

Method: read the live Workspace and Research capability registries, their
adapters, handlers, schemas, task-automation executors, metering service, and
the tests that pin those contracts. Findings are split into implemented,
release-gated, and recommended. Every claim names the symbol or file that owns
it. Fixes that shipped with this review are listed in section 6; the rest are
backlog, not implied commitments.

## 1. Products, at a glance

| Product | Endpoint | Identity | Tools | State |
| --- | --- | --- | --- | --- |
| Workspace MCP | `/api/mcp/workspace` | User OAuth grant + live RBAC | 28 (`app/services/automation_capabilities.py`) | Implemented, tenant/per-user gated |
| Research MCP | `/api/mcp` | `lhrk_` product key or Research OAuth | 19 public tools (`app/services/mcp_product.py`) | Implementation complete, `MCP_PRODUCT_ENABLED` defaults **off** |

The two share retrieval/capability internals in places but not public identity,
authorization, billing, or release state. This is the documented boundary in
`docs/mcp/README.md` and is correct.

## 2. Workspace MCP coverage versus the requested workflow

`CAPABILITY_SPECS` exposes exactly two effects: `read` and `propose`. Proposals
land in the board's **Review** column and a deterministic worker in
`app/services/task_automation.py` executes them only after a human approves.
There is no `execute` effect. The coverage below is judged against that model.

| Requested ability | Verdict | Evidence |
| --- | --- | --- |
| List/fetch firm templates for a matter | Covered | `list_document_templates` (`matter_workspace_capabilities.py`) |
| Read a template's field schema | Covered | `get_document_template_text` returns `variable_names` + `variable_schema` |
| Fill fields and produce a document | Covered (DOCX/Markdown) | `propose_document_from_template` → `render_workspace_template` |
| Submit the completed document to a matter | Covered as reviewed work | Same tool writes the cloud DOCX and opens a staff→attorney Review task; final approval/filing stays human |
| Read/list matters | Covered | `search_matters`, `find_matter`, `get_matter_context` |
| Create/update matters | **Missing** | No capability spec; REST-only `routers/matters.py` |
| Read/list tasks | Covered | `search_tasks`, `get_task`, `list_matter_tasks` |
| Create tasks | Covered (proposal) | `propose_task` creates a Review task |
| Update/assign/status tasks | **Added in this review** | `propose_task_update` (section 6) |
| Attach a document/artifact | Covered (proposals) | `propose_matter_document`, `propose_matter_document_file`, `propose_matter_file` |
| Approve / file / deliver | Intentionally absent | `workspace_mcp_protocol.py` docstring and `docs/workspace_mcp_adapter.md` |

The template leg of the requested workflow is complete end to end within the
review-first model. The genuine gap was task mutation; matters remain
read-only by MCP.

## 3. Workspace MCP gaps and follow-ups

1. **Matter create/update are not MCP tools.** A power user cannot open a
   matter, change its status, or edit its posture from an assistant. Adding a
   `propose_matter`/`propose_matter_update` pair would fit the existing model,
   but matter creation carries conflict-check, numbering, and engagement
   side-effects that need their own review; recommend a separate design PR.
2. **Template publication is REST-only.** `propose_document_template` can
   only save an **inactive draft**; activation remains a human Template Studio
   action. This is deliberate and should stay.
3. **PDF templates fail closed** in `render_workspace_template` until exact
   visual preview can bind the fields, so only DOCX/Markdown render from MCP.
4. **No in-product "connect an assistant" surface.** The grant panel lists
   and revokes grants but shows no server URL or client config. Onboarding is
   effectively "someone emails you the URL". (Also raised in
   `docs/reviews/MCP_POWER_USER_REVIEW.md`; still open.)
5. **Privacy Mode silently disables MCP.** `_load_workspace_actor` returns a
   bare 403 when `user.privacy_mode` is set, with nothing next to the toggle
   explaining it.
6. **Hard size caps are machine-visible but terse.** `propose_matter_document`
   body is capped at 50,000 characters and `source_ids` at 10. The generated
   `inputSchema` publishes both, but the prose description did not, and the
   rejection was a generic "invalid body". Fixed in this review.

## 4. Pushing work authored outside LawHand

`propose_matter_document` rendered assistant text with
`cloud_artifact_materialization.render_revision_docx`, which emitted one bare
`add_paragraph` per line. Every external client emits Markdown, so headings
arrived as literal `##`, emphasis as literal `**`, lists lost their numbering,
and blank lines became real empty paragraphs. The workflow's whole value — a
draft produced elsewhere arriving ready for review — was being discarded at the
last step. Fixed in this review.

## 5. Research MCP: RAG query and usage metering

### 5.1 Query path (validated)

1. `/api/mcp` or `/api/mcp/tools/call` authenticates the product key/OAuth via
   `services/mcp_protocol.py` and `routers/mcp.py`.
2. The backend proxies to the private sidecar with its service credential;
   customer keys are never forwarded (`_proxy_post`).
3. The sidecar (`mcp-server/mcp_server/server.py`) embeds the query with
   `mixedbread-ai/mxbai-embed-large-v1`, version 1, dimension 1024
   (`query_embeddings.py`), then `repository.search_caselaw` /
   `search_legal_authorities`.
4. Hybrid search runs dense top-K plus `ts_rank_cd` keyword top-K fused by
   weighted reciprocal-rank (`0.6 dense / 0.4 fts`).
5. Vector search is gated on the promoted `authority_corpus_versions`
   embedding model/version/dimension (`_embedding_matches_promoted`). A
   mismatch or an embedding outage degrades to keyword-only search and labels
   `search_source`, rather than returning padded or wrong-space vectors.

This path answers the "can we accurately query the RAG data" question: yes,
with the caveats already documented — coverage/source admission are fail-closed
and no good-law/currentness claim is implied.

### 5.2 What is billed (validated)

- Unit: **one `MCPUsageEvent` per successful external tool call**, written by
  `record_mcp_usage` after the upstream call succeeds.
- Rate: `MCP_PRODUCT_CALL_PRICE_CENTS` (default **45¢**), snapshot to each
  product key's `unit_price_cents`; `monthly_key_usage` computes
  `successful_calls × unit_price`.
- Entitlement, quota, budget, and burst checks run **before** retrieval
  (`enforce_product_key_quota` takes a transaction advisory lock).
- Billing is emitted as a durable, idempotent `mcp_stripe_meter` job keyed on
  the usage-event id, so a job retry cannot double-charge.
- Failed calls are recorded as evidence but never billed (`status_code >= 400`).

### 5.3 Metering issues found

1. **Billed and unbilled calls were blended.** Internal chat records the same
   corpus reads (`record_internal_chat_mcp_usage`) with no key/grant, so they
   are never invoiced — but `usage_summary().total_calls` counted them
   together with billable calls. Fixed in this review: the summary now reports
   `billable_calls`, `unbilled_calls`, `failed_calls`, and a per-`auth_type`
   breakdown alongside the total.
2. **No request-level idempotency.** A client that retries a timed-out
   `tools/call` creates a new usage event and therefore a second billable
   Stripe unit. Durable-job idempotency only protects delivery retries of one
   event. Recommended fix needs a dedupe key (product key/grant + client
   idempotency key) stored with a unique constraint — a migration, so it is
   deliberately out of scope here.
3. **Meter-after-work window.** Usage is written after retrieval. A crash or a
   failed usage write between proxy success and `record_mcp_usage`'s commit
   under-counts that call. The write also raises if the tenant has no
   `stripe_customer_id`. Fail-closed for billing, but an accounting gap; the
   durable outbox only covers the post-insert delivery step.
4. **OAuth usage is absent from the portal charge estimate.** `monthly_key_usage`
   filters `product_key_id IS NOT NULL`, so Research OAuth calls (which are
   billed through the same Stripe meter) do not appear in the per-key charge
   totals. Reporting gap, not a billing gap.
5. **Rate divergence risk.** `record_mcp_usage` sends the Stripe meter
   `value=1`; the invoice price is Stripe's configured meter price, while
   portal budgets/estimates use the DB snapshot. If the two drift, quoted
   estimates and actual invoices disagree.

## 6. Fixes shipped with this review

| Fix | Where | Why |
| --- | --- | --- |
| Parse assistant Markdown into styled DOCX (headings, emphasis, lists, quotes, fenced code, pipe tables; skip blank lines) | `cloud_artifact_materialization.render_revision_docx` | The push workflow was destroying every draft's formatting |
| Actionable length-argument errors naming the submitted size and the limit | `automation_capabilities.CapabilitySpec.parse_arguments` + `_argument_error_detail` | Model retried blindly on a generic schema rejection |
| Name the body/source limits in tool descriptions | `propose_matter_document`, `propose_client_email` specs | Let the model plan around the caps |
| Split billable from unbilled RAG usage in the summary | `mcp_product._summarize_usage_rows` / `usage_summary` | Tenant totals could not be reconciled to the Stripe meter |
| Review-gated `propose_task_update` (status/priority/due date/assignee/note) | `automation_capabilities`, `schemas/workspace_mcp`, `chat_tools/handlers.propose_task_update`, `task_automation._run_task_update` | The requested "work/update tasks" ability, without adding a raw write |

`propose_task_update` keeps the architectural boundary: the assistant stages a
Review task carrying a `TaskUpdateAction`; the deterministic worker applies the
change only after approval, re-validating tenant, matter, and assignee, and it
requires a reason when moving a task to Waiting or cancelling it. It is
Workspace-only and requires the existing `matters:read` + `tasks:propose`
scopes and `manage_matters` RBAC.

## 7. Remaining backlog

- Matter create/update proposals (separate design + security review).
- Request-level idempotency for billable Research calls (schema migration).
- Meter-before-work reservation or an outbox write in the same transaction.
- Include OAuth usage in the portal charge estimate.
- In-product connection instructions and a Privacy-Mode/blocked-state banner.
- Catalog drift check: generate the tool table from `capability_catalog` and
  compare in CI (currently hand-maintained in `docs/workspace_mcp_adapter.md`).
- Raise or chunk the 50,000-character push ceiling for long briefs/discovery
  sets; revisit the 10-source citation cap.

## 8. Release state

Workspace MCP changes are implemented and subject to the normal release and
tenant gates; they add no public exposure. Research MCP remains release-gated
behind `MCP_PRODUCT_ENABLED` (default off); no production corpus, coverage, or
billing claim is made by this review.
