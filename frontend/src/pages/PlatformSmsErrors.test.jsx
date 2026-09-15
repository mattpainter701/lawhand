// Issue #506: "the 400s return no useful error to the UI — the toast/page
// shows nothing actionable". The API now returns a structured detail
// ({message, code, provider_code}); these pin that the operator actually reads
// the message rather than being left with a bare status in the console.
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PlatformSmsTab } from './PlatformPage'
import {
  getPlatformSmsProvider,
  sendPlatformSmsTest,
  updatePlatformSmsProvider,
} from '../api'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal()),
  getPlatformSmsProvider: vi.fn(),
  updatePlatformSmsProvider: vi.fn(),
  deletePlatformSmsProvider: vi.fn(),
  sendPlatformSmsTest: vi.fn(),
}))

const UNCONFIGURED = {
  provider: 'twilio',
  configured: false,
  account_sid: null,
  auth_token_configured: false,
  sender_ready: false,
  is_active: false,
}

/** An axios rejection carrying the API's structured detail. */
const apiError = (status, detail) => ({
  response: { status, data: { detail } },
  message: `Request failed with status code ${status}`,
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

async function renderTab() {
  getPlatformSmsProvider.mockResolvedValue(UNCONFIGURED)
  render(<PlatformSmsTab platformKey="platform-key" onAuthError={vi.fn()} />)
  await waitFor(() => expect(getPlatformSmsProvider).toHaveBeenCalled())
}

/** Send test is disabled until a destination is entered. */
async function sendTest(user) {
  await user.type(screen.getByLabelText(/destination/i), '+17015273866')
  await user.click(screen.getByRole('button', { name: /send test/i }))
}

describe('platform SMS sender errors reach the operator', () => {
  it('shows why a save was refused instead of leaving a bare 400', async () => {
    const user = userEvent.setup()
    await renderTab()
    updatePlatformSmsProvider.mockRejectedValue(
      apiError(400, {
        message:
          'The Messaging Service SID must start with MG. You entered a Verify Service SID. Copy the Messaging Service SID from the Twilio console.',
        code: 'platform_sms_invalid_messaging_service_sid',
      }),
    )

    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(await screen.findByText(/must start with MG/)).toBeInTheDocument()
    expect(screen.getByText(/Verify Service SID/)).toBeInTheDocument()
  })

  it("shows Twilio's own words when Twilio rejects a test send", async () => {
    const user = userEvent.setup()
    await renderTab()
    sendPlatformSmsTest.mockRejectedValue(
      apiError(400, {
        message: "The 'From' number +15551234567 is not a valid phone number",
        code: 'platform_sms_provider_rejected',
        provider_code: 21606,
        provider_status: 400,
      }),
    )

    await sendTest(user)

    expect(
      await screen.findByText(/is not a valid phone number/),
    ).toBeInTheDocument()
  })

  it('still says something when the API sends only a plain string', async () => {
    const user = userEvent.setup()
    await renderTab()
    sendPlatformSmsTest.mockRejectedValue(apiError(503, 'The shared SMS sender is not configured.'))

    await sendTest(user)

    expect(await screen.findByText(/not configured/)).toBeInTheDocument()
  })

  it('falls back to a readable message when there is no detail at all', async () => {
    const user = userEvent.setup()
    await renderTab()
    // What a proxy-generated 502 looks like from the client: an HTML body
    // with no detail field. The operator must still see something.
    sendPlatformSmsTest.mockRejectedValue({
      response: { status: 502, data: '<html>gateway</html>' },
      message: 'Request failed with status code 502',
    })

    await sendTest(user)

    expect(await screen.findByText(/502|Failed to send test message/)).toBeInTheDocument()
  })
})
