---
slug: users-roles-and-licensing
title: Users, roles & licensing
description: Invite and remove people, give them the right roles and views, assign licenses and premium AI, and control connected assistants.
order: 20
read_time: 12 min
icon: users
---

# Users, roles & licensing

Three separate controls decide what a person can do in LawHand:

- the **account** says who they are;
- **roles** say what they may do and which functions they see; and
- **licensing** says which paid capabilities they have, such as a standard seat and premium AI.

Treat each one explicitly. Fixing a missing matter assignment by granting administrator settings, for example, solves the wrong problem.

## The Users tab

Open [Users](/admin?tab=users).

![The Users tab listing the firm's people with their roles, billing rates, join dates, 30-day AI usage, MCP access status, and active toggles, plus one pending invitation](/guide-assets/admin-users.webp "Administration: Users")

1. **Invite user** sends an invitation.
2. The role button shows each person's roles; select it to change them.
3. **Manage** under **MCP access** controls whether the person can connect an external assistant.
4. A pending invitation offers **Resend invite** and **Revoke** instead of the active toggle.

The count above the list shows how many people are active, invited, and inactive; **Show inactive** reveals deactivated accounts. Each row also shows the person's billing **Rate**, when they joined, and their AI **Usage (30d)** in dollars and tokens.

## Invite a person

1. Select **Invite user**.
2. Enter their individual business **Email address** and, optionally, their **Full name**.
3. Choose the **Role**: **User** for most staff, **Accountant** for finance staff who need billing screens, or **Admin** for administrators.
4. Select **Send invitation**. The link expires in 7 days.

The person appears as **Invited** with the link's expiry date until they accept. If the link expires or was lost, select **Resend invite**; the previous link stops working. **Revoke** cancels an invitation you sent by mistake.

Never put temporary passwords, tokens, or recovery codes in an invitation.

## Change a person's access

- **Roles.** Select the role button in the person's row, tick the roles that match their duties, and confirm **Update roles**.
- **Billing rate.** Select the rate (or **No rate — set**) to edit the person's default hourly rate for time entries, then save it.
- **Deactivate.** Turn off the **Active** toggle. The person can no longer sign in, and their records and history stay intact. If they own the consent for a connected service, LawHand warns you first with **Deactivate consent owner?**, because that connection may stop working. Turn the toggle back on to reactivate a returning person instead of creating a second account.
- **Aliases.** **Manage aliases** records other addresses the person uses, such as a send-as address. LawHand emails a verification link to the address; until its owner verifies it, the alias shows **Pending verification** and is not treated as theirs. Verified aliases let LawHand recognize mail from that address, for example when capturing correspondence on matters they are assigned to.

> [!WARNING]
> Before you change or deactivate an administrator, make sure another administrator account exists and can sign in. Do not lock the firm out of its own settings.

## Roles and what people see

Open [Roles](/admin?tab=roles). A role combines **access capabilities**, which decide what a person may do, with an optional **view profile**, which decides which functions appear in their navigation.

### Create a role

1. Enter a **Role name**, such as "Paralegal".
2. Under **View profile**, choose a **View starting point**: **Receptionist**, **Finance**, **Secretary**, **Paralegal**, **Attorney**, or **Partner**. Or keep **No view restriction**.
3. Adjust the **Visible functions** so the role sees what its work needs.
4. Choose the role's **Access capabilities**.
5. Select **Create role**, then assign it to people on the **Users** tab.

Prefer reusable job-function roles over one-off permission collections. The legacy **Admin**, **Accountant**, and **User** roles still decide high-level navigation, so test custom capabilities against the exact workflow they should allow.

### How view profiles combine

- **Receptionist** starts with Intake, Call Intake, Conflict Search, Clients & CRM, Tasks, and Calendar. **Partner** includes the Attorney functions plus Invoices, Trust Accounting, and Reports.
- A view profile only hides or shows functions. It does not revoke a permission or block a direct link; control access with capabilities.
- A person with several roles sees the combined functions of the roles that have a view. Roles without a view do not widen it, and if none of their roles has a view, the full navigation stays available.
- **Hide all functions** creates an empty view. Administration, the profile, and sign out always stay reachable for authorized staff.
- Plan and license restrictions always apply. People see role changes after they reload LawHand.

Each person can also personalize their own navigation with the **Customize navigation** gear at the bottom of it: hide functions or reorder them, then **Save layout**. The layout follows their account across devices. **Reset to role defaults** clears their personal changes.

When you change a role, compare the person's actual duties with its capabilities, check for incompatible financial, approval, or administrative powers, save, and confirm the result with the person.

## Licensing

Open [Licensing](/admin?tab=licensing). It shows the firm's **Billing Tier** (**Per-seat subscription** or **Pay-as-you-go**), **Seat Usage**, and a **User Licenses** list.

1. To change how many seats the firm pays for, enter the number under **Seats** and select **Update Seats**.
2. In **User Licenses**, turn **Standard** on for each person who needs a seat.
3. Turn **Premium AI** on only for people whose work needs the more capable models. Premium AI requires a standard license.
4. On pay-as-you-go plans, set a **Budget cap** per person, or leave **No cap**.

A person can exist without an active standard license, for example to keep their records, but they cannot use licensed features. Watch for licensed people who no longer use LawHand, and never share accounts to save seats. Confirm the commercial effect of seat changes under [Subscription](/admin?tab=billing).

## Control connected assistants

The **MCP access** column governs Workspace MCP: whether each person may connect an external assistant, such as Claude or ChatGPT, to their own LawHand workspace. The status explains the current state:

| Status | Meaning |
| --- | --- |
| **Ready to connect** | Allowed, with no connections yet. |
| **Connected (1)** | One assistant is connected; select **Manage** to review or revoke it. |
| **Disabled for user** | You turned access off for this person. |
| **Disabled by firm** | Workspace MCP is off for the whole firm. |
| **Paused by Privacy Mode** | The person turned on **Protect private details**; only they can turn it off. |
| **Unlicensed** | The person needs an active license. |
| **Inactive account** | The account is deactivated. |

Turn the toggle in the column off to end a person's connected assistants immediately. Grant access to the people whose work needs it rather than to everyone by default.

The firm-wide switches are in [Integrations](/admin?tab=integrations&integration=mcp) under **MCP servers** > **Tenant controls**: **Enable Platform MCP for this tenant**, and **Enable Platform MCP for new users**, which sets the default for people invited or synced from your directory later. Choose that default deliberately: it decides whether a new hire can connect an outside assistant on their first day. See [MCP server operations](/admin?tab=guide&chapter=mcp-server-operations).

## Joiners, movers, and leavers

- **Joiner:** confirm identity, invite with the right role, assign a license and premium AI if needed, check integration prerequisites such as their mailbox connection, and arrange training.
- **Mover:** remove old roles before adding new ones; review matter access and approval authority.
- **Leaver:** deactivate promptly, reassign their open work and matters, turn off their MCP access, remove their license, and verify each step. Their authored records stay in place.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| An invited person never received the email | The message was filtered, or the link expired | Check the address, then **Resend invite**. |
| A person cannot see a function their role should show | They have not reloaded, or another role's view is narrower than you expect | Ask them to reload; review every role they hold. |
| A person sees a function but cannot use it | The view shows it, but a capability or license is missing | Add the capability to their role or assign the license. |
| **Premium AI** cannot be turned on | The person has no standard license | Turn on **Standard** first. |
| An assistant cannot connect for one person | Their status is **Disabled for user**, **Paused by Privacy Mode**, or **Unlicensed** | Fix the cause the status names. |

## Related chapters

- [Administrator overview](/admin?tab=guide&chapter=admin-overview)
- [Subscription, usage & alerts](/admin?tab=guide&chapter=subscription-usage-alerts)
- [MCP server operations](/admin?tab=guide&chapter=mcp-server-operations)
