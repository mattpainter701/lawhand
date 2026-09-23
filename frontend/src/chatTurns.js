/**
 * One assistant turn, from the optimistic pair to the settled record.
 *
 * The read runs outside the React tree for the same reason the registry does:
 * the server persists an answer only once the stream reaches
 * `[STREAM_COMPLETE]`, so nothing about the page — leaving Chat, opening another
 * thread, a queued follow-up firing while a different thread is on screen — may
 * cancel it. The page decides what to show; this module only publishes.
 */
import { streamMessage } from './api'
import {
  GENERATION_COMPLETE,
  GENERATION_ERROR,
  beginChatGeneration,
  patchChatGeneration,
  releaseChatGeneration,
  settleChatGeneration,
} from './chatGenerations'
import { reportError } from './utils/reportError'

function deriveKeyphrases(text) {
  const stopWords = new Set([
    'about', 'after', 'before', 'case', 'cases', 'could', 'from', 'have',
    'legal', 'need', 'that', 'their', 'there', 'this', 'what', 'when',
    'where', 'which', 'with', 'would',
  ])
  return String(text || '')
    .split(/[^A-Za-z0-9]+/)
    .map((word) => word.trim())
    .filter((word) => word && (word.length > 2 || /^[A-Z]{2}$/.test(word)))
    .filter((word) => !stopWords.has(word.toLowerCase()))
    .slice(0, 5)
}

function initialStreamProgress(content, attachmentCount) {
  const uploads = Number.isFinite(attachmentCount) ? attachmentCount : 0
  return {
    type: 'progress',
    event: 'retrieving',
    status: 'Retrieving source material',
    keyphrases: deriveKeyphrases(content),
    counts: {
      matter: 0,
      uploads,
      firm: 0,
      courtlistener: 0,
      total: uploads,
    },
    activities: [],
  }
}

export function completedStreamStatus(publicRetrieval) {
  if (publicRetrieval?.state === 'service_unavailable') {
    return 'Response complete — public authority unavailable'
  }
  return 'Response complete'
}

function mergeStreamProgress(current, event, content) {
  if (!event || event.type !== 'progress') return current
  const counts = {
    ...(current?.counts || {}),
    ...(event.counts || {}),
  }
  const activities = [...(current?.activities || [])]
  if (event.activity?.id) {
    const activityIndex = activities.findIndex((item) => item.id === event.activity.id)
    if (activityIndex >= 0) {
      activities[activityIndex] = {
        ...activities[activityIndex],
        ...event.activity,
        sources: event.activity.sources || activities[activityIndex].sources || [],
      }
    } else {
      activities.push(event.activity)
    }
  }
  return {
    ...(current || {}),
    ...event,
    counts,
    activities,
    keyphrases: event.keyphrases || current?.keyphrases || deriveKeyphrases(content),
  }
}

function countSourcesByType(sources) {
  const counts = {
    matter: 0,
    uploads: 0,
    firm: 0,
    courtlistener: 0,
    total: 0,
  }

  for (const src of Array.isArray(sources) ? sources : []) {
    const type = src?.source_type || ''
    if (type === 'public_authority') {
      counts.courtlistener += 1
    } else if (type === 'matter_context') {
      counts.matter += 1
    } else if (type === 'tenant_document' && src?.source_label === 'Attached document') {
      counts.uploads += 1
    } else {
      counts.firm += 1
    }
  }
  counts.total = counts.matter + counts.uploads + counts.firm + counts.courtlistener
  return counts
}

export function buildReferenceContext({ progress, sources, status, citedCount } = {}) {
  const sourceList = Array.isArray(sources) ? sources : []
  const progressCounts = progress?.counts || null
  const derivedCounts = countSourcesByType(sourceList)
  const counts = {
    matter: Number(progressCounts?.matter ?? derivedCounts.matter ?? 0),
    uploads: Number(progressCounts?.uploads ?? derivedCounts.uploads ?? 0),
    firm: Number(progressCounts?.firm ?? derivedCounts.firm ?? 0),
    courtlistener: Number(progressCounts?.courtlistener ?? derivedCounts.courtlistener ?? 0),
  }
  counts.total = Number(progressCounts?.total ?? (counts.matter + counts.uploads + counts.firm + counts.courtlistener))
  const hasContext = counts.total > 0 || sourceList.length > 0 || progress?.status || status
  if (!hasContext) return null

  const referenceContext = {
    counts,
    source_count: sourceList.length,
    status: status || progress?.status || (sourceList.length ? 'Materials retrieved for source audit' : ''),
    complete: Boolean(progress?.complete),
  }
  if (Number.isFinite(citedCount)) {
    referenceContext.cited_count = citedCount
  }
  return referenceContext
}

function newClientTurnId() {
  return globalThis.crypto?.randomUUID?.()
    || `turn-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

async function drainTurn({
  conversationId,
  clientTurnId,
  generation,
  content,
  attachmentIds,
  includePublic,
  usePremium,
}) {
  const publish = (assistant, user = null) => {
    patchChatGeneration(conversationId, clientTurnId, { assistant, user })
  }

  let streamProgress = generation.assistantMessage.progress
  let accumulatedText = ''
  let streamError = null
  let sawStreamComplete = false
  let streamedSources = []
  let streamedCitationAnnotations = []

  try {
    for await (const token of streamMessage(
      conversationId,
      content,
      includePublic,
      usePremium,
      attachmentIds,
      { signal: generation.controller.signal },
    )) {
      if (token?.type === 'progress' && token.event === 'citation_metadata') {
        streamedSources = token.sources || []
        streamedCitationAnnotations = token.citation_annotations || []
        if (token.public_retrieval && typeof token.public_retrieval === 'object') {
          streamProgress = {
            ...streamProgress,
            public_retrieval: token.public_retrieval,
          }
        }
        const referenceContext = buildReferenceContext({
          progress: streamProgress,
          sources: streamedSources,
          citedCount: streamedSources.length,
        })
        publish({
          sources: streamedSources,
          citation_annotations: streamedCitationAnnotations,
          progress: streamProgress,
          referenceContext,
        })
        continue
      }
      if (token?.type === 'progress' && token.event === 'action_proposal') {
        // Reviewable work the assistant proposed. Attached to the message
        // rather than merged into progress, since it outlives the stream.
        publish({ proposed_actions: token.proposed_actions || [] })
        continue
      }
      if (token?.type === 'progress') {
        streamProgress = mergeStreamProgress(streamProgress, token, content)
        const referenceContext = buildReferenceContext({
          progress: streamProgress,
          sources: streamedSources,
          citedCount: streamedSources.length,
        })
        publish({ progress: streamProgress, referenceContext }, { referenceContext })
        continue
      }
      if (token?.type === 'artifacts') {
        const streamArtifacts = Array.isArray(token.artifacts) ? token.artifacts : []
        if (streamArtifacts.length > 0) publish({ artifacts: streamArtifacts })
        continue
      }
      if (token === '[STREAM_COMPLETE]') {
        sawStreamComplete = true
        streamProgress = {
          ...streamProgress,
          complete: true,
          status: completedStreamStatus(streamProgress.public_retrieval),
        }
        const referenceContext = buildReferenceContext({
          progress: streamProgress,
          sources: streamedSources,
          citedCount: streamedSources.length,
        })
        publish({ progress: streamProgress, referenceContext }, { referenceContext })
        break
      } else if (typeof token === 'string' && token.startsWith('[ERROR]')) {
        streamError = token.slice(7)
        break
      } else if (typeof token === 'string') {
        accumulatedText += token
        publish({ content: accumulatedText })
      }
    }

    if (!streamError && !sawStreamComplete) {
      streamError = 'The assistant stream ended before completion. Please retry.'
    }
    if (!streamError && !accumulatedText.trim()) {
      streamError = 'The assistant completed without a visible answer. Please retry.'
    }

    settleChatGeneration(conversationId, clientTurnId, {
      status: streamError ? GENERATION_ERROR : GENERATION_COMPLETE,
      error: streamError,
      errorSource: streamError ? 'stream' : null,
      assistant: {
        content: accumulatedText,
        sources: streamedSources,
        citation_annotations: streamedCitationAnnotations,
        progress: { ...streamProgress, complete: true },
      },
    })
  } catch (err) {
    if (err?.name === 'AbortError') {
      // Only a deleted conversation aborts a read, and its transcript is gone.
      releaseChatGeneration(conversationId, clientTurnId)
      return
    }
    reportError('Failed to send message', err)
    settleChatGeneration(conversationId, clientTurnId, {
      status: GENERATION_ERROR,
      error: err?.response?.data?.detail || err?.message || 'Please try again.',
      errorSource: 'request',
      assistant: { content: accumulatedText, progress: streamProgress },
    })
  }
}

/**
 * Register a turn and start reading its answer.
 *
 * Registration is synchronous so the conversation reads as busy before this
 * returns — that is what routes a follow-up typed in the same instant into the
 * queue rather than into a second request the server's lease would refuse.
 * `attached` says whether a page is showing this conversation right now; see
 * `detachChatGenerations` for how that binding is later let go.
 */
export function startChatTurn({
  conversationId,
  content,
  attachmentIds = [],
  includePublic = true,
  usePremium = false,
  knownServerMessageIds = [],
  attached = true,
}) {
  const clientTurnId = newClientTurnId()
  const initialProgress = initialStreamProgress(content, attachmentIds.length)
  const initialReferenceContext = buildReferenceContext({ progress: initialProgress })
  const createdAt = new Date().toISOString()

  const generation = beginChatGeneration({
    conversationId,
    clientTurnId,
    controller: new AbortController(),
    attached,
    userMessage: {
      id: `temp-${clientTurnId}`,
      role: 'user',
      content,
      sources: [],
      referenceContext: initialReferenceContext,
      client_turn_id: clientTurnId,
      _known_server_message_ids: knownServerMessageIds,
      created_at: createdAt,
    },
    assistantMessage: {
      id: `stream-${clientTurnId}`,
      role: 'assistant',
      content: '',
      sources: [],
      progress: initialProgress,
      referenceContext: initialReferenceContext,
      client_turn_id: clientTurnId,
      created_at: createdAt,
    },
  })
  if (!generation) return { generation: null, completion: Promise.resolve() }

  const completion = drainTurn({
    conversationId,
    clientTurnId,
    generation,
    content,
    attachmentIds,
    includePublic,
    usePremium,
  })
  return { generation, completion }
}
