# Onboarding hotfix review — 2026-09-16

## Scope and live evidence

This review covers the first-admin onboarding wizard and the tenant-wide cloud
OAuth routes. The production test tenant is **LawHand Gmail Trial** (`getlawhand@gmail.com`),
a 30-day trial. The observed flow reached `/onboarding`, allowed the user to
defer setup, and allowed direct re-entry.

## Findings

| Area | Current behavior / evidence | Hotfix decision |
| --- | --- | --- |
| Agreement gate | `agreement_status()` reports `blocking=false` when no required counsel-owned agreement is published while enforcement is off. The wizard shows “Not published” and controlled-rollout copy, but remains usable. | Honor `TENANT_AGREEMENT_GATE_ENABLED`: when false, onboarding may proceed with acceptance not recorded; when true, new/unconnected tenants fail closed until current agreements are configured and accepted. Existing connected tenants remain usable. |
| Deferment | `/skip` marked `onboarding_completed=true` and step 5. The UI consequently rendered every prior step as complete and “Your firm is ready”, despite no integration or storage root. | Deferment keeps `onboarding_completed=false`, returns the wizard to its welcome step, and preserves core workspace access. The UI calls this “Set up later” and does not present completion evidence. |
| Re-entry | `/reenter` intentionally preserves a completed tenant’s root and completion state while reopening at Connect. | Preserve this behavior for genuinely completed existing tenants. A deferred tenant can re-enter normally from `/onboarding`. |
| Google account type | Admin OAuth requests the Workspace Directory scope plus Gmail, Drive, and Calendar. A consumer `@gmail.com` account is not Google Workspace and cannot provide directory sync. The live account also hit Google’s unverified-app interstitial. | The wizard now offers a distinct Personal Google / Google One mode using least-privilege Gmail/Drive/Calendar scopes and records a tenant credential without directory sync. Workspace mode remains administrator-only. Launch readiness must include OAuth verification. |
| Storage copy and behavior | Matter uploads prefer the selected connected provider but the code has explicit fallback/reconciliation paths. The old copy “never on LawHand infrastructure” overpromises the implementation. New roots are named `lawhand-records`; existing legacy roots must not be renamed destructively without the dedicated migration path. | Describe connected cloud as the matter-document system of record and say setup blocks matter creation until a root is confirmed. Show `lawhand-records` for new setup while retaining explicit backend compatibility for legacy roots. |
| Trial/billing CTA | The onboarding wizard has no checkout CTA. Billing is a separate surface and Helcim availability is runtime/provider dependent. | No billing redesign in this PR. Any future trial CTA must use billing capability status and must not imply checkout when Helcim is unavailable. |

## Follow-up risks

1. Complete Google OAuth verification before inviting trial users to connect;
   the production unverified-app interstitial remains an external launch blocker.
2. If the root naming policy changes, add a migration/alias strategy first;
   never rename existing customer folders in place.

## Operator sequence to make Terms available for onboarding

1. Open Platform → **Agreements** and click **Load current LawHand Terms**.
2. Confirm the preview is `terms_of_use`, title `LawHand Terms of Use`, version
   `2026-07-27`, effective `2026-07-27T00:00:00.000Z`, URL `${window.location.origin}/terms`,
   and review the complete SHA-256 hash of the canonical Terms content source with counsel.
3. Check the explicit counsel-approval box. The panel revalidates `/terms`
   availability and its canonical legal article with `cache: no-store`, then
   recomputes the deterministic canonical content hash immediately before
   publishing; a mismatch or validation failure aborts publishing.
4. Click **Re-fetch, verify, and publish**. No placeholder text is seeded and
   nothing is auto-published.
5. For each tenant, open onboarding after publication. The tenant administrator
   reviews the current definition and accepts it with legal name, title, and
   authority attestation. Only then does enforced agreement gating permit a new
   cloud connection.
