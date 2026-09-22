import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MatterPicker from './MatterPicker'
import { getMattersV2 } from '../../api'

vi.mock('../../api', () => ({ getMattersV2: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers() })

describe('choosing a source matter', () => {
  it('finds an older matter from the server and selects it without an internal ID', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const select = vi.fn()
    getMattersV2.mockResolvedValue({ items: [{ id: 'old', matter_name: 'Estate administration', matter_number: 'EST0001', client_name: 'Jordan Example' }] })
    render(<MatterPicker matters={[]} onSelect={select} />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Fill from a matter' }), { target: { value: 'Jordan' } })
    await vi.advanceTimersByTimeAsync(300)
    fireEvent.click(await screen.findByRole('button', { name: /Estate administration/ }))
    expect(getMattersV2).toHaveBeenCalledWith({ search: 'Jordan', page_size: 20, sort_by: 'updated_at', sort_dir: 'desc' })
    expect(select).toHaveBeenCalledWith('old')
  })

  it('ignores an older search response and explains a failed workspace search', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let oldResponse
    getMattersV2.mockImplementationOnce(() => new Promise(resolve => { oldResponse = resolve }))
      .mockRejectedValueOnce(new Error('Offline'))
    render(<MatterPicker matters={[]} onSelect={vi.fn()} />)
    const search = screen.getByRole('textbox', { name: 'Fill from a matter' })
    fireEvent.change(search, { target: { value: 'old' } })
    await vi.advanceTimersByTimeAsync(300)
    fireEvent.change(search, { target: { value: 'new' } })
    await vi.advanceTimersByTimeAsync(300)
    await screen.findByRole('alert')
    oldResponse({ items: [{ id: 'old', matter_name: 'Wrong stale result' }] })
    await waitFor(() => expect(screen.queryByText('Wrong stale result')).not.toBeInTheDocument())
  })
})
