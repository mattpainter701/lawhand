import { useEffect, useMemo, useState } from 'react'
import {
  GENERATION_COMPLETE,
  GENERATION_ERROR,
  GENERATION_STREAMING,
  listChatGenerations,
  subscribeToChatGenerations,
} from '../chatGenerations'
import { listChatQueues, subscribeToChatQueue } from '../chatQueue'

// Only what the markers show. Streamed tokens patch a generation many times a
// second without changing any of this, and the rail need not re-render for them.
function activitySignature() {
  const parts = []
  for (const record of listChatGenerations()) {
    parts.push(`${record.conversationId}:${record.status}:${record.attached ? 1 : 0}`)
  }
  for (const [conversationId, queue] of listChatQueues()) {
    parts.push(`${conversationId}:q${queue.items.length}:${queue.paused ? 1 : 0}`)
  }
  return parts.sort().join('|')
}

const IDLE = Object.freeze({
  responding: false,
  replyReady: false,
  failed: false,
  queued: 0,
  paused: false,
})

/**
 * What every conversation is doing in the background: answering, holding
 * queued follow-ups, or sitting on a reply nobody has opened yet.
 *
 * A settled turn that is no longer attached to a page is one the person has not
 * seen — opening the conversation reconciles and releases it, which is what
 * clears the marker.
 */
export function useChatActivity() {
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let lastSignature = null
    const bump = () => {
      const signature = activitySignature()
      if (signature === lastSignature) return
      lastSignature = signature
      setVersion((current) => current + 1)
    }
    const unsubscribeGenerations = subscribeToChatGenerations(bump)
    const unsubscribeQueue = subscribeToChatQueue(bump)
    // Catch anything that changed between the first render and subscribing.
    bump()
    return () => {
      unsubscribeGenerations()
      unsubscribeQueue()
    }
  }, [])

  return useMemo(() => {
    const byConversation = new Map()
    const entry = (conversationId) => {
      if (!byConversation.has(conversationId)) byConversation.set(conversationId, { ...IDLE })
      return byConversation.get(conversationId)
    }

    for (const record of listChatGenerations()) {
      if (record.status === GENERATION_STREAMING) {
        entry(record.conversationId).responding = true
      } else if (record.status === GENERATION_COMPLETE && !record.attached) {
        entry(record.conversationId).replyReady = true
      } else if (record.status === GENERATION_ERROR && !record.attached) {
        entry(record.conversationId).failed = true
      }
    }
    for (const [conversationId, queue] of listChatQueues()) {
      const activity = entry(conversationId)
      activity.queued = queue.items.length
      activity.paused = Boolean(queue.paused)
    }

    let respondingCount = 0
    let queuedCount = 0
    let attentionCount = 0
    for (const activity of byConversation.values()) {
      if (activity.responding) respondingCount += 1
      queuedCount += activity.queued
      if (activity.replyReady || activity.failed || activity.paused) attentionCount += 1
    }

    return {
      byConversation,
      respondingCount,
      queuedCount,
      attentionCount,
      activityFor: (conversationId) => byConversation.get(conversationId) || IDLE,
    }
    // The registries are the real dependency; `version` is how they report a change.
  }, [version])
}
