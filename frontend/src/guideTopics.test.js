import { describe, expect, it } from 'vitest'
import coverage from '../platform_docs/coverage.json'
import { ADMINISTRATIVE_GUIDE, USER_GUIDE } from './platformDocs'
import {
  MATTER_SECTION_GUIDES,
  adminGuideHref,
  guideTopicForIntegrationSection,
  guideTopicForLocation,
  isParameterizedRoute,
  screensForChapter,
  userGuideHref,
} from './guideTopics'

describe('guide topics', () => {
  it('builds user and administrator guide addresses', () => {
    expect(userGuideHref('matters-and-documents')).toBe('/guide/matters-and-documents')
    expect(userGuideHref('matters-and-documents', 'documents')).toBe('/guide/matters-and-documents#documents')
    expect(adminGuideHref('integrations')).toBe('/admin?tab=guide&chapter=integrations')
    expect(adminGuideHref('integrations', 'document-storage')).toBe('/admin?tab=guide&chapter=integrations#document-storage')
  })

  it('resolves every documented user screen, preferring the most specific route', () => {
    expect(guideTopicForLocation('/tasks')).toMatchObject({ audience: 'user', chapter: 'tasks-calendar-communications', label: 'Tasks' })
    expect(guideTopicForLocation('/tasks/7c9e')).toMatchObject({ chapter: 'tasks-calendar-communications', label: 'Tasks' })
    expect(guideTopicForLocation('/matters/42')).toMatchObject({ chapter: 'matters-and-documents', label: 'My Matters' })
    expect(guideTopicForLocation('/matters/42/research')).toMatchObject({ label: 'Research Workspace' })
    expect(guideTopicForLocation('/matters/42/brief-check')).toMatchObject({ label: 'Brief Check' })
    expect(guideTopicForLocation('/matters/42/documents/9/revisions/3')).toMatchObject({ label: 'Document revisions' })
    expect(guideTopicForLocation('/intake/dashboard')).toMatchObject({ chapter: 'intake-and-call-reception', label: 'Call Intake' })
    expect(guideTopicForLocation('/intake')).toMatchObject({ label: 'Intake' })
    expect(guideTopicForLocation('/templates/prepare')).toMatchObject({ label: 'Prepare a document' })
    expect(guideTopicForLocation('/templates/5/studio')).toMatchObject({ label: 'Template Studio' })
    expect(guideTopicForLocation('/plugins/mediation/cases/12')).toMatchObject({ chapter: 'mediation-workflows' })
    expect(guideTopicForLocation('/plugins/mediation-legal')).toMatchObject({ chapter: 'add-on-module-management' })
  })

  it('never offers a guide link for the guide itself or an undocumented page', () => {
    expect(guideTopicForLocation('/guide')).toBeNull()
    expect(guideTopicForLocation('/guide/matters-and-documents')).toBeNull()
    expect(guideTopicForLocation('/admin', '?tab=guide&chapter=integrations')).toBeNull()
    expect(guideTopicForLocation('/nowhere')).toBeNull()
  })

  it('resolves Administration tabs, integration sections, and the setup wizard', () => {
    expect(guideTopicForLocation('/admin')).toMatchObject({ audience: 'admin', chapter: 'users-roles-and-licensing', label: 'Users' })
    expect(guideTopicForLocation('/admin', '?tab=support')).toMatchObject({ chapter: 'support-and-escalation' })
    expect(guideTopicForLocation('/admin', '?tab=integrations')).toMatchObject({ chapter: 'integrations', label: 'Integrations' })
    expect(guideTopicForLocation('/admin', '?tab=integrations&integration=overview')).toMatchObject({ chapter: 'integrations' })
    expect(guideTopicForLocation('/admin', '?tab=integrations&integration=zoom')).toMatchObject({ chapter: 'zoom-phone-administration', label: 'Zoom' })
    expect(guideTopicForLocation('/onboarding')).toMatchObject({ audience: 'admin', chapter: 'onboarding-and-storage-setup' })
    // Legacy tab ids are rewritten by the Administration page before render.
    expect(guideTopicForLocation('/admin', '?tab=zoom')).toBeNull()
    expect(guideTopicForIntegrationSection('unknown-section')).toMatchObject({ chapter: 'integrations' })
  })

  it('lists the screens a chapter can open directly', () => {
    expect(screensForChapter('user', 'matters-and-documents').map((screen) => screen.href)).toEqual(['/matters', '/firm-memory'])
    expect(screensForChapter('admin', 'storage-imports-and-readiness').map((screen) => screen.href)).toEqual([
      '/admin?tab=integrations&integration=storage-migration',
      '/admin?tab=integrations&integration=data-import',
      '/admin?tab=integrations&integration=readiness',
    ])
    expect(screensForChapter('admin', 'admin-overview')).toEqual([])
    expect(isParameterizedRoute('/matters/:matterId/research')).toBe(true)
    expect(isParameterizedRoute('/matters')).toBe(false)
  })

  it('points every registry entry at a real chapter and heading', () => {
    const chapters = {
      user: new Map(USER_GUIDE.map((chapter) => [chapter.slug, chapter])),
      admin: new Map(ADMINISTRATIVE_GUIDE.map((chapter) => [chapter.slug, chapter])),
    }
    const entries = [
      ...coverage.user_modules.map((entry) => ['user', entry]),
      ...coverage.admin_tabs.map((entry) => ['admin', entry]),
      ...coverage.admin_integration_sections.map((entry) => ['admin', entry]),
      ...coverage.admin_routes.map((entry) => ['admin', entry]),
    ]
    for (const [audience, entry] of entries) {
      const chapter = chapters[audience].get(entry.chapter)
      expect(chapter, `${audience} chapter ${entry.chapter}`).toBeDefined()
      expect(entry.label, `label for ${entry.chapter}`).toBeTruthy()
      if (entry.anchor) expect(chapter.anchors, `${entry.chapter}#${entry.anchor}`).toContain(entry.anchor)
    }
  })

  it('points every matter section at a real guide heading', () => {
    const chapters = new Map(USER_GUIDE.map((chapter) => [chapter.slug, chapter]))
    for (const [section, guide] of Object.entries(MATTER_SECTION_GUIDES)) {
      const chapter = chapters.get(guide.chapter)
      expect(chapter, `${section} → ${guide.chapter}`).toBeDefined()
      expect(chapter.anchors, `${section} → ${guide.chapter}#${guide.anchor}`).toContain(guide.anchor)
    }
  })
})
