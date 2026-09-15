import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Regression cover for #487: the tier and public-case-law preference used to
// live only in this component's state, so reopening a conversation silently
// reverted both to Standard with public case law on.

const apiMocks = vi.hoisted(() => ({
  getConversation: vi.fn(),
  streamMessage: vi.fn(),
  createConversation: vi.fn(),
  updateConversation: vi.fn(),
  uploadChatAttachment: vi.fn(),
  getMattersV2: vi.fn(),
  getLegalSourceHealth: vi.fn(),
}))

const shellHarness = vi.hoisted(() => ({ value: null }))
const authHarness = vi.hoisted(() => ({ value: null }))
const routerHarness = vi.hoisted(() => ({ query: 'conv=conversation-a', navigate: vi.fn() }))

vi.mock('../api', () => apiMocks)
vi.mock('../components/AppShell', () => ({ useAppShell: () => shellHarness.value }))
vi.mock('../App', () => ({ useAuth: () => authHarness.value }))
vi.mock('react-router-dom', () => ({
  useNavigate: () => routerHarness.navigate,
  useSearchParams: () => [new URLSearchParams(routerHarness.query)],
}))
// A stand-in for the settings popover: the toggles are what this page owns.
vi.mock('../components/ChatHeader', () => ({
  default: ({ usePremium, setUsePremium, includePublic, setIncludePublic, publicCaseLawAllowed }) => (
    <div>
      <span data-testid="tier">{usePremium ? 'premium' : 'standard'}</span>
      <span data-testid="public">{includePublic ? 'public-on' : 'public-off'}</span>
      <span data-testid="policy">{publicCaseLawAllowed ? 'allowed' : 'restricted'}</span>
      <button type="button" onClick={() => setUsePremium(true)}>Use premium</button>
      <button type="button" onClick={() => setIncludePublic((value) => !value)}>Toggle public</button>
    </div>
  ),
}))
vi.mock('../components/ChatInput', () => ({
  default: ({ inputValue, onInputChange, onSend }) => (
    <div>
      <textarea
        aria-label="Message the assistant"
        value={inputValue}
        onChange={(event) => onInputChange(event.target.value)}
      />
      <button type="button" onClick={onSend}>Send message</button>
    </div>
  ),
}))
vi.mock('../components/Messages', () => ({ default: () => <div data-testid="messages" /> }))
vi.mock('../components/chat/ChatRail', () => ({
  default: ({ onNewConversation }) => (
    <button type="button" onClick={onNewConversation}>New conversation</button>
  ),
}))

import { resetChatGenerations } from '../chatGenerations'
import ChatPage from './ChatPage'

const conversation = (overrides = {}) => ({
  conversation: {
    id: 'conversation-a',
    title: 'Conversation A',
    updated_at: '2099-01-01T00:00:00Z',
    use_premium_llm: false,
    include_public: true,
    public_case_law_restricted: false,
    ...overrides,
  },
  messages: [],
})

describe('ChatPage response settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetChatGenerations()
    authHarness.value = { user: { privacy_mode: false }, refreshUser: vi.fn() }
    routerHarness.query = 'conv=conversation-a'
    routerHarness.navigate.mockImplementation((target) => {
      routerHarness.query = String(target || '').split('?')[1] || ''
    })
    shellHarness.value = {
      conversations: [{ id: 'conversation-a', title: 'Conversation A' }],
      setConversations: vi.fn((update) => {
        shellHarness.value.conversations = typeof update === 'function'
          ? update(shellHarness.value.conversations)
          : update
      }),
      activeConvId: 'conversation-a',
      setActiveConvId: vi.fn((id) => { shellHarness.value.activeConvId = id }),
      onConversationDeleted: vi.fn(),
      documents: [],
      onDocumentUploaded: vi.fn(),
      onDocumentDeleted: vi.fn(),
    }
    apiMocks.getMattersV2.mockResolvedValue({ items: [] })
    apiMocks.getLegalSourceHealth.mockResolvedValue({
      available: false, status: 'unavailable', sources: [], partitions: [],
    })
    apiMocks.createConversation.mockResolvedValue({ id: 'conversation-new', title: 'New Conversation' })
    apiMocks.updateConversation.mockImplementation(async (id, data) => ({ id, ...data }))
  })

  afterEach(() => {
    cleanup()
    resetChatGenerations()
  })

  it('restores the tier and public-case-law choice stored on the conversation', async () => {
    apiMocks.getConversation.mockResolvedValue(
      conversation({ use_premium_llm: true, include_public: false }),
    )

    render(<ChatPage />)

    await waitFor(() => expect(screen.getByTestId('tier')).toHaveTextContent('premium'))
    expect(screen.getByTestId('public')).toHaveTextContent('public-off')
  })

  it('saves a changed setting to the conversation so the next open sees it', async () => {
    apiMocks.getConversation.mockResolvedValue(conversation())
    render(<ChatPage />)
    await waitFor(() => expect(apiMocks.getConversation).toHaveBeenCalled())

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Use premium' }))
    await user.click(screen.getByRole('button', { name: 'Toggle public' }))

    await waitFor(() => expect(apiMocks.updateConversation).toHaveBeenCalledWith(
      'conversation-a', { use_premium_llm: true },
    ))
    expect(apiMocks.updateConversation).toHaveBeenCalledWith(
      'conversation-a', { include_public: false },
    )
    expect(screen.getByTestId('tier')).toHaveTextContent('premium')
    expect(screen.getByTestId('public')).toHaveTextContent('public-off')
  })

  it('carries the current settings onto a conversation started from this page', async () => {
    apiMocks.getConversation.mockResolvedValue(conversation())
    render(<ChatPage />)
    await waitFor(() => expect(apiMocks.getConversation).toHaveBeenCalled())

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Use premium' }))
    // The rail renders twice (desktop column and mobile drawer).
    await user.click(screen.getAllByRole('button', { name: 'New conversation' })[0])

    await waitFor(() => expect(apiMocks.createConversation).toHaveBeenCalledWith({
      use_premium_llm: true,
      include_public: true,
    }))
  })

  it('reports the firm public-case-law policy to the settings popover', async () => {
    authHarness.value = {
      user: { privacy_mode: false, public_case_law_allowed: false },
      refreshUser: vi.fn(),
    }
    apiMocks.getConversation.mockResolvedValue(conversation())

    render(<ChatPage />)

    await waitFor(() => expect(screen.getByTestId('policy')).toHaveTextContent('restricted'))
  })
})
