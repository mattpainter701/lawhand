# Permissions, visibility and the firm connection

Status: model agreed with the product owner on 25 September 2026. Nothing here is built yet; section 8 is the delivery plan.
Date: 2026-09-25

This document defines who can see what in LawHand, and how LawHand connects to a firm's Microsoft 365 or Google Workspace. It replaces rules that grew up implicitly, most of them from an early build against a single personal Gmail account. It is the reference for the open integration-review items D02, D03, D04, D06, D13, D15, D16 and D25 (see [the M365/Google review](./m365-google-workspace-integration-review-2026-09-24.md)).

It matters more now because LawHand is moving to MCP servers that firms use from their own AI tool (Claude Desktop and similar). An MCP client acting as a user gets exactly that user's access, so the access rules have to be single, explicit and the same everywhere.

---

## 1. Principles

1. **The person who signs the firm up is not special.** As in Zoom, Jira or Slack, they become the first admin. Their personal mailbox, drive and calendar are never "the firm's".
2. **The firm connects once, at the organization level.** A Microsoft 365 or Google Workspace admin approves LawHand for the organization. LawHand never borrows one person's login to act for everyone.
3. **Correspondence about a matter belongs to the matter and the firm.** Once filed, it is visible to whoever can see the matter. Mail that matches no matter never enters LawHand.
4. **Matters are open by default and can be restricted.** Restricted means partner, attorney of record, assignees and named people. Firm admins keep break-glass access, and it is logged.
5. **One access check, everywhere.** The UI, chat, search, cloud search, the file share, background jobs and every MCP tool ask the same question the same way.
6. **LawHand's model drives the cloud, not the other way round.** Folder permissions in SharePoint/Drive follow matter visibility. Directory groups feed LawHand roles. The direction of each sync is fixed (section 6).

---

## 2. How it works today

This summary comes from a read of `origin/main` at `704593d`.

**Who becomes admin.** Whoever signs the firm up (`routers/auth.py:1969`), or the first person to sign in to a new tenant (`auth.py:813`). Everyone invited later is `user`.

**The "firm connection" is that person's own login.** Onboarding step 1 (`routers/onboarding.py`) has them connect Microsoft or Google with their own account, and that delegated grant becomes the tenant credential (`routers/integrations.py:242-266`; `services/token_vault.py:413-435`). As a result:

| Effect | Where | Review item |
|---|---|---|
| The 15-minute sync indexes that person's mailbox, and every staff user can search it (no owner filter) | `services/cloud_sync.py:128-162`, `841-872`; `services/cloud_search.py:472-480` | D03 |
| Anyone without their own connection searches, and reads full messages, through that person's mail and files | `cloud_search.py:1550-1574`, `1379`, `1189`; `services/rag.py:344-376` | D02 |
| Approved client email is sent from that person's mailbox | `services/connected_mail.py:383-412` | D25 |
| Task calendar events land in that person's calendar | `services/google_calendar.py:18-30`; `services/microsoft_calendar.py:23-35` | D04 |
| With Microsoft, firm matter files sit in that person's personal OneDrive, which other users' tokens can't reach | `services/cloud_init.py:146-160`; `services/matter_file_store.py:171-174` | D06, D13 |

**Matter access.** Three rules exist side by side:

| Rule | Meaning | Used by |
|---|---|---|
| A. Whole firm | Any staff user can open, edit and delete any matter, and assign anyone | Matters, documents, notes, chat, email log, calendar, most MCP reads (`routers/matters.py:135-153`; `services/matter_workspace_capabilities.py:95-105`) |
| B. Owner, assignee or admin | Only people on the matter | SMS, SMS tasks, workflow runs, intake, MCP task tools (`services/matter_access.py:14-115`) |
| C. Whole firm unless restricted | Restricted or walled matters limited to owner, attorney, partner, assignees and `allowed_user_ids` | On-premises file-share search and file opening only (`services/native_authorization.py:101-223`). Nothing can set the flag |

**Roles.** There are two systems: `User.role` (admin, accountant, user, client) and capability roles (`services/capabilities.py`). "Admin" means one in some places and the other elsewhere. No attorney or staff distinction exists, and `MatterAssignment.role` is free text that access never reads.

**Deactivation.** It cuts the UI and MCP and removes OneDrive/Drive shares (PR #625). It does not stop correspondence capture of the person's mailbox (`services/scheduler.py:1911-1917`), and directory sync reactivates people an admin turned off (`services/user_sync.py:180`, `326`; D15). Sync never deprovisions and treats guests and resource mailboxes as staff (D16). Directory groups are not read.

---

## 3. Identity and the firm connection

Four roles a person or account can play, kept separate:

| What | Who | Purpose |
|---|---|---|
| **LawHand admin** | Any user granted the admin capability. The first sign-up gets it. | Firm settings, people, roles, integrations, break-glass matter access |
| **Organization approver** | A Microsoft 365 Global/Privileged Role admin or a Google Workspace super admin, acting once in their own admin console | Approves LawHand for the organization. They need not be a LawHand user. |
| **Firm connection** | An app identity, never a person | Directory sync, firm storage, per-user mail and calendar through org-level permission |
| **Personal connection** | Each user, only when the org-level route is unavailable | Their own mailbox and calendar |

One person can hold all of these. The owner's `cybersafeadvisor.com` tenant (a single user who is admin, approver and staff) is the reference case: it must work with no second account, and the owner's mailbox is captured as a user's mailbox, not as "the firm's".

### 3.1 Microsoft 365

- **Firm connection:** an application (client-credentials) grant against the customer's directory GUID, approved once through Microsoft's admin-consent flow. LawHand already runs this pattern for Teams voice (`docs/TEAMS_VOICE_SETUP.md`; `routers/teams.py:384`, `556`): the multi-tenant `common`/`organizations` endpoints cannot issue app-only tokens, so the real directory GUID is stored.
- **Permissions (application):**
  - `Sites.Selected` for the firm's SharePoint library, granted on that one site;
  - `User.Read.All` and `GroupMember.Read.All` for directory and group sync;
  - `Mail.Read` and `Mail.Send`, and `Calendars.ReadWrite`, for capture, sending and calendar pushes.
- **Mailbox scope:** Exchange "RBAC for Applications" (the successor to application access policies) limits the mail and calendar permissions to a mail-enabled security group, for example "LawHand users". LawHand keeps that group in step with its active users, so the app cannot read mailboxes of people who aren't LawHand users.

### 3.2 Google Workspace

- **Firm connection:** LawHand's service account, authorized by the Workspace super admin under domain-wide delegation for LawHand's client ID and an explicit scope list.
- **Scopes:**
  - `admin.directory.user.readonly` and `admin.directory.group.readonly` for directory and group sync;
  - Drive access to the firm's Shared Drive (the service account is already added as a member, `cloud_init.py:236-247`);
  - `gmail.readonly` and `gmail.send`, and `calendar.events`, used by impersonating one user at a time.
- **Isolation:** one service account serves every firm that authorizes it. LawHand must only ever impersonate addresses in domains verified for the tenant making the request, and must record the domain→tenant binding at authorization time. D01 showed the cost of getting this wrong.
- **Open question:** whether Gmail restricted scopes under domain-wide delegation from a Marketplace listing still need Google's CASA assessment. See section 9.

### 3.3 When the org-level route isn't available

The firm may have no admin rights, a consumer Gmail or Outlook.com account, or an IT policy against app-wide mail access. In that case:

- Storage and directory still need a firm connection. For a consumer account that means a Google Shared Drive or SharePoint library owned by the firm, or LawHand-managed storage.
- Each user connects their own mailbox and calendar during their onboarding (the existing per-user flow).
- The firm's matter email address (BCC or forward, `routers/firm_email_intake.py`) stays available as a backstop for everyone.

Onboarding detects which route applies and says so plainly. It never silently falls back to one person's account.

---

## 4. Roles

LawHand roles, defined as capability sets, with admin a capability rather than a `User.role` value:

| Role | Can |
|---|---|
| Admin | Everything, including firm settings, people, roles and integrations; break-glass access to Restricted matters |
| Attorney | Create, restrict and delete matters; change who is on a matter; approve client communications |
| Staff (paralegal, assistant) | Work on any matter they can see; propose communications for approval |
| Accounting | Billing, trust and time; read-only matter view |
| Client | Portal only |

**Directory groups map to roles natively.** An admin maps a directory group (for example Entra "Attorneys" or Workspace "paralegals@") to a LawHand role. Directory sync then:
- keeps role membership in step with the group;
- creates users for new group members, and deactivates users who leave every mapped group or are disabled or deleted in the directory;
- never reactivates a user a LawHand admin deactivated (D15);
- skips guests, and resource or shared mailboxes (D16).

A user with no mapped group keeps whatever role an admin gave them in LawHand. The two are shown side by side so an admin can see where a role came from.

---

## 5. Matter visibility

Set when the matter is created, and changeable later by an attorney or admin:

- **Open (default):** every active staff user in the firm.
- **Restricted:**
  - the partner, attorney of record and assignees;
  - people added by name (the existing `allowed_user_ids`);
  - people explicitly excluded, which is an ethical wall. They are refused even if they are on the matter's team or in a role that would otherwise see it. Exclusion is kept for later; the field exists in `native_authorization`.
- **Break-glass:** admins can open a Restricted matter. Every such access is recorded in the matter's audit trail and visible to the attorney of record.

This is rule C, made settable and used everywhere. Rule A becomes "rule C with visibility Open". Rule B stays for things that belong to a person rather than a matter, such as a user's own SMS drafts and personal tasks.

**One check.** A single `can_access_matter(user, matter, action)` in `services/native_authorization.py` (or its successor) is the only matter-access check used by:
- the matters, documents, notes, tasks, calendar and communications routers;
- chat and RAG retrieval, cloud search and the file-share search;
- background capture and filing;
- every Workspace MCP tool (`matter_workspace_capabilities._require_matter`, `chat_tools/handlers.py`, `workspace_lifecycle_capabilities.py`).

Lists and search results filter by the same rule, so a Restricted matter never appears for someone who can't open it.

---

## 6. Sync directions

"Sync" means a fixed direction per attribute, a periodic reconcile, and visible drift. It never means two systems overwriting each other.

| Attribute | Source of truth | Flows to | On drift |
|---|---|---|---|
| Who is in the firm; their role (where groups are mapped) | Directory | LawHand users and roles | LawHand follows the directory, except that a LawHand deactivation holds |
| Matter visibility and team | LawHand | SharePoint/Drive folder permissions | Permissions LawHand created are corrected. A permission someone added by hand is flagged to the matter's attorney and admins, who either adopt it (the person becomes a named member in LawHand) or remove it. It is never silently granted and never silently removed. |
| Filed correspondence | The matter in LawHand | — | — |

How folder permissions follow visibility:
- **Open matter:** the firm's staff group (a directory group LawHand manages, or the SharePoint site members / Shared Drive members) has access, so no per-person shares are needed.
- **Restricted matter:** the folder stops inheriting firm-wide access, and LawHand shares it with each allowed person, using the per-person share records and removal added in PR #625.
- **Firm storage is always firm-owned:** a SharePoint library or a Google Shared Drive, never a person's OneDrive or My Drive (D06, D13).

---

## 7. Correspondence

**Whose mail is captured.** Every active staff user's mailbox:
- through the org-level connection, for firms that have one;
- through that user's own connection, for firms that don't;
- plus the firm's matter address (BCC or forward).

The connecting admin's mailbox is captured only as that person's own mailbox. There is no firm-wide admin mailbox index.

**What is captured.** Only messages that match a matter under the existing capture rules (`services/correspondence_capture.py`): client and counterparty addresses, matter number in the subject, and so on. Matched mail is filed to the matter as correspondence. Everything else is never stored and never searchable.

**Who sees it.** Anyone who can see the matter (section 5). Filed correspondence belongs to the case and the firm, as with any other matter record.

**Sending.** Approved client email is sent as the approving user, through the org-level connection or their own. A firm may also nominate a shared mailbox (for example `office@`) to send from. It is never sent from whichever admin happened to connect first (D25).

**Deactivated users.** Their mailbox is no longer captured. Mail already filed stays with the matter.

---

## 8. Delivery plan

Each phase is shippable on its own. Per-tenant switches let an existing tenant move to the new path before the old one is removed (expand, migrate, contract).

1. **Stop using the admin as a stand-in (safe now).**
   - Stop indexing the tenant credential's mailbox firm-wide (D03), and purge those rows.
   - Firm-storage Drive search uses the service account (Google) or the firm connection (Microsoft) instead of the admin's personal token. Personal mail search needs the user's own connection until phase 3 (D02).
   - Correspondence capture skips deactivated users.
   - Directory sync no longer reactivates LawHand-deactivated users, and skips guests and resource mailboxes (D15, D16).
2. **One access check and matter visibility.**
   - `can_access_matter` with Open/Restricted, used everywhere in section 5.
   - Visibility on the create-matter form and matter settings.
   - Break-glass audit.
   - MCP tools switched to the same check.
3. **Org-level connection.**
   - Microsoft app-only (reusing the Teams voice pattern), with RBAC for Applications limited to the LawHand users group.
   - Google domain-wide delegation, with a domain→tenant binding.
   - Onboarding step "Connect your organization", with the fallback in 3.3.
   - Per-user capture, sending and calendar pushes through it (D04, D25).
   - Remove the admin fallback everywhere once tenants have moved (D02).
4. **Roles and directory groups.** The role set in section 4, group→role mapping, and deprovisioning.
5. **Firm-owned storage and folder-permission sync.**
   - SharePoint library as the Microsoft default, and a move out of the admin's OneDrive for existing firms (the Microsoft counterpart of #548).
   - Folder permissions derived from visibility, with the drift report in section 6 (D06, D13).

### Existing tenants

Nothing breaks if each phase goes in order:

| Change | Existing tenant impact | Mitigation |
|---|---|---|
| Admin mailbox index removed | Firm-wide search no longer shows the admin's mail | None needed; it should not have been visible |
| Admin fallback for Drive search removed | Users without their own connection would lose firm file search | Phase 1 moves firm-storage search to the service account or firm connection first |
| Google root still in My Drive | Files not in firm-owned storage | Run the #548 move before phase 5 |
| Mail and calendar through the admin | Continue until the tenant enables the org-level connection | The per-tenant switch in phase 3 removes the fallback only after the tenant has moved |
| Sending from the admin mailbox | Continues until phase 3 for that tenant | Send as the approver, or from a nominated shared mailbox |

---

## 9. Open questions

1. **Google CASA.** Do `gmail.readonly` and `gmail.send` under domain-wide delegation from a Marketplace listing still require a CASA assessment? The answer decides whether Google phase 3 ships as org-level only or keeps a per-user option (review decision 4).
2. **Break-glass notice.** Should the attorney of record be notified when an admin opens a Restricted matter, or only see it in the audit trail?
3. **Firm staff group.** Should LawHand create and manage its own "LawHand users" group in the directory, or should the firm nominate an existing one?
4. **LawHand-managed storage.** Is it offered for firms with no Microsoft or Google admin (section 3.3), or are those firms required to have one?

## 10. Decisions recorded (25 September 2026)

| # | Decision |
|---|---|
| 1 | The firm connection is an org-level admin approval, not a person's login. The approver may also be a normal user, and a single-person firm must work. |
| 2 | Connect mailboxes automatically through the org-level approval where the admin has the rights. Otherwise each user connects their own, with the matter address as a backstop. |
| 3 | Matters are Open by default. Restricted means partner, attorney of record, assignees and named people. Admins keep break-glass access. |
| 4 | Roles are Admin, Attorney, Staff, Accounting and Client, and map to directory groups natively where available. |
| 5 | Matter visibility and cloud folder permissions stay in sync, with LawHand as the source for matter access and the directory as the source for people and roles (section 6). |
| — | BYOK (a firm's own model API key) is removed; AI reaches firms through MCP servers used from their own paid AI tool. |
