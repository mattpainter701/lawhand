import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const frontendRoot = join(repositoryRoot, 'frontend')
const docsRoot = join(frontendRoot, 'platform_docs')
const publicRoot = join(frontendRoot, 'public')
const coveragePath = join(docsRoot, 'coverage.json')
const appSource = readFileSync(join(frontendRoot, 'src', 'App.jsx'), 'utf8')
const adminTabsSource = readFileSync(join(frontendRoot, 'src', 'adminTabs.js'), 'utf8')
const integrationsHubSource = readFileSync(join(frontendRoot, 'src', 'components', 'IntegrationsHub.jsx'), 'utf8')
const guideViewerSource = readFileSync(join(frontendRoot, 'src', 'components', 'GuideViewer.jsx'), 'utf8')
const requiredFields = ['slug', 'title', 'description', 'order', 'read_time', 'icon']
const allowedRouteRoots = new Set([
  'admin', 'calendar', 'chat', 'clients', 'communications', 'conflicts', 'contacts', 'guide', 'intake',
  'firm-memory', 'invoices', 'matters', 'onboarding', 'plugins', 'profile', 'reports', 'tasks',
  'teams', 'templates', 'time-tracking', 'trust',
])
// Guide screenshots are served as static files; keep each one small enough to
// load quickly inside the product.
const maxImageBytes = 600 * 1024

// Tabs are declared grouped (`export const ADMIN_TAB_GROUPS = [{ id, label,
// tabs: [...] }]`) in frontend/src/adminTabs.js. Only the entries inside
// `tabs: [...]` are tabs; group ids are navigation labels.
const adminTabGroupsBlock = adminTabsSource.match(/const ADMIN_TAB_GROUPS = \[([\s\S]*?)\n\]/)?.[1] || ''
const adminTabsBlock = Array.from(adminTabGroupsBlock.matchAll(/tabs:\s*\[([\s\S]*?)\]/g), ([, tabs]) => tabs).join('\n')
const adminTabLabels = new Map(Array.from(adminTabsBlock.matchAll(/id:\s*'([^']+)',\s*label:\s*'([^']+)'/g), ([, tab, label]) => [tab, label]))
const adminTabs = new Set(adminTabLabels.keys())
const integrationSectionsBlock = integrationsHubSource.match(/export const INTEGRATION_SECTIONS = \[([\s\S]*?)\n\]/)?.[1] || ''
const integrationSectionLabels = new Map(
  Array.from(integrationSectionsBlock.matchAll(/id:\s*'([^']+)',\s*label:\s*'([^']+)'/g), ([, section, label]) => [section, label]),
)
const integrationSections = new Set(integrationSectionLabels.keys())
const guideIconsBlock = guideViewerSource.match(/const ICONS = \{([\s\S]*?)\n\}/)?.[1] || ''
const guideIcons = new Set(Array.from(guideIconsBlock.matchAll(/^\s*([a-z]+):/gm), ([, icon]) => icon))

// Every route the application registers, including the Template Studio
// routes that App.jsx declares in an array.
const templateStudioBlock = appSource.match(/const TEMPLATE_STUDIO_ROUTES = \[([\s\S]*?)\]/)?.[1] || ''
const registeredRoutes = [
  ...Array.from(appSource.matchAll(/path="([^"]+)"/g), ([, route]) => route),
  ...Array.from(templateStudioBlock.matchAll(/'([^']+)'/g), ([, route]) => route),
].filter((route) => route !== '*')

const errors = []
const seenSlugs = new Map()
const chapters = new Map()

function fail(file, message) {
  errors.push(`${file}: ${message}`)
}

// Must match slugifyHeading in frontend/src/platformDocs.js, which produces the
// ids the guide renders on each heading.
function slugifyHeading(value) {
  return String(value || '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`]/g, '')
    .trim()
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

function segmentsOf(path) {
  return path.split('/').filter(Boolean)
}

function isParameterized(route) {
  return segmentsOf(route).some((segment) => segment.startsWith(':'))
}

function normalizeRoute(route) {
  return route.replace(/\/:([^/]+)/g, '').replace(/\/$/, '') || '/'
}

// The static part of a parameterized route, e.g. /matters for
// /matters/:matterId/research: the address a reader can actually open.
function entryRouteFor(route) {
  const segments = []
  for (const segment of segmentsOf(route)) {
    if (segment.startsWith(':')) break
    segments.push(segment)
  }
  return `/${segments.join('/')}`
}

function routeMatches(pathname, route) {
  const path = segmentsOf(pathname)
  const pattern = segmentsOf(route)
  const required = pattern.filter((segment) => !segment.endsWith('?')).length
  if (path.length < required || path.length > pattern.length) return false
  return pattern.every((segment, index) => {
    if (index >= path.length) return segment.endsWith('?')
    return segment.startsWith(':') || segment === path[index]
  })
}

const staticRoutes = new Set(registeredRoutes.filter((route) => !isParameterized(route)))
// Addresses that look like a screen but are only the parameter-free spelling
// of a record route, e.g. /matters/research for /matters/:matterId/research.
// They resolve to another screen (or no screen) and must never be linked.
const pseudoRoutes = new Set(
  registeredRoutes.filter(isParameterized).map(normalizeRoute).filter((route) => !staticRoutes.has(route)),
)

function parseChapter(file, audience) {
  const source = readFileSync(file, 'utf8')
  const relativeFile = file.slice(repositoryRoot.length + 1).replaceAll('\\', '/')
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/)
  if (!match) {
    fail(relativeFile, 'missing front matter')
    return
  }

  const metadata = {}
  for (const line of match[1].split(/\r?\n/)) {
    const separator = line.indexOf(':')
    if (separator !== -1) metadata[line.slice(0, separator).trim()] = line.slice(separator + 1).trim()
  }

  for (const field of requiredFields) {
    if (!metadata[field]) fail(relativeFile, `missing required field "${field}"`)
  }

  if (metadata.slug && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(metadata.slug)) {
    fail(relativeFile, 'slug must be lowercase kebab-case')
  }
  if (metadata.slug && seenSlugs.has(`${audience}:${metadata.slug}`)) {
    fail(relativeFile, `duplicate slug also used by ${seenSlugs.get(`${audience}:${metadata.slug}`)}`)
  } else if (metadata.slug) {
    seenSlugs.set(`${audience}:${metadata.slug}`, relativeFile)
  }
  if (metadata.icon && !guideIcons.has(metadata.icon)) {
    fail(relativeFile, `icon "${metadata.icon}" is not one of the guide icons in GuideViewer.jsx (${[...guideIcons].join(', ')})`)
  }

  const numericOrder = Number(metadata.order)
  if (!Number.isInteger(numericOrder) || numericOrder <= 0) fail(relativeFile, 'order must be a positive integer')
  const filenameOrder = Number(file.split(/[\\/]/).at(-1).match(/^(\d+)-/)?.[1])
  if (Number.isFinite(filenameOrder) && numericOrder !== filenameOrder * 10) {
    fail(relativeFile, `order ${numericOrder} must match filename sequence ${filenameOrder}0`)
  }

  const content = source.slice(match[0].length).trim()
  if (!content.startsWith(`# ${metadata.title}`)) fail(relativeFile, 'first heading must match the title')
  if (!/^##\s+.+/m.test(content)) fail(relativeFile, 'chapter needs at least one level-two heading')

  const anchors = new Set()
  for (const [, heading] of content.matchAll(/^#{2,3}\s+(.+)$/gm)) {
    if (heading.includes('](')) fail(relativeFile, `heading "${heading}" must not contain a link; its anchor would change with the link`)
    const anchor = slugifyHeading(heading)
    if (anchors.has(anchor)) fail(relativeFile, `duplicate section anchor #${anchor}; make the headings distinct`)
    anchors.add(anchor)
  }

  if (metadata.slug) chapters.set(`${audience}:${metadata.slug}`, { audience, content, anchors, relativeFile })
}

function checkAnchor(relativeFile, href, target, anchor) {
  if (anchor && !target.anchors.has(anchor)) fail(relativeFile, `link ${href} points to a section that does not exist`)
}

function checkLinks({ audience, content, anchors, relativeFile }) {
  const links = Array.from(content.matchAll(/(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g), ([, href]) => href)
  for (const href of links) {
    if (href.startsWith('#')) {
      if (!anchors.has(decodeURIComponent(href.slice(1)))) fail(relativeFile, `link ${href} points to a section that does not exist in this chapter`)
      continue
    }
    if (!href.startsWith('/') || href.startsWith('//')) continue

    const url = new URL(href, 'https://guide.invalid')
    const anchor = decodeURIComponent(url.hash.replace(/^#/, ''))
    const routeRoot = segmentsOf(url.pathname)[0]
    if (!allowedRouteRoots.has(routeRoot)) {
      fail(relativeFile, `unsupported in-app route ${href}`)
      continue
    }
    if (audience === 'user' && ['admin', 'onboarding'].includes(routeRoot)) {
      fail(relativeFile, `user guide must not link to administrative route ${href}`)
      continue
    }
    if (pseudoRoutes.has(url.pathname)) {
      fail(relativeFile, `link ${href} is not an address a reader can open; link to ${entryRouteFor(registeredRoutes.find((route) => normalizeRoute(route) === url.pathname))} and describe how to reach the screen`)
      continue
    }
    if (!registeredRoutes.some((route) => routeMatches(url.pathname, route))) {
      fail(relativeFile, `link ${href} does not match a route registered in App.jsx`)
      continue
    }

    if (routeRoot === 'guide') {
      const slug = segmentsOf(url.pathname)[1]
      if (!slug) continue
      const target = chapters.get(`user:${slug}`)
      if (!target) fail(relativeFile, `link ${href} names an unknown user guide chapter; administrator chapters open at /admin?tab=guide&chapter=<slug>`)
      else checkAnchor(relativeFile, href, target, anchor)
      continue
    }

    if (routeRoot === 'admin') {
      const tab = url.searchParams.get('tab') || 'users'
      if (!adminTabs.has(tab)) fail(relativeFile, `unknown admin tab in ${href}`)
      const integration = url.searchParams.get('integration')
      if (integration && (tab !== 'integrations' || !integrationSections.has(integration))) {
        fail(relativeFile, `unknown integration section in ${href}`)
      }
      const chapterSlug = url.searchParams.get('chapter')
      if (chapterSlug && tab !== 'guide') fail(relativeFile, `chapter= is only valid with tab=guide in ${href}`)
      if (tab === 'guide' && chapterSlug) {
        const target = chapters.get(`admin:${chapterSlug}`)
        if (!target) fail(relativeFile, `link ${href} names an unknown administrator guide chapter`)
        else checkAnchor(relativeFile, href, target, anchor)
      } else if (anchor) {
        fail(relativeFile, `link ${href} has a section anchor but does not open a guide chapter`)
      }
    }
  }

  const images = Array.from(content.matchAll(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g))
  for (const [, alt, href] of images) {
    if (!href.startsWith('/guide-assets/')) {
      fail(relativeFile, `image ${href} must be served from /guide-assets/`)
      continue
    }
    if (!alt.trim()) fail(relativeFile, `image ${href} needs meaningful alternative text`)
    const file = join(publicRoot, href)
    if (!existsSync(file)) fail(relativeFile, `image does not exist: ${href}`)
    else if (statSync(file).size > maxImageBytes) fail(relativeFile, `image ${href} is larger than ${maxImageBytes / 1024} KB`)
  }
}

for (const [directory, audience] of [['user-guide', 'user'], ['administrative-guide', 'admin']]) {
  const fullDirectory = join(docsRoot, directory)
  if (!existsSync(fullDirectory)) {
    fail(directory, 'required guide directory does not exist')
    continue
  }
  const files = readdirSync(fullDirectory).filter((name) => name.endsWith('.md')).sort()
  if (files.length === 0) fail(directory, 'guide must contain at least one Markdown chapter')
  files.forEach((file) => parseChapter(join(fullDirectory, file), audience))
}

chapters.forEach(checkLinks)

if (!existsSync(join(docsRoot, 'README.md'))) fail('frontend/platform_docs', 'README.md is required')

function checkEntry(audience, entry, what) {
  const chapter = chapters.get(`${audience}:${entry.chapter}`)
  if (!entry?.label) fail('frontend/platform_docs/coverage.json', `${what} needs a label`)
  if (!chapter) {
    fail('frontend/platform_docs/coverage.json', `${what} references unknown ${audience} chapter ${entry.chapter}`)
    return null
  }
  if (entry.anchor && !chapter.anchors.has(entry.anchor)) {
    fail('frontend/platform_docs/coverage.json', `${what} anchor #${entry.anchor} does not exist in ${entry.chapter}`)
  }
  return chapter
}

function validateCoverage() {
  if (!existsSync(coveragePath)) {
    fail('frontend/platform_docs', 'coverage.json is required')
    return
  }

  let coverage
  try {
    coverage = JSON.parse(readFileSync(coveragePath, 'utf8'))
  } catch (error) {
    fail('frontend/platform_docs/coverage.json', `invalid JSON: ${error.message}`)
    return
  }

  const userModules = Array.isArray(coverage.user_modules) ? coverage.user_modules : []
  const coveredUserRoutes = new Set()
  const coveredUserIds = new Set()
  for (const entry of userModules) {
    if (!entry?.id || !entry?.route || !entry?.chapter) {
      fail('frontend/platform_docs/coverage.json', 'every user module needs id, route, label, and chapter')
      continue
    }
    const route = normalizeRoute(entry.route)
    if (coveredUserIds.has(entry.id)) fail('frontend/platform_docs/coverage.json', `duplicate user module id ${entry.id}`)
    if (coveredUserRoutes.has(route)) fail('frontend/platform_docs/coverage.json', `duplicate user route ${entry.route}`)
    coveredUserIds.add(entry.id)
    coveredUserRoutes.add(route)
    if (isParameterized(entry.route) && !registeredRoutes.includes(entry.route)) {
      fail('frontend/platform_docs/coverage.json', `user module ${entry.id} route ${entry.route} must match a route pattern in App.jsx`)
    }
    const chapter = checkEntry('user', entry, `user module ${entry.id}`)
    // A record screen has no address of its own, so its chapter links to the
    // list it is opened from and explains the way in.
    const linkTarget = isParameterized(entry.route) ? entryRouteFor(entry.route) : entry.route
    if (chapter && !chapter.content.includes(`](${linkTarget})`)) {
      fail(chapter.relativeFile, `coverage chapter must link to ${linkTarget} for module ${entry.id}`)
    }
  }

  const authenticatedSection = appSource
    .split('{/* Authenticated pages wrapped in AppShell */}')[1]
    ?.split('{/* Admin routes */}')[0] || ''
  const excludedUserRoutes = new Set(['/billing', '/guide', '/teams/config'])
  const applicationUserRoutes = new Set(
    Array.from(authenticatedSection.matchAll(/path="([^"]+)"/g), ([, route]) => normalizeRoute(route))
      .filter((route) => !excludedUserRoutes.has(route)),
  )
  for (const route of applicationUserRoutes) {
    if (!coveredUserRoutes.has(route)) fail('frontend/platform_docs/coverage.json', `authenticated product route is undocumented: ${route}`)
  }
  for (const route of coveredUserRoutes) {
    if (!applicationUserRoutes.has(route)) fail('frontend/platform_docs/coverage.json', `user module route is not registered in App.jsx: ${route}`)
  }

  const adminEntries = Array.isArray(coverage.admin_tabs) ? coverage.admin_tabs : []
  const coveredAdminTabs = new Set()
  for (const entry of adminEntries) {
    if (!entry?.tab || !entry?.chapter) {
      fail('frontend/platform_docs/coverage.json', 'every admin tab needs tab, label, and chapter')
      continue
    }
    if (coveredAdminTabs.has(entry.tab)) fail('frontend/platform_docs/coverage.json', `duplicate admin tab ${entry.tab}`)
    coveredAdminTabs.add(entry.tab)
    if (adminTabLabels.has(entry.tab) && entry.label !== adminTabLabels.get(entry.tab)) {
      fail('frontend/platform_docs/coverage.json', `admin tab ${entry.tab} label must match "${adminTabLabels.get(entry.tab)}"`)
    }
    const chapter = checkEntry('admin', entry, `admin tab ${entry.tab}`)
    if (chapter && !chapter.content.includes(`](/admin?tab=${entry.tab})`)) {
      fail(chapter.relativeFile, `coverage chapter must link to /admin?tab=${entry.tab}`)
    }
  }
  for (const tab of adminTabs) {
    if (!coveredAdminTabs.has(tab)) fail('frontend/platform_docs/coverage.json', `admin tab is undocumented: ${tab}`)
  }
  for (const tab of coveredAdminTabs) {
    if (!adminTabs.has(tab)) fail('frontend/platform_docs/coverage.json', `admin tab is not registered in adminTabs.js: ${tab}`)
  }

  const integrationEntries = Array.isArray(coverage.admin_integration_sections)
    ? coverage.admin_integration_sections
    : []
  const coveredIntegrationSections = new Set()
  for (const entry of integrationEntries) {
    if (!entry?.section || !entry?.chapter) {
      fail('frontend/platform_docs/coverage.json', 'every admin integration section needs section, label, and chapter')
      continue
    }
    if (coveredIntegrationSections.has(entry.section)) {
      fail('frontend/platform_docs/coverage.json', `duplicate admin integration section ${entry.section}`)
    }
    coveredIntegrationSections.add(entry.section)
    if (integrationSectionLabels.has(entry.section) && entry.label !== integrationSectionLabels.get(entry.section)) {
      fail('frontend/platform_docs/coverage.json', `integration section ${entry.section} label must match "${integrationSectionLabels.get(entry.section)}"`)
    }
    const chapter = checkEntry('admin', entry, `integration section ${entry.section}`)
    const route = `/admin?tab=integrations&integration=${entry.section}`
    if (chapter && !chapter.content.includes(`](${route})`)) {
      fail(chapter.relativeFile, `coverage chapter must link to ${route}`)
    }
  }
  for (const section of integrationSections) {
    if (!coveredIntegrationSections.has(section)) {
      fail('frontend/platform_docs/coverage.json', `admin integration section is undocumented: ${section}`)
    }
  }
  for (const section of coveredIntegrationSections) {
    if (!integrationSections.has(section)) {
      fail('frontend/platform_docs/coverage.json', `admin integration section is not registered in IntegrationsHub.jsx: ${section}`)
    }
  }

  // Administration pages outside the portal tabs (the setup wizard).
  const adminSection = appSource.split('{/* Admin routes */}')[1]?.split('{/* Legacy redirects */}')[0] || ''
  const applicationAdminRoutes = new Set(
    Array.from(adminSection.matchAll(/path="([^"]+)"/g), ([, route]) => route).filter((route) => !['/admin', '/mcp'].includes(route)),
  )
  const adminRouteEntries = Array.isArray(coverage.admin_routes) ? coverage.admin_routes : []
  const coveredAdminRoutes = new Set()
  for (const entry of adminRouteEntries) {
    if (!entry?.route || !entry?.chapter) {
      fail('frontend/platform_docs/coverage.json', 'every admin route needs route, label, and chapter')
      continue
    }
    coveredAdminRoutes.add(entry.route)
    const chapter = checkEntry('admin', entry, `admin route ${entry.route}`)
    if (chapter && !chapter.content.includes(`](${entry.route})`)) {
      fail(chapter.relativeFile, `coverage chapter must link to ${entry.route}`)
    }
  }
  for (const route of applicationAdminRoutes) {
    if (!coveredAdminRoutes.has(route)) fail('frontend/platform_docs/coverage.json', `administration route is undocumented: ${route}`)
  }
  for (const route of coveredAdminRoutes) {
    if (!applicationAdminRoutes.has(route)) fail('frontend/platform_docs/coverage.json', `admin route is not registered in App.jsx: ${route}`)
  }
}

validateCoverage()

if (errors.length) {
  console.error(`Platform documentation check failed with ${errors.length} error(s):`)
  errors.forEach((error) => console.error(`- ${error}`))
  process.exit(1)
}

console.log(`Platform documentation check passed (${seenSlugs.size} chapters; all product routes, admin tabs, guide links, and sections verified).`)
