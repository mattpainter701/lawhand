import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
}))

vi.mock('axios', () => ({
  default: { create: vi.fn(() => apiClient), post: vi.fn() },
}))

import { disconnectCloudProvider } from './api'

describe('disconnectCloudProvider', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('posts to the Google disconnect route with no body and returns the response data', async () => {
    apiClient.post.mockResolvedValueOnce({ data: { status: 'disconnected', provider: 'google' } })

    expect(await disconnectCloudProvider('google')).toEqual({ status: 'disconnected', provider: 'google' })
    expect(apiClient.post).toHaveBeenCalledOnce()
    expect(apiClient.post).toHaveBeenCalledWith('/integrations/google/disconnect')
    expect(apiClient.get).not.toHaveBeenCalled()
    expect(apiClient.delete).not.toHaveBeenCalled()
  })

  it('posts to the Microsoft disconnect route', async () => {
    apiClient.post.mockResolvedValueOnce({ data: { status: 'disconnected', provider: 'microsoft' } })

    expect(await disconnectCloudProvider('microsoft')).toEqual({ status: 'disconnected', provider: 'microsoft' })
    expect(apiClient.post).toHaveBeenCalledWith('/integrations/microsoft/disconnect')
  })

  it('never builds the route from the raw argument', async () => {
    apiClient.post.mockResolvedValue({ data: {} })

    await disconnectCloudProvider('../admin/users')

    expect(apiClient.post).toHaveBeenCalledWith('/integrations/microsoft/disconnect')
    expect(apiClient.post.mock.calls[0][0]).not.toContain('admin')
  })

  it('passes a failed request through to the caller', async () => {
    const failure = Object.assign(new Error('Request failed with status code 403'), { response: { status: 403 } })
    apiClient.post.mockRejectedValueOnce(failure)

    await expect(disconnectCloudProvider('google')).rejects.toBe(failure)
  })
})
