import { createContext, useContext, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import { guideHref } from '../guideTopics'

// The app shell provides a setter so a page can point the header's Guide
// button at the section for the panel currently in view (for example, the
// active tab of a matter). Outside the shell the setter is absent and the
// hook does nothing, so pages still render in isolation and in tests.
export const PageGuideTopicContext = createContext(null)

export function usePageGuideTopic(audience, chapter, anchor = null, label = null) {
  const setPageTopic = useContext(PageGuideTopicContext)
  useEffect(() => {
    if (!setPageTopic) return undefined
    setPageTopic(chapter ? { audience, chapter, anchor, label, href: guideHref(audience, chapter, anchor) } : null)
    return () => setPageTopic(null)
  }, [setPageTopic, audience, chapter, anchor, label])
}

const VARIANTS = {
  inline: 'inline-flex items-center gap-1.5 text-xs font-semibold text-brand-accent hover:text-brand-ink',
  pill: 'inline-flex items-center gap-1.5 rounded-full border border-brand-line bg-brand-surface px-3 py-1.5 text-xs font-semibold text-brand-ink-2 hover:border-brand-accent hover:text-brand-accent',
}

// A link from a feature panel to the guide section that explains it. Callers
// decide visibility for administrator chapters (see canOpenAdminGuide), since
// those open inside Administration.
export default function GuideLink({
  audience = 'user',
  chapter,
  anchor = null,
  children = 'Guide',
  variant = 'inline',
  className = '',
  ...props
}) {
  return (
    <Link
      to={guideHref(audience, chapter, anchor)}
      className={`${VARIANTS[variant] || VARIANTS.inline} ${className}`}
      {...props}
    >
      <BookOpen size={13} aria-hidden="true" className="shrink-0" />
      <span>{children}</span>
    </Link>
  )
}
