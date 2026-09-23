import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { reportError } from '../utils/reportError'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAppShell } from '../components/AppShell'
import { useAuth } from '../App'
import ChatHeader from '../components/ChatHeader'
import ChatInput from '../components/ChatInput'
import { citedSourceCount } from '../components/ChatMessage'
import Messages from '../components/Messages'
import ChatRail from '../components/chat/ChatRail'
import ChatContextPicker from '../components/chat/ChatContextPicker'
import {
  getConversation,
  createConversation,
  updateConversation,
  uploadChatAttachment,
  getMattersV2,
  getLegalSourceHealth,
  updateMe,
} from '../api'
import {
  GENERATION_ABORTED,
  GENERATION_ERROR,
  GENERATION_STREAMING,
  MAX_PARALLEL_CHAT_RESPONSES,
  abortChatGeneration,
  detachChatGenerations,
  getChatGeneration,
  releaseChatGeneration,
  subscribeToChatGenerations,
} from '../chatGenerations'
import { buildReferenceContext, completedStreamStatus, startChatTurn } from '../chatTurns'
import {
  chatSendMustQueue,
  clearChatQueue,
  enqueueChatMessage,
  getChatQueue,
  readChatDraft,
  rememberChatTranscript,
  removeQueuedChatMessage,
  resumeChatQueue,
  saveChatDraft,
  setViewedChatConversation,
  subscribeToChatQueue,
} from '../chatQueue'
import { useChatActivity } from '../hooks/useChatActivity'
import { AlertBanner } from '../components/ui'

const MESSAGE_IDENTITY_KEYS = [
  'id',
  'client_message_id',
  'clientMessageId',
  'optimistic_id',
  'optimisticId',
]
const TURN_IDENTITY_KEYS = [
  'client_turn_id',
  'clientTurnId',
  'turn_id',
  'turnId',
  'client_request_id',
  'clientRequestId',
  'request_id',
  'requestId',
]
const REPLY_IDENTITY_KEYS = [
  'parent_message_id',
  'parentMessageId',
  'user_message_id',
  'userMessageId',
  'in_reply_to',
  'inReplyTo',
]

function identityValues(message, keys) {
  return new Set(
    keys
      .map((key) => message?.[key])
      .filter((value) => value !== undefined && value !== null && String(value).trim())
      .map(String),
  )
}

function sharesIdentity(left, right, keys) {
  const leftValues = identityValues(left, keys)
  if (leftValues.size === 0) return false
  return [...identityValues(right, keys)].some((value) => leftValues.has(value))
}

function assistantRepliesTo(assistant, user) {
  const userIds = identityValues(user, [...MESSAGE_IDENTITY_KEYS, ...TURN_IDENTITY_KEYS])
  return [...identityValues(assistant, REPLY_IDENTITY_KEYS)].some((value) => userIds.has(value))
}

export function mergeRefreshedTranscript(serverMessages, optimisticUserMessage, fallbackAssistantMessage) {
  const next = Array.isArray(serverMessages) ? [...serverMessages] : []
  const knownServerIds = new Set(
    (optimisticUserMessage?._known_server_message_ids || []).map(String),
  )

  let userIndex = next.findIndex((message) => (
    message.role === 'user'
    && (
      sharesIdentity(message, optimisticUserMessage, MESSAGE_IDENTITY_KEYS)
      || sharesIdentity(message, optimisticUserMessage, TURN_IDENTITY_KEYS)
    )
  ))

  if (userIndex < 0) {
    const contentMatches = next
      .map((message, index) => ({ message, index }))
      .filter(({ message }) => (
        message.role === 'user' && message.content === optimisticUserMessage.content
      ))
    const unseenMatch = [...contentMatches].reverse().find(({ message }) => (
      message.id && !knownServerIds.has(String(message.id))
    ))
    const fallbackMatch = knownServerIds.size === 0 ? contentMatches.at(-1) : null
    userIndex = unseenMatch?.index ?? fallbackMatch?.index ?? -1
  }

  if (userIndex < 0) {
    const stableAssistantIndex = next.findIndex((message) => (
      message.role === 'assistant'
      && (
        sharesIdentity(message, fallbackAssistantMessage, MESSAGE_IDENTITY_KEYS)
        || sharesIdentity(message, optimisticUserMessage, TURN_IDENTITY_KEYS)
        || sharesIdentity(message, fallbackAssistantMessage, TURN_IDENTITY_KEYS)
      )
    ))
    userIndex = stableAssistantIndex >= 0 ? stableAssistantIndex : next.length
    next.splice(userIndex, 0, optimisticUserMessage)
  }

  const matchedUser = next[userIndex]
  let assistantIndex = next.findIndex((message) => (
    message.role === 'assistant'
    && (
      sharesIdentity(message, fallbackAssistantMessage, MESSAGE_IDENTITY_KEYS)
      || sharesIdentity(message, optimisticUserMessage, TURN_IDENTITY_KEYS)
      || sharesIdentity(message, fallbackAssistantMessage, TURN_IDENTITY_KEYS)
      || assistantRepliesTo(message, matchedUser)
    )
  ))

  if (assistantIndex < 0) {
    for (let index = userIndex + 1; index < next.length; index += 1) {
      if (next[index].role === 'user') break
      if (next[index].role === 'assistant') {
        assistantIndex = index
        break
      }
    }
  }

  if (assistantIndex < 0 && fallbackAssistantMessage?.content) {
    const nextUserIndex = next.findIndex((message, index) => (
      index > userIndex && message.role === 'user'
    ))
    assistantIndex = nextUserIndex >= 0 ? nextUserIndex : next.length
    next.splice(assistantIndex, 0, fallbackAssistantMessage)
  } else if (assistantIndex >= 0 && fallbackAssistantMessage) {
    const serverAssistant = next[assistantIndex]
    next[assistantIndex] = {
      ...serverAssistant,
      ...(!serverAssistant.content && fallbackAssistantMessage.content
        ? { content: fallbackAssistantMessage.content }
        : {}),
      ...(!serverAssistant.progress && fallbackAssistantMessage.progress
        ? { progress: fallbackAssistantMessage.progress }
        : {}),
      ...((serverAssistant.proposed_actions || []).length === 0
        && (fallbackAssistantMessage.proposed_actions || []).length > 0
        ? { proposed_actions: fallbackAssistantMessage.proposed_actions }
        : {}),
      ...((serverAssistant.sources || []).length === 0
        && (fallbackAssistantMessage.sources || []).length > 0
        ? { sources: fallbackAssistantMessage.sources }
        : {}),
      ...((serverAssistant.citation_annotations || []).length === 0
        && (fallbackAssistantMessage.citation_annotations || []).length > 0
        ? { citation_annotations: fallbackAssistantMessage.citation_annotations }
        : {}),
    }
  }

  return attachTurnReferences(next)
}

/**
 * Render a registry generation into the transcript on screen.
 *
 * The first call for a turn places the streaming pair against whatever the
 * server already holds — the page may have mounted after the turn began, in
 * which case the persisted user message is already there and must not be
 * duplicated. Later calls replace the streamed turn in place.
 */
export function upsertGenerationTurn(messages, generation) {
  const next = Array.isArray(messages) ? [...messages] : []
  const { userMessage, assistantMessage } = generation
  const assistantIndex = next.findIndex((message) => message.id === assistantMessage.id)
  if (assistantIndex >= 0) {
    next[assistantIndex] = { ...next[assistantIndex], ...assistantMessage }
    const userIndex = assistantIndex - 1
    if (userIndex >= 0 && next[userIndex].role === 'user' && userMessage.referenceContext) {
      next[userIndex] = { ...next[userIndex], referenceContext: userMessage.referenceContext }
    }
    return next
  }

  const merged = mergeRefreshedTranscript(next, userMessage, assistantMessage)
  if (merged.some((message) => message.id === assistantMessage.id)) return merged

  // mergeRefreshedTranscript reconciles finished turns, so it only splices an
  // assistant that already carries text. A turn that has only just started has
  // none yet and still needs its placeholder mounted: that placeholder is what
  // shows retrieval progress, and what a failure before the first token is
  // reported in.
  let userIndex = merged.findIndex((message) => message.id === userMessage.id)
  if (userIndex < 0) {
    for (let index = merged.length - 1; index >= 0; index -= 1) {
      if (merged[index].role === 'user' && merged[index].content === userMessage.content) {
        userIndex = index
        break
      }
    }
  }
  if (userIndex < 0) return [...merged, assistantMessage]

  // Never add a second answer to a turn the server has already answered.
  let insertAt = userIndex + 1
  while (insertAt < merged.length && merged[insertAt].role !== 'user') {
    if (merged[insertAt].role === 'assistant') return merged
    insertAt += 1
  }
  merged.splice(insertAt, 0, assistantMessage)
  return merged
}

function persistedPublicRetrievalStatus(retrievalMetadata) {
  const publicRetrieval = retrievalMetadata?.public_retrieval
  return publicRetrieval?.state === 'service_unavailable'
    ? completedStreamStatus(publicRetrieval)
    : ''
}

function attachTurnReferences(messages) {
  const next = (Array.isArray(messages) ? messages : []).map((msg) => ({ ...msg }))

  for (let i = 0; i < next.length; i += 1) {
    if (next[i].role !== 'user') continue
    let assistantIndex = -1
    for (let idx = i + 1; idx < next.length; idx += 1) {
      if (next[idx].role === 'user') break
      if (next[idx].role === 'assistant') {
        assistantIndex = idx
        break
      }
    }
    if (assistantIndex < 0) continue

    const assistant = next[assistantIndex]
    const citedCount = citedSourceCount(
      assistant.content,
      assistant.sources,
      assistant.citation_annotations,
    )
    const context = buildReferenceContext({
      progress: assistant.progress,
      sources: assistant.sources,
      status: persistedPublicRetrievalStatus(assistant.retrieval_metadata),
      citedCount,
    })
    if (!context) continue

    next[i] = {
      ...next[i],
      referenceContext: next[i].referenceContext || context,
    }
    next[assistantIndex] = {
      ...assistant,
      referenceContext: assistant.referenceContext || context,
    }
  }

  return next
}

export default function ChatPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const routeConvId = searchParams.get('conv')
  const { conversations, setConversations, activeConvId, setActiveConvId, onConversationDeleted } = useAppShell()
  const { user, refreshUser } = useAuth()

  const [messages, setMessages] = useState([])
  // Drafts belong to their conversation, so a question half-typed in one thread
  // is never sent from another one opened in the meantime.
  const [inputValue, setInputValue] = useState(() => readChatDraft(activeConvId))
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [generationVersion, setGenerationVersion] = useState(0)
  const [queueVersion, setQueueVersion] = useState(0)
  const [includePublic, setIncludePublic] = useState(true)
  const [usePremium, setUsePremium] = useState(false)
  const [activeConvTitle, setActiveConvTitle] = useState('')
  const [matters, setMatters] = useState([])
  const [matterLinking, setMatterLinking] = useState(false)
  const [pendingAttachments, setPendingAttachments] = useState([])
  const [railOpen, setRailOpen] = useState(false)
  const [notice, setNotice] = useState(null)
  const [sourceHealth, setSourceHealth] = useState(null)
  const [metadataRefreshRetrying, setMetadataRefreshRetrying] = useState(false)
  const [privacySaving, setPrivacySaving] = useState(false)
  const fileInputRef = useRef(null)
  const messagesRef = useRef(messages)
  const inputValueRef = useRef(inputValue)
  const activeConvIdRef = useRef(activeConvId)
  const draftConversationIdRef = useRef(activeConvId)
  const loadedConversationIdRef = useRef(null)
  const loadingConversationIdRef = useRef(null)
  const conversationLoadRequestRef = useRef(0)
  const metadataRefreshContextRef = useRef(null)
  const metadataRefreshRequestRef = useRef(0)
  const metadataRefreshRetryingRef = useRef(false)
  const settledGenerationsRef = useRef(new Set())

  // Generations live in module scope so that they survive this page. Re-render
  // on every registry mutation; the derived values below are the only readers.
  useEffect(() => subscribeToChatGenerations(
    () => setGenerationVersion((version) => version + 1),
  ), [])
  useEffect(() => subscribeToChatQueue(
    () => setQueueVersion((version) => version + 1),
  ), [])

  // The registries are the real dependency of these; the version counters are
  // how they report a change.
  const liveGeneration = useMemo(
    () => getChatGeneration(activeConvId),
    [activeConvId, generationVersion],
  )
  const activeQueue = useMemo(
    () => getChatQueue(activeConvId),
    [activeConvId, queueVersion],
  )
  const activity = useChatActivity()
  const isResponding = liveGeneration?.status === GENERATION_STREAMING

  useEffect(() => {
    activeConvIdRef.current = activeConvId
  }, [activeConvId])

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    inputValueRef.current = inputValue
  }, [inputValue])

  // Park the draft of the thread being left and bring back the one being
  // opened. A draft typed before any conversation existed follows the
  // conversation created for it.
  useEffect(() => {
    const previousId = draftConversationIdRef.current
    if (previousId === activeConvId) return
    draftConversationIdRef.current = activeConvId
    if (previousId) saveChatDraft(previousId, inputValueRef.current)
    const restored = readChatDraft(activeConvId)
    if (restored || previousId) setInputValue(restored)
  }, [activeConvId])

  // Tell the queue which thread is on screen once its transcript is, so a
  // queued follow-up waits for this page to reconcile the answer ahead of it.
  useEffect(() => {
    const viewing = activeConvId
      && !isLoadingMessages
      && loadedConversationIdRef.current === activeConvId
    setViewedChatConversation(viewing ? activeConvId : null)
    if (viewing) rememberChatTranscript(activeConvId, messages)
  }, [activeConvId, isLoadingMessages, messages])

  // The response settings a conversation created from this page starts with,
  // read through a ref so a stale closure cannot create a conversation with
  // settings the user already changed.
  const preferencesRef = useRef({ usePremium: false, includePublic: true })
  useEffect(() => {
    preferencesRef.current = { usePremium, includePublic }
  }, [usePremium, includePublic])

  const newConversationPreferences = useCallback(() => ({
    use_premium_llm: preferencesRef.current.usePremium,
    include_public: preferencesRef.current.includePublic,
  }), [])

  const showErrorNotice = useCallback((title, fallback, err) => {
    setNotice({
      type: 'error',
      title,
      message: err?.response?.data?.detail || err?.message || fallback,
    })
  }, [])

  const togglePrivacyMode = useCallback(async () => {
    if (privacySaving || user?.demo) return
    const nextValue = !user?.privacy_mode
    if (nextValue && !window.confirm('Turn on Privacy Mode? This immediately revokes any connected Claude, ChatGPT, Codex, or other external MCP assistant. Native LawHand features remain available with Privacy Mode safeguards.')) return
    setPrivacySaving(true)
    try {
      await updateMe({ privacy_mode: nextValue })
      await refreshUser?.()
    } catch (err) {
      showErrorNotice('Privacy preference could not be saved', 'Please try again.', err)
    } finally {
      setPrivacySaving(false)
    }
  }, [privacySaving, refreshUser, showErrorNotice, user?.demo, user?.privacy_mode])

  // Unbind this page from the turns it was showing without touching the reads
  // themselves: a detached generation keeps draining in the registry so the
  // server still commits the answer.
  const detachActiveStream = useCallback(() => {
    detachChatGenerations()
  }, [])

  // Leaving Chat must not cancel an answer. The server persists a streamed turn
  // only once the read reaches [STREAM_COMPLETE]; aborting here made it record an
  // interruption instead, so opening another menu lost the response outright.
  // The read and its partial answer live in the generation registry, which
  // outlives this page — detach UI state and let the read finish. Queued
  // follow-ups keep draining too; only the draft needs parking.
  useEffect(() => () => {
    conversationLoadRequestRef.current += 1
    metadataRefreshRequestRef.current += 1
    detachChatGenerations()
    setViewedChatConversation(null)
    saveChatDraft(draftConversationIdRef.current, inputValueRef.current)
  }, [])

  const handleUploadClick = () => {
    fileInputRef.current?.click()
  }

  const handleFilesSelected = async (e) => {
    const files = e.target.files
    if (!files?.length) return
    await uploadFiles(Array.from(files))
    e.target.value = ''
  }

  const handleDropFiles = async (files) => {
    if (!files?.length) return
    await uploadFiles(files)
  }

  const uploadFiles = async (files) => {
    let convId = activeConvIdRef.current

    if (!convId) {
      try {
        const conv = await createConversation(newConversationPreferences())
        setConversations((prev) => [conv, ...prev])
        activeConvIdRef.current = conv.id
        loadedConversationIdRef.current = conv.id
        setActiveConvId(conv.id)
        setActiveConvTitle(conv.title || 'New Conversation')
        navigate(`/chat?conv=${conv.id}`)
        convId = conv.id
      } catch (err) {
        reportError('Failed to create conversation', err)
        showErrorNotice('Conversation could not be created', 'Start a new conversation and try again.', err)
        return
      }
    }

    for (const file of files) {
      try {
        const doc = await uploadChatAttachment(convId, file)
        setPendingAttachments((prev) => [...prev, { id: doc.id, filename: doc.filename }])
      } catch (err) {
        reportError('Upload failed:', err)
        showErrorNotice('Attachment upload failed', `${file.name} could not be uploaded.`, err)
      }
    }
  }

  const loadConversation = useCallback(async (id) => {
    if (!id) return
    const conversationChanged = Boolean(
      activeConvIdRef.current && activeConvIdRef.current !== id
    )
    detachActiveStream()
    if (conversationChanged) {
      setPendingAttachments([])
    }

    const loadRequestId = conversationLoadRequestRef.current + 1
    conversationLoadRequestRef.current = loadRequestId
    activeConvIdRef.current = id
    loadingConversationIdRef.current = id
    metadataRefreshContextRef.current = null
    metadataRefreshRequestRef.current += 1
    metadataRefreshRetryingRef.current = false
    setMetadataRefreshRetrying(false)
    setNotice((current) => current?.kind === 'metadata' ? null : current)
    setIsLoadingMessages(true)
    setActiveConvId(id)
    try {
      const data = await getConversation(id)
      if (
        conversationLoadRequestRef.current !== loadRequestId
        || activeConvIdRef.current !== id
      ) return

      loadedConversationIdRef.current = id
      // Reattach on arrival rather than waiting for the next token: a generation
      // this page left behind may still be running, and its turn belongs back in
      // view as soon as the saved transcript is.
      const loaded = attachTurnReferences(data.messages || [])
      const live = getChatGeneration(id)
      setMessages(
        live && live.status !== GENERATION_ABORTED
          ? upsertGenerationTurn(loaded, live)
          : loaded
      )
      setActiveConvTitle(data.conversation?.title || 'Untitled')
      if (data.conversation) {
        // The conversation, not this component, owns the tier and source
        // choice: reopening it must restore what the user picked rather than
        // silently dropping back to Standard with public case law on.
        setUsePremium(Boolean(data.conversation.use_premium_llm))
        setIncludePublic(data.conversation.include_public !== false)
        setConversations((prev) =>
          prev.some((conv) => conv.id === data.conversation.id)
            ? prev.map((conv) => (conv.id === data.conversation.id ? { ...conv, ...data.conversation } : conv))
            : [data.conversation, ...prev]
        )
      }
    } catch (err) {
      if (
        conversationLoadRequestRef.current !== loadRequestId
        || activeConvIdRef.current !== id
      ) return

      reportError('Failed to load conversation', err)
      const status = err?.response?.status
      // Never leave a previous conversation visible beneath a newly selected
      // conversation ID. A stale legal transcript is worse than an empty error
      // state because its action cards still remain operable.
      loadedConversationIdRef.current = id
      setMessages([])
      setActiveConvTitle('')
      if (status === 403 || status === 404) {
        setConversations((prev) => prev.filter((conv) => conv.id !== id))
        activeConvIdRef.current = null
        loadedConversationIdRef.current = null
        setActiveConvId(null)
        navigate('/chat', { replace: true })
      }
      showErrorNotice('Conversation could not be loaded', 'Select another conversation or retry.', err)
    } finally {
      if (conversationLoadRequestRef.current === loadRequestId) {
        loadingConversationIdRef.current = null
        setIsLoadingMessages(false)
      }
    }
  }, [detachActiveStream, navigate, setActiveConvId, setConversations, showErrorNotice])

  useEffect(() => {
    getMattersV2({ page_size: 200, sort_by: 'updated_at', sort_dir: 'desc' })
      .then((data) => setMatters(Array.isArray(data) ? data : (data.items || [])))
      .catch(() => setMatters([]))
    getLegalSourceHealth()
      .then(setSourceHealth)
      .catch(() => setSourceHealth({ available: false, status: 'unavailable', sources: [], partitions: [] }))
  }, [])

  // A prompt handed off from another page is a one-time draft, independent of
  // which conversation ultimately loads.
  useEffect(() => {
    const pending = sessionStorage.getItem('pending_chat_message')
    if (pending) {
      setInputValue(pending)
      sessionStorage.removeItem('pending_chat_message')
    }
  }, [])

  // Treat the URL as the durable conversation selection and react to browser
  // back/forward and AppShell Ctrl+N changes. Refs prevent the state updates
  // inside loadConversation from starting the same request twice.
  useEffect(() => {
    const targetId = routeConvId || activeConvId || conversations[0]?.id
    if (!targetId) return
    if (
      loadedConversationIdRef.current === targetId
      || loadingConversationIdRef.current === targetId
    ) return
    loadConversation(targetId)
  }, [conversations, activeConvId, routeConvId, loadConversation])

  const handleNewConversation = useCallback(async () => {
    try {
      detachActiveStream()
      conversationLoadRequestRef.current += 1
      const conv = await createConversation(newConversationPreferences())
      setConversations((prev) => [conv, ...prev])
      activeConvIdRef.current = conv.id
      loadedConversationIdRef.current = conv.id
      loadingConversationIdRef.current = null
      metadataRefreshContextRef.current = null
      metadataRefreshRequestRef.current += 1
      metadataRefreshRetryingRef.current = false
      setActiveConvId(conv.id)
      setMessages([])
      setActiveConvTitle(conv.title || 'New Conversation')
      setPendingAttachments([])
      setNotice(null)
      navigate(`/chat?conv=${conv.id}`)
    } catch (err) {
      reportError('Failed to create conversation', err)
      showErrorNotice('Conversation could not be created', 'Please try again.', err)
    }
  }, [detachActiveStream, navigate, setConversations, setActiveConvId, showErrorNotice])

  const handleConversationDeleted = useCallback(
    (id) => {
      // AppShell context performs the API delete + list mutation;
      // here we additionally clear local thread state if it was active.
      // A detached response for a conversation that no longer exists must not
      // keep consuming model time or attempt a late persistence write, and
      // nothing queued for it has anywhere left to go.
      abortChatGeneration(id)
      clearChatQueue(id)
      saveChatDraft(id, '')
      if (activeConvIdRef.current === id) {
        detachActiveStream()
        conversationLoadRequestRef.current += 1
        // Keep what is in the composer rather than filing it under a thread
        // that no longer exists.
        draftConversationIdRef.current = null
        activeConvIdRef.current = null
        loadedConversationIdRef.current = null
        loadingConversationIdRef.current = null
        metadataRefreshContextRef.current = null
        metadataRefreshRequestRef.current += 1
        metadataRefreshRetryingRef.current = false
        setMetadataRefreshRetrying(false)
        setActiveConvId(null)
        setMessages([])
        setActiveConvTitle('')
        setPendingAttachments([])
        navigate('/chat', { replace: true })
      }
    },
    [detachActiveStream, navigate, setActiveConvId]
  )

  const handleRailDeleteConversation = useCallback(
    async (id) => {
      try {
        const deleted = await onConversationDeleted(id)
        if (deleted === false) return
      } catch (err) {
        const status = err?.response?.status
        if (status !== 403 && status !== 404) {
          showErrorNotice('Conversation could not be deleted', 'Please try again.', err)
          return
        }
        setConversations((prev) => prev.filter((conv) => conv.id !== id))
      }
      handleConversationDeleted(id)
    },
    [onConversationDeleted, handleConversationDeleted, setConversations, showErrorNotice]
  )

  const handleRailSelectConversation = useCallback(
    (id) => {
      navigate(`/chat?conv=${id}`)
      loadConversation(id)
      setRailOpen(false)
    },
    [loadConversation, navigate]
  )

  const applyRefreshedConversation = useCallback((conversationId, refreshed, nextMessages) => {
    if (activeConvIdRef.current !== conversationId) return false
    loadedConversationIdRef.current = conversationId
    setMessages(nextMessages)
    setActiveConvTitle((current) => refreshed.conversation?.title || current)
    if (refreshed.conversation) {
      setConversations((prev) =>
        prev.some((conv) => conv.id === refreshed.conversation.id)
          ? prev.map((conv) => (conv.id === refreshed.conversation.id ? { ...conv, ...refreshed.conversation } : conv))
          : [refreshed.conversation, ...prev]
      )
    }
    return true
  }, [setConversations])

  const handleRetryMetadataRefresh = useCallback(async () => {
    const retryContext = metadataRefreshContextRef.current
    if (!retryContext || activeConvIdRef.current !== retryContext.conversationId) {
      setNotice({
        type: 'info',
        title: 'Select the affected conversation',
        message: 'Source metadata can only be retried while that conversation is open.',
      })
      return
    }
    if (metadataRefreshRetryingRef.current) return

    const retryRequestId = metadataRefreshRequestRef.current + 1
    metadataRefreshRequestRef.current = retryRequestId
    metadataRefreshRetryingRef.current = true
    setMetadataRefreshRetrying(true)
    setNotice({
      type: 'info',
      kind: 'metadata',
      title: 'Refreshing source metadata',
      message: 'Retrieving the persisted citations and proposed actions for this answer.',
    })
    try {
      const refreshed = await getConversation(retryContext.conversationId)
      if (
        metadataRefreshRequestRef.current !== retryRequestId
        || activeConvIdRef.current !== retryContext.conversationId
      ) return
      const nextMessages = mergeRefreshedTranscript(
        refreshed.messages,
        retryContext.userMessage,
        retryContext.fallbackAssistantMessage,
      )
      applyRefreshedConversation(retryContext.conversationId, refreshed, nextMessages)
      metadataRefreshContextRef.current = null
      setNotice({
        type: 'success',
        title: 'Sources refreshed',
        message: 'Citation links and proposed actions now reflect the persisted response.',
      })
    } catch (err) {
      if (
        metadataRefreshRequestRef.current !== retryRequestId
        || activeConvIdRef.current !== retryContext.conversationId
      ) return
      reportError('Failed to retry streamed message metadata', err)
      setNotice({
        type: 'warning',
        kind: 'metadata',
        title: 'Source metadata is still unavailable',
        message: err?.response?.data?.detail || err?.message || 'Retry before relying on this answer or approving any proposed work.',
      })
    } finally {
      if (metadataRefreshRequestRef.current === retryRequestId) {
        metadataRefreshRetryingRef.current = false
        setMetadataRefreshRetrying(false)
      }
    }
  }, [applyRefreshedConversation])

  const handleSend = useCallback(async () => {
    const content = inputValue.trim()
    if (!content || isSubmitting) return
    const hasLinkedMatter = conversations.some(
      (conversation) => conversation.id === activeConvIdRef.current && conversation.matter_id,
    )
    if (!usePremium && hasLinkedMatter) {
      setNotice({
        type: 'info',
        title: 'Matter context requires a private route',
        message: 'Standard AI cannot use matter context. Switch to Premium or unlink the matter and start a general conversation.',
      })
      return
    }
    if (!usePremium && pendingAttachments.length) {
      setNotice({
        type: 'info',
        title: 'Attachments require a private route',
        message: 'Standard AI cannot process attachments. Switch to Premium or remove the attachment before sending.',
      })
      return
    }

    const attachments = pendingAttachments
    const existingConvId = activeConvIdRef.current
    const clearComposer = (conversationId) => {
      setInputValue('')
      setPendingAttachments([])
      saveChatDraft(conversationId, '')
      // A draft started before any conversation existed has now been sent.
      if (!existingConvId) saveChatDraft(null, '')
    }

    // A conversation that is still answering holds the server's lease, and one
    // with messages already waiting keeps them ahead of this one — either way
    // the message waits its turn instead of the composer locking.
    if (existingConvId && chatSendMustQueue(existingConvId)) {
      enqueueChatMessage(existingConvId, { content, attachments, includePublic, usePremium })
      clearComposer(existingConvId)
      return
    }

    setIsSubmitting(true)
    try {
      let convId = existingConvId
      if (!convId) {
        try {
          const conv = await createConversation({
            ...newConversationPreferences(),
            title: content.slice(0, 60),
          })
          setConversations((prev) => [conv, ...prev])
          activeConvIdRef.current = conv.id
          loadedConversationIdRef.current = conv.id
          setActiveConvId(conv.id)
          setActiveConvTitle(conv.title || 'New Conversation')
          navigate(`/chat?conv=${conv.id}`)
          convId = conv.id
          // Brief pause to let DB commit settle before the streaming read
          await new Promise(r => setTimeout(r, 150))
          // Creating a conversation is the only send path with an await before
          // the optimistic turn is mounted. If the user selected another thread
          // during that window, do not append this turn to (or send it from) the
          // newly selected conversation.
          if (activeConvIdRef.current !== convId) return
        } catch (err) {
          reportError('Failed to create conversation', err)
          showErrorNotice('Conversation could not be created', 'Your message was not sent. Try again after starting a new conversation.', err)
          return
        }
      }

      metadataRefreshContextRef.current = null
      metadataRefreshRequestRef.current += 1
      metadataRefreshRetryingRef.current = false
      setMetadataRefreshRetrying(false)
      setNotice((current) => current?.kind === 'metadata' ? null : current)
      clearComposer(convId)

      // Other threads may have used every parallel slot while this one was
      // being created; if so it waits in line like any other follow-up.
      if (chatSendMustQueue(convId)) {
        enqueueChatMessage(convId, { content, attachments, includePublic, usePremium })
        return
      }

      // The registry — not this component — owns the turn from here on, so the
      // optimistic pair is registered rather than pushed into `messages`. An
      // effect renders whichever generation belongs to the conversation on
      // screen, which is what lets a page that mounts later pick this one up.
      startChatTurn({
        conversationId: convId,
        content,
        attachmentIds: attachments.map((attachment) => attachment.id),
        includePublic,
        usePremium,
        knownServerMessageIds: messagesRef.current
          .map((message) => String(message?.id || ''))
          .filter((id) => id && !/^(temp|stream|err)-/.test(id)),
        attached: true,
      })
    } finally {
      setIsSubmitting(false)
    }
  }, [inputValue, isSubmitting, includePublic, usePremium, conversations, pendingAttachments, newConversationPreferences, setConversations, setActiveConvId, showErrorNotice, navigate])

  // A generation outlives this page, so the transcript renders from the registry
  // rather than from the send handler: whichever ChatPage is mounted when tokens
  // arrive shows them, including one that mounted after the user came back from
  // another menu. Keying on the conversation on screen is also what keeps a
  // detached generation's tokens out of the thread the user moved to.
  useEffect(() => {
    if (!liveGeneration || !activeConvId) return
    if (liveGeneration.conversationId !== activeConvId) return
    if (liveGeneration.status === GENERATION_ABORTED) return
    // `isLoadingMessages` is a dependency, not just a guard: the transcript this
    // splices into arrives asynchronously, and a ref would not re-run the effect
    // once it did.
    if (isLoadingMessages || loadedConversationIdRef.current !== activeConvId) return
    setMessages((prev) => upsertGenerationTurn(prev, liveGeneration))
  }, [liveGeneration, activeConvId, isLoadingMessages])

  const settleGeneration = useCallback(async (generation) => {
    const {
      conversationId,
      clientTurnId,
      userMessage,
      assistantMessage,
      status,
      error,
      errorSource,
      attached,
    } = generation
    try {
      if (!attached) {
        // The page let go of this turn before it ended — another thread was
        // opened, or Chat was left and reopened. Either way the server finished
        // the read and persisted the outcome, so re-read rather than reconcile
        // against an optimistic turn this page may no longer be showing.
        await loadConversation(conversationId)
        return
      }

      if (status === GENERATION_ERROR) {
        // This page watched the turn fail, so fail its placeholder in place.
        // Re-reading the conversation would only swap one terminal message for
        // the interruption marker the server just wrote.
        const failedProgress = { ...assistantMessage.progress, complete: true, status: 'Response failed' }
        const failedReferenceContext = buildReferenceContext({ progress: failedProgress })
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  content: `An error occurred: ${error}`,
                  progress: failedProgress,
                  referenceContext: failedReferenceContext,
                }
              : msg.id === userMessage.id
                ? { ...msg, referenceContext: failedReferenceContext }
                : msg
          )
        )
        if (errorSource === 'request') {
          showErrorNotice('Message could not be sent', 'Please try again.', { message: error })
        } else {
          setNotice({
            type: 'error',
            title: 'Response could not be completed',
            message: error || 'The assistant stopped before finishing the response.',
          })
        }
        return
      }

      const fallbackAssistantMessage = {
        ...assistantMessage,
        referenceContext: buildReferenceContext({
          progress: assistantMessage.progress,
          sources: assistantMessage.sources,
          citedCount: (assistantMessage.sources || []).length,
        }),
      }
      try {
        const refreshed = await getConversation(conversationId)
        if (activeConvIdRef.current !== conversationId) return
        applyRefreshedConversation(
          conversationId,
          refreshed,
          mergeRefreshedTranscript(refreshed.messages, userMessage, fallbackAssistantMessage),
        )
        metadataRefreshContextRef.current = null
      } catch (refreshErr) {
        if (activeConvIdRef.current !== conversationId) return
        reportError('Failed to refresh streamed message metadata', refreshErr)
        metadataRefreshContextRef.current = {
          conversationId,
          userMessage,
          fallbackAssistantMessage,
        }
        setNotice({
          type: 'warning',
          kind: 'metadata',
          title: 'Source metadata could not be verified',
          message: 'The answer text is shown, but its persisted citation links and proposed actions could not be refreshed. Retry before relying on it.',
        })
      }
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === conversationId ? { ...conv, updated_at: new Date().toISOString() } : conv
        )
      )
    } finally {
      releaseChatGeneration(conversationId, clientTurnId)
    }
  }, [applyRefreshedConversation, loadConversation, setConversations, showErrorNotice])

  // Reconcile a finished turn against the saved transcript here rather than in
  // the send handler, so the page that is mounted — not the one that started the
  // answer — is the one that settles it.
  useEffect(() => {
    if (!liveGeneration || !activeConvId) return
    if (liveGeneration.conversationId !== activeConvId) return
    if (liveGeneration.status === GENERATION_STREAMING) return
    if (liveGeneration.status === GENERATION_ABORTED) {
      releaseChatGeneration(liveGeneration.conversationId, liveGeneration.clientTurnId)
      return
    }
    if (isLoadingMessages || loadedConversationIdRef.current !== activeConvId) return
    const turnKey = `${liveGeneration.conversationId}:${liveGeneration.clientTurnId}`
    if (settledGenerationsRef.current.has(turnKey)) return
    settledGenerationsRef.current.add(turnKey)
    settleGeneration(liveGeneration)
  }, [liveGeneration, activeConvId, isLoadingMessages, settleGeneration])

  const handleExportConversation = () => {
    if (messages.length === 0) {
      setNotice({
        type: 'info',
        title: 'Nothing to export',
        message: 'Start or select a conversation before exporting.',
      })
      return
    }

    const content = messages
      .map((msg) => `**${msg.role === 'user' ? 'You' : 'LawHand'}:**\n\n${msg.content}`)
      .join('\n\n---\n\n')

    const element = document.createElement('a')
    element.setAttribute('href', 'data:text/markdown;charset=utf-8,' + encodeURIComponent(content))
    element.setAttribute('download', `conversation-${activeConvId}.md`)
    element.style.display = 'none'
    document.body.appendChild(element)
    element.click()
    document.body.removeChild(element)
  }

  const handleRenameConversation = useCallback(async (title) => {
    if (!activeConvId) {
      throw new Error('Select a conversation before renaming it.')
    }
    const updated = await updateConversation(activeConvId, { title })
    setActiveConvTitle(updated.title || title)
    setConversations((prev) =>
      prev.map((conv) => (conv.id === updated.id ? { ...conv, ...updated } : conv))
    )
    return updated
  }, [activeConvId, setConversations])

  // A response setting belongs to the conversation, so it is saved the moment
  // it changes. A failure is surfaced rather than swallowed: the setting still
  // applies to the next message, but it would not survive a reopen.
  const persistPreference = useCallback(async (patch) => {
    const convId = activeConvIdRef.current
    if (!convId) return
    try {
      const updated = await updateConversation(convId, patch)
      setConversations((prev) =>
        prev.map((conv) => (conv.id === updated.id ? { ...conv, ...updated } : conv))
      )
    } catch (err) {
      reportError('Failed to save response settings', err)
      showErrorNotice(
        'Response setting could not be saved',
        'It applies to your next message but may not survive reopening this conversation.',
        err,
      )
    }
  }, [setConversations, showErrorNotice])

  const changeUsePremium = useCallback((value) => {
    const current = preferencesRef.current.usePremium
    const next = typeof value === 'function' ? value(current) : Boolean(value)
    if (next === current) return
    preferencesRef.current = { ...preferencesRef.current, usePremium: next }
    setUsePremium(next)
    persistPreference({ use_premium_llm: next })
  }, [persistPreference])

  const changeIncludePublic = useCallback((value) => {
    const current = preferencesRef.current.includePublic
    const next = typeof value === 'function' ? value(current) : Boolean(value)
    if (next === current) return
    preferencesRef.current = { ...preferencesRef.current, includePublic: next }
    setIncludePublic(next)
    persistPreference({ include_public: next })
  }, [persistPreference])

  const activeConversation = conversations.find((conv) => conv.id === activeConvId) || null
  const activeQueuedCount = activeQueue.items.length
  const conversationContextLocked = messages.length > 0
    || Number(activeConversation?.message_count || 0) > 0
    || Number(activeConversation?.attachment_count || 0) > 0
    || pendingAttachments.length > 0
  // Matter context is per conversation, so only this thread's own work in
  // flight holds it — another thread answering in the background does not.
  const matterLinkBlocked = isLoadingMessages
    || isSubmitting
    || isResponding
    || activeQueuedCount > 0
    || conversationContextLocked
  const linkedMatterId = activeConversation?.matter_id || null
  const linkedMatter = matters.find((matter) => matter.id === linkedMatterId) || null
  const linkedMatterName = linkedMatter?.matter_name || linkedMatter?.name || (linkedMatterId ? 'Linked matter' : '')

  // Returns whether the picker is done: false keeps it open so a failed link
  // can be retried without searching again.
  const applyMatterLink = useCallback(async (matterId) => {
    if (!activeConvId) {
      setNotice({ type: 'info', title: 'No conversation selected', message: 'Start or select a conversation before linking it to a matter.' })
      return true
    }
    if (matterLinkBlocked) {
      setNotice({
        type: 'info',
        title: 'Matter context is in use',
        message: conversationContextLocked
          ? 'Matter context is locked after a conversation has messages or attachments. Start a new conversation for a different matter.'
          : 'Wait for the conversation to load and the active response to finish before changing its matter context.',
      })
      return true
    }
    setMatterLinking(true)
    try {
      const updated = await updateConversation(activeConvId, { matter_id: matterId || '' })
      setConversations((prev) =>
        prev.map((conv) => (conv.id === updated.id ? { ...conv, ...updated } : conv))
      )
      setNotice({
        type: 'success',
        title: matterId ? 'Matter linked' : 'Matter unlinked',
        message: matterId ? 'Future messages in this conversation will use that matter context.' : 'This conversation is no longer tied to a matter.',
      })
      return true
    } catch (err) {
      showErrorNotice('Matter link failed', 'The conversation could not be updated.', err)
      return false
    } finally {
      setMatterLinking(false)
    }
  }, [activeConvId, conversationContextLocked, matterLinkBlocked, setConversations, showErrorNotice])

  // Pull a queued message back into the composer to change it. Only offered
  // while the composer is empty, so nothing already typed is overwritten.
  const handleEditQueued = useCallback((itemId) => {
    const convId = activeConvIdRef.current
    if (!convId || inputValueRef.current.trim()) return
    const item = removeQueuedChatMessage(convId, itemId)
    if (!item) return
    setInputValue(item.content)
    setPendingAttachments(item.attachments || [])
  }, [])

  const willQueue = useMemo(
    () => chatSendMustQueue(activeConvId),
    [activeConvId, generationVersion, queueVersion],
  )
  let otherResponding = 0
  let otherAttention = 0
  for (const [conversationId, state] of activity.byConversation) {
    if (conversationId === activeConvId) continue
    if (state.responding) otherResponding += 1
    if (state.replyReady || state.failed || state.paused) otherAttention += 1
  }
  const queueHint = !willQueue
    ? ''
    : activeQueue.paused
      ? 'Held until you resume the queue'
      : isResponding
        ? 'Sends when this response finishes'
        : activeQueuedCount > 0
          ? 'Sends after the messages already queued'
          : `${MAX_PARALLEL_CHAT_RESPONSES} chats are answering — sends when one finishes`

  return (
    <div className="flex h-full bg-brand-bg">
      {/* Desktop rail */}
      <ChatRail
        className="hidden lg:flex w-[300px] flex-shrink-0 border-r border-brand-line h-full"
        isOpen
        onNewConversation={handleNewConversation}
        onSelectConversation={handleRailSelectConversation}
        onDeleteConversation={handleRailDeleteConversation}
        sourceHealth={sourceHealth}
      />

      {/* Mobile rail drawer */}
      <div
        className={`fixed inset-0 z-30 bg-brand-ink/45 backdrop-blur-[2px] transition-opacity duration-300 lg:hidden ${railOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={() => setRailOpen(false)}
        aria-hidden="true"
      />
      <ChatRail
        className={`fixed inset-y-0 left-0 z-40 w-[min(340px,calc(100vw-1rem))] rounded-r-2xl border-r border-brand-line shadow-2xl transition-transform duration-300 ease-in-out lg:hidden ${railOpen ? 'sidebar-visible' : 'sidebar-hidden'}`}
        isOpen={railOpen}
        onNewConversation={() => { handleNewConversation(); setRailOpen(false) }}
        onSelectConversation={handleRailSelectConversation}
        onDeleteConversation={handleRailDeleteConversation}
        sourceHealth={sourceHealth}
        onClose={() => setRailOpen(false)}
      />

      {/* Thread column */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        <ChatHeader
          activeConvTitle={activeConvTitle}
          usePremium={usePremium}
          setUsePremium={changeUsePremium}
          demoMode={Boolean(user?.demo)}
          standardMatterContextAllowed={Boolean(user?.standard_matter_context_allowed)}
          includePublic={includePublic}
          setIncludePublic={changeIncludePublic}
          publicCaseLawAllowed={user?.public_case_law_allowed !== false}
          privacyMode={Boolean(user?.privacy_mode)}
          privacySaving={privacySaving}
          onTogglePrivacy={togglePrivacyMode}
          onExportConversation={handleExportConversation}
          onRenameConversation={handleRenameConversation}
          onRenameError={(message) => setNotice({ type: 'error', title: 'Rename failed', message })}
          onOpenSidebar={() => setRailOpen(true)}
          backgroundActivity={{ responding: otherResponding, attention: otherAttention }}
          context={(
            <ChatContextPicker
              conversationId={activeConvId}
              linkedMatterId={linkedMatterId}
              linkedMatter={linkedMatter}
              linkedMatterName={linkedMatterName}
              matters={matters}
              linking={matterLinking}
              blocked={matterLinkBlocked}
              locked={conversationContextLocked}
              onLink={applyMatterLink}
              onOpenMatter={(matterId) => navigate(`/matters/${matterId}`)}
            />
          )}
        />

        {notice && (
          <div className="px-2 pt-2 sm:px-4 sm:pt-3 md:px-6">
            <div className="mx-auto w-full max-w-4xl">
              <AlertBanner
                type={notice.type}
                title={notice.title}
                actionLabel={notice.kind === 'metadata'
                  ? (metadataRefreshRetrying ? 'Retrying…' : 'Retry source metadata')
                  : notice.actionLabel}
                onAction={notice.kind === 'metadata' ? handleRetryMetadataRefresh : notice.onAction}
                onDismiss={() => setNotice(null)}
              >
                {notice.message}
              </AlertBanner>
            </div>
          </div>
        )}

        <Messages
          messages={messages}
          isLoading={isLoadingMessages}
          isSending={isResponding}
          conversationKey={activeConvId}
          onPromptSelect={(prompt) => setInputValue(prompt)}
        />

        <ChatInput
          inputValue={inputValue}
          onInputChange={setInputValue}
          onSend={handleSend}
          onUploadClick={handleUploadClick}
          onDropFiles={handleDropFiles}
          isSending={isSubmitting}
          isResponding={isResponding}
          willQueue={willQueue}
          queueHint={queueHint}
          otherRespondingCount={otherResponding}
          disabled={false}
          pendingAttachments={pendingAttachments}
          onRemoveAttachment={(id) =>
            setPendingAttachments((prev) => prev.filter((a) => a.id !== id))
          }
          suggestions={messages.length > 0 ? [] : undefined}
          queuedMessages={activeQueue.items}
          queuePaused={activeQueue.paused}
          onRemoveQueued={(itemId) => removeQueuedChatMessage(activeConvId, itemId)}
          onEditQueued={handleEditQueued}
          onResumeQueue={() => resumeChatQueue(activeConvId)}
          onClearQueue={() => clearChatQueue(activeConvId)}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          multiple
          className="hidden"
          onChange={handleFilesSelected}
        />
      </div>
    </div>
  )
}
