import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  FOOTER_NAVIGATION,
  HOME_DESCRIPTION,
  HOME_FAQ,
  HOME_TITLE,
  LEGAL_LAST_UPDATED,
  MCP_TOOL_CALL_PRICE_USD,
  PLATFORM_PRICE_USD,
  PRICING_FAQ,
  PRIMARY_NAVIGATION,
  PUBLIC_CONTENT_LASTMOD,
  PUBLIC_ROUTE_META,
  buildMarketingStructuredData,
  buildRobotsTxt,
  buildSitemapXml,
  buildStructuredData,
  getRouteMeta,
  isKnownRoute,
  normalizeOrganizationProfile,
  normalizeSiteOrigin,
} from './config'
import { CORE_CAPABILITIES, CORE_CAPABILITY_NAMES } from '../marketing/capabilities'
import { PUBLIC_SERVER_SHELL_PATHS, buildPublicRouteHtml } from './serverShell'

const INDEXABLE_PATHS = Object.values(PUBLIC_ROUTE_META)
  .filter((route) => route.indexable)
  .map((route) => route.canonicalPath)

/**
 * Whether a crawler may fetch `path` under `robots`, decided the way RFC 9309
 * and Google do it: the longest matching rule wins and an Allow wins a tie.
 * Written independently of buildRobotsTxt so it cannot share its mistakes.
 */
function robotsAllows(robots, path) {
  const [winner] = robots.split('\n')
    .map((line) => line.match(/^(Allow|Disallow): (\S+)$/))
    .filter((rule) => rule && path.startsWith(rule[2]))
    .sort((a, b) => b[2].length - a[2].length || (a[1] === 'Allow' ? -1 : 1))
  return !winner || winner[1] === 'Allow'
}

/** Every path App.jsx routes, with each `:param` filled in by a sample value. */
function appRoutePaths() {
  const app = readFileSync('src/App.jsx', 'utf8')
  const studioRoutes = app.match(/const TEMPLATE_STUDIO_ROUTES = \[([\s\S]*?)\]/)[1]
  return [
    ...Array.from(app.matchAll(/<Route\s+path="([^"]+)"/g), (match) => match[1]),
    ...Array.from(studioRoutes.matchAll(/'([^']+)'/g), (match) => match[1]),
  ]
    .filter((path) => path !== '*')
    .map((path) => path.replace(/:\w+\??/g, 'sample'))
}

function linkedPaths(html) {
  return new Set(Array.from(html.matchAll(/<a\s[^>]*href="([^"]+)"/g), (match) => match[1]))
}

describe('SEO configuration', () => {
  it('ships the LawHand value proposition in the server-delivered HTML', () => {
    const html = readFileSync('index.html', 'utf8')

    expect(html).toContain('Law practice management, simplified.')
    expect(html).toContain('Book a demo')
    expect(html).not.toContain('<div id="root"></div>')
  })

  it('states what LawHand is, not only what it is called, before JavaScript runs', () => {
    const html = readFileSync('index.html', 'utf8')

    // A crawler that reads only the served HTML must still learn the product
    // category and the functions the meta description promises.
    expect(html).toContain(`<title>${HOME_TITLE}</title>`)
    expect(html).toContain(`content="${HOME_DESCRIPTION}"`)
    expect(html).toContain('legal automation platform for law firms')
    for (const term of ['CRM', 'intake', 'invoicing', 'legal research', 'MCP']) {
      expect(html).toContain(term)
    }
  })

  it('shows every capability it publishes as structured data', () => {
    // Structured data may never advertise a capability the served page hides.
    // The home shell in index.html and the React home page both render this
    // list; if a capability is added to featureList without being written into
    // the shell, this fails.
    const html = readFileSync('index.html', 'utf8')

    for (const name of CORE_CAPABILITY_NAMES) {
      expect(html).toContain(name)
    }
    expect(CORE_CAPABILITY_NAMES).toHaveLength(CORE_CAPABILITIES.length)
  })

  it('keeps the home title and description inside what Google renders', () => {
    expect(HOME_TITLE.length).toBeLessThanOrEqual(60)
    expect(HOME_DESCRIPTION.length).toBeLessThanOrEqual(165)

    for (const route of Object.values(PUBLIC_ROUTE_META)) {
      expect(route.title.length).toBeLessThanOrEqual(70)
      expect(route.description.length).toBeLessThanOrEqual(230)
    }
  })

  it('indexes only the substantiated public marketing and legal-policy routes', () => {
    expect(getRouteMeta('/').indexable).toBe(true)
    expect(getRouteMeta('/privacy/').canonicalPath).toBe('/privacy')
    expect(getRouteMeta('/terms').indexable).toBe(true)
    expect(getRouteMeta('/product/chat').indexable).toBe(true)
    expect(getRouteMeta('/product/mcp/').canonicalPath).toBe('/product/mcp')
    expect(getRouteMeta('/pricing').indexable).toBe(true)
    expect(getRouteMeta('/product').indexable).toBe(true)

    expect(getRouteMeta('/login').indexable).toBe(false)
    expect(getRouteMeta('/demo').title).toBe('Guided demo | LawHand')
    expect(getRouteMeta('/demo/session').title).toBe('Guided demo | LawHand')
    expect(getRouteMeta('/matters/customer-id').indexable).toBe(false)
    expect(getRouteMeta('/templates/new').title).toBe('Template Studio | LawHand')
    expect(getRouteMeta('/templates/11111111-1111-4111-8111-111111111111/studio').indexable).toBe(false)
    expect(getRouteMeta('/portal/client/matter?token=secret').indexable).toBe(false)
    expect(getRouteMeta('/unknown').indexable).toBe(false)
  })

  it('describes an unrecognized path as missing rather than as a private page', () => {
    // A stale inbound link should not be told it landed on a sign-in wall.
    expect(getRouteMeta('/no-such-page').title).toMatch(/Page not found/)
    expect(getRouteMeta('/no-such-page').canonicalPath).toBeNull()
    expect(getRouteMeta('/matters/abc').title).toMatch(/Matters/)
  })

  it('keeps sign-in-walled routes out of the crawl budget', () => {
    const robots = buildRobotsTxt('https://clarity.example')

    // Prefix rules, so each one covers the route itself as well as everything
    // beneath it. A trailing slash here would leave /login crawlable.
    for (const route of ['/demo', '/login', '/signup', '/chat', '/matters', '/admin', '/platform', '/portal']) {
      expect(robots).toContain(`Disallow: ${route}\n`)
      expect(robots).not.toContain(`Disallow: ${route}/`)
    }
    // Public marketing routes must stay crawlable.
    expect(robots).not.toContain('Disallow: /pricing')
    expect(robots).not.toContain('Disallow: /product')
    // /request-demo is public and must not be caught by the /demo rule.
    expect(robots).not.toContain('Disallow: /request-demo')
  })

  it('never blocks a page the sitemap publishes, even beneath a workspace prefix', () => {
    const robots = buildRobotsTxt('https://clarity.example')

    for (const path of INDEXABLE_PATHS) {
      expect(robotsAllows(robots, path), `robots.txt blocks ${path}`).toBe(true)
      expect(robotsAllows(robots, `${path.replace(/\/$/, '')}/`), `robots.txt blocks ${path}/`).toBe(true)
    }
    // `Disallow: /trust` (trust accounting) is a prefix of /trust-center, so
    // the public page needs its own, longer Allow; the workspace stays blocked.
    expect(robots).toContain('Allow: /trust-center\n')
    expect(robotsAllows(robots, '/trust')).toBe(false)
    expect(robotsAllows(robots, '/trust/11111111-1111-4111-8111-111111111111')).toBe(false)
  })

  it('knows every route the app serves, so none is titled or crawled as a missing page', () => {
    const robots = buildRobotsTxt('https://clarity.example')
    const paths = appRoutePaths()
    expect(paths.length).toBeGreaterThan(40)

    for (const path of paths) {
      // An unknown path gets the 404 metadata, which names a real page
      // "Page not found" in the browser tab and in history.
      expect(isKnownRoute(path), `${path} is missing from the SEO route table`).toBe(true)
      // Every served route is either a public page or kept out of the crawl.
      expect(robotsAllows(robots, path), `robots.txt treats ${path} wrongly`).toBe(getRouteMeta(path).indexable)
    }
    expect(getRouteMeta('/firm-memory').title).toBe('Firm Memory | LawHand')
    expect(getRouteMeta('/clients/sample').title).toBe('Clients | LawHand')
  })

  it('accepts only host-safe public origins', () => {
    expect(normalizeSiteOrigin('https://clarity.example/')).toBe('https://clarity.example')
    expect(normalizeSiteOrigin('http://localhost:3000')).toBe('http://localhost:3000')
    expect(normalizeSiteOrigin('')).toBe('')

    expect(() => normalizeSiteOrigin('http://clarity.example')).toThrow(/https/)
    expect(() => normalizeSiteOrigin('https://clarity.example/app')).toThrow(/bare origin/)
    expect(() => normalizeSiteOrigin('not-a-url')).toThrow(/absolute/)
  })

  it('emits crawl controls and a sitemap only when the production origin is known', () => {
    const withoutOrigin = buildRobotsTxt()
    expect(withoutOrigin).toContain('Disallow: /api/')
    expect(withoutOrigin).not.toContain('Sitemap:')

    const origin = 'https://clarity.example'
    const robots = buildRobotsTxt(origin)
    const sitemap = buildSitemapXml(origin)
    expect(robots).toContain(`Sitemap: ${origin}/sitemap.xml`)
    expect(sitemap).toContain(`<loc>${origin}/</loc>`)
    expect(sitemap).toContain(`<loc>${origin}/privacy</loc>`)
    expect(sitemap).toContain(`<loc>${origin}/terms</loc>`)
    expect(sitemap).toContain(`<loc>${origin}/product/chat</loc>`)
    expect(sitemap).toContain(`<loc>${origin}/product/mcp</loc>`)
    expect(sitemap).toContain(`<loc>${origin}/pricing</loc>`)
    expect(sitemap).toContain(`<loc>${origin}/product</loc>`)
    expect(sitemap).toContain(`<loc>${origin}/request-demo</loc>`)
    expect(sitemap).toContain('<lastmod>')
    expect(sitemap).not.toContain('/login')
    expect(sitemap).not.toContain('/matters')
    // The demo request page used to canonicalize onto /demo, the sign-in-walled
    // guided demo, which the app itself serves as noindex.
    expect(sitemap).not.toContain(`<loc>${origin}/demo</loc>`)
    expect(sitemap).not.toContain('undefined')
  })

  it('dates each policy in the sitemap the way the policy dates itself', () => {
    const origin = 'https://clarity.example'
    const sitemap = buildSitemapXml(origin)

    // A lastmod older than the page's own "Last updated" line teaches search
    // engines to ignore the site's lastmod values altogether.
    for (const [path, { iso }] of Object.entries(LEGAL_LAST_UPDATED)) {
      expect(sitemap).toContain(`<loc>${origin}${path}</loc>\n    <lastmod>${iso}</lastmod>`)
    }
    expect(sitemap).toContain(`<loc>${origin}/pricing</loc>\n    <lastmod>${PUBLIC_CONTENT_LASTMOD}</lastmod>`)
  })

  it('links every indexable page from the HTML a crawler sees without JavaScript', () => {
    const base = readFileSync('index.html', 'utf8')

    // The home shell is where such a crawler enters, so it reaches every public
    // page in one hop rather than leaving some to the sitemap alone.
    const home = linkedPaths(base)
    for (const path of INDEXABLE_PATHS.filter((path) => path !== '/')) {
      expect(home.has(path), `index.html does not link ${path}`).toBe(true)
    }

    // Every route shell leads home and carries the same footer as the app.
    for (const shellPath of PUBLIC_SERVER_SHELL_PATHS) {
      const links = linkedPaths(buildPublicRouteHtml(base, shellPath, 'https://clarity.example'))
      expect(links.has('/')).toBe(true)
      for (const { path } of FOOTER_NAVIGATION.filter(({ path }) => path !== shellPath)) {
        expect(links.has(path), `the ${shellPath} shell does not link ${path}`).toBe(true)
      }
    }

    // And the app's own header and footer, between them, link every page.
    const chrome = new Set([...PRIMARY_NAVIGATION, ...FOOTER_NAVIGATION].map(({ path }) => path))
    for (const path of INDEXABLE_PATHS.filter((path) => path !== '/')) {
      expect(chrome.has(path), `no header or footer link reaches ${path}`).toBe(true)
    }
  })

  it('gives search engines a short, consistent set of sitelink candidates', () => {
    const origin = 'https://clarity.example'
    const graph = buildStructuredData(origin, '/')['@graph']
    const navigation = graph.find((node) => node['@id'] === `${origin}/#navigation`)

    expect(navigation.itemListElement.map((item) => item.url)).toEqual(
      PRIMARY_NAVIGATION.map(({ path }) => `${origin}${PUBLIC_ROUTE_META[path].canonicalPath}`),
    )
    // Every advertised destination must be a route that is actually indexable.
    for (const { path } of PRIMARY_NAVIGATION) {
      expect(PUBLIC_ROUTE_META[path].indexable).toBe(true)
    }
    // Sitelinks are earned by internal links, so the same list is not published
    // on interior pages.
    expect(buildStructuredData(origin, '/pricing')['@graph']
      .some((node) => node['@type'] === 'ItemList')).toBe(false)
  })

  it('publishes the capability list search engines should read', () => {
    const software = buildStructuredData('https://clarity.example', '/')['@graph']
      .find((node) => node['@type'] === 'SoftwareApplication')

    expect(software.featureList).toEqual(CORE_CAPABILITY_NAMES)
    expect(software.featureList).toContain('Client and matter CRM')
    expect(software.featureList).toContain('Time, invoicing, and trust accounting')
    expect(software.featureList).toContain('Document preparation and automation')
    expect(software.featureList).toContain('MCP for approved AI assistants')
  })

  it('reconciles the site with external profiles only when they are usable', () => {
    const origin = 'https://clarity.example'
    const organization = (profile) => buildStructuredData(origin, '/', profile)['@graph']
      .find((node) => node['@type'] === 'Organization')

    // Nothing configured: no empty or invented identity claims.
    expect(organization({})).not.toHaveProperty('sameAs')
    expect(organization({})).not.toHaveProperty('contactPoint')

    const configured = organization({
      contactUrl: 'mailto:sales@clarity.example?subject=Demo',
      telephone: '+15550100',
      sameAs: 'https://maps.google.com/?cid=1, not-a-url ,https://www.linkedin.com/company/lawhand',
    })
    expect(configured.sameAs).toEqual([
      'https://maps.google.com/?cid=1',
      'https://www.linkedin.com/company/lawhand',
    ])
    expect(configured.contactPoint).toMatchObject({
      email: 'sales@clarity.example',
      telephone: '+15550100',
    })

    expect(normalizeOrganizationProfile({ sameAs: 'javascript:alert(1)' }).sameAs).toEqual([])
  })

  it('publishes the home questions verbatim as FAQPage structured data', () => {
    const graph = buildStructuredData('https://clarity.example', '/')['@graph']
    const faq = graph.find((node) => node['@type'] === 'FAQPage')

    expect(faq['@id']).toBe('https://clarity.example/#faq')
    expect(faq.mainEntity).toHaveLength(HOME_FAQ.length)
    expect(faq.mainEntity[0].name).toBe('What is LawHand?')
    expect(faq.mainEntity[0].acceptedAnswer.text).toBe(HOME_FAQ[0][1])
    // The answer a search or answer engine is most likely to quote must name
    // the product category and its concrete functions.
    expect(faq.mainEntity[0].acceptedAnswer.text).toContain('legal automation platform')
    expect(JSON.stringify(faq)).toContain('CRM')
    // MCP is release-gated; the published answer must say so rather than
    // describing it as generally available.
    expect(JSON.stringify(faq)).toContain('successful tool call')
  })

  it('limits structured data to claims supported by the product', () => {
    const graph = buildMarketingStructuredData('https://clarity.example')['@graph']
    expect(graph.map((node) => node['@type'])).toEqual([
      'Organization',
      'WebSite',
      'SoftwareApplication',
      'ItemList',
      'FAQPage',
    ])
    const software = graph.find((node) => node['@type'] === 'SoftwareApplication')
    expect(software).toMatchObject({
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Modern web browser',
    })
    // The offer may state only the price the pricing page itself publishes,
    // and must not imply a self-serve purchase the product does not offer.
    expect(software.offers.price).toBe(PLATFORM_PRICE_USD)
    expect(software.offers.priceCurrency).toBe('USD')
    expect(software.offers).not.toHaveProperty('availability')

    // Ratings and reviews would be fabricated social proof; never emit them.
    for (const node of graph) {
      expect(node).not.toHaveProperty('aggregateRating')
      expect(node).not.toHaveProperty('review')
    }
  })

  it('gives every indexable route its own structured data', () => {
    const origin = 'https://clarity.example'

    for (const route of ['/', '/product', '/product/chat', '/product/mcp', '/pricing', '/privacy', '/terms']) {
      const types = buildStructuredData(origin, route)['@graph'].map((node) => node['@type'])
      expect(types).toContain('Organization')
      expect(types).toContain('WebSite')
    }

    expect(buildStructuredData(origin, '/pricing')['@graph'].map((node) => node['@type']))
      .toContain('BreadcrumbList')
    expect(buildStructuredData(origin, '/login')).toBeNull()
    expect(buildStructuredData(origin, '/no-such-page')).toBeNull()
    expect(buildStructuredData('', '/')).toBeNull()
  })

  it('publishes the pricing FAQ verbatim as FAQPage structured data', () => {
    const graph = buildStructuredData('https://clarity.example', '/pricing')['@graph']
    const faq = graph.find((node) => node['@type'] === 'FAQPage')

    expect(faq.mainEntity).toHaveLength(PRICING_FAQ.length)
    expect(faq.mainEntity[0].name).toBe(PRICING_FAQ[0][0])
    expect(faq.mainEntity[0].acceptedAnswer.text).toBe(PRICING_FAQ[0][1])
    // The published answers must carry the same prices as the rest of the site.
    expect(JSON.stringify(faq)).toContain(`$${PLATFORM_PRICE_USD}`)
    expect(JSON.stringify(faq)).toContain(`$${MCP_TOOL_CALL_PRICE_USD}`)
  })

  it.each([
    // Each policy carries its own last-updated date and its own section count;
    // the privacy shell gained the Google Limited Use disclosure.
    ['/privacy', 'Privacy Policy | LawHand', 'Privacy Policy', 'Terms of Use', '2026-09-13', 'September 13, 2026', 9],
    ['/terms', 'Terms of Use | LawHand', 'Terms of Use', 'Privacy Policy', '2026-07-27', 'July 27, 2026', 8],
  ])('builds substantive route-correct no-JavaScript HTML for %s', (route, title, heading, otherPolicy, updatedIso, updatedLabel, sectionCount) => {
    const base = readFileSync('index.html', 'utf8')
    const html = buildPublicRouteHtml(base, route, 'https://clarity.example')

    expect(html).toContain(`<title>${title}</title>`)
    expect(html).toContain(`rel="canonical" href="https://clarity.example${route}"`)
    expect(html).toContain(`property="og:url" content="https://clarity.example${route}"`)
    expect(html).toContain(`<h1>${heading}</h1>`)
    expect(html).toContain('<article class="server-legal__article">')
    expect(html).toContain('<nav class="server-legal__contents" aria-label="On this page">')
    expect(html).toContain('<ol>')
    expect(html).toContain(`<time datetime="${updatedIso}">${updatedLabel}</time>`)
    expect(html.match(/<section id=/g)).toHaveLength(sectionCount)
    expect(html).toContain(`>${otherPolicy}</a>`)
    expect(html).toContain('mailto:support@getlawhand.com')
    // The marketing hero must not survive into a policy page. The slogan may
    // still appear inside the Organization structured data, which describes the
    // publisher rather than this page, so assert on the rendered body.
    expect(html).not.toContain('<h1>Law practice management, simplified.</h1>')
    expect(html).not.toContain('<main class="server-marketing">')
    expect(html).toContain('<script type="module" src="/src/main.jsx"></script>')
  })

  it('serves the Google Limited Use disclosure in the no-JavaScript privacy shell', () => {
    const base = readFileSync('index.html', 'utf8')
    const html = buildPublicRouteHtml(base, '/privacy', 'https://clarity.example')

    expect(html).toContain('Google user data and Limited Use')
    expect(html).toContain('adhere to the Google API Services User Data Policy, including the Limited Use requirements')
    expect(html).toContain('https://developers.google.com/terms/api-services-user-data-policy')
    expect(html).toContain('<section id="google-user-data">')

    const terms = buildPublicRouteHtml(base, '/terms', 'https://clarity.example')
    expect(terms).not.toContain('Limited Use requirements')
  })

  it('keeps each legal shell specific to its policy', () => {
    const base = readFileSync('index.html', 'utf8')
    const privacy = buildPublicRouteHtml(base, '/privacy')
    const terms = buildPublicRouteHtml(base, '/terms')

    expect(privacy).toContain('How information is used')
    expect(privacy).toContain('Choices and privacy requests')
    expect(privacy).not.toContain('Acceptable use')
    expect(terms).toContain('Acceptable use')
    expect(terms).toContain('Disclaimers and liability')
    expect(terms).not.toContain('Choices and privacy requests')
  })

  it.each([
    ['/product/chat', 'Ask with the whole matter in hand.', 'matter-aware AI workspace'],
    ['/product/mcp', 'Bring approved public legal authority into the tools you already use.', '$0.45 per successful tool call'],
    ['/pricing', 'One clear platform price. Controlled expansion.', '$89 per user per month'],
    ['/product', 'See the entire matter move.', 'The matter flow'],
    ['/request-demo', 'Book a LawHand demo.', 'client and matter CRM'],
  ])('builds a substantive public product shell for %s', (route, heading, claim) => {
    const base = readFileSync('index.html', 'utf8')
    const html = buildPublicRouteHtml(base, route, 'https://lawhand.example')

    expect(html).toContain(`rel="canonical" href="https://lawhand.example${route}"`)
    expect(html).toContain(`<h1>${heading}</h1>`)
    expect(html).toContain(claim)
    expect(html).toContain('aria-label="LawHand product pages"')
    expect(html).toContain('mailto:support@getlawhand.com')
  })
})
