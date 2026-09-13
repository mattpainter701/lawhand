# Provider app ownership migration

Move the Google and Microsoft OAuth applications off personal accounts (a
personal Gmail with Google One/Workspace Individual, and a personal-name
Microsoft 365 business tenant) onto identities owned by **Perevaga Group LLC**,
so the product can be operated, audited, and sold independently of any one
person's login.

**Do this before the first paying firm connects an integration.** Section 2
explains why the cost of this migration multiplies with every tenant that
consents.

> **Verify before you rely on this.** Provider console wording, verification
> program names, and assessment pricing change often. Every step below names
> *what* to achieve and the value to enter; confirm the current click-path
> against the provider's live documentation as you go. Costs quoted are
> order-of-magnitude, not quotes.

---

## 0. Three decisions to make before you touch a console

These are forks in the road. Making them after you submit for verification
means starting verification over.

### Decision 1 — Google restricted scopes: settled, Track A

LawHand requests two Google **restricted** scopes
(`backend/app/routers/integrations.py:235-259`):

| Scope | Google class | Consequence |
| --- | --- | --- |
| `https://www.googleapis.com/auth/gmail.readonly` | **Restricted** | Verification **+ annual third-party CASA assessment** |
| `https://www.googleapis.com/auth/drive` (full) | **Restricted** | Same |
| `https://www.googleapis.com/auth/gmail.send` | Sensitive | Verification only |
| `https://www.googleapis.com/auth/calendar` | Sensitive | Verification only |
| `https://www.googleapis.com/auth/admin.directory.user.readonly` | Sensitive | Verification only |

**The decisive property: CASA is a binary gate, not per-scope pricing.** One
restricted scope puts you in the assessment; the second one is then free. So
there is no partial saving — you either eliminate *every* restricted scope or
you are in CASA and may as well keep the capable ones.

Measured against the first customer's requirements — Google Workspace, staff
login, staff email sync, matters saved to their Drive:

| Requirement | Minimum scope | Restricted? |
| --- | --- | --- |
| Staff login | `openid email profile` | No |
| Know who the staff are | `admin.directory.user.readonly` | No (sensitive) |
| **Sync staff email** | `gmail.readonly` | **Yes** |
| Send from the firm's mailbox | `gmail.send` | No (sensitive) |
| Create matter folders and upload documents to Drive | `drive.file` | No |
| **Index/search what the firm already has in Drive** | `drive` | **Yes** |

Two things make this Track A and close the question:

1. **No Gmail read scope escapes CASA.** `gmail.metadata` is also classified
   restricted, so even though `cloud_sync._sync_gmail`
   (`backend/app/services/cloud_sync.py:455-520`) already fetches only
   `format=metadata` headers rather than message bodies, narrowing the scope
   buys nothing — and `gmail.metadata` additionally forbids the `q` query
   parameter that both that sync (`q=after:...`) and the mail search in
   `cloud_search.py:751-760` depend on. Mailbox sync means CASA. Full stop.

2. **Given (1), narrowing Drive is pure product loss for zero saving.** Under
   `drive.file` the write path still works — LawHand could create the matter
   tree and upload documents. But `drive.file` grants access only to files the
   app itself created or the user picked explicitly, so a document an attorney
   drags into a matter folder through the Drive web UI is **invisible** to
   LawHand. For a law firm that is a daily occurrence, not an edge case. It
   would also disable Drive search outright: `cloud_search.py:615-655` queries
   `fullText contains` across `corpora: allDrives`, which `drive.file` cannot do.

**Therefore: keep the current scope set, and treat the CASA assessment as the
critical path of this entire migration.** Budget low four figures per year and
engage an assessor in the same week you submit for verification — assessor lead
time, not Google's review queue, is what sets your launch date.

#### The only genuine ways out, for the record

Neither is recommended, but decide against them deliberately rather than by
omission:

- **Drop mailbox sync; use forwarding-based capture instead.** LawHand already
  has a production-shaped inbound path — Cloudflare Email Routing → per-matter
  opaque aliases → quarantine → human "File to matter"
  (`docs/inbound_email_setup.md`). Combined with `drive.file`, that removes
  every restricted scope and therefore CASA entirely. But it is a different
  product: it captures what staff deliberately forward, not what lands in their
  inbox. Your customer asked for sync.
- **Google Workspace Marketplace private distribution / domain-wide delegation.**
  For a single Workspace tenant, scopes can be authorized by the customer's own
  super admin rather than through a public consent screen, which changes the
  verification posture. Three problems: LawHand has no service-account
  impersonation code path at all (`token_vault` is refresh-token OAuth only), it
  serves Workspace tenants only — contradicting the personal-tier onboarding in
  `docs/superpowers/plans/2026-09-07-cloud-provider-portability-remediation.md` —
  and Google has been steering vendors away from domain-wide delegation. If you
  want to explore it, raise it with your CASA assessor before assuming it exempts
  you from anything.

#### What to do anyway, cheaply

Restricted or not, review scope **usage** before you record justifications:
Google reviewers compare the scopes you request against what the demo video
shows. `Sites.Read.All` on the Microsoft side and `drive` on the Google side are
both broad enough to draw questions from law-firm security reviewers even after
Google approves them. Have the answer from
[section 4.2](#42-register-the-server-side-application) ready.

### Decision 2 — Microsoft audience: `common` or `organizations`?

`backend/app/config.py:101` sets `MICROSOFT_TENANT_ID: str = "common"`, which
admits both work/school accounts and personal Microsoft accounts. But the
requested Graph scopes include `User.Read.All` and `Sites.Read.All`, which do
not exist for personal accounts — a consumer sign-in gets a confusing failure
rather than a clean refusal.

Recommended: register the app as **multitenant (any Microsoft Entra ID tenant)**
and set `MICROSOFT_TENANT_ID=organizations`. Keep `common` only if you have a
concrete consumer-Outlook use case.

### Decision 3 — Which legal entity and domain is the permanent home?

Everything below assumes **Perevaga Group LLC** and **`getlawhand.com`**, which
is what `teams-app/manifest.json:6-11` already declares. If the entity that will
sell the product is going to be a different one (a newco, an asset sale
vehicle), register there instead. Re-verifying under a new publisher later is
the same restart penalty as Decision 1.

Note the inconsistency already in the repo: `teams-app/manifest.json:49-50`
exposes the API as `api://legalapp.perevagagroup.com/c805316c-...` while the
developer block and `validDomains` say `getlawhand.com`. That legacy domain must
not survive this migration.

---

## 1. What is currently bound to a personal account

| Binding | Where | Owned by |
| --- | --- | --- |
| Google OAuth client + consent screen | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (`backend/app/config.py:126-127`) | personal Google account's Cloud project |
| Microsoft app registration | `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` (`backend/app/config.py:99-100`) | personal-name M365 tenant |
| Office add-in SPA registration | `OFFICE_ENTRA_CLIENT_ID` / `OFFICE_ENTRA_API_AUDIENCE` (`backend/app/config.py:109-110`) | same tenant |
| Teams app + exposed API | `teams-app/manifest.json:5,49-50`, `TEAMS_APP_ID` | same tenant |
| Zoom meetings app | `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` (`backend/app/config.py:130-131`) | personal Zoom marketplace account |
| QuickBooks app | `QBO_CLIENT_ID` / `QBO_CLIENT_SECRET` (`backend/app/config.py:296-297`) | personal Intuit developer account |

Zoom **Phone** is already tenant-owned per customer
(`backend/app/services/tenant_oauth_apps.py`, `tenant_oauth_apps` table) and is
*not* affected. Zoom **meetings** is a global app and is affected.

---

## 2. Why the cost of delay is non-linear

`backend/app/services/token_vault.py:238-253` refreshes every stored provider
token using the **global** `GOOGLE_CLIENT_ID` / `MICROSOFT_CLIENT_ID`. OAuth
refresh tokens are bound to the client ID that issued them. The moment the
client ID changes:

1. Every row in `user_oauth_tokens` for `provider in ('google','microsoft')`
   becomes unrefreshable. Gmail sync, Drive writes, and calendar go dark for
   every connected user.
2. Every tenant admin must re-run admin consent
   (`GET /api/integrations/{microsoft,google}/connect?intent=admin`, and for
   Teams the `/adminconsent` flow at `backend/app/routers/teams.py:402`).
3. Every individual user must re-run user consent.
4. Microsoft service-principal grants in each customer tenant must be
   re-approved; the old app's enterprise-application entry should be removed by
   the customer.
5. Google verification and any CASA assessment restart against the new project —
   they are granted per project/client, not per company.

At zero connected firms this is an afternoon. At twenty firms it is a
coordinated support incident across twenty IT contacts, with integrations broken
until each one acts.

**There is also a hard deadline you may not have noticed.** While a Google
consent screen sits in **Testing** publishing status, Google expires issued
refresh tokens after seven days and caps you at 100 test users. If production
is running on a Testing-status client today, every firm's integration silently
breaks weekly. Confirm the current publishing status before anything else.

---

## 3. Google — exact steps

### 3.1 Create a company-owned identity (free)

Do **not** simply create the project under a different personal Gmail. A project
owned by a bare consumer account has no Google Cloud **Organization**: there is
no central admin, no clean ownership transfer, and the project is orphaned if
that account is ever disabled. That is precisely what an acquirer's diligence
flags.

Sign up for **Google Cloud Identity Free** on `getlawhand.com` — free, up to 50
users, no Workspace mailbox required:

1. Go to `https://workspace.google.com/gcpidentity/signup` (Cloud Identity Free
   signup). If you are steered toward paid Workspace, look for the Cloud
   Identity **Free** edition explicitly.
2. Business name: **Perevaga Group LLC**. Domain: **getlawhand.com**.
3. Create the first admin, e.g. `admin@getlawhand.com`.
4. Verify the domain with the TXT record Google gives you, at your DNS provider.
5. In the Admin console, create a role account for provider ownership, e.g.
   `oauth@getlawhand.com`, and give at least two people access to it. Nothing
   production-critical should sit behind one person's MFA.

> If you already pay for Google Workspace on `getlawhand.com`, you have this
> already — skip to 3.2. If your existing paid Workspace is on a *personal*
> domain, do not reuse it.

This automatically gives you a Google Cloud **Organization** node for
`getlawhand.com`. Projects created inside it belong to the company and transfer
with the domain.

### 3.2 Create the project

1. `https://console.cloud.google.com` — sign in as `admin@getlawhand.com`.
2. Create project **`lawhand-prod`**, and set **Location / Organization** to
   `getlawhand.com` (not "No organization"). This field cannot be changed later
   without a project move.
3. Create a second project `lawhand-dev` the same way, for dev1/Skynet. Keep
   dev credentials out of the production client so a dev misconfiguration can
   never affect verified production.
4. Enable the APIs the scopes require: Gmail API, Google Drive API, Google
   Calendar API, Admin SDK API, People API.

### 3.3 Verify the domain for OAuth

Google will only accept `getlawhand.com` as an authorized domain if the account
owning the project has verified it:

1. `https://search.google.com/search-console` — add `getlawhand.com` as a
   **Domain** property, signed in as `admin@getlawhand.com`.
2. Verify via the DNS TXT record.

### 3.4 Configure the consent screen / Google Auth Platform

In the Cloud console under **APIs & Services → Google Auth Platform** (older
consoles: **OAuth consent screen**):

- **Branding:** App name `LawHand`. User support email `support@getlawhand.com`.
  App logo (use `frontend/public/brand`). App home page
  `https://getlawhand.com`. Privacy policy `https://getlawhand.com/privacy`.
  Terms of service `https://getlawhand.com/terms`. Authorized domain
  `getlawhand.com`. Developer contact `oauth@getlawhand.com`.
- **Audience:** **External**. (Internal would restrict consent to your own
  Cloud Identity users — useless for selling to law firms.)
- **Data Access:** add exactly the scopes from Decision 1, and nothing more.
  Every extra scope lengthens review.

Confirm the privacy policy actually exists at that URL, describes each scope's
use in plain language, and carries the Google API Services **Limited Use**
disclosure (mandatory for the restricted scopes). A missing or generic privacy policy is the single
most common cause of a rejected review.

### 3.5 Create the OAuth client

**APIs & Services → Credentials → Create credentials → OAuth client ID → Web
application.** Name it `LawHand production`.

Authorized redirect URIs — these must match byte-for-byte, no trailing slash.
Read the production origin from `BACKEND_URL` in the production env file rather
than assuming; with `BACKEND_URL=https://getlawhand.com` the values are:

```text
https://getlawhand.com/api/auth/google/callback
https://getlawhand.com/api/integrations/google/callback
```

(Constructed at `backend/app/routers/auth.py:1208` and
`backend/app/routers/integrations.py:632`.)

Add the dev1 equivalents to the **`lawhand-dev`** client, not this one.

Record the client ID and secret straight into the production secret store. Do
not paste them into chat, tickets, or this repo.

### 3.6 Submit for verification

**APIs & Services → Google Auth Platform → Verification Center.** You will need:

- a demo video (screen recording) showing the real OAuth consent flow and each
  requested scope actually being used in-product;
- justification text per scope — say concretely what LawHand does with it;
- the verified domain and live privacy policy from 3.3/3.4.

Google will additionally require a **CASA** assessment for the restricted
scopes, performed by an authorized third-party assessor. Start scheduling this
the same week you submit — assessor lead time, not Google's review, is usually
what sets the date. It renews annually.

Then **publish the app** (Testing → In production). Until you do, the 7-day
refresh-token expiry from section 2 applies.

Realistic timeline: plan for four to eight weeks, and do not commit a customer
launch date against it. This is the critical path of the whole migration —
everything in sections 4 and 5 can proceed in parallel while it runs.

### 3.6.1 Scope justification text

The **Data Access** screen wants a justification per scope group, and the
reviewer reads it next to your demo video. If the two disagree, you are
rejected and requeued, so the text below describes only what the code in this
repository actually does. Each block is under Google's 1000-character limit.

Before pasting, re-read section 5.3: if the scope manifest has moved, this text
has to move with it.

**Sensitive scopes** — `admin.directory.user.readonly`, `calendar`,
`gmail.send`. Source: `user_sync.sync_google_users`, `calendar_sync`
(`google_get_events` / `google_create_event` / `google_delete_event`),
`email_admin._send_via_google`.

> LawHand is legal practice management software. A firm administrator connects the firm's own Google Workspace account.
>
> admin.directory.user.readonly - at setup and on demand we list the firm's domain users so the administrator can provision staff into the firm's LawHand workspace without retyping names and addresses. We read name, primary email and suspension status only, and never modify directory data.
>
> calendar - we write court dates, filing deadlines and limitation dates calculated in LawHand to the user's primary calendar, update them when a matter's dates change, and remove them when a deadline is deleted. We read existing events to avoid duplicates and surface scheduling conflicts.
>
> gmail.send - we send the firm's own operational mail (matter assignments, deadline reminders, intake confirmations) from the firm's address, so mail to clients and staff stays in the firm's sent mail rather than arriving from a third-party sender.

**Restricted — Drive** (`auth/drive`). Source: `cloud_search._search_google_drive`
(`fullText contains`, `corpora=allDrives`), `matter_file_store`,
`matter_folder_marker`, `storage_discovery._google`, `document_sync`.

> LawHand is legal practice management software. A firm connects its own Google Workspace; its matter documents live in its Drive.
>
> We use this scope to: (1) full-text search My Drive and Shared Drives (files.list with q="fullText contains ...") to find correspondence, pleadings and contracts relating to a specific matter; (2) read or export those files so their text appears in the matter record; (3) create matter folders and upload documents LawHand generates; (4) read an existing folder tree at onboarding so the firm's filing structure is preserved. We delete only files our own upload staged and failed to commit, and never alter sharing or permissions.
>
> drive.file is insufficient: it reaches only files our app created or the user picked individually. The documents a firm must find are pre-existing, authored by staff over years, often in Shared Drives, and added to matter folders outside our app. drive.readonly is insufficient because we also create folders and upload files.

**Restricted — Gmail** (`auth/gmail.readonly`). Source:
`cloud_sync` and `cloud_search._search_gmail` (`messages.list` with `q=`),
`cloud_search._fetch_gmail_content` (`format=full`), `google_mail.gmail_read_raw`
(`format=raw`, used by `correspondence_capture`).

> LawHand is legal practice management software. A firm connects its own Google Workspace so client correspondence can be found and filed against the right matter.
>
> We use this scope to: (1) search the user's mailbox with messages.list q= (from:, to:, subject:, after:) for messages relating to a specific matter or client; (2) read a message the user selects so it can be filed to that matter.
>
> Data is minimised. Search results are fetched with format=metadata, returning only From, To, Cc, Subject and Date. A message body is read only when the user explicitly opens a result or files a message onto a matter (format=full, or format=raw to store the .eml). We do not bulk-download mailboxes.
>
> gmail.metadata is insufficient: it forbids the q search parameter, and searching by correspondent, subject and date is the entire feature. No narrower Gmail read scope supports search.

**"What features will you use?"** — tick only what the demo video shows. Every
box you check is a claim the reviewer will look for on screen, and an unshown
claim is a rejection. For Drive that is searching, reading/downloading, and
creating folders and files; *not* sharing, permission changes, or ownership
transfer, none of which LawHand performs. For Gmail that is searching and
reading; *not* sending (that is `gmail.send`, justified above as a sensitive
scope), labels, or deletion.

**One caveat that is not cosmetic.** Google's Limited Use terms forbid using
this data to develop or improve generalized AI models, and the privacy policy
now asserts that LawHand does not. LawHand trains nothing — but Gmail and Drive
content does reach the configured model provider for inference, and the
assertion is only true if *every* provider in that chain is contractually
no-training. OpenRouter is the open question, because it forwards to downstream
providers on terms LawHand does not set. Confirm that before submitting, not
after: it is the same claim in the privacy policy, the verification form, and
the CASA questionnaire, and getting caught out on it in one place discredits it
in the other two.

### 3.6.2 Demo video — recording setup and shot list

Two things get a video rejected far more than anything else: the **OAuth client
ID is not legible on screen**, and a **restricted scope is claimed but never
shown in use**. Both are avoidable, and both are the whole point of the script
below.

**Mechanics**

- Record the **production app on the verified domain** (`getlawhand.com`).
  Localhost, a staging hostname, or a mock is an automatic rejection.
- 1080p, real time. Do not speed up or cut between steps in a way that hides
  a transition — the reviewer is checking that the flow is real.
- Narrate in English, or add English subtitles.
- Upload to YouTube as **unlisted**; paste the link into the form.
- OBS Studio works everywhere and is free. macOS QuickTime and Windows Game Bar
  are fine too. Keep the cursor visible and the browser URL bar on screen.
- Sign in with a Workspace account you control, seeded with **fabricated**
  matters, mail and Drive files. Never record real client data: it is a
  confidentiality breach independent of anything Google requires.
- Expect the "Google hasn't verified this app" interstitial while unverified.
  Show yourself clicking through it. That is normal and not a defect.

**The client ID shot.** During consent, before clicking Allow, pause on the
browser URL bar and zoom so `client_id=...apps.googleusercontent.com` is
readable. It must match the client submitted for verification. This single
frame is the most common reason for a requeue.

**Shot list.** Each restricted scope needs a visible, in-product use, and the
two narrower-scope arguments from 3.6.1 should be *demonstrated*, not merely
asserted:

| # | Scope | Surface | What must be on screen |
|---|---|---|---|
| 1 | — | `getlawhand.com` | The homepage on the verified domain |
| 2 | `openid`, `email`, `profile` | `/login` | Sign in with Google |
| 3 | all | consent screen | App name, full scope list, **client ID in the URL**, the privacy policy link resolving to `/privacy` |
| 4 | `admin.directory.user.readonly` | `/admin?tab=users` | Directory sync listing the domain's staff |
| 5 | `drive` | `/admin?tab=integrations` → Cloud Search | A query finding a Drive file **created before the app existed** |
| 6 | `drive` | `/matters/:id` | Matter folder created and a document uploaded, then the same folder shown in `drive.google.com` |
| 7 | `gmail.readonly` | `/matters/:id` → Correspondence → **Scan now** | Mail searched by correspondent and date, a message filed to the matter |
| 8 | `gmail.send` | any notification trigger | The sent message in the firm's Gmail **Sent** folder |
| 9 | `calendar` | `/calendar` | A LawHand deadline written through to `calendar.google.com` |
| 10 | — | `/admin?tab=integrations` | Disconnect, showing the user can revoke |

Shots 5 and 7 carry the argument. In 5, open the found file and show it
predates the integration — that is `drive.file` failing on camera. In 7, let the
search box and the correspondent/date filter be legible — that is the `q`
parameter `gmail.metadata` forbids.

Close on shot 10. Reviewers look for revocation, and it costs fifteen seconds.

---

## 4. Microsoft — exact steps

### 4.1 Create a company Entra tenant (free)

You cannot create additional workforce tenants from the Microsoft 365 / Entra
admin portal on a free or trial subscription. Use the Azure signup path:

1. `https://azure.microsoft.com/free` — sign up. Use a **new** Microsoft account
   tied to a company address, not your personal one. The signup creates a
   default Microsoft Entra directory (`something.onmicrosoft.com`).
   - Azure free signup asks for a card for identity verification. App
     registrations, Entra ID Free, and multitenant OAuth cost nothing; you are
     not obligated to run paid Azure resources.
2. In **Microsoft Entra admin center → Identity → Overview → Properties**, set
   the organization name to **Perevaga Group LLC**.
3. **Identity → Domain names → Add custom domain** → `getlawhand.com` → add the
   TXT record at your DNS provider → verify. This both looks right on consent
   screens and is the simplest route to publisher-domain verification in 4.4.
4. Create a second Global Administrator account and store its credentials with
   the LLC's records. A tenant with one admin is a single point of failure and a
   diligence finding.

You do **not** need a paid Microsoft 365 license for any of this. Entra ID Free
supports app registrations, multitenant apps, and admin consent.

### 4.2 Register the server-side application

**Entra admin center → Applications → App registrations → New registration:**

- Name: `LawHand`
- Supported account types: **Accounts in any organizational directory (Any
  Microsoft Entra ID tenant — Multitenant)** — per Decision 2.
- Redirect URI (Web), both entries:

```text
https://getlawhand.com/api/auth/microsoft/callback
https://getlawhand.com/api/integrations/microsoft/callback
```

(Constructed at `backend/app/routers/auth.py:1003` and
`backend/app/routers/integrations.py:416`.)

Then:

- **Certificates & secrets → New client secret.** Set a calendar reminder for
  rotation *before* the expiry date; an expired secret takes every customer's
  Microsoft integration down at once.
- **API permissions → Microsoft Graph → Delegated**, add exactly:
  `offline_access`, `User.Read`, `User.Read.All`, `Mail.Read`, `Mail.Send`,
  `Files.ReadWrite.All`, `Sites.Read.All`, `Calendars.ReadWrite`.
  For the Teams opt-in bundle also add `Channel.ReadBasic.All`,
  `ChannelMessage.Send`, `Chat.ReadWrite`, `Team.ReadBasic.All`,
  `TeamsActivity.Send`, `Channel.Create`.
  Keep this list identical to `frontend/src/marketing/integration-scopes.json` —
  `backend/tests/test_public_integration_scopes.py` asserts the published claim
  matches the code, so a drift here becomes a failing test rather than a false
  public statement.
- **Owners:** add the second Global Admin from 4.1.

`Sites.Read.All` grants read across every SharePoint site in a customer tenant.
Sophisticated law-firm IT will push back. The long-term answer is
`Sites.Selected` with explicit per-site grants, already flagged in
`docs/integrations-setup.md`. Not a blocker for this migration, but expect the
question in security review and have an answer.

### 4.3 Register the Office add-in SPA

Separate registration, no client secret — follow `docs/office-pilot-activation.md`
section 1, in the **new** tenant. Values:

- SPA redirect `brk-multihub://getlawhand.com`
- SPA redirect `https://getlawhand.com/office/index.html`
- Application ID URI `api://<new-office-client-id>`
- Delegated scope `office.access`, pre-authorize its own client ID
- Requested access token version `2`

### 4.4 Publisher verification — the one that decides whether firms can install

Without it, consent screens say the publisher is unverified, and many law-firm
tenants enforce a consent policy that **blocks unverified multitenant apps
outright**. Teams store submission also requires it. It is free.

1. `https://partner.microsoft.com` — enroll in the Microsoft AI Cloud Partner
   Program as **Perevaga Group LLC**. You get a Partner One ID / MPN ID.
2. Complete the **legal business profile** verification in Partner Center
   (Microsoft verifies the entity — have formation documents and a business
   address ready). This step takes days, sometimes longer. Start it in parallel
   with everything else; it gates nothing else, and nothing else gates it.
3. Associate the Partner Center account with the new Entra tenant.
4. In the app registration → **Branding & properties**, set the **publisher
   domain** to `getlawhand.com`, then **Add MPN ID to verify publisher**.
   - The verified custom domain from 4.1 step 3 normally satisfies the publisher
     domain requirement.
   - Fallback, if Microsoft asks you to prove domain ownership by file: serve
     `https://getlawhand.com/.well-known/microsoft-identity-association.json`
     containing the new app ID. Add an explicit nginx location for it beside the
     existing `location /.well-known/acme-challenge/` block
     (`nginx/nginx.conf:391`) rather than relying on the SPA static server —
     `frontend` is served by `serve -s dist` (`frontend/Dockerfile:34`), whose
     dotfile handling should not be assumed. Verify with
     `curl -sS https://getlawhand.com/.well-known/microsoft-identity-association.json`
     before clicking verify.
5. Confirm the blue "verified" marker appears on the consent screen in a test
   tenant.

---

## 5. Changes inside this repository

### 5.1 Secrets to replace in the production environment

Nothing here is committed; these are set in the host-managed production `.env`.
Follow the handling rules in `docs/credential_security_operations.md` — never
paste populated values into chat or logs.

```dotenv
GOOGLE_CLIENT_ID=<new>
GOOGLE_CLIENT_SECRET=<new>

MICROSOFT_CLIENT_ID=<new>
MICROSOFT_CLIENT_SECRET=<new>
MICROSOFT_TENANT_ID=organizations   # see Decision 2

OFFICE_ENTRA_CLIENT_ID=<new office SPA client id>
OFFICE_ENTRA_API_AUDIENCE=api://<new office SPA client id>
OFFICE_ENTRA_REQUIRED_SCOPE=office.access

TEAMS_APP_ID=<new teams app guid>
```

Mirror the dev values into the dev1 environment from the `lawhand-dev` Google
project and, ideally, a separate dev app registration.

### 5.2 Tracked files that carry old identifiers

| File | Line | Change |
| --- | --- | --- |
| `teams-app/manifest.json` | 5 | new Teams app GUID |
| `teams-app/manifest.json` | 49 | `webApplicationInfo.id` → new server app client ID |
| `teams-app/manifest.json` | 50 | `resource` → `api://getlawhand.com/<new-client-id>` — retires `legalapp.perevagagroup.com` |
| `teams-app/package.ps1` | 3 | same GUID as manifest line 5 |
| `office-addin/.env.example` | 2-4 | keep placeholder zeros; document the new `api://` shape |

The `<Id>` GUIDs in `office-addin/manifests/outlook.xml:8` and
`word-excel.xml:8` are Office add-in identifiers, **not** Entra client IDs, and
do not change. The Entra binding for the add-in flows through
`VITE_OFFICE_ENTRA_CLIENT_ID` / `VITE_OFFICE_API_SCOPE` at build time and
`OFFICE_ENTRA_*` at runtime.

### 5.3 Scope manifest

No scope change is required by this migration (see Decision 1). If you ever do
revisit the scope set, narrow the constants in
`backend/app/routers/integrations.py:235-259` **and**
`frontend/src/marketing/integration-scopes.json` in the same change.
`backend/tests/test_public_integration_scopes.py` will fail if they drift, which
is the intended guardrail — the public `/requirements` page must never overstate
or understate what LawHand asks for.

---

## 6. Cutover and re-consent runbook

Run this only once the new Google client is **published and verified** and the
new Microsoft app is **publisher-verified**. Cutting over to an unverified
client puts an "unverified app" interstitial in front of every customer.

1. **Announce.** If any firm is already connected, tell their admin the date and
   that they will need to re-approve. Do not surprise a law firm's IT with an
   unexpected consent prompt — it reads as a phishing attempt.
2. **Prove on dev1 first.** Deploy the new dev credentials to dev1 and run a
   full round trip per provider: login callback, admin consent callback, user
   consent callback, `GET /api/integrations/status` with no missing scopes, one
   forced token refresh, one licensed Graph/Gmail/Drive/Calendar operation, and
   disconnect. This is the proof list from `docs/integrations-setup.md`.
3. **Deploy production** with the new values, via the `lawhand-deploy` skill and
   its promotion gate.
4. **Clear the dead credentials.** Existing `user_oauth_tokens` rows for
   `provider in ('google','microsoft')` are unrefreshable against the new client
   and must not be left to fail silently. Have each user hit
   `POST /api/integrations/{google,microsoft}/disconnect`
   (`backend/app/routers/integrations.py:1877,1909`), or purge those rows
   directly — take a database backup first, and leave Zoom Phone and QBO rows
   untouched.
5. **Re-consent, admins first.** Tenant admin re-runs
   `/api/integrations/{provider}/connect?intent=admin`, then users re-run the
   user flow. Teams tenants re-run `/adminconsent`.
6. **Verify.** `GET /api/integrations/status` clean for each tenant; one live
   read and one live write per enabled provider; scheduler sync runs
   (`integration_sync_runs`) succeeding rather than erroring.
7. **Ask each customer to remove the stale enterprise application** for the old
   Microsoft app ID from their tenant, and to revoke the old Google app at
   `https://myaccount.google.com/permissions`. Leaving an orphaned grant that
   points at a personal developer account is exactly the finding you are doing
   this migration to eliminate.
8. **Decommission.** Delete the old Google OAuth client and the old Entra app
   registration only after a full billing cycle of clean operation — deleting
   early removes your ability to roll back.

---

## 7. Everything else on a personal account

Same principle, same exercise, lower urgency (no customer re-consent blast
radius, but full diligence exposure):

- **Zoom meetings app** — Zoom Marketplace account under the LLC.
  (`ZOOM_CLIENT_ID`; Zoom *Phone* is already per-customer and is fine.)
- **Intuit / QuickBooks developer account** — `QBO_CLIENT_ID`.
- **Stripe** — account legal entity and bank details under the LLC.
- **Domain registrar for `getlawhand.com`** — the single most important asset in
  this list; every verification above chains off it.
- **Cloudflare / IONOS** — billing and admin contacts.
- **Google Search Console / Analytics** — see
  `docs/GOOGLE_SEARCH_AND_BUSINESS_SETUP.md`; move to `admin@getlawhand.com`.
- **GitHub organization** — repository ownership.
- **Anthropic / OpenAI API accounts** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
  billing entity.

The test for each: *if this person's account were disabled tomorrow, what stops
working, and can the company get it back without them?*

---

## 8. Checklist

**Decisions**
- [ ] Decision 1: confirmed Track A — keep restricted scopes, CASA is in scope
- [ ] Decision 2: `MICROSOFT_TENANT_ID` = `common` or `organizations`
- [ ] Decision 3: entity and domain confirmed as Perevaga Group LLC / getlawhand.com
- [ ] Confirmed current Google consent screen publishing status (Testing = 7-day token expiry)

**Google**
- [ ] Cloud Identity Free on `getlawhand.com`, domain TXT-verified
- [ ] `oauth@getlawhand.com` role account, two people with access
- [ ] `lawhand-prod` + `lawhand-dev` projects created **inside the organization**
- [ ] Gmail / Drive / Calendar / Admin SDK / People APIs enabled
- [ ] `getlawhand.com` verified in Search Console
- [ ] Branding, External audience, scopes configured
- [ ] Privacy policy live, per-scope, with Limited Use disclosure
- [ ] OAuth web client created, both redirect URIs byte-exact
- [ ] Verification submitted; demo video recorded
- [ ] CASA assessor engaged — **start this first, it is the critical path**
- [ ] App published to In production

**Microsoft**
- [ ] New Entra tenant via Azure free signup, org name set to Perevaga Group LLC
- [ ] `getlawhand.com` added and verified as a custom domain
- [ ] Second Global Administrator created
- [ ] `LawHand` multitenant app registered, both redirect URIs, secret stored, rotation reminder set
- [ ] Delegated Graph permissions match `integration-scopes.json` exactly
- [ ] Office add-in SPA registration created per `docs/office-pilot-activation.md`
- [ ] Partner Center enrollment + legal business profile verified
- [ ] Publisher verification complete, blue marker confirmed in a test tenant

**Repo and cutover**
- [ ] `teams-app/manifest.json` + `package.ps1` updated; `perevagagroup.com` resource URI retired
- [ ] Scope constants unchanged (or changed in both places together)
- [ ] New credentials in dev1; full round trip proven per provider
- [ ] Production deployed via the promotion gate
- [ ] Stale `user_oauth_tokens` cleared (backup taken first)
- [ ] Admin + user re-consent completed per tenant; status clean
- [ ] Customers asked to remove old enterprise app / revoke old Google grant
- [ ] Old client and old app registration deleted after a clean cycle

**Other accounts**
- [ ] Zoom marketplace, Intuit, Stripe, registrar, Cloudflare/IONOS, Search Console, GitHub org, model-provider billing

---

## Appendix — what a buyer will ask

Have a one-page answer to each before you go to market:

1. Who legally owns the Google Cloud project and the Entra tenant, and what
   document proves it?
2. Is any production credential recoverable only through an individual's
   personal account or personal MFA device?
3. Is the Google app verified, in production, and — if restricted scopes are in
   use — currently CASA-assessed, with the renewal date on a calendar?
4. Is the Microsoft publisher verified, under the selling entity?
5. Can a customer revoke LawHand's access entirely, on their own, without
   contacting you? (Yes: provider-side revocation plus the `disconnect`
   endpoints.)
6. What is the customer-visible blast radius of rotating any one provider
   secret, and is that rotation rehearsed?
