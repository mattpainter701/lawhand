import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ArrowDown, FileSearch, ListTree, PenLine, Scale, Sparkles } from 'lucide-react'
import ChatMessage from './ChatMessage'
import { MessageSkeleton } from './LoadingSkeleton'

// How close to the bottom still counts as "following along". Anything further
// up means the reader scrolled back on purpose, and streaming must not yank
// them down again.
const STICK_TO_BOTTOM_PX = 96

const STARTER_ACTIONS = [
  {
    icon: FileSearch,
    title: 'Review a source',
    prompt: 'Summarize the key issues, authorities, and open questions in the available sources.',
  },
  {
    icon: PenLine,
    title: 'Draft work product',
    prompt: 'Draft a client-ready follow-up that explains the next steps and questions we still need answered.',
  },
  {
    icon: ListTree,
    title: 'Build a chronology',
    prompt: 'Create a dated chronology from the available matter context and documents.',
  },
]

function EmptyState({ onPromptSelect }) {
  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center py-4 text-center sm:py-12">
      <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-brand-ink text-brand-bg shadow-sm sm:h-14 sm:w-14 sm:rounded-2xl">
        <Scale className="h-7 w-7" strokeWidth={1.5} />
      </div>
      <p className="mt-3 text-[10px] font-bold uppercase tracking-[0.16em] text-brand-accent-2 sm:mt-5 sm:text-[11px]">
        Research, drafting, and analysis
      </p>
      <h2 className="mt-1.5 font-serif text-xl font-semibold tracking-tight text-brand-ink sm:mt-2 sm:text-3xl">
        What do you want to move forward?
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-xs leading-relaxed text-brand-ink-2 sm:mt-3 sm:text-base">
        Link a matter or attach a document for focused context, then choose a starting point or ask in your own words.
      </p>

      <div className="mt-4 grid gap-2 text-left sm:mt-7 sm:grid-cols-3 sm:gap-3">
        {STARTER_ACTIONS.map(({ icon: Icon, title, prompt }) => (
          <button
            key={title}
            type="button"
            onClick={() => onPromptSelect?.(prompt)}
            className="group flex min-h-11 items-center gap-3 rounded-xl border border-brand-line bg-brand-surface p-2.5 hover:-translate-y-0.5 hover:border-brand-line-2 hover:shadow-sm sm:block sm:rounded-2xl sm:p-4"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-bg-soft text-brand-accent-2 group-hover:bg-brand-accent/10">
              <Icon size={18} />
            </span>
            <span className="block text-sm font-semibold text-brand-ink sm:mt-4">{title}</span>
            <span className="mt-1.5 hidden text-xs leading-relaxed text-brand-muted sm:block">{prompt}</span>
          </button>
        ))}
      </div>

      <div className="mt-7 hidden rounded-2xl border border-brand-line bg-brand-surface/70 p-4 text-left sm:block">
        <div className="flex items-start gap-3">
          <Sparkles size={17} className="mt-0.5 shrink-0 text-brand-accent-2" />
          <div>
            <p className="text-sm font-semibold text-brand-ink">Answers show their working context</p>
            <p className="mt-1 text-xs leading-relaxed text-brand-muted">
              Retrieved sources, review tags, and matter context stay visible so the result can be checked before use.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Messages({
  messages,
  isLoading,
  isSending,
  conversationKey = null,
  onMessageScroll,
  onPromptSelect,
}) {
  const scrollRef = useRef(null)
  const followingRef = useRef(true)
  const [following, setFollowing] = useState(true)

  const scrollToLatest = useCallback((behavior = 'auto') => {
    const element = scrollRef.current
    if (!element) return
    followingRef.current = true
    setFollowing(true)
    if (typeof element.scrollTo === 'function') {
      element.scrollTo({ top: element.scrollHeight, behavior })
    } else {
      element.scrollTop = element.scrollHeight
    }
  }, [])

  // A different conversation always opens at its latest message.
  useEffect(() => {
    followingRef.current = true
    setFollowing(true)
  }, [conversationKey])

  // Keep up with a streaming answer only while the reader is at the bottom.
  // Layout effect, so each token lands already in view rather than a frame late.
  useLayoutEffect(() => {
    if (!followingRef.current) return
    const element = scrollRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [messages, isSending, isLoading, conversationKey])

  const handleScroll = (event) => {
    const element = event.currentTarget
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight
    const atBottom = distance <= STICK_TO_BOTTOM_PX
    if (atBottom !== followingRef.current) {
      followingRef.current = atBottom
      setFollowing(atBottom)
    }
    onMessageScroll?.(event)
  }

  const hasMessages = Array.isArray(messages) && messages.length > 0

  return (
    <div
      ref={scrollRef}
      className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3 sm:px-5 sm:py-5 md:px-8 md:py-6"
      onScroll={handleScroll}
      aria-live={isSending ? 'polite' : 'off'}
    >
      {isLoading ? (
        <div className="mx-auto w-full max-w-4xl">
          <MessageSkeleton />
          <MessageSkeleton />
        </div>
      ) : !hasMessages ? (
        <EmptyState onPromptSelect={onPromptSelect} />
      ) : (
        <div className="mx-auto w-full max-w-4xl">
          {messages.map((message, index) => (
            <div
              key={message.id}
              className="animate-fade-in"
              style={{ animationDelay: `${Math.min(index * 35, 210)}ms` }}
            >
              <ChatMessage message={message} />
            </div>
          ))}
        </div>
      )}

      {hasMessages && !isLoading && !following && (
        <div className="pointer-events-none sticky bottom-2 z-10 flex justify-center">
          <button
            type="button"
            onClick={() => scrollToLatest('smooth')}
            className="pointer-events-auto inline-flex min-h-9 items-center gap-1.5 rounded-full border border-brand-line bg-brand-surface px-3.5 text-xs font-semibold text-brand-ink shadow-lg hover:bg-brand-bg-soft"
          >
            <ArrowDown size={14} aria-hidden="true" />
            {isSending ? 'Jump to the answer' : 'Jump to latest'}
          </button>
        </div>
      )}
    </div>
  )
}
