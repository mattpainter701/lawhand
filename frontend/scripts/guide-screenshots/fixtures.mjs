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

// ── Assistant ───────────────────────────────────────────────────────────────
export const CONVERSATIONS = [
  { id: 'conv-1', title: 'Keller — issues before the settlement conference', matter_id: 'm-0006', use_premium_llm: false, include_public: true, created_at: isoAt(0, '09:02'), updated_at: isoAt(0, '09:06') },
  { id: 'conv-2', title: 'Voss estate — inventory deadline', matter_id: 'm-0002', use_premium_llm: false, include_public: true, created_at: isoAt(-1, '15:40'), updated_at: isoAt(-1, '15:52') },
  { id: 'conv-3', title: 'Draft follow-up to Lena Ortiz', matter_id: 'm-0003', use_premium_llm: false, include_public: false, created_at: isoAt(-3, '11:15'), updated_at: isoAt(-3, '11:21') },
]

const CHAT_SOURCES = [
  {
    source_id: 's1', source_type: 'tenant_document', source_label: 'Matter document', cited: true,
    case_name: 'Settlement agreement — second draft (opposing counsel).docx', citation: 'Section 7 (Indemnity)', locator: 'p. 4',
    court: 'Keller v. Northgate Properties', excerpt: 'Plaintiff shall indemnify and hold harmless the Released Parties from any claim arising out of the Premises, including claims by lienholders.',
  },
  {
    source_id: 's2', source_type: 'matter_context', source_label: 'Matter record', cited: true,
    case_name: 'Key dates and deadlines', citation: 'Settlement conference', locator: 'Key dates',
    court: 'Keller v. Northgate Properties', excerpt: 'Settlement conference set for the 30th at 9:30 a.m.; position statements due five days before.',
  },
  {
    source_id: 's3', source_type: 'tenant_document', source_label: 'Matter document', cited: true,
    case_name: 'Medical expense summary.xlsx', citation: 'Summary tab', locator: 'rows 2–19',
    court: 'Keller v. Northgate Properties', excerpt: 'Billed medical expenses to date total $48,312; two providers have asserted liens.',
  },
]

export const CHAT_MESSAGES = [
  {
    id: 'msg-1', role: 'user', created_at: isoAt(0, '09:04'),
    content: 'Summarize the open issues in the second settlement draft before the conference, and list what we still need from the client.',
  },
  {
    id: 'msg-2', role: 'assistant', created_at: isoAt(0, '09:05'), sources: CHAT_SOURCES,
    content: [
      'Here is a working summary of the second draft. Verify each point against the sources before relying on it.',
      '',
      '**Open issues**',
      '',
      '1. **Indemnity is broader than we discussed.** Section 7 has Ms. Keller indemnifying the released parties for any claim "arising out of the Premises", including lienholder claims [source: s1].',
      '2. **Medical liens are not addressed.** Two providers have asserted liens against billed expenses of $48,312, but the draft does not say how they are resolved [source: s3].',
      '3. **Timing.** Position statements are due five days before the settlement conference [source: s2].',
      '',
      '**Still needed from the client**',
      '',
      '- Current lien payoff figures from both providers.',
      '- Confirmation of any other insurance or benefit plans with reimbursement rights.',
    ].join('\n'),
  },
]

// ── Conflict search ─────────────────────────────────────────────────────────
export const CONFLICT_CHECKS = [
  {
    id: 'cc-1', label: 'Northgate Properties — new matter intake', status: 'open', decision: 'needs_review',
    created_at: isoAt(0, '08:47'), match_count: 2, restricted_matter_count: 1, notes: '',
    matches: [
      { contact_id: 'c-0006', display_name: 'Northgate Properties LLC', match_field: 'organization_name', match_value: 'Northgate Properties', matter_names: ['Keller v. Northgate Properties'], restricted_matter_count: 0 },
      { contact_id: 'c-0031', display_name: 'Dana Whitfield', match_field: 'email', match_value: 'dwhitfield@northgate.example', matter_names: [], restricted_matter_count: 1 },
    ],
  },
  {
    id: 'cc-2', label: 'Abernathy trust — beneficiaries', status: 'closed', decision: 'no_conflict_found',
    created_at: isoAt(-9, '14:20'), match_count: 0, restricted_matter_count: 0, matches: [],
    notes: 'Searched the grantor, trustee, and both beneficiaries, including maiden names. No relationships found.',
  },
]

// ── Client intake ───────────────────────────────────────────────────────────
function lead(id, name, fields) {
  return { id: `lead-${id}`, contact_id: `c-l${id}`, contact: { display_name: name }, matter_id: null, estimated_value: null, declined_reason: null, ...fields }
}

export const LEADS = [
  lead('01', 'Marisol Duarte', { status: 'new', practice_area: 'Family Law', source: 'website', created_at: isoAt(0, '08:12'), description: 'Asking about modifying a parenting schedule after a job relocation.' }),
  lead('02', 'Owen Patel', { status: 'contacted', practice_area: 'Employment', source: 'referral', created_at: isoAt(-1, '16:40'), estimated_value: 12000, description: 'Terminated after reporting a safety issue; has the separation letter.' }),
  lead('03', 'Greenway Bakery LLC', { status: 'qualified', practice_area: 'Commercial Litigation', source: 'existing_client', created_at: isoAt(-3, '10:05'), estimated_value: 45000, description: 'Supplier breach of a two-year flour contract; wants to preserve the relationship if possible.' }),
  lead('04', 'Harriet Cole', { status: 'conflict_checked', practice_area: 'Estate Planning & Probate', source: 'bar_referral', created_at: isoAt(-6, '09:30'), description: 'Needs a will and powers of attorney before surgery next month.' }),
  lead('05', 'Tomas Reyes', { status: 'engaged', practice_area: 'Personal Injury', source: 'referral', created_at: isoAt(-9, '13:15'), estimated_value: 80000, description: 'Rear-end collision; fee agreement signed.' }),
  lead('06', 'Priscilla Moss', { status: 'declined', practice_area: 'Immigration', source: 'cold_call', created_at: isoAt(-14, '11:00'), declined_reason: 'Outside the firm\'s practice areas; referred to bar referral service.' }),
]

// ── Template Studio ─────────────────────────────────────────────────────────
function template(id, title, fields) {
  return {
    id: `tpl-${id}`, title, description: '', category: 'general', format: 'docx', body: '',
    source_filename: `${title}.docx`, source_sha256: `sha-${id}`, source_ready: true,
    is_active: false, status: 'draft', published_version_no: null, current_version_no: 1, tested_version_no: null,
    variable_schema: { fields: [] }, updated_at: isoAt(-2, '10:00'), ...fields,
  }
}

const TEMPLATES = [
  template('01', 'Engagement letter — hourly litigation', { category: 'engagement', is_active: true, status: 'published', published_version_no: 3, current_version_no: 3, tested_version_no: 3, fill_coverage: { fills: 14, total: 16 }, description: 'Hourly engagement for commercial litigation, with the firm\'s standard billing terms.' }),
  template('02', 'Notice of appearance', { category: 'litigation', is_active: true, status: 'published', published_version_no: 2, current_version_no: 2, tested_version_no: 2, fill_coverage: { fills: 9, total: 9 }, description: 'Caption, court, case number, and appearing attorney.' }),
  template('03', 'Parenting plan — Wisconsin', { category: 'family', format: 'pdf', status: 'ready_to_publish', current_version_no: 4, tested_version_no: 4, fill_coverage: { fills: 21, total: 30 }, description: 'Court form with placement schedule and holiday rotation.' }),
  template('04', 'Estate inventory', { category: 'probate', status: 'draft', current_version_no: 2, fill_coverage: { fills: 6, total: 18 }, description: 'Inventory of probate assets for the personal representative.' }),
  template('05', 'Demand letter — personal injury', { category: 'personal_injury', status: 'test_failed', current_version_no: 5, tested_version_no: 4, fill_coverage: { fills: 11, total: 13 }, description: 'Liability summary, damages, and settlement demand.' }),
  template('06', 'Lease renewal addendum', { category: 'real_estate', format: 'pdf', source_ready: false, status: 'draft', description: 'Original sample file is no longer retained.' }),
]

const SAMPLE_FORMS = [
  { id: 'smp-1', title: 'Health care power of attorney', category: 'advance_directive', jurisdictions: ['WI'], provenance: { source_name: 'State forms collection', edition: '2024' } },
  { id: 'smp-2', title: 'Residential lease', category: 'contract', jurisdictions: [], provenance: { source_name: 'Practice forms collection' } },
  { id: 'smp-3', title: 'Petition for summary assignment', category: 'court_form', jurisdictions: ['WI'], provenance: { source_name: 'State court forms', edition: '2025' } },
  { id: 'smp-4', title: 'Motor vehicle bill of sale', category: 'bill_of_sale', jurisdictions: ['IL'], provenance: { source_name: 'State forms collection' } },
]

function queue(items) {
  return { total: items.length, items: items.slice(0, 3) }
}

export const TEMPLATE_QUEUES = {
  continue_setup: queue(TEMPLATES.filter((item) => !item.is_active && item.source_ready && ['draft', 'test_failed'].includes(item.status))),
  needs_attention: queue(TEMPLATES.filter((item) => !item.source_ready)),
  awaiting_publish: queue(TEMPLATES.filter((item) => item.status === 'ready_to_publish')),
  published: queue(TEMPLATES.filter((item) => item.is_active)),
}

// ── Administration ──────────────────────────────────────────────────────────
export const ROLES = [
  { id: 'r-admin', name: 'Admin', description: 'Manages people, settings, and integrations.', is_system: true, capabilities: ['manage_users', 'manage_roles', 'admin_settings', 'manage_integrations'], user_count: 1 },
  { id: 'r-attorney', name: 'Attorney', description: 'Works matters and approves legal work.', is_system: true, capabilities: ['manage_matters', 'approve_legal_work', 'use_premium_ai'], user_count: 2 },
  { id: 'r-paralegal', name: 'Paralegal', description: 'Prepares documents and manages tasks.', is_system: true, capabilities: ['manage_matters', 'manage_documents'], user_count: 1 },
  { id: 'r-reception', name: 'Reception', description: 'Captures calls and new inquiries.', is_system: false, capabilities: ['manage_intake'], user_count: 1 },
  { id: 'r-finance', name: 'Finance', description: 'Billing, invoices, and trust accounting.', is_system: true, capabilities: ['view_billing', 'manage_billing'], user_count: 1 },
]

function adminUser(base, fields) {
  return {
    ...base, is_active: true, invitation_status: null, license_active: true, privacy_mode: false,
    workspace_mcp_enabled: true, workspace_mcp_active_grant_count: 0, default_billing_rate: null,
    created_at: isoAt(-400, '09:00'), ...fields,
  }
}

export const ADMIN_USERS = [
  adminUser(PEOPLE.avery, { role_ids: ['r-admin'], default_billing_rate: 450, created_at: isoAt(-720, '09:00') }),
  adminUser(PEOPLE.marcus, { role_ids: ['r-attorney'], default_billing_rate: 425, created_at: isoAt(-690, '09:00'), workspace_mcp_active_grant_count: 1 }),
  adminUser(PEOPLE.priya, { role_ids: ['r-attorney'], default_billing_rate: 325, created_at: isoAt(-380, '09:00'), workspace_mcp_active_grant_count: 1 }),
  adminUser(PEOPLE.jordan, { role_ids: ['r-paralegal'], default_billing_rate: 175, created_at: isoAt(-300, '09:00') }),
  adminUser(PEOPLE.sofia, { role_ids: ['r-reception'], created_at: isoAt(-120, '09:00'), workspace_mcp_enabled: false }),
  adminUser(PEOPLE.dana, { role_ids: ['r-finance'], created_at: isoAt(-90, '09:00') }),
  adminUser({ id: 'u-0007', full_name: 'Noah Kim', email: `noah.kim@${FIRM.domain}`, role: 'user' }, {
    is_active: false, invitation_status: 'pending', invitation_expires_at: isoAt(5, '09:00'), created_at: isoAt(-2, '15:10'), role_ids: ['r-paralegal'],
  }),
]

const USAGE_BY_USER = [
  { user_id: PEOPLE.avery.id, total_cost_usd: 18.42, total_tokens_in: 612000, total_tokens_out: 148000 },
  { user_id: PEOPLE.marcus.id, total_cost_usd: 9.77, total_tokens_in: 301000, total_tokens_out: 88000 },
  { user_id: PEOPLE.priya.id, total_cost_usd: 31.05, total_tokens_in: 1043000, total_tokens_out: 262000 },
  { user_id: PEOPLE.jordan.id, total_cost_usd: 6.2, total_tokens_in: 190000, total_tokens_out: 51000 },
]

export const TENANT = {
  id: FIRM.id, name: FIRM.name, domain: FIRM.domain, billing_tier: 'standard', max_users: 25, max_documents: 50000,
  created_at: isoAt(-730, '09:00'), is_active: true,
}

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
  ['GET', '/api/firm/branding', () => ({
    tenant_name: FIRM.name, tenant_domain: FIRM.domain, firm_name: FIRM.name, firm_name_override: '',
    firm_logo_url: '', firm_address: '400 Lakeside Avenue, Suite 1200, Madison, WI 53703',
    firm_phone: '(608) 555-0142', firm_email: `office@${FIRM.domain}`, firm_website: `https://www.${FIRM.domain}`,
    firm_pdf_footer: 'Confidential — attorney–client privileged communication',
  })],
  ['GET', '/api/admin/permissions', () => ({
    overall_health: 'healthy',
    microsoft: { connected: true, capabilities: { teams: { status: 'ok' } } },
    google: { connected: false },
  })],
  ['GET', '/api/integrations/qbo/status', () => ({ connected: false, configured: true })],
  ['GET', '/api/admin/users', () => ({ users: ADMIN_USERS })],
  ['GET', '/api/admin/usage/by-user', () => ({ users: USAGE_BY_USER })],
  ['GET', '/api/admin/mcp', () => ({ workspace: { status_available: true, deployment_enabled: true, tenant_enabled: true } })],
  ['GET', '/api/admin/roles', () => ROLES],
  ['GET', '/api/admin/tenant', () => TENANT],
  ['GET', '/api/templates/queues', () => TEMPLATE_QUEUES],
  ['GET', '/api/templates/library', () => ({ items: SAMPLE_FORMS, total: SAMPLE_FORMS.length })],
  ['GET', '/api/templates', () => ({
    items: TEMPLATES, total: TEMPLATES.length,
    summary: { total: TEMPLATES.length, active: 2, inactive: 4, ready: 2, source_missing: 1 },
  })],
  ['GET', '/api/conflict-checks', () => ({ items: CONFLICT_CHECKS, total: CONFLICT_CHECKS.length })],
  ['GET', '/api/sms/review', () => []],
  ['GET', '/api/sms/reconciliation', () => []],
  ['GET', '/api/intake', ({ query }) => (query.get('status') ? LEADS.filter((item) => item.status === query.get('status')) : LEADS)],
  ['GET', '/api/conversations', () => CONVERSATIONS],
  ['GET', '/api/documents', () => []],
  ['GET', '/api/mcp/source-health', () => ({ available: false, sources: [] })],
  ['GET', '/api/conversations/:id', ({ params }) => {
    const conversation = CONVERSATIONS.find((item) => item.id === params.id)
    return conversation ? { conversation, messages: params.id === 'conv-1' ? CHAT_MESSAGES : [] } : { __status: 404, body: { detail: 'Not found' } }
  }],
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
