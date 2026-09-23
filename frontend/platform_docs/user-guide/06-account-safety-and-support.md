---
slug: account-safety-and-support
title: Account safety & help
description: Protect your account and sessions, control what connected assistants can reach, and give support the context needed to help.
order: 60
read_time: 8 min
icon: shield
---

# Account safety & help

Your account represents your identity in approvals, edits, time, and audit history. Keep it personal and protect it like any other system that holds client information. Most of the controls in this chapter are on [your profile](/profile); open it from the person icon at the bottom of the navigation.

## Everyday safety

- Use your own account and your firm's approved sign-in method.
- Lock your device when you step away, and sign out on shared or temporary devices.
- Confirm the matter and recipients before working with sensitive content.
- Do not paste passwords, tokens, recovery codes, or unrelated client data into the assistant.

## Your profile

[Your profile](/profile) shows your name, email, professional role, account access, and billing tier, followed by the controls below, links to the **User guide** (and the **Administrative guide** for administrators), your assigned matters, and your recent time totals. Your role, license, and module access are managed by an administrator.

### Set your professional context

The assistant uses this context to tailor general chats to your work; matter chats also use the context saved on that matter.

1. Under **Professional context**, fill in **Professional role**, **Job title**, **Office location**, and **Primary jurisdictions** (separate several with commas).
2. Select **Save context**. The message "Your profile context has been saved." confirms it.

## Protect private details

**Protect private details** redacts detected personal details before eligible requests go to an AI provider. It is a safeguard, not a substitute for an approved private route.

![The profile's Protect private details switch, the Signed in elsewhere control, and the Workspace MCP assistants list with one connected assistant](/guide-assets/profile-security.webp "The security controls on your profile")

1. Select the **Protect private details** switch.
2. LawHand asks you to confirm. Turning it on revokes every connected external assistant (such as Claude, ChatGPT, or Codex), and the message names the ones it will disconnect.
3. Confirm. The status line under the switch says what is now in effect.

Native LawHand features keep working with the safeguards on. Connected assistants must be reconnected, from the assistant, after you turn protection off again.

## Sign out of other devices

Each sign-in leaves a session on that device until it is used or reaches its maximum age. If you have left yourself signed in somewhere you no longer control:

1. Under **Signed in elsewhere**, select **Sign out everywhere else**.
2. Confirm. Anyone signed in as you on another computer, phone, or browser is signed out immediately; you stay signed in here.

This ends browser sessions only. Connected assistants keep their own access, so revoke them separately below. Resetting your password ends both.

## Connected assistants

If your firm enables Workspace MCP, you can connect an external assistant, such as Claude or ChatGPT, to your LawHand workspace. A connection is made through an explicit consent step, is limited to the scopes shown when you approve it, acts only as you, and is audit logged.

**Workspace MCP assistants** on your profile lists every assistant connected to your account. For each one you see its status, the scopes it holds (for example "Find matters and read bounded matter context" or "Create tasks that start in human review"), and when it was **Created**, when it **Expires**, and when it was **Last used**.

- Select **Revoke** for any connection you do not recognize or no longer use, then **Revoke access** to confirm. The assistant loses access immediately and must be connected again from the start.
- Select **Refresh** to reload the list.

Review the list when you change assistants, retire a device or client, and before you leave a matter or a role. An assistant reaches the workspace with your permissions, so treat what it can retrieve as though you retrieved it yourself, and verify anything it drafts or quotes before relying on it.

If connections are blocked, the panel says why: **Protect private details** is on, your administrator disabled Workspace MCP for your account, your account needs a Standard license, or the account is inactive. After a password reset, a **Waiting to be reconnected** box lists the assistants the reset disconnected; reconnect each one from the assistant itself using the server URL shown (select **Copy URL**).

## If you suspect unauthorized access

1. Select **Sign out everywhere else** on your profile.
2. **Revoke** any connected assistant you do not recognize.
3. Reset your password with **Forgot password?** on the sign-in page. A reset ends every session and every assistant connection.
4. Tell your administrator right away. Include the approximate time and what you observed, but never send credentials through chat or email.

Follow your firm's incident process for a suspected security or privacy incident without delay.

## Get useful help

Start with the **Guide** button in the top bar: it opens the section of this guide for the screen you are on. If you still need help, contact your LawHand administrator first for access, assignments, integration status, or firm policy.

When you report a problem, include:

1. the page and the action you were using;
2. what you expected to happen;
3. what happened instead;
4. when it happened, and whether it repeats; and
5. any request or error ID shown on screen.

The **Version & release notes** panel on your profile shows the version and build you are using, which helps support reproduce a problem.

Use redacted screenshots when they make the issue clearer. Do not copy full client documents into a support message unless your approved support process specifically asks for them.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| An external assistant says it cannot reach LawHand | **Protect private details** is on, your access was turned off, or the grant was revoked | Read the message in **Workspace MCP assistants**; turn protection off or ask your administrator, then reconnect from the assistant. |
| **Save context** shows an error | The profile could not be saved, often a brief connection problem | Try again; if it repeats, report it with the time it happened. |
| You were signed out unexpectedly | Someone used **Sign out everywhere else**, your password was reset, or the session expired | Sign in again. If you did not expect it, follow [If you suspect unauthorized access](#if-you-suspect-unauthorized-access). |

## Related chapters

- [Start here](/guide/getting-started)
- [Assistant & add-ons](/guide/assistant-and-add-ons)
- [What connected integrations can view](/guide/integration-transparency)
