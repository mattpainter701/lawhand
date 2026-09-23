import React, { useEffect, useRef, useState } from 'react'
import { Tags } from 'lucide-react'

// Review tags are read at a glance mid-sentence, so each tone keeps its text at
// WCAG AA contrast against its own fill. The brand amber and green used before
// fell below 3:1 at nine pixels, which is most of why the key was hard to read.
const TAG_TONES = {
  cited: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  verify: 'border-amber-300 bg-amber-50 text-amber-900',
  model: 'border-blue-200 bg-blue-50 text-blue-800',
  reasoning: 'border-indigo-200 bg-indigo-50 text-indigo-800',
  uncertain: 'border-rose-300 bg-rose-50 text-rose-800',
}

const TAG_CHIP_BASE = 'mx-0.5 inline-flex items-center rounded border px-1.5 py-px align-middle font-mono text-[10px] font-bold uppercase leading-4 tracking-wider sm:text-[11px]'

export const REVIEW_TAGS = [
  {
    label: 'cited',
    text: 'Source-backed',
    detail: 'Supported by a retrieved source. Follow the link to check it.',
    classes: TAG_TONES.cited,
    swatch: 'bg-emerald-600',
  },
  {
    label: 'verify',
    text: 'Confirm before relying',
    detail: 'Plausible but not fully supported. Check the source or the pinpoint.',
    classes: TAG_TONES.verify,
    swatch: 'bg-amber-500',
  },
  {
    label: 'model',
    text: 'General reasoning',
    detail: 'The assistant’s own knowledge, not a retrieved source.',
    classes: TAG_TONES.model,
    swatch: 'bg-blue-600',
  },
]

const SECONDARY_REVIEW_TAGS = [
  {
    label: 'uncertain',
    text: 'Flagged doubt',
    detail: 'The assistant is unsure. Treat it as an open question.',
    classes: TAG_TONES.uncertain,
  },
  {
    label: 'firm context',
    text: 'From your material',
    detail: 'Drawn from matter or firm documents rather than public authority.',
    classes: TAG_TONES.cited,
  },
]

// Citation tag definitions: pattern → { label, classes, meaning }
const CITATION_PATTERNS = [
  {
    regex: /\[cited\]/gi,
    label: 'cited',
    classes: TAG_TONES.cited,
    meaning: 'Source-backed',
  },
  {
    regex: /\[settled\]/gi,
    label: 'cited',
    classes: TAG_TONES.cited,
    meaning: 'Source-backed',
  },
  {
    regex: /\[verify-pinpoint\]/gi,
    label: 'verify-pinpoint',
    classes: TAG_TONES.reasoning,
    meaning: 'Check the pinpoint citation',
  },
  {
    regex: /\[verify\]/gi,
    label: 'verify',
    classes: TAG_TONES.verify,
    meaning: 'Confirm before relying',
  },
  {
    regex: /\[model knowledge\]/gi,
    label: 'model knowledge',
    classes: TAG_TONES.model,
    meaning: 'General reasoning, not a retrieved source',
  },
  {
    regex: /\[model reasoning\]/gi,
    label: 'model reasoning',
    classes: TAG_TONES.reasoning,
    meaning: 'General reasoning, not a retrieved source',
  },
  {
    regex: /\[well[-\s]known fact\]/gi,
    label: 'well known fact',
    classes: TAG_TONES.model,
    meaning: 'Common knowledge, not source-backed',
  },
  {
    regex: /\[cited by context\]/gi,
    label: 'cited by context',
    classes: TAG_TONES.cited,
    meaning: 'Supported by matter or firm material',
  },
  {
    regex: /\[cited by context:\s*([^\]]*)\]/gi,
    label: null,
    classes: TAG_TONES.cited,
    meaning: 'Supported by matter or firm material',
    dynamic: true,
    prefix: 'cited by context: ',
  },
  {
    regex: /\[firm context\]/gi,
    label: 'firm context',
    classes: TAG_TONES.cited,
    meaning: 'Drawn from your firm’s material',
  },
  {
    regex: /\[UNCERTAIN:\s*([^\]]*)\]/gi,
    label: null, // dynamic
    classes: TAG_TONES.uncertain,
    meaning: 'The assistant is unsure — confirm independently',
    dynamic: true,
    prefix: 'UNCERTAIN: ',
  },
  {
    regex: /\[VERIFY:\s*([^\]]*)\]/gi,
    label: null,
    classes: TAG_TONES.verify,
    meaning: 'Confirm before relying',
    dynamic: true,
    prefix: 'VERIFY: ',
  },
]

function TagChip({ label, classes }) {
  return <span className={`${TAG_CHIP_BASE} ${classes}`}>{label}</span>
}

/**
 * What the review tags mean, one tap away from any chat.
 *
 * This replaced a legend pinned over the top of the transcript: it was
 * translucent, so answers scrolled visibly through it, and on a phone it wrapped
 * to three lines of permanently covered screen. The button itself doubles as a
 * compact legend on wider screens. On a phone the popover spans the nearest
 * positioned ancestor (the chat header) instead of hanging off the button,
 * which would push it past the left edge of a narrow screen.
 */
export function ReviewTagKey() {
  const [open, setOpen] = useState(false)
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

  return (
    <div ref={containerRef} className="sm:relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-label="Review tag key"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="What the review tags mean"
        className={`inline-flex min-h-9 items-center gap-2 rounded-lg border px-2 text-xs font-semibold sm:min-h-10 sm:rounded-xl sm:px-2.5 ${
          open
            ? 'border-brand-ink bg-brand-ink text-white'
            : 'border-brand-line bg-brand-surface text-brand-ink hover:bg-brand-bg-soft'
        }`}
      >
        <Tags size={16} aria-hidden="true" className="xl:hidden" />
        <span className="hidden items-center gap-2 xl:inline-flex" aria-hidden="true">
          {REVIEW_TAGS.map(({ label, swatch }) => (
            <span key={label} className="inline-flex items-center gap-1">
              <span className={`h-2 w-2 rounded-full ${swatch}`} />
              <span className="font-mono text-[10px] uppercase tracking-wider">{label}</span>
            </span>
          ))}
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Review tags"
          className="absolute inset-x-2 top-[calc(100%+0.25rem)] z-30 rounded-2xl border border-brand-line bg-brand-surface p-4 text-left shadow-xl sm:inset-x-auto sm:right-0 sm:top-[calc(100%+0.5rem)] sm:w-[22rem]"
        >
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-brand-muted">Review tags</p>
          <dl className="mt-3 space-y-3">
            {[...REVIEW_TAGS, ...SECONDARY_REVIEW_TAGS].map(({ label, text, detail, classes }) => (
              <div key={label} className="grid grid-cols-[6.5rem,1fr] items-start gap-3">
                <dt className="pt-0.5">
                  <TagChip label={label} classes={classes} />
                </dt>
                <dd className="text-xs leading-snug text-brand-ink-2">
                  <span className="block font-semibold text-brand-ink">{text}</span>
                  {detail}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 border-t border-brand-line pt-3 text-[11px] leading-relaxed text-brand-muted">
            Verify cited authority, dates, and legal conclusions before relying on assistant work.
          </p>
        </div>
      )}
    </div>
  )
}

export function transformCitations(text) {
  if (!text) return []

  const parts = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    let earliest = null
    let earliestIndex = Infinity
    let earliestPattern = null
    let earliestMatch = null

    for (const pattern of CITATION_PATTERNS) {
      const r = new RegExp(pattern.regex.source, pattern.regex.flags)
      const m = r.exec(remaining)
      if (m && m.index < earliestIndex) {
        earliest = m[0]
        earliestIndex = m.index
        earliestPattern = pattern
        earliestMatch = m
      }
    }

    if (earliest === null) {
      parts.push(<span key={key++}>{remaining}</span>)
      break
    }

    if (earliestIndex > 0) {
      parts.push(<span key={key++}>{remaining.slice(0, earliestIndex)}</span>)
    }

    const label = earliestPattern.dynamic
      ? earliestPattern.prefix + (earliestMatch[1] || '')
      : earliestPattern.label

    parts.push(
      <span
        key={key++}
        className={`${TAG_CHIP_BASE} ${earliestPattern.classes}`}
        title={earliestPattern.meaning}
      >
        {label}
      </span>
    )

    remaining = remaining.slice(earliestIndex + earliest.length)
  }

  return parts
}

function transformCitationChildren(children) {
  return React.Children.map(children, (child) => {
    if (typeof child === 'string') return transformCitations(child)
    if (!React.isValidElement(child) || child.props.children == null) return child
    return React.cloneElement(child, {
      children: transformCitationChildren(child.props.children),
    })
  })
}

function CitationParagraph({ children }) {
  return (
    <p className="mb-4 leading-relaxed font-sans">
      {transformCitationChildren(children)}
    </p>
  )
}

export const markdownComponents = {
  p: ({ children }) => <CitationParagraph>{children}</CitationParagraph>,
  h1: ({ children }) => (
    <h1 className="font-serif text-2xl font-semibold text-brand-ink mt-6 mb-4 leading-snug">{transformCitationChildren(children)}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="font-sans text-sm font-bold uppercase tracking-widest text-brand-muted mt-8 mb-4 border-b border-brand-line pb-2">{transformCitationChildren(children)}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="font-sans text-sm font-bold uppercase tracking-widest text-brand-muted mt-8 mb-4 border-b border-brand-line pb-2">{transformCitationChildren(children)}</h3>
  ),
  ul: ({ children }) => <ul className="list-disc pl-5 mb-4 space-y-1.5 text-brand-ink font-sans marker:text-brand-line-2">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-4 space-y-1.5 text-brand-ink font-sans marker:font-mono marker:text-brand-muted">{children}</ol>,
  li: ({ children }) => <li className="text-[15px] leading-relaxed">{transformCitationChildren(children)}</li>,
  strong: ({ children }) => <strong className="font-semibold text-brand-ink">{transformCitationChildren(children)}</strong>,
  em: ({ children }) => <em className="italic">{transformCitationChildren(children)}</em>,
  a: ({ children, href }) => {
    const isInternalSource = String(href || '').startsWith('#source-')
    const childText = React.Children.toArray(children).join('').trim().toLowerCase()
    const linkedReviewTag = ['cited', 'verify'].includes(childText) ? childText : null
    if (linkedReviewTag) {
      const classes = linkedReviewTag === 'cited' ? TAG_TONES.cited : TAG_TONES.verify
      return (
        <a
          href={href}
          className={`${TAG_CHIP_BASE} no-underline hover:underline ${classes}`}
          aria-label={`${linkedReviewTag} — jump to supporting source`}
          title={linkedReviewTag === 'cited' ? 'Source-backed — jump to the source' : 'Confirm before relying — jump to the source'}
        >
          {linkedReviewTag}
        </a>
      )
    }
    return (
      <a
        href={href}
        target={isInternalSource ? undefined : '_blank'}
        rel={isInternalSource ? undefined : 'noreferrer'}
        className="font-semibold text-brand-accent-2 underline decoration-brand-line-2 underline-offset-2 hover:text-brand-ink"
      >
        {children}
      </a>
    )
  },
  blockquote: ({ children }) => (
    <blockquote className="border-l-[3px] border-brand-line-2 pl-4 italic font-serif text-brand-ink-2 my-4 py-1 bg-brand-surface-2">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-4 border border-brand-line">
      <table className="min-w-full text-sm border-collapse bg-brand-bg">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-brand-surface-2 border-b border-brand-line">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-brand-line">{children}</tbody>,
  tr: ({ children }) => <tr className="hover:bg-brand-surface transition-colors">{children}</tr>,
  th: ({ children }) => (
    <th className="px-4 py-3 text-left text-[11px] font-bold text-brand-muted uppercase tracking-widest font-mono">{transformCitationChildren(children)}</th>
  ),
  td: ({ children }) => <td className="px-4 py-3 text-[14px] text-brand-ink font-sans">{transformCitationChildren(children)}</td>,
  code: ({ children, inline }) =>
    inline ? (
      <code className="bg-brand-line/30 text-brand-accent-2 px-1.5 py-0.5 text-[13px] font-mono border border-brand-line">
        {children}
      </code>
    ) : (
      <pre className="bg-brand-surface-2 p-4 overflow-x-auto text-[13px] font-mono my-4 text-brand-ink border border-brand-line">
        <code>{children}</code>
      </pre>
    ),
  hr: () => <hr className="border-brand-line my-6" />,
}
