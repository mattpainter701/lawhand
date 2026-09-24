// Resolves product screens to the guide section that explains them, and back.
//
// frontend/platform_docs/coverage.json is the single registry: every
// authenticated route, Administration tab, and Integrations section names the
// chapter (and optionally the heading anchor) that documents it. The docs
// check (scripts/check_platform_docs.mjs) fails when a screen is unmapped,
// when a chapter does not link back to its screen, or when an anchor does not
// exist, so links in both directions stay honest.
//
// Only the small coverage map is imported here — never the guide text — so the
// app shell can offer a contextual guide link without bundling every chapter.
import coverage from '../platform_docs/coverage.json'

const USER_MODULES = coverage.user_modules || []
const ADMIN_TABS = coverage.admin_tabs || []
const ADMIN_INTEGRATION_SECTIONS = coverage.admin_integration_sections || []
const ADMIN_ROUTES = coverage.admin_routes || []

function withAnchor(path, anchor) {
  return anchor ? `${path}#${anchor}` : path
}

export function userGuideHref(chapter, anchor) {
  return withAnchor(`/guide/${chapter}`, anchor)
}

export function adminGuideHref(chapter, anchor) {
  return withAnchor(`/admin?tab=guide&chapter=${encodeURIComponent(chapter)}`, anchor)
}

export function guideHref(audience, chapter, anchor) {
  return audience === 'admin' ? adminGuideHref(chapter, anchor) : userGuideHref(chapter, anchor)
}

function topicFrom(audience, entry) {
  if (!entry) return null
  return {
    audience,
    chapter: entry.chapter,
    anchor: entry.anchor || null,
    label: entry.label,
    href: guideHref(audience, entry.chapter, entry.anchor),
  }
}

function segmentsOf(path) {
  return path.split('/').filter(Boolean)
}

export function isParameterizedRoute(route) {
  return segmentsOf(route).some((segment) => segment.startsWith(':'))
}

// Scores how well a registered route pattern (e.g. /matters/:matterId/research)
// covers a pathname: null when it does not match as a prefix, otherwise higher
// for more literal segments, then for longer patterns.
function routeMatchScore(pathname, route) {
  const path = segmentsOf(pathname)
  const pattern = segmentsOf(route)
  if (pattern.length > path.length) return null
  let literal = 0
  for (let index = 0; index < pattern.length; index += 1) {
    if (pattern[index].startsWith(':')) continue
    if (pattern[index] !== path[index]) return null
    literal += 1
  }
  return literal * 100 + pattern.length
}

function matchesRoute(pathname, route) {
  return routeMatchScore(pathname, route) !== null
}

// The most specific registered route wins, so /matters/<id>/research resolves
// to the Research Workspace entry and /matters/<id> to the matters entry.
export function guideTopicForUserRoute(pathname) {
  let best = null
  let bestScore = -1
  for (const entry of USER_MODULES) {
    const score = routeMatchScore(pathname, entry.route)
    if (score !== null && score > bestScore) {
      best = entry
      bestScore = score
    }
  }
  return topicFrom('user', best)
}

export function guideTopicForAdminTab(tab) {
  return topicFrom('admin', ADMIN_TABS.find((entry) => entry.tab === tab))
}

export function guideTopicForIntegrationSection(section) {
  const entry = ADMIN_INTEGRATION_SECTIONS.find((item) => item.section === section)
  return entry ? topicFrom('admin', entry) : guideTopicForAdminTab('integrations')
}

// Returns the guide topic for the screen at `pathname` + `search`, or null
// when the screen is the guide itself or is not documented.
export function guideTopicForLocation(pathname = '', search = '') {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (matchesRoute(path, '/guide')) return null

  if (path === '/admin') {
    const params = new URLSearchParams(search)
    const tab = params.get('tab') || 'users'
    if (tab === 'guide') return null
    if (tab === 'integrations') {
      const section = params.get('integration')
      return section && section !== 'overview'
        ? guideTopicForIntegrationSection(section)
        : guideTopicForAdminTab('integrations')
    }
    return guideTopicForAdminTab(tab)
  }

  const adminRoute = ADMIN_ROUTES.find((entry) => matchesRoute(path, entry.route))
  if (adminRoute) return topicFrom('admin', adminRoute)

  return guideTopicForUserRoute(path)
}

// The screens a chapter documents, for "open this screen" links from the guide.
// Screens that only exist inside a record (a matter's Research Workspace, for
// example) have no standalone address, so the chapter explains how to reach
// them instead.
export function screensForChapter(audience, chapter) {
  if (audience === 'admin') {
    return [
      ...ADMIN_TABS.filter((entry) => entry.chapter === chapter && entry.tab !== 'guide')
        .map((entry) => ({ key: `tab:${entry.tab}`, label: entry.label, href: `/admin?tab=${entry.tab}` })),
      ...ADMIN_INTEGRATION_SECTIONS.filter((entry) => entry.chapter === chapter)
        .map((entry) => ({
          key: `integration:${entry.section}`,
          label: entry.label,
          href: `/admin?tab=integrations&integration=${entry.section}`,
        })),
      ...ADMIN_ROUTES.filter((entry) => entry.chapter === chapter)
        .map((entry) => ({ key: `route:${entry.route}`, label: entry.label, href: entry.route })),
    ]
  }
  return USER_MODULES.filter((entry) => entry.chapter === chapter && !isParameterizedRoute(entry.route))
    .map((entry) => ({ key: `route:${entry.route}`, label: entry.label, href: entry.route }))
}

// Where the user guide explains each section of a matter record, so the
// shell's Guide button follows the tab in view. guideTopics.test.js checks
// every anchor against the guide's headings.
export const MATTER_SECTION_GUIDES = {
  dashboard: { chapter: 'matters-and-documents', anchor: 'tour-of-a-matter', label: 'Matter overview' },
  activity: { chapter: 'tasks-calendar-communications', anchor: 'log-a-communication', label: 'Matter activity' },
  team: { chapter: 'matters-and-documents', anchor: 'define-caption-parties', label: 'Matter people and parties' },
  workflow: { chapter: 'document-automation-and-esignature', anchor: 'documents-from-a-workflow', label: 'Matter workflow' },
  documents: { chapter: 'matters-and-documents', anchor: 'work-with-documents', label: 'Matter documents' },
  correspondence: { chapter: 'matters-and-documents', anchor: 'correspondence-and-matter-email', label: 'Matter correspondence' },
  portal: { chapter: 'teams-and-client-portals', anchor: 'client-and-participant-portals', label: 'Client portal' },
  billing: { chapter: 'time-billing-and-reports', anchor: 'record-time', label: 'Matter billing' },
  chat: { chapter: 'assistant-and-add-ons', anchor: 'ask-better-questions', label: 'Matter chat' },
  settings: { chapter: 'matters-and-documents', anchor: 'tour-of-a-matter', label: 'Matter settings' },
}
