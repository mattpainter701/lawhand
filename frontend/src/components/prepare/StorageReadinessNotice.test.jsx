import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { getStorageReadiness } from '../../api'
import StorageReadinessNotice from './StorageReadinessNotice'

vi.mock('../../api', () => ({ getStorageReadiness: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('warns about the chosen cloud connection and clears after repair and retry', async () => {
  getStorageReadiness.mockResolvedValueOnce({ ready: false, status: 'needs_reconnect', message: 'Reconnect Microsoft before saving.' }).mockResolvedValueOnce({ ready: true })
  render(<StorageReadinessNotice />)
  expect(await screen.findByText('Reconnect Microsoft before saving.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Check connection again' }))
  await waitFor(() => expect(screen.queryByText('Document storage needs attention')).not.toBeInTheDocument())
})

it('offers a retry if readiness cannot be checked', async () => {
  getStorageReadiness.mockRejectedValue(new Error('offline'))
  render(<StorageReadinessNotice />)
  expect(await screen.findByText('Storage check unavailable')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check connection again' })).toBeEnabled()
})

it('does not check a draft that cannot save to a matter', () => {
  render(<StorageReadinessNotice enabled={false} />)
  expect(getStorageReadiness).not.toHaveBeenCalled()
})
