# Onboarding hotfix review — 2026-09-16

## Scope and live evidence

This review covers the first-admin onboarding wizard and the tenant-wide cloud
OAuth routes. The production test tenant is **LawHand Gmail Trial** (`getlawhand@gmail.com`),
a 30-day trial. The observed flow reached `/onboarding`, allowed the user to
defer setup, and allowed direct re-entry.

## Findings

| Area | Current behavior / evidence | Hotfix decision |
| --- | --- | --- |
| Agreement gate | `agreement_status()` reports `blocking=false` when no required counsel-owned agreement is published because enforcement is a rollout flag. The wizard therefore enabled both Connect buttons while the panel said “Not published”. | A new tenant may not start tenant-wide cloud OAuth unless current required agreements are configured and accepted. Existing connected tenants remain usable; this is not a global credential revocation. |
| Deferment | `/skip` marked `onboarding_completed=true` and step 5. The UI consequently rendered every prior step as complete and “Your firm is ready”, despite no integration or storage root. | Deferment keeps `onboarding_completed=false`, returns the wizard to its welcome step, and preserves core workspace access. The UI calls this “Set up later” and does not present completion evidence. |
| Re-entry | `/reenter` intentionally preserves a completed tenant’s root and completion state while reopening at Connect. | Preserve this behavior for genuinely completed existing tenants. A deferred tenant can re-enter normally from `/onboarding`. |
| Google account type | Admin OAuth requests the Workspace Directory scope plus Gmail, Drive, and Calendar. A consumer `@gmail.com` account is not Google Workspace and cannot provide directory sync. The live account also hit Google’s unverified-app interstitial. | Do not claim directory sync for personal Gmail. A separate solo OAuth intent using existing least-privilege scopes is a follow-up requiring explicit auth/provider approval; this PR does not fake that support. Workspace flow remains unchanged. Launch readiness must include OAuth verification. |
| Storage copy and behavior | Matter uploads prefer the selected connected provider but the code has explicit fallback/reconciliation paths. The old copy “never on LawHand infrastructure” overpromises the implementation. New roots are still named `claritylegal-records`; existing roots must not be renamed destructively. | Describe connected cloud as the matter-document system of record and say setup blocks matter creation until a root is confirmed. Keep the legacy folder name in this hotfix and document any rename separately. |
| Trial/billing CTA | The onboarding wizard has no checkout CTA. Billing is a separate surface and Helcim availability is runtime/provider dependent. | No billing redesign in this PR. Any future trial CTA must use billing capability status and must not imply checkout when Helcim is unavailable. |

## Follow-up risks

1. Add a dedicated `solo` Google OAuth intent that stores a tenant credential
   with Gmail/Drive/Calendar scopes, skips directory sync, and records the
   personal account tier. This requires provider/auth review and end-to-end
   consent testing; it is intentionally not implemented here.
2. Complete Google OAuth verification before inviting trial users to connect.
3. If the root naming policy changes, add a migration/alias strategy first;
   never rename existing customer folders in place.

