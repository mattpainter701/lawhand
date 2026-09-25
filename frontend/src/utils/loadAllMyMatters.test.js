import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadAllMyMatters } from './loadAllMyMatters'
import { getMyMattersPage } from '../api'

vi.mock('../api', () => ({ getMyMattersPage: vi.fn() }))

const page = (ids, total) => ({ items: ids.map(id => ({ id })), total })

describe('loadAllMyMatters', () => {
  beforeEach(() => vi.clearAllMocks())

  it('pages until the server total is reached', async () => {
    getMyMattersPage.mockImplementation(({ page: n }) => Promise.resolve(
      n === 1 ? page(['a', 'b'], 3) : page(['c'], 3),
    ))

    const result = await loadAllMyMatters({ pageSize: 2 })

    expect(result).toEqual({ items: [{ id: 'a' }, { id: 'b' }, { id: 'c' }], total: 3, complete: true })
    expect(getMyMattersPage).toHaveBeenCalledTimes(2)
    expect(getMyMattersPage).toHaveBeenLastCalledWith({ page: 2, page_size: 2 })
  })

  it('stops on a short page and drops a repeated row', async () => {
    getMyMattersPage.mockImplementation(({ page: n }) => Promise.resolve(
      n === 1 ? page(['a', 'b']) : page(['b'])),
    )

    const result = await loadAllMyMatters({ pageSize: 2 })

    expect(result.items.map(m => m.id)).toEqual(['a', 'b'])
    expect(result.complete).toBe(true)
  })

  it('reports a partial set when the page cap is hit', async () => {
    getMyMattersPage.mockImplementation(({ page: n }) => Promise.resolve(page([`m${n}a`, `m${n}b`], 10)))

    const result = await loadAllMyMatters({ pageSize: 2, maxPages: 2 })

    expect(result.items).toHaveLength(4)
    expect(result.total).toBe(10)
    expect(result.complete).toBe(false)
  })

  it('rejects rather than returning an empty list when a page fails', async () => {
    getMyMattersPage.mockRejectedValueOnce(new Error('offline'))
    await expect(loadAllMyMatters()).rejects.toThrow('offline')

    getMyMattersPage.mockResolvedValueOnce({ detail: 'nope' })
    await expect(loadAllMyMatters()).rejects.toThrow('Missing assigned-matter results')
  })
})
