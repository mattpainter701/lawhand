---
slug: assistant-and-add-ons
title: Assistant & add-ons
description: Ask the assistant grounded questions, check every answer against its sources, approve the work it proposes, and use your firm's add-on modules.
order: 50
read_time: 12 min
icon: sparkles
---

# Assistant & add-ons

LawHand's assistant can summarize a file, build a chronology, compare standards, and prepare drafts from your firm's material and, where your firm allows it, public legal authority. It is a collaborator inside a controlled workflow, not the final decision-maker: every answer shows what it relied on, and nothing it proposes is sent, filed, or saved until a person approves it.

## Start a conversation

Open the [Assistant](/chat) from the navigation. On a matter, use **Start Chat** in Quick Actions or the matter's **Chat** section so the conversation starts with that matter's context.

![The Assistant with the conversation list, a question about a settlement draft, the answer with numbered citations, and the Cited Sources table listing two matter documents and a matter record](/guide-assets/assistant-answer.webp "An answer with its cited sources")

1. The context line shows what the assistant uses: your profile, plus the linked matter. **Change** links a different matter.
2. **Response settings** (shown as **Standard** or **Premium**) chooses the response model and the sources.
3. **Cited Sources** lists every source the answer relied on, numbered to match the citations in the text.
4. **Attach** adds a PDF, Word, or text document to the conversation.

To ask a question:

1. Select **New conversation**, or open an earlier one from the **Conversations** list.
2. Type your question in the message box, or choose one of the suggested starting points, such as "Build a chronology from the available sources".
3. Press Enter to send. Shift+Enter starts a new line.

While the assistant is responding, you can type a follow-up and select **Queue**; it is sent when the current answer finishes. If a response fails, queued messages are held so nothing is sent out of order.

### Link a matter

A matter link gives the assistant that matter's record, its documents, and its **AI Context**.

1. Select **Change** on the context line.
2. Under **Choose matter context**, search by matter, client, or case number, and select the matter.

The line then reads "Using your profile + *matter name*". To give the assistant standing instructions for a matter, such as the client's goals or the preferred tone for drafts, open the matter's **Settings**, choose **AI Context**, add the details, and select **Save AI Context**. The summary, jurisdiction, your role, and the stage are added automatically when they are available.

### Choose response settings

Select **Response settings** to choose:

- **Standard** for everyday research and drafting, or **Premium** for more complex analysis. Your firm decides which routes may see private material; if a Standard route is public and general only, the panel says it excludes matters, attachments, and private context.
- **Public case law**, to include available public authorities alongside firm and matter sources. If your firm has turned it off, the assistant answers from firm and matter sources only.
- **Protect private details**, to redact detected personal details before eligible requests go to an AI provider. Turning it on disconnects external assistants connected to your account; see [Account safety & help](/guide/account-safety-and-support#protect-private-details).

A conversation remembers its settings when you reopen it.

## Ask better questions

State the matter, jurisdiction, task, desired format, and important constraints. Compare:

- **Vague:** "What about the settlement?"
- **Useful:** "Summarize the open issues in the second settlement draft before Thursday's conference, and list what we still need from the client. Answer as a numbered list."

Point the assistant at the right material: link the matter, attach the document, or name the file. Separate facts from assumptions, and ask it to call out uncertainty and missing information. For research, ask for the controlling authority in your jurisdiction and then inspect each cited source yourself.

## Attach documents

1. Select **Attach** and choose a PDF, Word (.docx), or text file.
2. Wait for the attachment to appear with your message, then ask your question.

An attachment stays available for follow-up questions in the same conversation. It does not become searchable in other conversations or part of the matter's documents. Saving a file to a matter, attaching it to a conversation, and indexing it for search are separate steps.

The assistant receives bounded text from an attachment. A long document may supply only its opening 4,000 characters, and the attachment's row in **Cited Sources** says so: its pinpoint reads "Only the opening 4,000 characters" instead of "Full attached document". To ask about a later section, paste or attach that section. Scanned pages need text extraction or OCR before they can support an answer.

## Read the answer and its sources

Numbers in brackets, such as **[1]**, link to the matching row in **Cited Sources**. Each row shows:

- the source's name, with a badge for its origin, such as **Matter document**, **Matter record**, or a public authority;
- a **Cited** tag, and a pinpoint such as a page or row range when one is known;
- the reference, such as a section or citation; and
- the excerpt the assistant relied on.

Public authorities also show their jurisdiction, catalogue status, and when they were retrieved and last synchronized. The **References** strip summarizes how many sources were cited and retrieved.

Answers are marked with review tags. The **Review required** key in the header explains them:

| Tag | Meaning |
| --- | --- |
| **cited** | Supported by a retrieved source. Follow the link to check it. |
| **verify** | Plausible but not fully supported. Check the source or the pinpoint. |
| **model** | The assistant's own general reasoning, not a retrieved source. |
| **uncertain** | The assistant is unsure. Treat it as an open question. |
| **firm context** | Drawn from matter or firm documents rather than public authority. |

If the status reads "Response complete — public authority unavailable", public research did not complete. The message may still contain a draft or general reasoning, but no authority was retrieved or checked for it. Check this status again when you reopen the conversation.

## Review every result

Before you use any output outside LawHand:

- verify names, dates, amounts, quotations, and citations against the sources;
- check the governing jurisdiction and current law;
- remove unsupported conclusions;
- confirm privilege, confidentiality, and recipient scope; and
- obtain the approval your firm requires.

An authoritative tone is not evidence of accuracy. If the assistant cannot reach a source, provide the document or narrow the task.

## Approve work the assistant proposes

The assistant can propose work, such as a task, a client email or text message, or a matter document. A proposal appears in the conversation as a card marked **Proposed for your approval**, and the card says exactly what approval will do.

- **Approve** creates the proposed task. For an email, the button reads **Approve and send**; for a document, **Approve and save .docx**.
- **Edit draft** (or **Edit document**) lets you change the text first. Select **Done editing** when you finish.
- **Hide for now** puts the card away without approving it. You can also review it on the work board.

Email recipients come from the matter's parties and cannot be changed on the card. Nothing is sent, filed, or saved until someone approves it, and approving a document does not deliver it to the client.

## Manage conversations

- **Rename.** Select the conversation title, type a new one, and press Enter.
- **Find.** Use **Search conversations** in the list, or **Search messages** from the **Conversation options** menu (⋮).
- **Keep.** **Pin conversation** keeps it at the top of the list.
- **Export.** **Export conversation** from the **Conversation options** menu saves a copy.
- **Delete.** Select the bin, then **Delete conversation**. This permanently deletes the conversation and its messages.

The **Sources** tab next to **Conversations** shows the firm source library and the coverage and freshness of public legal authority available to the assistant.

## Add-on modules

[Add-on Modules](/plugins) lists the specialized practice workflows your firm has enabled, such as estate administration, domestic relations, mediation, or renewal tracking. A module may add its own portfolio, structured intake, or matter-level tools. The same review discipline applies: structured fields and generated output support professional judgment but do not replace it. See [Add-on modules](/guide/add-on-module-management) for trials, setup, and configuration.

If a module says setup is incomplete, contact an administrator. Do not invent firm-wide profile information just to clear a setup step.

## Report a questionable result

Preserve the prompt, the relevant source, the output, and the matter context. Do not keep retrying with confidential information if you suspect the wrong data scope or an integration problem. Stop and tell your administrator when tenant boundaries, permissions, or source attribution appear wrong.

## Troubleshooting

| What you notice | Likely cause | What to do |
| --- | --- | --- |
| The assistant ignores your attachment or matter | The selected route is public and general only | Open **Response settings** and choose a route approved for private context, or ask your administrator. |
| An answer has no **Cited Sources** | Nothing relevant was retrieved; the answer is general reasoning | Link the matter, attach the document, or narrow the question. |
| "Response complete — public authority unavailable" | Public research did not complete | Treat the answer as unresearched; try again later or check authority yourself. |
| Questions about a long attachment miss later sections | Only the opening part of the document reached the assistant | Check the coverage label; attach or paste the section you need. |
| **Public case law** cannot be turned on | Your firm has turned public case law off | Work from firm and matter sources, or ask your administrator. |
| **Approve and send** is not offered on an email card | The proposal was already approved, hidden, or is historical | Open the task on the work board to see its state. |

## Related chapters

- [Matters & documents](/guide/matters-and-documents)
- [Account safety & help](/guide/account-safety-and-support)
- [Add-on modules](/guide/add-on-module-management)
