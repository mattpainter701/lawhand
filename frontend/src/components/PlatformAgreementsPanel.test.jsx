import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PlatformAgreementsPanel, { TERMS_DEFAULTS } from './PlatformAgreementsPanel'
import { getPlatformAgreementDefinitions, publishPlatformAgreementDefinition } from '../api'

vi.mock('../api', () => ({
  getPlatformAgreementDefinitions: vi.fn(),
  publishPlatformAgreementDefinition: vi.fn(),
}))

afterEach(cleanup)
afterEach(() => vi.unstubAllGlobals())

describe('PlatformAgreementsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPlatformAgreementDefinitions.mockResolvedValue({ agreements: [] })
    global.fetch = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new TextEncoder().encode('terms-v1').buffer })
    vi.stubGlobal('crypto', { subtle: { digest: vi.fn().mockResolvedValue(new Uint8Array(32).buffer) } })
  })

  it('loads current Terms and pre-fills immutable metadata and hash', async () => {
    const user = userEvent.setup()
    render(<PlatformAgreementsPanel platformKey="key" />)
    await user.click(await screen.findByRole('button', { name: /load current LawHand Terms/i }))
    expect(await screen.findByText(TERMS_DEFAULTS.title)).toBeInTheDocument()
    expect(screen.getByText(TERMS_DEFAULTS.version)).toBeInTheDocument()
    expect(screen.getByText('00'.repeat(32))).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/terms', { cache: 'no-store' })
  })

  it('lists immutable definitions', async () => {
    getPlatformAgreementDefinitions.mockResolvedValueOnce({ agreements: [{ id: 'a1', title: 'Existing Terms', version: '1', content_hash: 'ab'.repeat(32) }] })
    render(<PlatformAgreementsPanel platformKey="key" />)
    expect(await screen.findByText('Existing Terms')).toBeInTheDocument()
  })

  it('reports list failures', async () => {
    getPlatformAgreementDefinitions.mockRejectedValueOnce(new Error('offline'))
    render(<PlatformAgreementsPanel platformKey="key" />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/offline/i)
  })

  it('requires counsel approval before publishing', async () => {
    const user = userEvent.setup()
    render(<PlatformAgreementsPanel platformKey="key" />)
    await user.click(await screen.findByRole('button', { name: /load current LawHand Terms/i }))
    const publish = screen.getByRole('button', { name: /re-fetch, verify, and publish/i })
    expect(publish).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /counsel approved/i }))
    publishPlatformAgreementDefinition.mockResolvedValueOnce({ id: 'published' })
    await user.click(publish)
    await vi.waitFor(() => expect(publishPlatformAgreementDefinition).toHaveBeenCalledWith('key', expect.objectContaining({ kind: 'terms_of_use', required_for_onboarding: true })))
    expect(await screen.findByRole('status')).toHaveTextContent(/Terms published/i)
  })

  it('aborts publishing when the served Terms bytes change', async () => {
    const user = userEvent.setup()
    global.fetch.mockResolvedValueOnce({ ok: true, arrayBuffer: async () => new TextEncoder().encode('v1').buffer }).mockResolvedValueOnce({ ok: true, arrayBuffer: async () => new TextEncoder().encode('v2').buffer })
    global.crypto.subtle.digest.mockResolvedValueOnce(new Uint8Array(32).buffer).mockResolvedValueOnce(new Uint8Array(32).fill(1).buffer)
    render(<PlatformAgreementsPanel platformKey="key" />)
    await user.click(await screen.findByRole('button', { name: /load current LawHand Terms/i }))
    await user.click(screen.getByRole('checkbox', { name: /counsel approved/i }))
    await user.click(screen.getByRole('button', { name: /re-fetch, verify, and publish/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/changed since it was loaded/i)
    expect(publishPlatformAgreementDefinition).not.toHaveBeenCalled()
  })

  it('surfaces API publish errors', async () => {
    const user = userEvent.setup()
    publishPlatformAgreementDefinition.mockRejectedValueOnce({ response: { data: { detail: 'duplicate version' } } })
    render(<PlatformAgreementsPanel platformKey="key" />)
    await user.click(await screen.findByRole('button', { name: /load current LawHand Terms/i }))
    await user.click(screen.getByRole('checkbox', { name: /counsel approved/i }))
    await user.click(screen.getByRole('button', { name: /re-fetch, verify, and publish/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/duplicate version/i)
  })
})
