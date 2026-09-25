import { getMyMattersPage } from '../api'

// A picker that links to any assigned matter (Conflict Checks) needs the whole
// assigned set, not page 1. Page through /matters/my/page until the server
// total is reached, with a page cap so one account with thousands of
// assignments cannot stall the screen. `complete` is false when the cap cut
// the list short, so the caller can say it is showing part of the set.
//
// A failed page rejects instead of resolving to an empty list: "no matters"
// and "could not load your matters" must read differently.
export const MY_MATTERS_PICKER_PAGE_SIZE = 200
export const MY_MATTERS_PICKER_MAX_PAGES = 10

export async function loadAllMyMatters({
  pageSize = MY_MATTERS_PICKER_PAGE_SIZE,
  maxPages = MY_MATTERS_PICKER_MAX_PAGES,
} = {}) {
  const items = []
  const seen = new Set()
  let total = null
  for (let page = 1; page <= maxPages; page += 1) {
    const data = await getMyMattersPage({ page, page_size: pageSize })
    if (!Array.isArray(data?.items)) throw new Error('Missing assigned-matter results')
    if (Number.isInteger(data.total)) total = data.total
    for (const matter of data.items) {
      if (seen.has(matter.id)) continue
      seen.add(matter.id)
      items.push(matter)
    }
    const done = data.items.length < pageSize || (total !== null && items.length >= total)
    if (done) return { items, total: total ?? items.length, complete: true }
  }
  return { items, total: total ?? items.length, complete: total !== null && items.length >= total }
}
