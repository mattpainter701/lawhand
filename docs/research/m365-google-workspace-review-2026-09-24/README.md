# Microsoft 365 / Google Workspace integration review — evidence (2026-09-24)

Status: **verified.** The review and roadmap are in
[`docs/m365-google-workspace-integration-review-2026-09-24.md`](../../m365-google-workspace-integration-review-2026-09-24.md).
This folder holds the evidence behind it.

| Path | Contents |
|---|---|
| `map/code-*.json` | Code maps from 9 investigators (ms-graph, google, sync, docs-templates, ai-client-leverage, addin-teams, ux-admin, ux-user, plans-ledger). Each lists capabilities, API surface, defects, opportunities and UX findings with `file:line` refs. |
| `map/research-*.json` | Web research as of September 2026 (copilot, gemini, office-suite-docs, eventing-consent, competitors). Each finding has status, licensing and sources, followed by recommended plays. |
| `defects.json`, `ux.json`, `opps.json` | Flattened inputs: 147 defects, 119 UX findings (the four with ids `shot#*` come from Playwright screenshots) and 147 opportunities. |
| `clusters-defects.json`, `clusters-ux.json` | De-duplicated clusters: 119 defect clusters (D01–D119) and 102 UX clusters (U01–U102). |
| `verified-defects.json` | Every defect cluster with its final verdict (63 confirmed, 55 partly confirmed, 1 refuted), corrected severity (19 high, 48 medium, 51 low) and each reviewer's `file:line` evidence and fix sketch. |
| `fact-check.json` | Per-claim fact-check of the research (holds, partly holds or wrong), with the current fact, sources and adjustments to each recommended play. |
| `verify/w1.json`, `w2.json`, `w3.json` | Verification batches: defects 1–18; defects 19–24 plus the high-severity impact batches and the research fact-check; UX 1–17. The defect and fact-check batches were run. The UX batch was not, so UX clusters are reported findings unless the review doc says they were fixed or checked. |

## Method

- Code maps: parallel read-only investigators, plus screenshots of each connection state rendered with a mocked API.
- Verification: one skeptical reviewer per batch of five defect clusters, told to refute each claim, plus a second privacy and security review of every high-severity cluster. The final verdict needs at least one reviewer to confirm and none to refute.
- Research: five web sweeps, then five fact-checkers who re-checked the claims the plays depend on. The network proxy blocked learn.microsoft.com, developers.google.com and some vendor sites. Those claims rest on the MicrosoftDocs GitHub sources or search snippets, and `fact-check.json` records which.
