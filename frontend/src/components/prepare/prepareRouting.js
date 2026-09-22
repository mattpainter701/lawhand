// Addresses for the Prepare route. Every entry point (Studio, the library,
// the matter page's readiness banner, the Probate tab) builds its link here
// so the query vocabulary lives in one place: `template` or `set` names what
// to prepare, `matter` preselects the destination, `folder` the destination
// folder, and `return` where to land after a save (a same-origin path only).
export const PREPARE_PATH = '/templates/prepare'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

const isId = (value) => UUID_PATTERN.test(String(value || ''))

// A return target must be a path on this app, never an absolute URL, so a
// crafted link cannot bounce a signed-in user somewhere else after saving.
// Browsers treat a backslash as a slash, so `/\evil.example` and `\\evil` are
// protocol-relative too; reject any backslash rather than just a leading `//`.
export const safeReturnPath = (value) => {
  const text = String(value || '')
  if (!text.startsWith('/') || text.startsWith('//')) return ''
  if (text.includes('\\') || Array.from(text).some((char) => char.charCodeAt(0) < 0x20)) return ''
  return text
}

export function buildPrepareTarget({ templateId, setId, matterId, folderId, returnTo, sessionId } = {}) {
  const params = new URLSearchParams()
  if (isId(templateId)) params.set('template', String(templateId).toLowerCase())
  else if (isId(setId)) params.set('set', String(setId).toLowerCase())
  if (isId(matterId)) params.set('matter', String(matterId).toLowerCase())
  if (isId(folderId)) params.set('folder', String(folderId).toLowerCase())
  if (isId(sessionId)) params.set('session', String(sessionId).toLowerCase())
  const back = safeReturnPath(returnTo)
  if (back) params.set('return', back)
  const search = params.toString()
  return { pathname: PREPARE_PATH, search: search ? `?${search}` : '', url: search ? `${PREPARE_PATH}?${search}` : PREPARE_PATH }
}

export function readPrepareQuery(search = '') {
  const params = search instanceof URLSearchParams ? search : new URLSearchParams(search)
  const template = params.get('template')
  const set = params.get('set')
  const matter = params.get('matter')
  const folder = params.get('folder')
  const session = params.get('session')
  return {
    templateId: isId(template) ? template.toLowerCase() : null,
    setId: isId(set) ? set.toLowerCase() : null,
    matterId: isId(matter) ? matter.toLowerCase() : null,
    folderId: isId(folder) ? folder.toLowerCase() : null,
    sessionId: isId(session) ? session.toLowerCase() : null,
    returnTo: safeReturnPath(params.get('return')),
  }
}

// Where a saved document lands: the matter's Documents tab with that
// document opened, or the caller's return path with the document appended.
export function buildSavedTarget({ matterId, documentId, returnTo }) {
  const base = safeReturnPath(returnTo) || `/matters/${encodeURIComponent(matterId)}?tab=documents`
  if (!isId(documentId)) return base
  const [path, query = ''] = base.split('?')
  const params = new URLSearchParams(query)
  params.set('document', String(documentId).toLowerCase())
  return `${path}?${params.toString()}`
}
