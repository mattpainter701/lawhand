import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The queue decides *when* to send; the turn runner is what sends. Standing in
// a runner that only registers the turn lets each test settle it by hand.
const runner = vi.hoisted(() => ({ turns: [] }))
vi.mock('./chatTurns', async () => {
  const registry = await import('./chatGenerations')
  return {
    startChatTurn: vi.fn((options) => {
      const clientTurnId = `turn-${runner.turns.length + 1}`
      runner.turns.push({ ...options, clientTurnId })
      const generation = registry.beginChatGeneration({
        conversationId: options.conversationId,
        clientTurnId,
        attached: options.attached,
        userMessage: { id: `temp-${clientTurnId}`, role: 'user', content: options.content },
        assistantMessage: { id: `stream-${clientTurnId}`, role: 'assistant', content: '' },
      })
      return { generation, completion: Promise.resolve() }
    }),
  }
})

import {
  GENERATION_COMPLETE,
  GENERATION_ERROR,
  MAX_PARALLEL_CHAT_RESPONSES,
  abortChatGeneration,
  beginChatGeneration,
  clearChatGenerationsForSignOut,
  getChatGeneration,
  releaseChatGeneration,
  resetChatGenerations,
  settleChatGeneration,
} from './chatGenerations'
import {
  QUEUE_PAUSED_AFTER_FAILURE,
  chatSendMustQueue,
  clearChatQueue,
  clearChatQueueForSignOut,
  countQueuedChatMessages,
  enqueueChatMessage,
  getChatQueue,
  readChatDraft,
  rememberChatTranscript,
  removeQueuedChatMessage,
  resetChatQueue,
  resumeChatQueue,
  saveChatDraft,
  setViewedChatConversation,
  subscribeToChatQueue,
} from './chatQueue'

const stream = (conversationId, clientTurnId = `live-${conversationId}`) => beginChatGeneration({
  conversationId,
  clientTurnId,
  userMessage: { id: `temp-${clientTurnId}`, role: 'user', content: 'Question' },
  assistantMessage: { id: `stream-${clientTurnId}`, role: 'assistant', content: '' },
})

const finish = (conversationId, status = GENERATION_COMPLETE) => {
  const record = getChatGeneration(conversationId)
  settleChatGeneration(conversationId, record.clientTurnId, { status, error: status === GENERATION_ERROR ? 'Failed' : null })
  return record.clientTurnId
}

describe('chat follow-up queue', () => {
  beforeEach(() => {
    runner.turns = []
    resetChatGenerations()
    resetChatQueue()
  })

  afterEach(() => {
    resetChatQueue()
    resetChatGenerations()
  })

  it('holds a follow-up while its conversation answers and sends it once the answer lands', () => {
    stream('conversation-a')
    expect(chatSendMustQueue('conversation-a')).toBe(true)

    enqueueChatMessage('conversation-a', { content: '  Next question  ', includePublic: false, usePremium: true })
    expect(getChatQueue('conversation-a').items.map((item) => item.content)).toEqual(['Next question'])
    expect(runner.turns).toHaveLength(0)

    finish('conversation-a')
    expect(runner.turns).toHaveLength(1)
    expect(runner.turns[0]).toMatchObject({
      conversationId: 'conversation-a',
      content: 'Next question',
      includePublic: false,
      usePremium: true,
      attached: false,
    })
    expect(countQueuedChatMessages()).toBe(0)
  })

  it('sends queued messages one at a time, in the order they were queued', () => {
    stream('conversation-a')
    enqueueChatMessage('conversation-a', { content: 'Second' })
    enqueueChatMessage('conversation-a', { content: 'Third' })

    finish('conversation-a')
    expect(runner.turns.map((turn) => turn.content)).toEqual(['Second'])
    expect(chatSendMustQueue('conversation-a')).toBe(true)

    finish('conversation-a')
    expect(runner.turns.map((turn) => turn.content)).toEqual(['Second', 'Third'])
  })

  it('keeps a newer message behind ones already waiting even when the thread is idle', () => {
    stream('conversation-a')
    enqueueChatMessage('conversation-a', { content: 'Waiting' })
    finish('conversation-a', GENERATION_ERROR)
    releaseChatGeneration('conversation-a')

    expect(getChatGeneration('conversation-a')).toBeNull()
    expect(chatSendMustQueue('conversation-a')).toBe(true)
  })

  it('waits for the page on screen to reconcile a finished answer before sending the next', () => {
    setViewedChatConversation('conversation-a')
    stream('conversation-a')
    enqueueChatMessage('conversation-a', { content: 'Follow-up' })

    const finished = finish('conversation-a')
    expect(runner.turns).toHaveLength(0)

    releaseChatGeneration('conversation-a', finished)
    expect(runner.turns).toHaveLength(1)
    expect(runner.turns[0].attached).toBe(true)
  })

  it(`never runs more than ${MAX_PARALLEL_CHAT_RESPONSES} answers at once`, () => {
    for (let index = 1; index <= MAX_PARALLEL_CHAT_RESPONSES; index += 1) stream(`busy-${index}`)
    expect(chatSendMustQueue('conversation-idle')).toBe(true)

    enqueueChatMessage('conversation-idle', { content: 'Waiting for a slot' })
    expect(runner.turns).toHaveLength(0)

    finish('busy-1')
    expect(runner.turns.map((turn) => turn.conversationId)).toEqual(['conversation-idle'])
    expect(chatSendMustQueue('conversation-other')).toBe(true)
  })

  it('holds the queue after a failed answer and resumes past that failure once', () => {
    stream('conversation-a')
    enqueueChatMessage('conversation-a', { content: 'Follow-up' })

    finish('conversation-a', GENERATION_ERROR)
    expect(getChatQueue('conversation-a').paused).toBe(QUEUE_PAUSED_AFTER_FAILURE)
    expect(runner.turns).toHaveLength(0)

    // The failed record is still in the registry — nobody has opened the
    // thread — and resuming must not immediately pause again because of it.
    expect(resumeChatQueue('conversation-a')).toBe(true)
    expect(runner.turns.map((turn) => turn.content)).toEqual(['Follow-up'])
    expect(getChatQueue('conversation-a').paused).toBeNull()
  })

  it('forgets the pause once nothing is left to hold back', () => {
    stream('conversation-a')
    const item = enqueueChatMessage('conversation-a', { content: 'Follow-up' })
    finish('conversation-a', GENERATION_ERROR)

    expect(removeQueuedChatMessage('conversation-a', item.id)).toMatchObject({ content: 'Follow-up' })
    expect(getChatQueue('conversation-a')).toMatchObject({ items: [], paused: null })
  })

  it('drops the queue of a conversation that was deleted mid-answer', () => {
    stream('conversation-a')
    enqueueChatMessage('conversation-a', { content: 'Never sent' })

    abortChatGeneration('conversation-a')
    expect(getChatQueue('conversation-a').items).toHaveLength(0)
    expect(runner.turns).toHaveLength(0)
  })

  it('clears a queue on request and tells subscribers', () => {
    const listener = vi.fn()
    subscribeToChatQueue(listener)
    stream('conversation-a')
    enqueueChatMessage('conversation-a', { content: 'One' })

    expect(clearChatQueue('conversation-a')).toBe(true)
    expect(getChatQueue('conversation-a').items).toHaveLength(0)
    expect(listener).toHaveBeenCalled()
    expect(clearChatQueue('conversation-a')).toBe(false)
  })

  it('refuses blank messages and messages with no conversation', () => {
    expect(enqueueChatMessage('conversation-a', { content: '   ' })).toBeNull()
    expect(enqueueChatMessage(null, { content: 'Question' })).toBeNull()
    expect(chatSendMustQueue(null)).toBe(false)
  })

  it('hands a queued turn the saved message ids the page has seen', () => {
    rememberChatTranscript('conversation-a', [
      { id: 'message-1' },
      { id: 'temp-turn' },
      { id: 'stream-turn' },
      { id: 'message-2' },
    ])
    stream('conversation-a')
    enqueueChatMessage('conversation-a', { content: 'Follow-up' })
    finish('conversation-a')

    expect(runner.turns[0].knownServerMessageIds).toEqual(['message-1', 'message-2'])
  })

  it('keeps each conversation its own draft', () => {
    saveChatDraft('conversation-a', 'Draft for A')
    saveChatDraft(null, 'Draft before any conversation')
    expect(readChatDraft('conversation-a')).toBe('Draft for A')
    expect(readChatDraft('conversation-b')).toBe('')
    expect(readChatDraft(null)).toBe('Draft before any conversation')

    saveChatDraft('conversation-a', '   ')
    expect(readChatDraft('conversation-a')).toBe('')
  })

  it('asks before a reload or close would drop messages that have not been sent', () => {
    const quiet = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(quiet)
    expect(quiet.defaultPrevented).toBe(false)

    stream('conversation-a')
    const item = enqueueChatMessage('conversation-a', { content: 'Unsent' })
    const guarded = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(guarded)
    expect(guarded.defaultPrevented).toBe(true)

    removeQueuedChatMessage('conversation-a', item.id)
    const released = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(released)
    expect(released.defaultPrevented).toBe(false)
  })

  it('hands nothing to the next person who signs in on the same tab', () => {
    const controller = new AbortController()
    beginChatGeneration({
      conversationId: 'conversation-a',
      clientTurnId: 'live-a',
      controller,
      userMessage: { id: 'temp-live-a', role: 'user', content: 'Question' },
      assistantMessage: { id: 'stream-live-a', role: 'assistant', content: '' },
    })
    enqueueChatMessage('conversation-a', { content: 'Privileged follow-up' })
    saveChatDraft(null, 'Unsent new-chat draft')
    saveChatDraft('conversation-a', 'Unsent thread draft')
    const listener = vi.fn()
    subscribeToChatQueue(listener)

    clearChatQueueForSignOut()
    clearChatGenerationsForSignOut()

    expect(controller.signal.aborted).toBe(true)
    expect(getChatGeneration('conversation-a')).toBeNull()
    expect(countQueuedChatMessages()).toBe(0)
    expect(readChatDraft(null)).toBe('')
    expect(readChatDraft('conversation-a')).toBe('')
    expect(runner.turns).toHaveLength(0)
    expect(listener).toHaveBeenCalled()
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(false)

    // Subscribers stay armed: the next session's queue still drains.
    stream('conversation-b')
    enqueueChatMessage('conversation-b', { content: 'Next user' })
    finish('conversation-b')
    expect(runner.turns.map((turn) => turn.content)).toEqual(['Next user'])
  })
})
