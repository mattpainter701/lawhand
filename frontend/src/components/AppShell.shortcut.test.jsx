import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AppShell, { isEditableShortcutTarget } from './AppShell'
import { createConversation } from '../api'

vi.mock('../App', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      role: 'user',
      full_name: 'Workspace User',
      enabled_modules: ['matters', 'chat'],
    },
    logout: vi.fn(),
  }),
}))

vi.mock('../api', () => ({
  getConversations: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn().mockResolvedValue({ id: 'conv-new' }),
  deleteConversation: vi.fn(),
  getDocuments: vi.fn().mockResolvedValue([]),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
  logout: vi.fn().mockResolvedValue(undefined),
  updateMe: vi.fn().mockResolvedValue({}),
}))

vi.mock('./dialog/ConfirmProvider', () => ({
  useConfirm: () => vi.fn(),
}))

vi.mock('./Sidebar', () => ({
  default: () => <nav aria-label="mock sidebar" />,
}))

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/tasks']}>
      <AppShell title="Tasks">
        <label>
          Probe
          <input aria-label="Probe input" />
        </label>
        <div role="dialog" aria-label="Probe dialog">
          <button type="button">ok</button>
        </div>
        <div role="alertdialog" aria-label="Confirmation">
          <button type="button">Confirm action</button>
        </div>
      </AppShell>
    </MemoryRouter>,
  )
}

describe('global new-conversation shortcut respects editing context (S1.10)', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('does not treat editable, dialog or non-element targets as shortcut targets', () => {
    expect(isEditableShortcutTarget({ tagName: 'INPUT' })).toBe(true)
    expect(isEditableShortcutTarget({ tagName: 'TEXTAREA' })).toBe(true)
    expect(isEditableShortcutTarget({ isContentEditable: true, tagName: 'DIV' })).toBe(true)
    expect(isEditableShortcutTarget({ tagName: 'BUTTON', closest: () => null })).toBe(false)
    expect(isEditableShortcutTarget(null)).toBe(false)
  })

  it('ignores the shortcut while a text field has focus', () => {
    renderShell()

    fireEvent.keyDown(screen.getByLabelText('Probe input'), { key: 'n', ctrlKey: true })

    expect(createConversation).not.toHaveBeenCalled()
  })

  it('ignores the shortcut inside a dialog', () => {
    renderShell()

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'n', ctrlKey: true })

    expect(createConversation).not.toHaveBeenCalled()
  })

  it.each([{ ctrlKey: true }, { metaKey: true }])('ignores the shortcut on confirmation controls (%j)', (modifier) => {
    renderShell()

    fireEvent.keyDown(screen.getByRole('button', { name: 'Confirm action' }), { key: 'n', ...modifier })

    expect(createConversation).not.toHaveBeenCalled()
  })

  it('ignores the shortcut during IME composition', () => {
    renderShell()

    const event = new KeyboardEvent('keydown', { key: 'n', ctrlKey: true, bubbles: true })
    Object.defineProperty(event, 'isComposing', { value: true })
    document.body.dispatchEvent(event)

    expect(createConversation).not.toHaveBeenCalled()
  })

  it('still opens a new conversation from ordinary workspace chrome', async () => {
    renderShell()

    fireEvent.keyDown(document.body, { key: 'n', ctrlKey: true })

    await waitFor(() => expect(createConversation).toHaveBeenCalledTimes(1))
  })
})
