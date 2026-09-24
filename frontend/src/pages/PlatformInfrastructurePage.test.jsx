import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import axios from 'axios'
import * as api from '../api'
import PlatformInfrastructurePage, { InfrastructureStatus } from './PlatformInfrastructurePage'

vi.mock('axios')
vi.mock('../api', () => ({ createPlatformSession: vi.fn() }))

afterEach(cleanup)

test('authenticates and renders fenced DR status', async () => {
  api.createPlatformSession.mockResolvedValue({ access_token: 'session-token' })
  axios.get.mockResolvedValue({ data: {
    status: 'healthy', checked_at: '2026-08-28T00:00:00Z', alerts: [],
    services: [{ id: 'dr', label: 'Skynet DR', role: 'disaster-recovery', status: 'healthy', checked_at: '2026-08-28T00:00:00Z', writer_enabled: false, detail: 'Health probe passed' }],
  } })
  render(<PlatformInfrastructurePage />)
  await userEvent.type(screen.getByLabelText(/bootstrap secret/i), 'operator-secret')
  await userEvent.click(screen.getByRole('button', { name: /open status/i }))
  expect(await screen.findByText('Skynet DR')).toBeInTheDocument()
  expect(screen.getByText('Writer: fenced')).toBeInTheDocument()
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/api/platform/infrastructure', expect.objectContaining({ headers: { Authorization: 'Bearer session-token' } })))
})

const forbidden = (detail) => ({ response: { status: 403, data: { detail } } })

test('returns to sign-in when the platform token expires (403, not 401)', async () => {
  axios.get.mockRejectedValue(forbidden('Invalid or expired platform token'))
  const onSessionEnded = vi.fn()
  render(<InfrastructureStatus token="session-token" onSessionEnded={onSessionEnded} />)

  await waitFor(() => expect(onSessionEnded).toHaveBeenCalled())
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('keeps the session when only the refresh fails', async () => {
  axios.get.mockRejectedValue({ response: { status: 502 } })
  const onSessionEnded = vi.fn()
  render(<InfrastructureStatus token="session-token" onSessionEnded={onSessionEnded} />)

  expect(await screen.findByRole('alert')).toHaveTextContent('could not be refreshed')
  expect(onSessionEnded).not.toHaveBeenCalled()
})
