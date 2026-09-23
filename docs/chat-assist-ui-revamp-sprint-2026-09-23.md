# Chat Assist UI Revamp — Sprint CA-1

Date: 23 September 2026. Branch `claude/chat-assist-ui-revamp-7azykg`.

## Why

Owner feedback on the assistant chat:

1. The UX is clunky, and it breaks down going from a workstation to a phone.
2. The tag key is hard to see through.
3. It is hard to queue messages.
4. It is hard to keep several chats going.

## What was actually wrong

| Complaint | Root cause in the code before this sprint |
| --- | --- |
| Several chats | `ChatPage.handleSend` refused to send while `countStreamingChatGenerations() > 0` — **any** conversation answering locked every other one ("Another response is still finishing"). The server never needed this: `_try_conversation_generation_lease` in `backend/app/routers/chat.py` locks **per conversation**. Matter linking was also blocked by other threads' answers. |
| Queueing | The composer textarea was `disabled={disabled \|\| isSending}` — you could not even type the next question while an answer streamed, let alone line it up. |
| Tag key | `ReviewTagLegend` was pinned `sticky top-0` over the transcript with a translucent `bg-brand-bg/95` + `bg-brand-surface/95` background, so answers scrolled visibly through it. On a phone it wrapped to three lines of permanently covered screen. The inline tags themselves were 9px, and brand amber/green on their 10% tints fell below 3:1 contrast. |
| Workstation → phone | On a 390×844 phone the thread had: app header, chat header, a separate matter-context card, the sticky legend, a background-status bar, the composer and the bottom nav — the answer got a few lines. `Messages` called `scrollIntoView` on every token, dragging a reader who had scrolled back down to the bottom. Enter always sent (no newline on touch keyboards). Settings popovers were anchored to their button and ran off the left edge of small screens. On a wide monitor, the transcript had no max width. |

## Sprint goal

Make the assistant a place where you can run several lines of work at once, line up the next question without waiting, read the review tags at a glance, and use it comfortably on a phone.

## Stories and acceptance

All stories below shipped in this branch.

### CA1.1 — Several chats at once
- A conversation sends immediately while other conversations are answering.
- A tab runs at most `MAX_PARALLEL_CHAT_RESPONSES` (3) answers at once. The server's generation pool is 3 + 2 overflow per worker (`DATABASE_GENERATION_POOL_SIZE`), so one person must not be able to fan out every thread. A send beyond the cap queues and says why.
- Matter context is blocked only by that conversation's own in-flight or queued work.
- Answers keep streaming when you switch threads or leave Chat (unchanged guarantee).

### CA1.2 — Queue follow-ups
- The composer is never locked by a streaming answer.
- Sending while the conversation is answering, or while it already has queued messages, adds the message to that conversation's queue. The button reads **Queue**.
- The queue shows above the composer. Each item can be removed, or moved back into the composer to edit (only into an empty composer, so a draft is never overwritten). Queued attachments travel with their message.
- Queued messages send in order, one at a time, each after the answer ahead of it is reconciled on screen. They keep sending when you are in another thread or outside Chat.
- If an answer fails, the queue behind it is **held** with the reason, and Resume or Clear. A follow-up never builds on an answer the person has not seen.
- Deleting a conversation drops its queue. Closing the tab with unsent queued messages asks first.
- Queued messages and drafts are held in memory only. They are client and matter content, so they are never written to browser storage.

### CA1.3 — Readable review tags
- No legend over the transcript. A **Review tag key** button in the chat header opens an opaque popover explaining cited / verify / model / uncertain / firm context. On wide screens the button itself shows the three main swatches.
- Inline tags use AA-contrast tones (emerald / amber / blue / indigo / rose, 50-level fill with 800–900 text), 10–11px, rounded, and carry a hover `title` with their meaning.

### CA1.4 — Workstation ↔ phone
- The matter context moved from its own card into one line under the conversation title (`ChatContextPicker`).
- The transcript and composer share a readable max width (`max-w-4xl`) instead of stretching across a wide monitor.
- Auto-scroll only follows while the reader is at the bottom. Once they scroll back up, a **Jump to latest** / **Jump to the answer** control appears.
- Return adds a new line on touch keyboards. Ctrl/Cmd+Enter always sends, and IME composition is ignored.
- Header popovers (tag key, response settings, matter picker) span the header on phones instead of overflowing.
- Suggestion chips appear only in an empty thread. The composer no longer double-pads the safe area, which the bottom nav already handles. Loading shows a skeleton, not the empty-state hero.

### CA1.5 — See what every chat is doing
- The conversation rail shows per-thread state: responding (spinner), `+n` queued, **Held**, new reply (a finished answer not yet opened), and failed.
- The rail header shows "n responding". On a phone, the drawer button carries a dot, and its accessible name gives the count, when other threads are responding or need a look.
- Drafts are per conversation: a half-typed question stays with the thread it was typed in.

## Design notes

- **Where the turn runs.** The SSE read moved out of `ChatPage` into `frontend/src/chatTurns.js`. That lets a queued turn start with no page mounted, which is the same reason generations already lived in module scope (`chatGenerations.js`).
- **Attachment is tracked by the registry.** `detachChatGenerations()` replaces the page's request counter. A settled turn that is still attached is reconciled in place, and a detached one is re-read from the server, as before.
- **Queue pump.** `chatQueue.js` subscribes to the generation registry and dispatches on change. It never double-sends: the pump is re-entrancy safe, and registration is synchronous, so the conversation reads as busy before `startChatTurn` returns. A finished turn in the thread on screen is left for the page to reconcile and release before the next message goes, so the saved transcript and the new turn do not race.
- **Failure semantics.** A queue pauses on the first failed turn (`heldBy` records it). Resume sticks even while that failed record is still waiting for its thread to be reopened.
- **No backend change.** The per-conversation advisory-lock lease and the generation pool's 503 "retry in a moment" behaviour are unchanged.

## Verification

- Frontend: `npm run lint` (no new warnings), full `vitest run` (all 230+ files), and `npm run build`.
- New and updated tests:
  - `chatQueue.test.js` covers FIFO order, the parallel cap, pause and resume, deleted-conversation cleanup, reconcile-before-next, drafts and the unload guard.
  - `ChatPage.test.jsx` covers parallel send across threads, queue then auto-send, a held queue after failure and resume, draining while viewing another thread, and per-thread drafts.
  - `ChatExperience.test.jsx` covers the tag key popover, inline tag titles and contrast, jump to latest, the composer queue UI and newline on touch.
  - `ConversationItem.test.jsx` and `useChatActivity.test.jsx` cover rail activity.
- Manual: Playwright screenshots against mocked APIs at 1440×900 and iPhone 13, covering the thread, tag key, a queue during a streaming answer, two chats answering in parallel, and the phone drawer with activity.

## Next sprint candidates (not in CA-1)

1. **Server-side queue / cross-device continuity.** Queued messages live in one tab today. Persisting them, for example as `queued` user messages, would survive reloads and follow the user across devices.
2. **Stop generating.** Needs a server contract that persists a partial answer as a deliberate stop rather than an interruption. Aborting the read today records an interruption.
3. **Per-user concurrency on the server.** The cap of 3 is enforced per tab. Several tabs can still exceed it, and the server's only backstop is the pool-wide 503.
4. **Keyboard switching between active chats** (for example Alt+↑/↓ through responding or new-reply threads), following the S1.10 shortcut rules: never while editing, composing or in a dialog.
5. **Side-by-side threads on ultra-wide screens.**
6. **Transcript virtualization** for very long threads, and a lighter restyle of the cited-sources ledger to match the new cards.
7. **Phone-only header consolidation.** The app shell header and the chat header still stack on phones. Folding the chat title into the shell header would reclaim another ~48px.
8. **Mobile Playwright journey** (`mobile-webkit`) for queue plus parallel chats, alongside `mobile-casework.e2e.js`.
