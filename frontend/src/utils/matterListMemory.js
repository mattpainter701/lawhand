// The matter portfolio is the hub people move between all day. Remembering its
// last URL and scroll offset lets the "Matter Portfolio" control on a matter
// return the reader to the same scope, filters, sort and row instead of a
// reset list.
//
// sessionStorage, not localStorage: this is per-tab working state, and a
// partner's filtered view must not leak into the next tab on a shared machine.
const LAST_URL_KEY = 'matters:list:last-url'
const scrollKey = (url) => `matters:list:scroll:${url}`

function storage() {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

// Only the list itself is a valid return target. A detail URL also starts with
// '/matters', so accept exactly the bare list path or its query form.
function isListPath(value) {
  return value === '/matters' || value.startsWith('/matters?')
}

export function rememberListUrl(url) {
  const store = storage()
  if (!store || typeof url !== 'string' || !isListPath(url)) return
  try {
    store.setItem(LAST_URL_KEY, url)
  } catch {
    // Quota or a denied storage policy is not worth interrupting the list for.
  }
}

export function readRememberedListUrl() {
  const store = storage()
  if (!store) return ''
  try {
    const value = store.getItem(LAST_URL_KEY) || ''
    return isListPath(value) ? value : ''
  } catch {
    return ''
  }
}

export function rememberListScroll(url, top) {
  const store = storage()
  if (!store || typeof url !== 'string' || !Number.isFinite(top)) return
  try {
    store.setItem(scrollKey(url), String(Math.max(0, Math.round(top))))
  } catch {
    // Same: best-effort working state.
  }
}

export function readListScroll(url) {
  const store = storage()
  if (!store || typeof url !== 'string') return null
  try {
    const raw = store.getItem(scrollKey(url))
    if (raw == null) return null
    const value = Number(raw)
    return Number.isFinite(value) ? value : null
  } catch {
    return null
  }
}
