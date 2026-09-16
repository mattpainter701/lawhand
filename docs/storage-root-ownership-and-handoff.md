# Cloud root ownership and tenant handoff

Status: Phase 0/1 in progress. This document is the design of record for who
owns a firm's document root, how it survives staff turnover, and how a tenant
leaves without their folders breaking.

## The guarantee

1. LawHand never deletes or destructively renames a customer's cloud folders —
   not on matter close, provider change, disconnect, or tenant exit.
2. The document root is **organisation-owned** for business tenants. It is
   created with an org identity (service account / app permissions) inside an
   org-owned location (Google Shared Drive / SharePoint site library), so it
   survives the departure of the admin who connected the integration.
3. Access inside LawHand is governed by the LawHand database (matter assignment
   and portal visibility). Cloud sharing is a convenience mirror for people who
   open Drive/OneDrive directly — it is not the security boundary.
4. On exit, LawHand stops writing, revokes its own tokens, hands the customer an
   XLSX manifest of their roots/folders, and deletes only LawHand-side rows.

## Provider ownership model

| Provider | Resource location | Access identity | Durable? |
|---|---|---|---|
| Google Drive (Shared Drive) | Org Shared Drive, `driveId` recorded | Service account (DWD or Shared Drive member) | Yes |
| Google Drive (My Drive) | Granting admin's My Drive | Delegated admin token | No — at risk |
| SharePoint | Org site document library | Delegated admin token (app-only planned) | Resource yes, identity no |
| OneDrive | Granting admin's `/me/drive` | Delegated admin token | No — at risk |

`app/services/storage_root_ownership.py` classifies a persisted root as
`durable`, `at_risk`, or `unbound`; `/api/admin/onboarding/status` returns it as
`root_ownership`.

## Environment contract

These are configured **once by LawHand (the operator)**, not per customer. The
customer only signs in and connects.

| Variable | Purpose |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` | LawHand's central service-account identity |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | LawHand service-account JSON (inline or path) |
| `GOOGLE_AUTO_SHARED_DRIVE` | Auto-create a Shared Drive on Workspace connect (default true) |
| `GOOGLE_ORG_SHARED_DRIVE_NAME` | Name of the auto-created Shared Drive |
| `GOOGLE_SHARED_DRIVE_ID` | Optional operator pin to a specific Shared Drive |
| `GOOGLE_IMPERSONATE_SUBJECT` | Workspace admin to impersonate for directory/mail only |

A tenant may override the Shared Drive with
`TenantSettings.custom_config["google_shared_drive_id"]`.

## Google Workspace — customer flow (no GCP setup)

The customer's only action is the normal admin sign-in/connect. On a Workspace
(not personal) connection, LawHand:

1. Creates a Shared Drive named `LawHand Firm Records` using the admin's token.
   A Shared Drive is owned by the Workspace domain, not the individual.
2. Adds **LawHand's central service account** as a Content manager of that drive,
   again with the admin's token. No customer GCP project, key, or delegation.
3. Creates `lawhand-records` inside the drive and records `drive_id` +
   `owner_type=org_shared_drive`.

From step 2 onward LawHand can operate with its own service-account identity, so
the root survives the admin being deactivated or leaving. If the drive can't be
created (Workspace policy) or the service account can't be added (external
sharing disabled), LawHand falls back to the admin's My Drive and reports
`root_ownership.status = at_risk`.

### Operator setup (once, not per customer)

1. In LawHand's own GCP project, enable the Drive API and create the service
   account; set `GOOGLE_SERVICE_ACCOUNT_EMAIL` / `GOOGLE_SERVICE_ACCOUNT_KEY`.
2. Nothing else. No per-customer Shared Drive, key, or delegation.
3. Domain-wide delegation (`GOOGLE_IMPERSONATE_SUBJECT`) is only needed for
   directory/mail impersonation and remains a one-time Admin-console step; it is
   **not** required for storage.

## Microsoft 365 — customer flow (one click, app-only planned)

The customer's only action is the normal admin connect; the app's consent
screen grants admin consent in that same click. LawHand then uses app-only
(`client_credentials`) permissions and binds the root to the org's SharePoint
site library (`/sites/{id}/drive`), not a personal `/me/drive`.

Today the code still uses the delegated admin token, so the SharePoint resource
is org-owned but access dies with that admin. See follow-ups.

## Handoff manifest (agreed)

An XLSX manifest is the customer-facing artifact at exit and after any
migration. Intended columns: tenant, provider, root name/id/URL, drive/site id,
owning identity, current grantor, per-matter folder name/id/path/URL,
subfolders, status, last-verified timestamp. It fits the existing evidence-only
offboarding skeleton, which performs no deletion.

## Follow-ups

- **Auth model**: Microsoft app-only (`Sites.Selected`) and a firm-level
  decision to forbid creating business roots in `/me/drive`.
- **Migration**: move existing My Drive / OneDrive roots into Shared Drive /
  SharePoint via the existing non-copying storage-migration framework.
- **Manifest builder + endpoint** and its tests.
- **Health surfacing** in the admin UI when `root_ownership.status` is
  `at_risk`.
- **Consumer Microsoft copy**: the onboarding review still claims a Microsoft
  365 directory sync for consumer accounts.
