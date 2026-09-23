import { useEffect, useRef, useState } from 'react'
import { Briefcase, ChevronDown, ExternalLink, Link2, Search, Unlink } from 'lucide-react'

/**
 * The matter a conversation draws on, as one line under the conversation title.
 *
 * It used to be a card of its own between the header and the transcript; on a
 * phone that card, the header, and the tag legend together left the answer a
 * few lines of screen. The picker it opens is positioned against the header, so
 * the header is expected to be the nearest positioned ancestor.
 */
export default function ChatContextPicker({
  conversationId,
  linkedMatterId,
  linkedMatter,
  linkedMatterName,
  matters = [],
  linking = false,
  blocked = false,
  locked = false,
  onLink,
  onOpenMatter,
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const containerRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined

    const handlePointerDown = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false)
    }
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpen(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const normalizedQuery = query.trim().toLowerCase()
  const filteredMatters = matters
    .filter((matter) => {
      if (!normalizedQuery) return true
      return [matter.matter_name, matter.name, matter.case_number, matter.client_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery))
    })
    .slice(0, 20)

  const choose = async (matterId) => {
    const linked = await onLink?.(matterId)
    if (linked === false) return
    setOpen(false)
    setQuery('')
  }

  const summary = linkedMatterId
    ? `Using your profile + ${linkedMatterName}`
    : conversationId
      ? 'Using your profile'
      : 'Using your profile — start a conversation to add a matter'

  return (
    <div ref={containerRef} className="flex min-w-0 items-center gap-1.5">
      <Briefcase
        size={13}
        aria-hidden="true"
        className={`shrink-0 ${linkedMatterId ? 'text-brand-accent-2' : 'text-brand-muted'}`}
      />
      <p className={`min-w-0 truncate text-[11px] sm:text-xs ${linkedMatterId ? 'font-semibold text-brand-ink' : 'text-brand-muted'}`}>
        {summary}
        {linkedMatter?.case_number ? (
          <span className="ml-1.5 font-normal text-brand-muted">{linkedMatter.case_number}</span>
        ) : null}
      </p>
      {linkedMatterId && (
        <button
          type="button"
          onClick={() => onOpenMatter?.(linkedMatterId)}
          className="hidden h-6 w-6 shrink-0 items-center justify-center rounded-full text-brand-muted hover:bg-brand-bg-soft hover:text-brand-ink sm:inline-flex"
          aria-label={`Open ${linkedMatterName}`}
          title="Open linked matter"
        >
          <ExternalLink size={13} />
        </button>
      )}
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        disabled={!conversationId || linking || blocked}
        title={locked
          ? 'Matter context is locked after messages or attachments are added'
          : blocked
            ? 'Wait for the conversation to load or finish responding'
            : linkedMatterId ? 'Change matter context' : 'Link this conversation to a matter'}
        aria-label={linkedMatterId ? 'Change matter context' : 'Link matter'}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="inline-flex h-7 shrink-0 items-center gap-1 rounded-full border border-brand-line bg-brand-surface px-2 text-[11px] font-semibold text-brand-ink hover:bg-brand-bg-soft disabled:cursor-not-allowed disabled:opacity-50 sm:h-6"
      >
        <Link2 size={12} className="hidden sm:block" aria-hidden="true" />
        <span className="hidden sm:inline">{linkedMatterId ? 'Change' : 'Link matter'}</span>
        <ChevronDown size={12} aria-hidden="true" />
      </button>

      {open && !blocked && (
        <div
          role="dialog"
          aria-label="Choose matter context"
          className="absolute inset-x-2 top-[calc(100%+0.25rem)] z-30 overflow-hidden rounded-2xl border border-brand-line bg-brand-surface shadow-xl sm:inset-x-auto sm:left-4 sm:w-[430px] md:left-6"
        >
          <div className="border-b border-brand-line p-3">
            <p className="mb-2 text-xs font-semibold text-brand-ink">Choose matter context</p>
            <div className="relative">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search matters"
                placeholder="Search by matter, client, or case number"
                className="w-full rounded-xl border border-brand-line bg-brand-bg py-2.5 pl-9 pr-3 text-sm text-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-accent"
                autoFocus
              />
            </div>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {filteredMatters.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-brand-muted">No matters found.</p>
            ) : filteredMatters.map((matter) => (
              <button
                key={matter.id}
                type="button"
                onClick={() => choose(matter.id)}
                disabled={linking}
                className="block w-full border-b border-brand-line px-4 py-3 text-left last:border-0 hover:bg-brand-bg-soft disabled:opacity-50"
              >
                <span className="block truncate text-sm font-semibold text-brand-ink">{matter.matter_name || matter.name || 'Untitled matter'}</span>
                <span className="mt-0.5 block truncate text-xs text-brand-muted">
                  {[matter.case_number, matter.client_name, matter.status].filter(Boolean).join(' · ') || 'Matter'}
                </span>
              </button>
            ))}
          </div>
          {linkedMatterId && (
            <div className="border-t border-brand-line p-2">
              <button
                type="button"
                onClick={() => choose('')}
                disabled={linking}
                className="flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-sm font-medium text-brand-muted hover:bg-brand-rose/10 hover:text-brand-rose disabled:opacity-50"
              >
                <Unlink size={15} /> Remove matter context
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
