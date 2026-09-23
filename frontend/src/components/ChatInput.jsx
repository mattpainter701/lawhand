import { useLayoutEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  FileText,
  ListPlus,
  Paperclip,
  Pencil,
  Play,
  Send,
  Sparkles,
  X,
} from 'lucide-react'

const QUICK_EXAMPLES = [
  'Summarize the key issues and open questions',
  'Draft a client-ready follow-up',
  'Build a chronology from the available sources',
  'Compare the governing standards',
]

// On a touch keyboard there is no Shift+Enter, so Return has to be able to
// start a new line; the send button (and the keyboard's own send key) sends.
function prefersNewlineOnEnter() {
  try {
    return Boolean(window.matchMedia?.('(pointer: coarse)')?.matches)
  } catch {
    return false
  }
}

function QueuedMessages({
  items,
  paused,
  canEdit,
  onRemove,
  onEdit,
  onResume,
  onClear,
}) {
  if (!items.length) return null
  return (
    <section
      aria-label="Queued messages"
      className={`overflow-hidden rounded-xl border ${
        paused ? 'border-amber-300 bg-amber-50' : 'border-brand-line bg-brand-surface-2'
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-xs">
        {paused ? (
          <p role="status" className="flex min-w-0 flex-1 items-center gap-1.5 font-semibold text-amber-900">
            <AlertTriangle size={14} aria-hidden="true" className="shrink-0" />
            <span className="min-w-0">{paused}</span>
          </p>
        ) : (
          <p className="min-w-0 flex-1 font-semibold text-brand-ink">
            Up next <span className="font-mono text-brand-muted">· {items.length}</span>
            <span className="ml-2 hidden font-normal text-brand-muted sm:inline">
              Sends in order as each response finishes
            </span>
          </p>
        )}
        {paused && onResume && (
          <button
            type="button"
            onClick={onResume}
            className="inline-flex min-h-8 items-center gap-1 rounded-lg bg-brand-ink px-2.5 font-semibold text-white hover:bg-brand-ink-2"
          >
            <Play size={12} aria-hidden="true" /> Resume queue
          </button>
        )}
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex min-h-8 items-center rounded-lg px-2 font-semibold text-brand-muted hover:bg-brand-surface hover:text-brand-ink"
          >
            Clear
          </button>
        )}
      </div>
      <ol className="max-h-28 divide-y divide-brand-line overflow-y-auto border-t border-brand-line sm:max-h-40">
        {items.map((item, index) => (
          <li key={item.id} className="flex items-center gap-2 bg-brand-surface px-3 py-1.5">
            <span className="w-4 shrink-0 text-center font-mono text-[10px] text-brand-muted">{index + 1}</span>
            <p className="min-w-0 flex-1 truncate text-sm text-brand-ink" title={item.content}>{item.content}</p>
            {item.attachments?.length > 0 && (
              <span className="inline-flex shrink-0 items-center gap-0.5 font-mono text-[10px] text-brand-muted" title={item.attachments.map((attachment) => attachment.filename).join(', ')}>
                <Paperclip size={11} aria-hidden="true" />
                {item.attachments.length}
                <span className="sr-only">{item.attachments.length === 1 ? ' attachment' : ' attachments'}</span>
              </span>
            )}
            {onEdit && (
              <button
                type="button"
                onClick={() => onEdit(item.id)}
                disabled={!canEdit}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-brand-muted hover:bg-brand-bg-soft hover:text-brand-ink disabled:cursor-not-allowed disabled:opacity-40"
                aria-label={`Edit queued message ${index + 1}`}
                title={canEdit ? 'Move back into the composer to edit' : 'Send or clear your draft first'}
              >
                <Pencil size={13} />
              </button>
            )}
            {onRemove && (
              <button
                type="button"
                onClick={() => onRemove(item.id)}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-brand-muted hover:bg-brand-rose/10 hover:text-brand-rose"
                aria-label={`Remove queued message ${index + 1}`}
                title="Remove from queue"
              >
                <X size={14} />
              </button>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function ChatInput({
  inputValue,
  onInputChange,
  onSend,
  onUploadClick,
  onDropFiles,
  // True only while this component's own send is being set up (for example,
  // creating the conversation). An answer streaming does not lock the composer.
  isSending,
  isResponding = false,
  willQueue = false,
  queueHint = '',
  otherRespondingCount = 0,
  disabled,
  sendDisabled = false,
  sendDisabledLabel = 'Wait for the current response to finish',
  pendingAttachments = [],
  onRemoveAttachment,
  queuedMessages = [],
  queuePaused = null,
  onRemoveQueued,
  onEditQueued,
  onResumeQueue,
  onClearQueue,
  // Kept to one line on a phone: an empty textarea sizes to its placeholder.
  placeholder = 'Ask about a matter or legal issue…',
  suggestions = QUICK_EXAMPLES,
}) {
  const textareaRef = useRef(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const charCount = inputValue.length
  const hasText = Boolean(inputValue.trim())
  const canSubmit = hasText && !disabled && !isSending && !sendDisabled

  // Grow with the draft and shrink back once it is sent; CSS caps the height.
  useLayoutEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    if (element.scrollHeight) element.style.height = `${element.scrollHeight}px`
  }, [inputValue])

  const handleDragEnter = (event) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragOver(true)
  }

  const handleDragLeave = (event) => {
    event.preventDefault()
    event.stopPropagation()
    if (!event.currentTarget.contains(event.relatedTarget)) setIsDragOver(false)
  }

  const handleDragOver = (event) => {
    event.preventDefault()
    event.stopPropagation()
  }

  const handleDrop = (event) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragOver(false)
    const files = event.dataTransfer?.files
    if (files?.length && onDropFiles) onDropFiles(Array.from(files))
  }

  const handleKeyDown = (event) => {
    if (event.key !== 'Enter' || event.nativeEvent?.isComposing) return
    const forceSend = event.metaKey || event.ctrlKey
    if (!forceSend && (event.shiftKey || prefersNewlineOnEnter())) return
    event.preventDefault()
    if (canSubmit) onSend()
  }

  const chooseSuggestion = (suggestion) => {
    onInputChange(suggestion)
    textareaRef.current?.focus()
  }

  const sendLabel = isSending
    ? 'Sending message'
    : sendDisabled
      ? sendDisabledLabel
      : willQueue
        ? 'Queue message'
        : 'Send message'

  const status = isResponding
    ? 'Responding…'
    : otherRespondingCount > 0
      ? `${otherRespondingCount} other ${otherRespondingCount === 1 ? 'chat' : 'chats'} responding`
      : ''

  return (
    <div
      className="relative z-20 flex-shrink-0 bg-gradient-to-t from-brand-bg via-brand-bg to-brand-bg/0 px-2 pb-2 pt-1 sm:px-4 sm:pb-3 md:px-6"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {isDragOver && (
        <div className="pointer-events-none absolute inset-2 z-30 flex items-center justify-center rounded-2xl border-2 border-dashed border-brand-accent bg-brand-surface/95">
          <p className="flex items-center gap-2 text-sm font-semibold text-brand-accent-2">
            <Paperclip size={17} /> Add files to this conversation
          </p>
        </div>
      )}

      <div className="mx-auto flex max-w-4xl flex-col gap-2">
        {!inputValue && pendingAttachments.length === 0 && queuedMessages.length === 0 && suggestions.length > 0 && (
          <div className="-mx-1 hidden gap-2 overflow-x-auto px-1 pb-0.5 sm:flex" aria-label="Suggested prompts">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => chooseSuggestion(suggestion)}
                className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full border border-brand-line bg-brand-surface px-3 text-xs font-medium text-brand-ink hover:border-brand-line-2 hover:bg-brand-bg-soft"
              >
                <Sparkles size={13} className="text-brand-accent-2" />
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <QueuedMessages
          items={queuedMessages}
          paused={queuePaused}
          canEdit={!hasText}
          onRemove={onRemoveQueued}
          onEdit={onEditQueued}
          onResume={onResumeQueue}
          onClear={onClearQueue}
        />

        {pendingAttachments.length > 0 && (
          <div className="flex flex-wrap gap-2" aria-label="Pending attachments">
            {pendingAttachments.map((attachment) => (
              <span
                key={attachment.id}
                className="inline-flex min-h-9 max-w-full items-center gap-2 rounded-lg border border-brand-line bg-brand-surface px-2.5 text-xs text-brand-ink"
              >
                <FileText size={13} className="shrink-0 text-brand-accent-2" />
                <span className="max-w-56 truncate">{attachment.filename}</span>
                {onRemoveAttachment && (
                  <button
                    type="button"
                    onClick={() => onRemoveAttachment(attachment.id)}
                    className="rounded-md p-1 text-brand-muted hover:bg-brand-bg-soft hover:text-brand-rose"
                    aria-label={`Remove ${attachment.filename}`}
                  >
                    <X size={13} />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}

        <div className="rounded-2xl border border-brand-line-2 bg-brand-surface shadow-sm focus-within:border-brand-accent focus-within:ring-2 focus-within:ring-brand-accent/15">
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={willQueue ? 'Type a follow-up to queue…' : placeholder}
            aria-label="Message the assistant"
            aria-describedby="assistant-review-note"
            enterKeyHint={willQueue ? 'enter' : 'send'}
            className="block max-h-[132px] min-h-[44px] w-full resize-none overflow-y-auto bg-transparent px-3.5 pb-1 pt-3 text-[15px] leading-relaxed text-brand-ink placeholder-brand-muted focus:outline-none sm:max-h-[220px] sm:min-h-[52px]"
            rows={1}
            disabled={disabled}
          />

          <div className="flex items-center justify-between gap-2 px-2 pb-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <button
                type="button"
                onClick={onUploadClick}
                disabled={disabled || isSending}
                className="inline-flex h-9 min-w-9 items-center justify-center gap-2 rounded-full px-2 text-xs font-semibold text-brand-muted hover:bg-brand-bg-soft hover:text-brand-ink disabled:cursor-not-allowed disabled:opacity-50 sm:px-2.5"
                aria-label="Attach a document"
              >
                <Paperclip size={16} />
                <span className="hidden sm:inline">Attach</span>
              </button>
              {status && (
                <span role="status" className="flex min-w-0 items-center gap-1.5 text-[11px] font-medium text-brand-muted">
                  <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-brand-accent" aria-hidden="true" />
                  <span className="truncate">{status}</span>
                </span>
              )}
              {!status && charCount > 0 && (
                <span className={`text-[10px] font-mono ${charCount > 1000 ? 'text-brand-rose' : 'text-brand-muted'}`}>
                  {charCount.toLocaleString()}
                </span>
              )}
            </div>

            <div className="flex min-w-0 items-center gap-2">
              {willQueue && hasText && queueHint && (
                <span className="hidden truncate text-[11px] text-brand-muted md:inline">{queueHint}</span>
              )}
              {!willQueue && (
                <span className="hidden text-[10px] text-brand-muted lg:inline">Enter to send · Shift+Enter for a new line</span>
              )}
              <button
                type="button"
                onClick={onSend}
                disabled={!canSubmit}
                title={willQueue && queueHint ? queueHint : undefined}
                className={`inline-flex h-9 min-w-9 shrink-0 items-center justify-center gap-2 rounded-full px-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:bg-brand-line-2 disabled:text-brand-muted sm:px-3.5 ${
                  willQueue
                    ? 'bg-brand-accent text-white hover:bg-brand-accent-2'
                    : 'bg-brand-ink text-white hover:bg-brand-ink-2'
                }`}
                aria-label={sendLabel}
              >
                {isSending ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden="true" />
                ) : willQueue ? (
                  <>
                    <ListPlus size={16} aria-hidden="true" />
                    <span className="hidden sm:inline">Queue</span>
                  </>
                ) : (
                  <>
                    <Send size={16} aria-hidden="true" />
                    <span className="hidden sm:inline">Send</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        <p id="assistant-review-note" className="hidden text-center text-[10px] leading-relaxed text-brand-muted sm:block">
          Verify cited authority, dates, and legal conclusions before relying on assistant work.
        </p>
      </div>
    </div>
  )
}
