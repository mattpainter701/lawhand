/**
 * Follow-up messages waiting for their conversation, and composer drafts.
 *
 * The server holds one generation lease per conversation, so a message typed
 * while that conversation is still answering cannot be sent yet. Rather than
 * lock the composer, it waits here and is sent, in order, once the answer ahead
 * of it lands. Like the generation registry this lives outside the React tree:
 * switching threads or leaving Chat must neither lose a queued message nor stop
 * the queue from draining.
 *
 * A queue pauses when the answer ahead of it fails. Sending the next question on
 * top of a failed turn would build on an answer the person never saw, so they
 * decide whether to resume.
 *
 * Queued messages and drafts are held in memory only, never in browser storage:
 * they are client and matter content. Closing the tab drops what has not been
 * sent, so the page asks first while anything is still waiting.
 */
import {
  GENERATION_ABORTED,
  GENERATION_COMPLETE,
  GENERATION_ERROR,
  GENERATION_STREAMING,
  MAX_PARALLEL_CHAT_RESPONSES,
  countStreamingChatGenerations,
  getChatGeneration,
  subscribeToChatGenerations,
} from './chatGenerations'
import { startChatTurn } from './chatTurns'

export const QUEUE_PAUSED_AFTER_FAILURE = 'The response ahead of these messages failed, so they were held.'

// `heldBy` is the failed turn a queue paused for, so resuming past it sticks.
const EMPTY_QUEUE = Object.freeze({ items: Object.freeze([]), paused: null, heldBy: null })
const NEW_CONVERSATION_DRAFT = '__new__'

const queues = new Map()
const drafts = new Map()
const knownTranscriptIds = new Map()
const listeners = new Set()
let viewedConversationId = null
let unsubscribeGenerations = null
let unloadGuardInstalled = false
let pumping = false
let pumpRequested = false
let itemSequence = 0

function notify() {
  for (const listener of [...listeners]) {
    try {
      listener()
    } catch {
      // One failing subscriber must not stop the others or the pump.
    }
  }
}

function watchGenerations() {
  if (unsubscribeGenerations) return
  // A settled answer is what frees a conversation, so the pump runs on every
  // registry change rather than on a timer.
  unsubscribeGenerations = subscribeToChatGenerations(() => pumpChatQueue())
}

function warnBeforeDroppingQueue(event) {
  if (countQueuedChatMessages() === 0) return
  event.preventDefault()
  // Older browsers only show the prompt when a return value is set.
  event.returnValue = ''
}

function guardUnload() {
  if (unloadGuardInstalled || typeof window === 'undefined') return
  window.addEventListener('beforeunload', warnBeforeDroppingQueue)
  unloadGuardInstalled = true
}

function setQueue(conversationId, queue) {
  if (!queue.items.length && !queue.paused) {
    queues.delete(conversationId)
  } else {
    queues.set(conversationId, queue)
  }
}

/** Subscribe to every queue or draft mutation. Returns the unsubscribe function. */
export function subscribeToChatQueue(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getChatQueue(conversationId) {
  if (!conversationId) return EMPTY_QUEUE
  return queues.get(conversationId) || EMPTY_QUEUE
}

/** Every conversation with something waiting, keyed by conversation id. */
export function listChatQueues() {
  return new Map(queues)
}

export function countQueuedChatMessages() {
  let count = 0
  for (const queue of queues.values()) count += queue.items.length
  return count
}

/**
 * Whether a message sent to this conversation now has to wait. Anything already
 * queued keeps its place ahead of a newer message, even when the conversation
 * itself is idle — for example while its queue is paused.
 */
export function chatSendMustQueue(conversationId) {
  if (!conversationId) return false
  if (getChatQueue(conversationId).items.length > 0) return true
  if (getChatGeneration(conversationId)?.status === GENERATION_STREAMING) return true
  return countStreamingChatGenerations() >= MAX_PARALLEL_CHAT_RESPONSES
}

export function enqueueChatMessage(conversationId, {
  content,
  attachments = [],
  includePublic = true,
  usePremium = false,
} = {}) {
  const text = String(content || '').trim()
  if (!conversationId || !text) return null
  itemSequence += 1
  const item = {
    id: `queued-${Date.now()}-${itemSequence}`,
    content: text,
    attachments: attachments.map(({ id, filename }) => ({ id, filename })),
    includePublic: Boolean(includePublic),
    usePremium: Boolean(usePremium),
    queuedAt: new Date().toISOString(),
  }
  const current = getChatQueue(conversationId)
  setQueue(conversationId, { ...current, items: [...current.items, item] })
  watchGenerations()
  guardUnload()
  notify()
  pumpChatQueue()
  return item
}

export function removeQueuedChatMessage(conversationId, itemId) {
  const current = getChatQueue(conversationId)
  const items = current.items.filter((item) => item.id !== itemId)
  if (items.length === current.items.length) return null
  const removed = current.items.find((item) => item.id === itemId)
  // Nothing left to hold back, so a pause no longer means anything.
  setQueue(conversationId, { ...current, items, paused: items.length ? current.paused : null })
  notify()
  return removed
}

export function clearChatQueue(conversationId) {
  if (!queues.has(conversationId)) return false
  queues.delete(conversationId)
  notify()
  return true
}

export function resumeChatQueue(conversationId) {
  const current = getChatQueue(conversationId)
  if (!current.paused) return false
  // The failed turn can stay in the registry until its conversation is opened
  // again; remember it was acknowledged so it does not pause the queue twice.
  setQueue(conversationId, { ...current, paused: null })
  notify()
  pumpChatQueue()
  return true
}

/**
 * Tell the queue which conversation a page is showing. A settled answer in that
 * conversation is left for the page to reconcile before the next message goes,
 * so the saved transcript and the new turn do not race each other on screen.
 */
export function setViewedChatConversation(conversationId) {
  const next = conversationId || null
  if (viewedConversationId === next) return
  viewedConversationId = next
  pumpChatQueue()
}

/**
 * Record which saved messages a page has already seen in a conversation. A
 * queued turn carries them so reconciliation can tell a repeated question from
 * the one it just sent.
 */
export function rememberChatTranscript(conversationId, messages) {
  if (!conversationId) return
  knownTranscriptIds.set(
    conversationId,
    (Array.isArray(messages) ? messages : [])
      .map((message) => String(message?.id || ''))
      .filter((id) => id && !/^(temp|stream|err)-/.test(id)),
  )
}

export function saveChatDraft(conversationId, text) {
  const key = conversationId || NEW_CONVERSATION_DRAFT
  const value = String(text || '')
  if (value.trim()) drafts.set(key, value)
  else drafts.delete(key)
}

export function readChatDraft(conversationId) {
  return drafts.get(conversationId || NEW_CONVERSATION_DRAFT) || ''
}

function nextDispatchable() {
  for (const [conversationId, queue] of queues) {
    if (!queue.items.length || queue.paused) continue
    const record = getChatGeneration(conversationId)
    if (record?.status === GENERATION_STREAMING) continue
    // The page on screen reconciles a finished answer against the saved
    // transcript and then releases it; the next turn waits for that.
    if (record?.status === GENERATION_COMPLETE && viewedConversationId === conversationId) continue
    return conversationId
  }
  return null
}

function pauseFailedQueues() {
  let changed = false
  for (const [conversationId, queue] of queues) {
    const record = getChatGeneration(conversationId)
    if (record?.status === GENERATION_ABORTED) {
      // Only a deleted conversation aborts, and there is nowhere left to send.
      queues.delete(conversationId)
      changed = true
    } else if (
      record?.status === GENERATION_ERROR
      && queue.items.length
      && !queue.paused
      && queue.heldBy !== record.clientTurnId
    ) {
      queues.set(conversationId, {
        ...queue,
        paused: QUEUE_PAUSED_AFTER_FAILURE,
        heldBy: record.clientTurnId,
      })
      changed = true
    }
  }
  return changed
}

/** Send whatever can go now. Safe to call at any time; it never double-sends. */
export function pumpChatQueue() {
  if (pumping) {
    pumpRequested = true
    return
  }
  pumping = true
  let changed = false
  try {
    do {
      pumpRequested = false
      changed = pauseFailedQueues() || changed
      while (countStreamingChatGenerations() < MAX_PARALLEL_CHAT_RESPONSES) {
        const conversationId = nextDispatchable()
        if (!conversationId) break
        const queue = queues.get(conversationId)
        const [item, ...rest] = queue.items
        setQueue(conversationId, { ...queue, items: rest })
        changed = true
        startChatTurn({
          conversationId,
          content: item.content,
          attachmentIds: item.attachments.map((attachment) => attachment.id),
          includePublic: item.includePublic,
          usePremium: item.usePremium,
          knownServerMessageIds: knownTranscriptIds.get(conversationId) || [],
          attached: viewedConversationId === conversationId,
        })
      }
    } while (pumpRequested)
  } finally {
    pumping = false
  }
  if (changed) notify()
}

/** Test helper: forget every queue, draft, and subscription. */
export function resetChatQueue() {
  queues.clear()
  drafts.clear()
  knownTranscriptIds.clear()
  listeners.clear()
  unsubscribeGenerations?.()
  unsubscribeGenerations = null
  if (unloadGuardInstalled) window.removeEventListener('beforeunload', warnBeforeDroppingQueue)
  unloadGuardInstalled = false
  viewedConversationId = null
  pumping = false
  pumpRequested = false
}
