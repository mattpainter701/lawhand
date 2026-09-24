// Synthetic data for guide screenshots. Every person, firm, client, matter,
// address, and number here is fictional; emails use the reserved .example
// domain. Dates are relative to FIXED_NOW, which the capture script also sets
// as the browser clock, so "tomorrow" and "overdue" stay stable between runs.

export const TIMEZONE = 'America/Chicago'
// Tuesday 22 September 2026, 10:00 in Chicago.
export const FIXED_NOW = new Date('2026-09-22T15:00:00Z')

const DAY = 24 * 60 * 60 * 1000

export function isoDay(offsetDays = 0) {
  return new Date(FIXED_NOW.getTime() + offsetDays * DAY).toISOString().slice(0, 10)
}

// An instant `offsetDays` from FIXED_NOW at a Chicago wall-clock time (CDT).
export function isoAt(offsetDays = 0, time = '10:00') {
  const [hours, minutes] = time.split(':').map(Number)
  const day = isoDay(offsetDays)
  const utc = new Date(`${day}T00:00:00Z`)
  utc.setUTCHours(hours + 5, minutes)
  return utc.toISOString()
}

export const FIRM = {
  id: '6a8f2c10-0000-4000-8000-000000000001',
  name: 'Maple & Birch Law',
  domain: 'maplebirch.example',
}

const ALL_MODULES = [
  'matters', 'chat', 'calendar', 'tasks', 'communications', 'contacts', 'intake', 'intake-dashboard',
  'templates', 'time-tracking', 'invoices', 'billing', 'trust', 'reports', 'plugins', 'admin', 'mcp', 'onboarding',
]
const ALL_CAPABILITIES = [
  'manage_users', 'manage_roles', 'manage_billing', 'view_billing', 'manage_matters', 'manage_intake',
  'view_confidential_call_content', 'manage_documents', 'search_firm_memory', 'manage_workflows',
  'manage_integrations', 'admin_settings', 'approve_legal_work', 'use_premium_ai',
]

function person(id, fullName, email, role, extra = {}) {
  return { id, full_name: fullName, email: `${email}@${FIRM.domain}`, role, ...extra }
}

export const PEOPLE = {
  avery: person('u-0001', 'Avery Chen', 'avery.chen', 'admin', { job_title: 'Managing Partner' }),
  jordan: person('u-0002', 'Jordan Ellis', 'jordan.ellis', 'user', { job_title: 'Senior Paralegal' }),
  priya: person('u-0003', 'Priya Raman', 'priya.raman', 'user', { job_title: 'Associate Attorney' }),
  marcus: person('u-0004', 'Marcus Webb', 'marcus.webb', 'user', { job_title: 'Partner' }),
  sofia: person('u-0005', 'Sofia Alvarez', 'sofia.alvarez', 'user', { job_title: 'Receptionist' }),
  dana: person('u-0006', 'Dana Brooks', 'dana.brooks', 'accountant', { job_title: 'Firm Accountant' }),
}

function sessionUser(base, overrides = {}) {
  return {
    ...base,
    tenant_id: FIRM.id,
    tenant_name: FIRM.name,
    is_active: true,
    license_active: true,
    premium_ai_enabled: true,
    premium_ai_available: true,
    standard_matter_context_allowed: true,
    public_case_law_allowed: true,
    created_at: '2025-11-03T15:00:00Z',
    billing_tier: 'professional',
    subscription_status: 'active',
    billing_status: 'active',
    access_state: 'active',
    enabled_modules: ALL_MODULES,
    active_addons: ['mediation-legal'],
    capabilities: ALL_CAPABILITIES,
    navigation_paths: null,
    navigation_preferences: { hidden: [], order: [] },
    default_route: '/matters',
    plan: 'full-platform',
    professional_role: 'Attorney',
    office_location: 'Madison office',
    primary_jurisdictions: ['WI', 'IL'],
    privacy_mode: false,
    workspace_mcp_enabled: true,
    workspace_mcp_reconnect: [],
    hidden_matter_panels: [],
    ...overrides,
  }
}

export const SESSION_USERS = {
  admin: sessionUser(PEOPLE.avery),
  attorney: sessionUser(PEOPLE.priya, {
    capabilities: ['manage_matters', 'manage_intake', 'manage_documents', 'view_confidential_call_content', 'search_firm_memory', 'approve_legal_work', 'use_premium_ai'],
    enabled_modules: ALL_MODULES.filter((module) => !['admin', 'onboarding', 'billing', 'mcp'].includes(module)),
  }),
}


// ── Matters ─────────────────────────────────────────────────────────────────
function matter(id, fields) {
  return {
    id: `m-${id}`,
    matter_number: fields.number,
    matter_name: fields.name,
    client_name: fields.client,
    client_id: `c-${id}`,
    attorney_of_record_name: fields.attorney || PEOPLE.priya.full_name,
    partner_attorney_name: fields.originating || PEOPLE.marcus.full_name,
    practice_area: fields.area,
    matter_type: fields.type || fields.area,
    status: fields.status || 'active',
    risk_level: fields.risk || 'low',
    opened_on: fields.opened || isoDay(-120),
    created_at: `${fields.opened || isoDay(-120)}T15:00:00Z`,
    updated_at: fields.updated || isoAt(-2, '09:15'),
    overdue_deadline_label: fields.deadline || null,
    description: fields.description || '',
    engagement_status: fields.engagement ?? 'signed_on_file',
    my_assignment_id: fields.mine === false ? null : `as-${id}`,
    is_active_working: Boolean(fields.working),
    active_workers: fields.workers || [],
    jurisdiction: fields.jurisdiction || 'Wisconsin',
    court: fields.court || null,
    case_number: fields.caseNumber || null,
    is_closed: fields.status === 'closed',
    cloud_folder: {
      onedrive: { url: 'https://example.invalid/folder', folder_name: `${fields.number} ${fields.client}` },
    },
  }
}

export const MATTERS = [
  matter('0001', { number: 'HARL0001', name: 'Harlow Manufacturing — supply contract dispute', client: 'Harlow Manufacturing LLC', area: 'Commercial Litigation', status: 'active', risk: 'high', deadline: 'Due tomorrow', working: true, workers: ['Priya Raman'], jurisdiction: 'Wisconsin', court: 'Dane County Circuit Court', caseNumber: '2026CV001482', opened: isoDay(-210) }),
  matter('0002', { number: 'VOSS0001', name: 'Estate of Eleanor Voss', client: 'Thomas Voss', area: 'Estate Planning & Probate', type: 'Probate', status: 'active', risk: 'medium', deadline: 'Due in 6 days', attorney: PEOPLE.marcus.full_name, opened: isoDay(-64) }),
  matter('0003', { number: 'ORTI0001', name: 'Ortiz — dissolution of marriage', client: 'Lena Ortiz', area: 'Family Law', status: 'open', risk: 'medium', deadline: '2 days overdue', opened: isoDay(-18) }),
  matter('0004', { number: 'RIVE0001', name: 'Riverside Dental Group — lease renewal', client: 'Riverside Dental Group', area: 'Real Estate', status: 'pending', risk: 'low', engagement: 'pending_copy', opened: isoDay(-45), updated: isoAt(-20, '11:00') }),
  matter('0005', { number: 'BRIG0001', name: 'Brightline Logistics — employment handbook review', client: 'Brightline Logistics Inc.', area: 'Employment', status: 'active', risk: 'low', deadline: 'Due in 12 days', working: true, workers: ['Jordan Ellis'], opened: isoDay(-90) }),
  matter('0006', { number: 'KELL0001', name: 'Keller v. Northgate Properties', client: 'Nadia Keller', area: 'Personal Injury', status: 'active', risk: 'critical', deadline: 'Due today', attorney: PEOPLE.marcus.full_name, jurisdiction: 'Illinois', court: 'Cook County Circuit Court', caseNumber: '2026L004417', opened: isoDay(-300) }),
  matter('0007', { number: 'ABER0001', name: 'Abernathy trust administration', client: 'Grace Abernathy', area: 'Estate Planning & Probate', status: 'open', risk: 'low', engagement: 'no_agreement', opened: isoDay(-9) }),
  matter('0008', { number: 'SUMM0001', name: 'Summit Outfitters — trademark clearance', client: 'Summit Outfitters Co.', area: 'Intellectual Property', status: 'closed', risk: 'low', opened: isoDay(-400), updated: isoAt(-30, '14:00') }),
]

const OTHER_MATTERS = [
  matter('0009', { number: 'PARK0001', name: 'Parkview HOA — collections', client: 'Parkview Homeowners Association', area: 'Real Estate', status: 'active', risk: 'low', mine: false, attorney: PEOPLE.marcus.full_name }),
  matter('0010', { number: 'NGUY0001', name: 'Nguyen immigration petition', client: 'Minh Nguyen', area: 'Immigration', status: 'open', risk: 'medium', mine: false }),
]

export const ALL_MATTERS = [...MATTERS, ...OTHER_MATTERS]

function page(items, query) {
  const size = Number(query.get('page_size') || items.length || 1)
  return { items, total: items.length, page: Number(query.get('page') || 1), page_size: size }
}

// ── Tasks ───────────────────────────────────────────────────────────────────
function task(id, fields) {
  return {
    id: `t-${id}`,
    version: 1,
    status: 'pending',
    priority: 'medium',
    task_type: 'general',
    description: '',
    assigned_to_user_id: PEOPLE.priya.id,
    viewed_at: null,
    customer_contacted_at: null,
    contact_id: null,
    matter_id: null,
    source: 'manual',
    created_at: isoAt(-6, '09:00'),
    updated_at: isoAt(-1, '16:30'),
    ...fields,
  }
}

export const OVERDUE_TASKS = [
  task('0001', { title: 'File response to motion to compel', description: 'Harlow Manufacturing — confirm the filing deadline against the scheduling order.', due_date: isoDay(-1), priority: 'urgent', task_type: 'filing', matter_id: 'm-0001', status: 'in_progress' }),
]

export const TASKS = [
  task('0002', { title: 'Call Lena Ortiz about the temporary custody hearing', description: 'Walk through the hearing logistics and the documents she still needs to send.', due_date: isoDay(0), priority: 'high', task_type: 'call', matter_id: 'm-0003', contact_id: 'c-0003' }),
  task('0003', { title: 'Review the settlement agreement draft', description: 'Keller v. Northgate Properties — second draft from opposing counsel.', due_date: isoDay(0), priority: 'high', task_type: 'review', matter_id: 'm-0006', status: 'review' }),
  task('0004', { title: 'Send engagement letter to Grace Abernathy', due_date: isoDay(2), task_type: 'general', matter_id: 'm-0007', assigned_to_user_id: PEOPLE.sofia.id }),
  task('0005', { title: 'Prepare the estate inventory', description: 'Estate of Eleanor Voss — use the verified asset list from the client portal.', due_date: isoDay(6), task_type: 'deadline', matter_id: 'm-0002', assigned_to_user_id: PEOPLE.jordan.id, viewed_at: isoAt(-1, '08:40') }),
  task('0006', { title: 'Deposition prep with the property manager', due_date: isoDay(10), priority: 'high', task_type: 'deposition', matter_id: 'm-0006' }),
  task('0007', { title: 'Update the employee handbook redlines', due_date: isoDay(13), priority: 'low', task_type: 'review', matter_id: 'm-0005', status: 'waiting', waiting_reason: 'Waiting on the client’s HR comments' }),
  task('0008', { title: 'Collect the lease history from Riverside Dental', priority: 'low', matter_id: 'm-0004' }),
  task('0009', { title: 'Deliver the trademark clearance memo', status: 'completed', closed_reason: 'Memo sent to the client and filed to the matter.', matter_id: 'm-0008', due_date: isoDay(-8) }),
]

// ── Calendar ────────────────────────────────────────────────────────────────
function calendarEvent(id, fields) {
  const { day, time, ...rest } = fields
  return {
    id: `ev-${id}`,
    date: isoDay(day),
    start: time ? isoAt(day, time) : null,
    ...rest,
  }
}

export const CALENDAR_EVENTS = [
  calendarEvent('01', { day: -19, event_type: 'matter_key_date', title: 'Scheduling conference', matter_name: 'Keller v. Northgate Properties', time: '09:30' }),
  calendarEvent('02', { day: -14, event_type: 'task_due', title: 'Serve discovery requests', matter_name: 'Harlow Manufacturing — supply contract dispute', task_id: 't-0101', is_completed: true }),
  calendarEvent('03', { day: -7, event_type: 'renewal', title: 'Lease notice window opens', matter_name: 'Riverside Dental Group — lease renewal' }),
  calendarEvent('04', { day: -4, event_type: 'estate_deadline', title: 'Notice to creditors published', matter_name: 'Estate of Eleanor Voss' }),
  calendarEvent('05', { day: -1, event_type: 'task_due', title: 'File response to motion to compel', matter_name: 'Harlow Manufacturing — supply contract dispute', task_id: 't-0001' }),
  calendarEvent('06', { day: 0, event_type: 'scheduled_event', title: 'Draft settlement agreement', matter_name: 'Keller v. Northgate Properties', task_id: 't-0003', time: '10:00', end: isoAt(0, '12:00') }),
  calendarEvent('07', { day: 0, event_type: 'task_due', title: 'Call Lena Ortiz', matter_name: 'Ortiz — dissolution of marriage', task_id: 't-0002' }),
  calendarEvent('08', { day: 0, event_type: 'scheduled_event', title: 'Client meeting — Harlow', matter_name: 'Harlow Manufacturing — supply contract dispute', time: '14:00', end: isoAt(0, '15:00'), meeting_provider: 'zoom' }),
  calendarEvent('09', { day: 2, event_type: 'task_due', title: 'Send engagement letter', matter_name: 'Abernathy trust administration', task_id: 't-0004' }),
  calendarEvent('10', { day: 3, event_type: 'matter_key_date', title: 'Mediation session', matter_name: 'Ortiz — dissolution of marriage', time: '09:00' }),
  calendarEvent('11', { day: 6, event_type: 'task_due', title: 'Prepare the estate inventory', matter_name: 'Estate of Eleanor Voss', task_id: 't-0005' }),
  calendarEvent('12', { day: 6, event_type: 'estate_deadline', title: 'Inventory due to the court', matter_name: 'Estate of Eleanor Voss' }),
  calendarEvent('13', { day: 8, event_type: 'external_calendar', title: 'Bar association lunch', time: '12:00' }),
  calendarEvent('14', { day: 10, event_type: 'task_due', title: 'Deposition prep', matter_name: 'Keller v. Northgate Properties', task_id: 't-0006' }),
  calendarEvent('15', { day: 13, event_type: 'task_due', title: 'Handbook redlines', matter_name: 'Brightline Logistics — employment handbook review', task_id: 't-0007' }),
  calendarEvent('16', { day: 14, event_type: 'matter_key_date', title: 'Deposition of property manager', matter_name: 'Keller v. Northgate Properties', time: '10:00' }),
]

// ── Firm email intake ───────────────────────────────────────────────────────
const INTAKE_STAFF = [PEOPLE.avery, PEOPLE.jordan, PEOPLE.priya, PEOPLE.marcus, PEOPLE.sofia]
  .map((person) => ({ id: person.id, name: person.full_name, email: person.email }))

export const EMAIL_INTAKE = {
  enabled: true,
  alias: { address: 'tasks-7fq2k9@intake.maplebirch.example' },
  timezone: TIMEZONE,
  pending_count: 2,
  staff: INTAKE_STAFF,
}

export const EMAIL_INTAKE_QUEUE = {
  items: [
    {
      id: 'q-0001',
      subject: '[TASK] Jordan, pull the Harlow shipping logs in two weeks',
      sender: PEOPLE.priya.email,
      body_preview: 'Forwarded message from Dale Harlow: “Our warehouse team can export the Q2 shipping logs once the audit closes…”',
      suggestion: {
        sender: `${PEOPLE.priya.full_name} <${PEOPLE.priya.email}>`,
        task: { tag: 'task', title: 'Pull the Harlow shipping logs', assigned_to_user_id: PEOPLE.jordan.id, due_date: isoDay(14) },
        matters: [{ id: 'm-0001', title: 'Harlow Manufacturing — supply contract dispute' }],
      },
    },
    {
      id: 'q-0002',
      subject: '[DEADLINE] Priya, response to the discovery letter',
      sender: PEOPLE.marcus.email,
      body_preview: 'Opposing counsel asks for a response to their discovery deficiency letter. Please confirm the date.',
      suggestion: {
        sender: `${PEOPLE.marcus.full_name} <${PEOPLE.marcus.email}>`,
        task: { tag: 'deadline', title: 'Response to the discovery letter', assigned_to_user_id: PEOPLE.priya.id, due_date: null },
        matters: [],
      },
    },
  ],
  matters: MATTERS.filter((item) => item.status !== 'closed').map((item) => ({ id: item.id, title: item.matter_name })),
}

// ── A matter record (Harlow) ────────────────────────────────────────────────
export function matterDetail(id) {
  const base = ALL_MATTERS.find((item) => item.id === id) || MATTERS[0]
  return {
    ...base,
    description: 'Breach of a two-year supply agreement after three late component shipments. Client seeks damages and early termination.',
    stage: 'Discovery',
    role: 'Plaintiff’s counsel',
    counterparty: 'Castellan Components Inc.',
    client_contact_id: `c-${base.id.slice(2)}`,
    attorney_of_record_id: PEOPLE.priya.id,
    partner_attorney_id: PEOPLE.marcus.id,
    billing_method: 'hourly',
    billing_cycle: 'monthly',
    hourly_rate: 325,
    budget_amount: 40000,
    budget_currency: 'USD',
    memory_content: '',
    assignments: [
      { id: 'as-0001', user_id: PEOPLE.priya.id, user_name: PEOPLE.priya.full_name, role: 'lead_attorney', is_active_working: true },
      { id: 'as-0002', user_id: PEOPLE.jordan.id, user_name: PEOPLE.jordan.full_name, role: 'paralegal', is_active_working: false },
    ],
  }
}

const MATTER_TASKS = [
  task('0101', { title: 'File response to motion to compel', due_date: isoDay(-1), priority: 'urgent', task_type: 'filing', matter_id: 'm-0001' }),
  task('0102', { title: 'Hearing on motion to compel', due_date: isoDay(9), task_type: 'hearing', matter_id: 'm-0001' }),
  task('0103', { title: 'Expert disclosure deadline', due_date: isoDay(24), task_type: 'deadline', matter_id: 'm-0001' }),
  task('0104', { title: 'Send the client the draft interrogatory answers', due_date: isoDay(1), matter_id: 'm-0001' }),
  task('0105', { title: 'Pull the Q2 shipping logs', due_date: isoDay(14), matter_id: 'm-0001', assigned_to_user_id: PEOPLE.jordan.id }),
  task('0106', { title: 'Calendar the mediation availability window', matter_id: 'm-0001' }),
]

function doc(id, fields) {
  return {
    id: `d-${id}`,
    matter_id: 'm-0001',
    file_size: 184_320,
    storage_backend: 'onedrive',
    cloud_url: 'https://example.invalid/file',
    portal_visible: false,
    tags: [],
    folder_path: null,
    created_at: isoAt(-12, '10:00'),
    ...fields,
  }
}

export const MATTER_DOCUMENTS = [
  doc('0001', { filename: 'Complaint - Harlow v Castellan.pdf', document_category: 'pleading', description: 'Filed complaint with exhibits A–D', folder_path: 'Pleadings', file_size: 2_457_600, created_at: isoAt(-200, '11:00') }),
  doc('0002', { filename: 'Supply Agreement (executed).pdf', document_category: 'contract', description: 'Two-year supply agreement, signed March 2025', folder_path: 'Contracts', file_size: 824_000, tags: [{ id: 'tag-1', name: 'Key document', color: 'amber' }] }),
  doc('0003', { filename: 'Motion to Compel - Castellan.pdf', document_category: 'pleading', description: 'Opposing motion; response due ' + isoDay(-1), folder_path: 'Pleadings', file_size: 612_000, created_at: isoAt(-15, '16:20') }),
  doc('0004', { filename: 'Shipping delay log Q1.xlsx', document_category: 'evidence', description: 'Client export of late shipments', folder_path: 'Evidence', file_size: 96_000, portal_visible: true }),
  doc('0005', { filename: 'Engagement letter - signed.pdf', document_category: 'correspondence', description: 'Signed engagement letter', folder_path: 'Correspondence', file_size: 140_000, portal_visible: true }),
]

export const MATTER_FOLDERS = [
  { id: 'f-1', name: 'Pleadings', parent_id: null, path: 'Pleadings', document_count: 2 },
  { id: 'f-2', name: 'Contracts', parent_id: null, path: 'Contracts', document_count: 1 },
  { id: 'f-3', name: 'Evidence', parent_id: null, path: 'Evidence', document_count: 1 },
  { id: 'f-4', name: 'Correspondence', parent_id: null, path: 'Correspondence', document_count: 1 },
]

export const CORRESPONDENCE = [
  { id: 'cr-1', thread_ref: 'th-1', direction: 'inbound', subject: 'Re: Q2 shipment delays', occurred_at: isoAt(-3, '09:12'), participants: { from: 'dale.harlow@harlowmfg.example', to: [PEOPLE.priya.email] }, summary: 'Dale confirms the warehouse can export the Q2 logs after the audit closes on Friday.', has_attachment: true },
  { id: 'cr-2', thread_ref: 'th-1', direction: 'outbound', subject: 'Re: Q2 shipment delays', occurred_at: isoAt(-3, '11:40'), participants: { from: PEOPLE.priya.email, to: ['dale.harlow@harlowmfg.example'] }, summary: 'Thanks, Dale. Please include the carrier confirmations for each late shipment.', has_attachment: true },
  { id: 'cr-3', direction: 'inbound', subject: 'Castellan discovery deficiency letter', occurred_at: isoAt(-5, '15:05'), participants: { from: 'counsel@castellanlaw.example', to: [PEOPLE.priya.email] }, summary: 'Opposing counsel lists five interrogatories they consider incomplete.', has_attachment: true },
]

export const INBOUND_EMAIL = [
  {
    id: 'ie-1',
    subject: '[TASK] Draft the carrier subpoena',
    participants: { from: PEOPLE.marcus.email },
    envelope_sender: PEOPLE.marcus.email,
    occurred_at: isoAt(0, '08:05'),
    body_preview: 'Forwarding the carrier’s records custodian details. Let’s serve before the expert disclosure date.',
    task_suggestion: { tag: 'task', title: 'Draft the carrier subpoena', due_date: isoDay(7) },
  },
]

// ── Time and invoices ───────────────────────────────────────────────────────
function timeEntry(id, fields) {
  return { id: `te-${id}`, user_name: PEOPLE.priya.full_name, hourly_rate: 325, is_billable: true, status: 'draft', invoice_id: null, ...fields }
}

export const TIME_ENTRIES = [
  timeEntry('01', { matter_id: 'm-0001', date: isoDay(0), hours: 1.2, amount: 390, description: 'Draft response to motion to compel; review scheduling order' }),
  timeEntry('02', { matter_id: 'm-0003', date: isoDay(-1), hours: 0.5, amount: 162.5, description: 'Call with client re temporary custody hearing logistics' }),
  timeEntry('03', { matter_id: 'm-0002', date: isoDay(-1), hours: 2.4, amount: 780, description: 'Prepare inventory schedule from verified asset list' }),
  timeEntry('04', { matter_id: 'm-0006', date: isoDay(-2), hours: 3.1, amount: 1007.5, description: 'Review settlement agreement draft; redline indemnity terms', status: 'approved' }),
  timeEntry('05', { matter_id: 'm-0005', date: isoDay(-3), hours: 0.8, amount: 0, description: 'Internal knowledge-sharing meeting', is_billable: false }),
  timeEntry('06', { matter_id: 'm-0001', date: isoDay(-9), hours: 4.9, amount: 1592.5, description: 'Draft interrogatory answers and document requests', status: 'invoiced', invoice_id: 'inv-2' }),
]

export const INVOICES = [
  { id: 'inv-1', invoice_number: 'INV-2026-0142', matter_name: 'Harlow Manufacturing — supply contract dispute', matter_id: 'm-0001', status: 'draft', issue_date: isoDay(0), due_date: isoDay(30), total: 3240, balance_due: 3240, qbo_sync_status: null },
  { id: 'inv-2', invoice_number: 'INV-2026-0137', matter_name: 'Harlow Manufacturing — supply contract dispute', matter_id: 'm-0001', status: 'sent', issue_date: isoDay(-9), due_date: isoDay(21), total: 1592.5, balance_due: 1592.5, qbo_sync_status: 'synced', qbo_invoice_id: '1187' },
  { id: 'inv-3', invoice_number: 'INV-2026-0129', matter_name: 'Keller v. Northgate Properties', matter_id: 'm-0006', status: 'sent', issue_date: isoDay(-45), due_date: isoDay(-15), total: 6810, balance_due: 2810, is_overdue: true, qbo_sync_status: 'synced', qbo_invoice_id: '1172' },
  { id: 'inv-4', invoice_number: 'INV-2026-0118', matter_name: 'Estate of Eleanor Voss', matter_id: 'm-0002', status: 'paid', issue_date: isoDay(-60), due_date: isoDay(-30), total: 2275, balance_due: 0, qbo_sync_status: 'synced', qbo_invoice_id: '1160' },
]

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

function compile(pattern) {
  const names = []
  const source = pattern.replace(/:[a-zA-Z_]+/g, (match) => {
    names.push(match.slice(1))
    return '([^/]+)'
  })
  return { regex: new RegExp(`^${source}/?$`), names }
}

// [method, path pattern, handler(context) => body | { status, body }]
const BASE_ROUTES = [
  ['POST', '/api/auth/refresh', () => ({ ok: true })],
  ['GET', '/api/auth/me', ({ user }) => user],
  ['PATCH', '/api/auth/me', ({ user }) => user],
  ['GET', '/api/version', () => ({ version: '0.0.0-guide', latest_release: null })],
  ['GET', '/api/release-window', () => ({ window: null })],
  ['GET', '/api/matters/my/page', ({ query }) => page(MATTERS, query)],
  ['GET', '/api/matters', ({ query }) => page(ALL_MATTERS, query)],
  ['GET', '/api/tasks', ({ query }) => {
    const matterId = query.get('matter_id')
    const items = matterId ? MATTER_TASKS.filter((item) => item.matter_id === matterId) : TASKS
    return { items, total: items.length }
  }],
  ['GET', '/api/matters/:id', ({ params }) => matterDetail(params.id)],
  ['GET', '/api/matters/:id/budget', () => ({ budget_amount: 40000, total_billed: 17200, utilization_pct: 43, billable_time_amount: 16350, billable_expense_amount: 850, remaining: 22800 })],
  ['GET', '/api/matters/:id/dashboard-summary', () => ({ open_tasks: 6, overdue_tasks: 1, utilization_pct: 43, budget_amount: 40000, total_billed: 17200, active_workers: ['Priya Raman'], last_activity_at: isoAt(0, '08:45') })],
  ['GET', '/api/matters/:id/cloud-files', () => ({ connected: true, files: [] })],
  ['GET', '/api/matters/:id/documents', () => ({ items: MATTER_DOCUMENTS, documents: MATTER_DOCUMENTS, total: MATTER_DOCUMENTS.length })],
  ['GET', '/api/trust/accounts', () => ({ items: [{ id: 'ta-0001', current_balance: 5000, matter_id: 'm-0001', account_name: 'Harlow Manufacturing LLC — client trust' }], total: 1 })],
  ['GET', '/api/plugins', () => []],
  ['GET', '/api/workspace-mcp/grants', () => ({ items: [{
    id: 'grant-1',
    client_name: 'Claude',
    tenant_name: FIRM.name,
    status: 'active',
    scopes: ['matters:read', 'tasks:read', 'documents:read', 'tasks:propose'],
    created_at: isoAt(-21, '14:02'),
    expires_at: isoAt(69, '14:02'),
    last_used_at: isoAt(0, '09:12'),
  }] })],
  ['GET', '/api/billing/time-entries', () => ({ items: TIME_ENTRIES, total: TIME_ENTRIES.length, total_hours: 12.9, total_amount: 4102.5 })],
  ['GET', '/api/billing/time-entries/timer', () => ({ id: 'te-timer', matter_id: 'm-0006', timer_started_at: isoAt(0, '09:18'), description: '' })],
  ['GET', '/api/billing/invoices', () => ({ items: INVOICES, total: INVOICES.length })],
  ['GET', '/api/billing/ready-to-bill', () => ({
    items: [
      { matter_id: 'm-0006', matter_name: 'Keller v. Northgate Properties', count: 4, oldest: isoDay(-12), amount: '1007.50', closed: false },
      { matter_id: 'm-0002', matter_name: 'Estate of Eleanor Voss', count: 3, oldest: isoDay(-6), amount: '780.00', closed: false },
      { matter_id: 'm-0003', matter_name: 'Ortiz — dissolution of marriage', count: 2, oldest: isoDay(-4), amount: '325.00', closed: false },
    ],
    total: 3,
    total_amount: '2112.50',
  })],
  ['GET', '/api/billing/time-entry-settings', () => ({ time_rounding_minutes: 6 })],
  ['GET', '/api/matters/:id/correspondence', () => ({ items: CORRESPONDENCE })],
  ['GET', '/api/matters/:id/inbound-email/alias', () => ({ enabled: true, alias: { address: 'harl0001-8c2d4f@matters.maplebirch.example' } })],
  ['GET', '/api/matters/:id/inbound-email', () => ({ items: INBOUND_EMAIL })],
  ['GET', '/api/matters/:id/document-folders', () => ({ items: MATTER_FOLDERS, root_document_count: 0 })],
  ['GET', '/api/document-tags', () => ({ items: [{ id: 'tag-1', name: 'Key document', color: 'amber' }] })],
  ['GET', '/api/matters/:id/fill-sessions', () => ({ items: [{ id: 'fs-1', template_id: 'tpl-2', title: 'Discovery response cover letter', status: 'in_progress', updated_at: isoAt(-1, '17:10') }] })],
  ['GET', '/api/matters/:id/document-prefill', () => ({ stale: false, templates: [
    { template_id: 'tpl-1', title: 'Notice of appearance', status: 'ready', percent: 92, filled: 11, fields: 12, review: 1 },
    { template_id: 'tpl-3', title: 'Litigation hold letter', status: 'ready', percent: 84, filled: 16, fields: 19, missing_required: 1 },
  ] })],
  ['GET', '/api/matters/:id/portal/upload-link', () => null],
  ['GET', '/api/tasks/overdue', () => ({ items: OVERDUE_TASKS, total: OVERDUE_TASKS.length })],
  ['GET', '/api/tasks/board/config', () => ({ enabled: true })],
  ['POST', '/api/tasks/board/telemetry', () => ({})],
  ['GET', '/api/firm-email-intake', () => EMAIL_INTAKE],
  ['GET', '/api/firm-email-intake/queue', () => EMAIL_INTAKE_QUEUE],
  ['GET', '/api/auth/calendar-providers', () => ({ providers: ['microsoft'], provider_status: { microsoft: { connected: true } } })],
  ['POST', '/api/calendar/sync', () => ({ events: [] })],
  ['GET', '/api/integrations/zoom/status', () => ({ configured: true, connected: true })],
  ['GET', '/api/calendar/events', ({ query }) => {
    const start = query.get('start') || '0000-00-00'
    const end = query.get('end') || '9999-99-99'
    const events = CALENDAR_EVENTS.filter((event) => event.date >= start && event.date <= end)
    return { events, total: events.length }
  }],
]

export function createFixtureRouter({ user = 'admin', overrides = [], onUnhandled, onRequest } = {}) {
  const sessionUser = typeof user === 'string' ? SESSION_USERS[user] : user
  const routes = [...overrides, ...BASE_ROUTES].map(([method, pattern, handler]) => ({ method, handler, ...compile(pattern) }))
  return async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const key = `${method} ${url.pathname}${url.search}`
    onRequest?.(key)
    for (const entry of routes) {
      if (entry.method !== method) continue
      const match = url.pathname.match(entry.regex)
      if (!match) continue
      const params = Object.fromEntries(entry.names.map((name, index) => [name, decodeURIComponent(match[index + 1])]))
      let body
      try {
        body = await entry.handler({ url, params, request, user: sessionUser, query: url.searchParams })
      } catch (error) {
        return json(route, { detail: `fixture error: ${error.message}` }, 500)
      }
      if (body && typeof body === 'object' && body.__status) return json(route, body.body ?? {}, body.__status)
      return json(route, body === undefined ? {} : body)
    }
    onUnhandled?.(`${method} ${url.pathname}`)
    // Reads get an empty collection, writes an empty acknowledgement; most
    // screens treat both as "nothing here yet".
    return json(route, method === 'GET' ? [] : {})
  }
}
