import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../chatTurns', () => ({ startChatTurn: vi.fn() }))

import {
  GENERATION_COMPLETE,
  GENERATION_ERROR,
  beginChatGeneration,
  detachChatGenerations,
  resetChatGenerations,
  settleChatGeneration,
} from '../chatGenerations'
import { enqueueChatMessage, resetChatQueue } from '../chatQueue'
import { useChatActivity } from './useChatActivity'

const begin = (conversationId) => beginChatGeneration({
  conversationId,
  clientTurnId: `turn-${conversationId}`,
  userMessage: { id: `temp-${conversationId}`, role: 'user', content: 'Question' },
  assistantMessage: { id: `stream-${conversationId}`, role: 'assistant', content: '' },
})

describe('useChatActivity', () => {
  afterEach(() => {
    cleanup()
    resetChatQueue()
    resetChatGenerations()
  })

  it('reports what every conversation is doing and updates as it changes', () => {
    const { result } = renderHook(() => useChatActivity())
    expect(result.current.respondingCount).toBe(0)
    expect(result.current.activityFor('conversation-a').responding).toBe(false)

    act(() => {
      begin('conversation-a')
      begin('conversation-b')
      begin('conversation-c')
      enqueueChatMessage('conversation-a', { content: 'Follow-up' })
    })
    expect(result.current.respondingCount).toBe(3)
    expect(result.current.queuedCount).toBe(1)
    expect(result.current.activityFor('conversation-a')).toMatchObject({ responding: true, queued: 1 })

    act(() => {
      // Nobody is looking at these threads when their answers land.
      detachChatGenerations()
      settleChatGeneration('conversation-b', 'turn-conversation-b', { status: GENERATION_COMPLETE })
      settleChatGeneration('conversation-c', 'turn-conversation-c', { status: GENERATION_ERROR, error: 'Failed' })
    })
    expect(result.current.activityFor('conversation-b')).toMatchObject({ responding: false, replyReady: true })
    expect(result.current.activityFor('conversation-c')).toMatchObject({ failed: true })
    expect(result.current.attentionCount).toBe(2)
  })
})
