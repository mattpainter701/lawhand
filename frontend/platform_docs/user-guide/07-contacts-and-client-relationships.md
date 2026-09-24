---
slug: contacts-and-client-relationships
title: Contacts & client relationships
description: Keep one dependable record for every person and organization, manage client relationships, and run and record conflict searches.
order: 70
read_time: 10 min
icon: users
---

# Contacts & client relationships

LawHand keeps people and organizations in two connected places:

- [Contacts](/contacts) is the firm-wide directory of everyone involved in your work: clients, opposing parties, witnesses, experts, vendors, referral sources, and others.
- [Clients & CRM](/clients) is the client-focused view, with each client's lifecycle stage, contact preferences, billing preferences, matters, and activity.

[Conflict Search](/conflicts) searches both before you take on or expand a representation, and saves exactly what the reviewer saw.

## Find before you create

Duplicates split a person's history across two records. Before adding anyone:

1. Open [Contacts](/contacts) and type in **Search name, email, org…**.
2. Try spelling variations, a prior name, the organization, and the email address or phone number.
3. If a likely match appears, open it and check the details rather than creating another record.

Narrow the list with **All roles** and **All types** (**Person** or **Organization**).

## Add a contact

1. On [Contacts](/contacts), select **New Contact**.
2. Choose the **Type**: **Person** or **Organization**.
3. Choose the **Role**: client, opposing party, witness, expert, vendor, referral, or other.
4. Enter the **First Name** and **Last Name**, or the **Organization Name**.
5. Add the **Email** and **Phone** you will actually use.
6. Add **Notes** only for operational details your firm permits, then select **Create Contact**.

Use neutral, factual language in notes. Do not put legal strategy, health information, payment details, or privileged advice in a general contact note.

## Work with a contact's record

Open a contact to see four tabs:

- **Profile**: name or organization, email, phone, secondary phone, role, notes, and when the record was added.
- **Matters**: the files the contact is linked to.
- **Communications**: calls, emails, and meetings logged with the contact.
- **Tasks**: work that involves the contact.

To correct a detail, select **Edit**, change the fields, and select **Save**. Check the **Matters** tab first: a renamed organization or corrected email affects every matter the contact is linked to.

## Manage clients

Open [Clients & CRM](/clients). The summary across the top counts **Active clients**, **Prospects**, clients with **SMS consent**, and **Former / inactive** relationships.

- Search by name, email, phone, or client number.
- Filter by lifecycle stage (prospect, active, inactive, former) and by **People** or **Organizations**.
- Sort by **Name**, **Newest**, or **Recently contacted**.

### Add a client

1. Select **New client**.
2. Choose the **Entity type** and the **Lifecycle** stage. Use **prospect** until the firm accepts the engagement.
3. Enter a **Client number** if your firm uses them, such as `CL-1042`.
4. Enter the name, **Email**, and **Primary phone**.
5. Choose the **Preferred contact** method (email, phone, sms, mail, or portal) and, if known, the **Preferred payment** method.
6. Record the **Referral source**, such as "Existing client" or "Bar referral".
7. Tick **SMS consent recorded** only when the client has actually agreed to receive text messages.
8. Select **Create client**.

### Import or export clients

- **Import CSV** loads an existing client directory. When it finishes, LawHand reports how many clients were created, updated, and skipped, and lists any rows it could not import.
- **Export** downloads the current directory as a CSV file.

### A client's record

A client record has five tabs:

- **Profile**: identity and lifecycle stage, contact details and consent to SMS alerts and email updates, the mailing address, and an emergency contact.
- **Matters**: every matter for the client.
- **Activity**: the client's communications and tasks.
- **Billing & integrations**: the preferred payment method, how invoices are delivered (email, mail, or portal), payment terms, and billing notes, plus the client's QuickBooks and Stripe customer references.
- **Internal notes**: firm-only context that is never sent to QuickBooks, Stripe, or the client portal.

To change a record, select **Edit client**, make your changes, and select **Save changes**. Administrators can select **Sync to QuickBooks** to create or update the matching QuickBooks customer. Payment credentials are never stored on the client record.

## Link people to a matter

A contact's role on a matter is recorded on the matter, not the contact. The same person can be the client on one matter and a witness on another.

1. Open the matter from [My Matters](/matters).
2. Select **Matter settings**, then **People**.
3. In the **Parties** panel, select **Add Party**, choose the **Contact**, and choose the **Role**: **Client**, **Plaintiff**, **Defendant**, **Petitioner**, **Respondent**, **Opposing Party**, **Counsel**, **Witness**, **Expert**, or **Other**.
4. Add optional **Notes**, such as "lead counsel, retained 2024-01", and select **Add Party**.

**Client** describes the firm's relationship; it does not mean the client is the plaintiff. See [Define caption parties](/guide/matters-and-documents#define-caption-parties) for litigation captions.

Being linked to a matter does not give anyone portal access. Portal invitations and sharing are separate, deliberate steps; see [Teams & client portals](/guide/teams-and-client-portals#client-and-participant-portals).

## Run a conflict search

Run a search before accepting or expanding a representation, and whenever a new party joins a matter.

![The Conflict Search page with the New search form, a saved check showing two potential matches including one restricted matter reference, and the Record review decision form](/guide-assets/conflict-search.webp "A saved conflict check that needs review")

1. **Run and save search** runs the search and saves the result.
2. A restricted matter reference means the search found a matter you are not permitted to see.
3. **Close and lock record** saves the attorney's decision and locks the check.

### Search

1. Open [Conflict Search](/conflicts).
2. Enter a **Search label** you will recognize later, such as "Smith intake conflict review".
3. Under **People and known aliases**, enter each person's name and any other names they use, one per line or separated by commas.
4. Under **Organizations**, include related entities and former names.
5. Add any **Email addresses** you know.
6. Optionally choose a matter under **Link to a matter**. Only your assigned matters are listed.
7. Select **Run and save search**.

### Review the result

The saved check shows the number of **Potential matches** and **Restricted matter references**. Each match names the contact, the field that matched (for example "Matched organization name: Northgate Properties"), and the matters it is linked to.

> [!IMPORTANT]
> A restricted matter reference is a match on a matter you are not allowed to identify. Stop and ask an administrator or conflicts reviewer to resolve it. Do not try to find the matter through another screen.

"No potential matches were returned" describes the database search only. It is not clearance: attorney review is still required.

### Record the decision

1. Under **Record review decision**, choose **No conflict found after review**, **Potential conflict identified**, or **Cleared with conditions**.
2. In the notes, record the sources you reviewed, your reasoning, and any escalation, waiver, or conditions.
3. Tick the confirmation that the decision reflects attorney review.
4. Select **Close and lock record**.

A closed check cannot be changed. Select **Report** at any time to download the check as a PDF for the file. **Saved checks** lists every earlier search.

## Communications and follow-up

Log meaningful contact through the matter's **Activity** section or [Communications](/communications). Create a [task](/tasks) when a promise, callback, document request, or deadline needs an owner. Do not use contact notes as a hidden task list.

## Data quality checks

Before relying on a contact or client record, confirm that:

1. the identity matches the intended person or organization;
2. the email and phone are current;
3. matter links use the correct role;
4. duplicates have been handled through your firm's process; and
5. communication preferences, such as SMS consent, are respected.

If a record appears to belong to another firm or an unrelated client, stop and tell an administrator rather than editing it.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| "Contact was not created" | A required field is missing, or the connection dropped | Check the name fields and try again. |
| A client import skipped rows | The rows were duplicates or missing required values | Read the import summary, correct the rows in the CSV, and import them again. |
| **Close and lock record** is disabled | The review notes are empty or the confirmation is not ticked | Record your reasoning and tick the attorney-review confirmation. |
| A match shows a lock and a restricted reference | The match is on a matter you are not permitted to see | Ask an administrator or conflicts reviewer to resolve it. |
| A matter is missing from **Link to a matter** | Only your assigned matters are listed | Ask the matter's responsible attorney to add you, or run the search unlinked. |

## Related chapters

- [Matters & documents](/guide/matters-and-documents)
- [Intake & call reception](/guide/intake-and-call-reception)
- [Teams & client portals](/guide/teams-and-client-portals)
