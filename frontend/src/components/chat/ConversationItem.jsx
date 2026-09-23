import { LoaderCircle, Pin, Trash2 } from 'lucide-react'

function ActivityMarker({ activity }) {
  if (!activity) return null
  if (activity.responding) {
    return (
      <span className="inline-flex shrink-0 items-center text-brand-accent-2" title="Responding">
        <LoaderCircle size={13} className="animate-spin" aria-hidden="true" />
        <span className="sr-only">Responding</span>
      </span>
    )
  }
  if (activity.paused) {
    return (
      <span className="shrink-0 rounded-full bg-amber-100 px-1.5 py-px text-[10px] font-semibold text-amber-900" title="Queued messages are held after a failed response">
        Held
      </span>
    )
  }
  if (activity.failed) {
    return (
      <span className="inline-flex shrink-0 items-center" title="Response failed">
        <span className="h-2 w-2 rounded-full bg-brand-rose" aria-hidden="true" />
        <span className="sr-only">Response failed</span>
      </span>
    )
  }
  if (activity.replyReady) {
    return (
      <span className="inline-flex shrink-0 items-center" title="New reply">
        <span className="h-2 w-2 rounded-full bg-brand-accent" aria-hidden="true" />
        <span className="sr-only">New reply</span>
      </span>
    )
  }
  return null
}

export default function ConversationItem({
  conv,
  index,
  isActive,
  isPinned,
  activity = null,
  onClick,
  onDelete,
  onTogglePin,
}) {
  const title = conv.title || 'Untitled conversation'
  const queued = Number(activity?.queued || 0)

  return (
    <div
      className={`group mx-2 flex items-stretch rounded-xl text-left text-sm transition-colors ${
        isActive
          ? 'bg-brand-surface font-medium text-brand-ink shadow-sm ring-1 ring-brand-line'
          : 'text-brand-ink-2 hover:bg-brand-bg-soft hover:text-brand-ink'
      }`}
    >
      <button
        type="button"
        aria-label={title}
        aria-current={isActive ? 'page' : undefined}
        onClick={onClick}
        className="flex min-h-[44px] min-w-0 flex-1 items-center gap-2.5 rounded-xl py-2 pl-3 pr-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-ink"
      >
        <span className="flex w-[18px] shrink-0 items-center justify-center">
          {isPinned
            ? <Pin size={11} className="text-brand-accent" fill="currentColor" />
            : <span className="font-mono text-[10px] text-brand-muted">{String(index + 1).padStart(2, '0')}</span>
          }
        </span>
        <span className="min-w-0 flex-1 truncate leading-tight" title={title}>{title}</span>
      </button>
      <div className="flex shrink-0 items-center gap-1 pr-1">
        <ActivityMarker activity={activity} />
        {queued > 0 && !activity?.paused && (
          <span className="shrink-0 rounded-full bg-brand-bg-soft px-1.5 py-px font-mono text-[10px] text-brand-ink-2" title={`${queued} queued`}>
            +{queued}
            <span className="sr-only"> queued</span>
          </span>
        )}
        <div className="flex items-center">
          <button
            type="button"
            onClick={() => onTogglePin?.(conv.id)}
            className={`inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
              isPinned
                ? 'text-brand-accent hover:bg-brand-accent/10'
                : 'text-brand-muted hover:bg-brand-accent/10 hover:text-brand-accent'
            }`}
            aria-label={`${isPinned ? 'Unpin' : 'Pin'} ${title}`}
            title={isPinned ? 'Unpin conversation' : 'Pin conversation'}
          >
            <Pin size={13} fill={isPinned ? 'currentColor' : 'none'} />
          </button>
          <button
            type="button"
            onClick={() => onDelete(conv.id)}
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-brand-muted transition-colors hover:bg-brand-rose/10 hover:text-brand-rose focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-rose"
            aria-label={`Delete ${title}`}
            title="Delete conversation"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </div>
  )
}
