// Guide screenshot definitions. Each shot opens a real screen with fixture
// data, optionally interacts with it, and captures one element or region.
//
//   name       output file: public/guide-assets/<name>.webp
//   path       app route to open
//   user       'admin' | 'attorney' (see SESSION_USERS in fixtures.mjs)
//   fixtures   extra [method, path, handler] API routes for this shot
//   waitFor    text that must be visible before capturing
//   setup      async (page) => {} for clicks and typing
//   annotate   [{ target, label }] numbered call-outs drawn on the capture
//   target     selector (or page => locator) to capture; default is the viewport
//   clip       { x, y, width, height }, or async (page) => region, to crop
//   viewport   defaults to 1440 × 900 at 2× pixel density
import { regionAround } from './helpers.mjs'

const byRole = (role, name, options = {}) => (page) => page.getByRole(role, { name, ...options })

export const SHOTS = [
  // ── User guide: getting started ─────────────────────────────────────────
  {
    name: 'workspace-tour',
    path: '/matters',
    user: 'attorney',
    viewport: { width: 1280, height: 800 },
    waitFor: 'assigned to you',
    annotate: [
      { target: 'nav.overflow-y-auto', label: '1', pad: -2 },
      { target: '[data-testid="shell-guide-link"]', label: '2' },
      { target: 'button[aria-label="Customize navigation"]', label: '3' },
      { target: 'button[aria-label="Open profile"]', label: '4' },
    ],
  },

  // ── User guide: matters ─────────────────────────────────────────────────
  {
    name: 'matters-list',
    path: '/matters',
    user: 'attorney',
    viewport: { width: 1440, height: 1060 },
    waitFor: 'assigned to you',
    clip: (page) => regionAround(page, [
      byRole('heading', 'My Matters', { level: 2 }),
      (p) => p.locator('table').first(),
    ], { pad: 24 }),
    annotate: [
      { target: (page) => page.getByRole('button', { name: /^All\s*8$/ }).locator('..'), label: '1' },
      { target: 'input[aria-label="Filter my matters by keyword"]', label: '2' },
      { target: byRole('button', 'Columns'), label: '3' },
      { target: (page) => page.locator('button[title="Board view"]').locator('..'), label: '4' },
      { target: (page) => page.getByRole('button', { name: 'Working on this' }).first(), label: '5' },
    ],
  },
  {
    name: 'matters-board',
    path: '/matters?view=board',
    user: 'attorney',
    viewport: { width: 1440, height: 1000 },
    waitFor: 'assigned to you',
    clip: (page) => regionAround(page, [
      byRole('heading', 'My Matters', { level: 2 }),
      (p) => p.getByRole('heading', { name: 'Closed', level: 3 }).locator('xpath=ancestor::section[1]'),
    ], { pad: 24, maxHeight: 820 }),
    annotate: [
      { target: (page) => page.getByRole('button', { name: 'Move Harlow Manufacturing — supply contract dispute' }), label: '1', pad: 2 },
      { target: (page) => page.getByRole('heading', { name: 'Closed', level: 3 }).locator('xpath=ancestor::section[1]'), label: '2' },
    ],
  },

  // ── User guide: tasks, calendar, email tasks ─────────────────────────────
  {
    name: 'tasks-list',
    path: '/tasks',
    user: 'attorney',
    viewport: { width: 1440, height: 1300 },
    waitFor: 'Tasks & Deadlines',
    setup: async (page) => {
      await page.getByRole('button', { name: 'Dismiss tip' }).click()
      await page.locator('#task-t-0002').hover()
    },
    clip: (page) => regionAround(page, [
      byRole('heading', 'Tasks & Deadlines', { level: 1 }),
      (p) => p.locator('#task-t-0006'),
    ], { pad: 24 }),
    annotate: [
      { target: byRole('button', 'New Task'), label: '1' },
      { target: (page) => page.getByRole('group', { name: 'Task view' }), label: '2' },
      { target: (page) => page.getByRole('toolbar', { name: 'Task filters' }).or(page.locator('[aria-label="Task filters"]')), label: '3' },
      { target: (page) => page.locator('#task-t-0002').getByRole('button', { name: 'Close', exact: true }), label: '4', pad: 3 },
    ],
  },
  {
    name: 'email-tasks-review',
    path: '/tasks',
    user: 'attorney',
    viewport: { width: 1440, height: 1500 },
    waitFor: 'Needs review (2)',
    setup: async (page) => {
      await page.getByRole('button', { name: 'Needs review (2)' }).click()
      await page.getByRole('heading', { name: 'Needs review', level: 4 }).waitFor()
    },
    target: 'section[aria-label="Email tasks"]',
  },
  {
    name: 'calendar-month',
    path: '/calendar',
    user: 'attorney',
    viewport: { width: 1440, height: 1000 },
    waitFor: 'Deadline Calendar',
    localStorage: { 'calendar-view': 'month' },
    target: 'main',
    annotate: [
      { target: byRole('button', 'New Event'), label: '1' },
      { target: (page) => page.getByRole('button', { name: /Sync Calendar|Connect Calendar/ }), label: '2' },
      { target: '[aria-label="Calendar view"]', label: '3' },
    ],
  },

  // ── User guide: the matter record ───────────────────────────────────────
  {
    name: 'matter-overview',
    path: '/matters/m-0001',
    user: 'attorney',
    viewport: { width: 1440, height: 1300 },
    waitFor: 'Quick Actions',
    clip: (page) => regionAround(page, [
      (p) => p.getByRole('button', { name: 'Matter Portfolio' }),
      (p) => p.getByText('Quick Actions').locator('xpath=ancestor::div[contains(@class, "rounded-2xl")][1]'),
    ], { pad: 24 }),
    annotate: [
      { target: byRole('button', 'Matter settings'), label: '1' },
      { target: byRole('button', 'Close matter'), label: '2' },
      { target: (page) => page.getByRole('button', { name: 'Overview', exact: true }).locator('..'), label: '3' },
      { target: (page) => page.getByText('Quick Actions').locator('xpath=ancestor::div[contains(@class, "rounded-2xl")][1]'), label: '4' },
    ],
  },
  {
    name: 'matter-documents',
    path: '/matters/m-0001?tab=documents',
    user: 'attorney',
    viewport: { width: 1440, height: 1500 },
    waitFor: 'Case Documents',
    clip: (page) => regionAround(page, [
      (p) => p.getByRole('heading', { name: /Case Documents/ }),
      (p) => p.locator('table').first(),
    ], { pad: 24 }),
    annotate: [
      { target: byRole('button', 'Upload Document'), label: '1' },
      { target: byRole('button', 'Attach template'), label: '2' },
      { target: '#matterdocumentstab-search', label: '3' },
      { target: (page) => page.getByRole('region', { name: 'Documents in progress' }).or(page.locator('section[aria-label="Documents in progress"]')), label: '4' },
    ],
  },
  {
    name: 'matter-correspondence',
    path: '/matters/m-0001?tab=correspondence',
    user: 'attorney',
    viewport: { width: 1440, height: 1500 },
    waitFor: 'Forward email to this matter',
    clip: (page) => regionAround(page, [
      (p) => p.getByRole('navigation', { name: 'Matter settings sections' }),
      (p) => p.getByText('Emails awaiting review').locator('xpath=ancestor::div[contains(@class, "p-4")][1]'),
    ], { pad: 24 }),
    annotate: [
      { target: (page) => page.getByRole('button', { name: 'Correspondence' }).first(), label: '1' },
      { target: byRole('button', 'Scan now'), label: '2' },
      { target: (page) => page.getByRole('button', { name: 'Copy' }).first().locator('..'), label: '3' },
      { target: (page) => page.getByRole('button', { name: /File \+ create task/ }), label: '4' },
    ],
  },

  // ── User guide: account safety ──────────────────────────────────────────
  {
    name: 'profile-security',
    path: '/profile',
    user: 'attorney',
    viewport: { width: 1280, height: 1500 },
    waitFor: 'Workspace MCP assistants',
    setup: async (page) => { await page.getByRole('heading', { name: 'Claude' }).waitFor() },
    clip: (page) => regionAround(page, [
      (p) => p.getByRole('heading', { name: 'Protect private details' }).locator('xpath=ancestor::section[1]'),
      (p) => p.locator('section[aria-labelledby="workspace-mcp-grants-heading"]'),
    ], { pad: 24 }),
    annotate: [
      { target: (page) => page.getByRole('switch', { name: 'Protect private details' }), label: '1', pad: 6 },
      { target: byRole('button', 'Sign out everywhere else'), label: '2' },
      { target: byRole('button', 'Revoke'), label: '3' },
    ],
  },

  // ── User guide: time and billing ────────────────────────────────────────
  {
    name: 'time-tracking',
    path: '/time-tracking',
    user: 'attorney',
    viewport: { width: 1440, height: 1250 },
    waitFor: 'Timer running',
    clip: (page) => regionAround(page, [
      byRole('heading', 'Time tracking', { level: 1 }),
      (p) => p.locator('table').first(),
    ], { pad: 24 }),
    annotate: [
      { target: byRole('button', 'Add entry'), label: '1' },
      { target: (page) => page.getByRole('region', { name: 'Running timer' }).or(page.locator('section[aria-label="Running timer"]')), label: '2' },
      { target: (page) => page.getByRole('button', { name: /Stop & log/ }), label: '3' },
    ],
  },
  {
    name: 'invoices-list',
    path: '/invoices',
    user: 'admin',
    viewport: { width: 1440, height: 1500 },
    waitFor: 'INV-2026-0142',
    clip: (page) => regionAround(page, [
      (p) => p.getByRole('heading', { level: 1 }).first(),
      (p) => p.locator('tr', { hasText: 'INV-2026-0118' }),
    ], { pad: 24 }),
    annotate: [
      { target: byRole('button', 'Generate invoice'), label: '1' },
    ],
  },
]
