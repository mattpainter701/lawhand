import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import LawHandLogo from './LawHandLogo'
import { trackMarketingEvent } from '../marketingAnalytics'
import { FOOTER_NAVIGATION, PRIMARY_NAVIGATION, SITE_TAGLINE } from '../seo/config'

// Derived from the one list that also drives the SiteNavigationElement
// structured data and the no-JavaScript shells, so the internal links Google
// weighs for sitelinks stay identical everywhere they are rendered.
const NAV_ITEMS = [
  ...PRIMARY_NAVIGATION.map(({ path, shortLabel }) => ({ label: shortLabel, to: path })),
  // Rendered as a router link so a visitor arriving from another marketing
  // page still lands on the home section; HomePage honours the hash on mount.
  { label: 'Security', to: '/#security', section: 'security' },
]

/**
 * First step of the demo funnel. The request page records `demo_form_started`
 * and `demo_form_submitted`; this records the click that brought the visitor
 * there, with the same `source` placement, so every CTA that links to the form
 * is measured without having to remember to instrument it.
 */
export function trackDemoCtaClick(event) {
  const link = event.target instanceof Element ? event.target.closest('a[href]') : null
  if (!link) return
  const url = new URL(link.href, window.location.href)
  if (url.origin !== window.location.origin || url.pathname !== '/request-demo') return
  trackMarketingEvent('demo_cta_clicked', { placement: url.searchParams.get('source') || 'direct' })
}

export function MarketingHeader({ onSectionClick }) {

  return (
    <header className="sticky top-0 z-40 border-b border-brand-line bg-brand-bg/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link to="/" aria-label="LawHand home" className="rounded-lg">
          <LawHandLogo compact />
        </Link>
        <nav aria-label="Marketing" className="hidden items-center gap-5 text-[13.5px] font-medium text-brand-ink-2 lg:flex">
          {NAV_ITEMS.map((item) => (
            // On the home page itself an in-page anchor scrolls without a
            // route change; everywhere else the same item routes home first.
            onSectionClick && item.section ? (
              <a
                key={item.label}
                href={`#${item.section}`}
                onClick={onSectionClick(item.section)}
                className="inline-flex min-h-11 items-center transition-colors hover:text-brand-ink"
              >
                {item.label}
              </a>
            ) : (
              <Link key={item.label} to={item.to} className="inline-flex min-h-11 items-center transition-colors hover:text-brand-ink">
                {item.label}
              </Link>
            )
          ))}
        </nav>
        <div className="flex items-center gap-2 sm:gap-3">
          <Link to="/login" className="inline-flex min-h-11 items-center px-2 text-[14px] font-semibold text-brand-ink transition-colors hover:text-brand-accent-2">
            Sign in
          </Link>
          <Link to="/request-demo" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand-ink px-3.5 text-[13px] font-semibold text-white shadow-sm transition-all hover:-translate-y-px hover:bg-brand-ink-2 sm:px-4 sm:text-[14px]">
            Book demo <ArrowRight size={15} className="hidden sm:block" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </header>
  )
}

export function MarketingFooter() {
  return (
    <footer className="border-t border-brand-line">
      <div className="mx-auto grid max-w-6xl gap-8 px-6 py-10 sm:grid-cols-[1fr_auto] sm:items-end">
        <div>
          <LawHandLogo compact />
          <p className="mt-3 font-sans text-[13px] text-brand-muted">{SITE_TAGLINE}</p>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-5 gap-y-2 font-sans text-[12.5px] text-brand-muted sm:justify-end">
          {/* The same list every no-JavaScript shell renders as its footer. */}
          {FOOTER_NAVIGATION.map(({ path, label }) => (
            <Link key={path} to={path} className="inline-flex min-h-11 items-center hover:text-brand-ink">{label}</Link>
          ))}
          <span>© 2026 Perevaga Group LLC d/b/a LawHand.</span>
        </nav>
      </div>
    </footer>
  )
}

export default function MarketingPageLayout({ children }) {
  return (
    <div className="min-h-screen bg-brand-bg text-brand-ink" onClickCapture={trackDemoCtaClick}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-brand-ink focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        Skip to main content
      </a>
      <MarketingHeader />
      <main id="main-content" tabIndex="-1">{children}</main>
      <MarketingFooter />
    </div>
  )
}
