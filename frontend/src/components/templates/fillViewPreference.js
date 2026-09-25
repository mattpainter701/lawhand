// The fill view (Document or Questions) a person last chose, remembered per
// browser so someone who prefers the list is not sent back to the page every
// time. A convenience only: storage may be unavailable, and the default is
// always the document.
const KEY = 'lawhand.fill.view'
export const FILL_VIEWS = ['document', 'questions']

export function readFillViewPreference() {
  try {
    const value = globalThis.localStorage?.getItem(KEY)
    return FILL_VIEWS.includes(value) ? value : 'document'
  } catch {
    return 'document'
  }
}

export function writeFillViewPreference(view) {
  if (!FILL_VIEWS.includes(view)) return
  try { globalThis.localStorage?.setItem(KEY, view) } catch { /* Private mode or blocked storage. */ }
}
