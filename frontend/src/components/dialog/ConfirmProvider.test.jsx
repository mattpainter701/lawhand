import { useState } from 'react'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { ConfirmProvider, useConfirm } from './ConfirmProvider'

function Harness() {
  const confirm = useConfirm()
  const [result, setResult] = useState('pending')
  return <><button onClick={async () => setResult(String(await confirm({ title: 'Delete record?', message: 'This is permanent.', destructive: true })))}>Open</button><output>{result}</output></>
}

  afterEach(() => cleanup())

describe('ConfirmProvider', () => {
  it('requires an explicit branded dialog decision', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><Harness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getByRole('alertdialog', { name: 'Delete record?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByText('false')).toBeInTheDocument()
  })
})

  it('traps focus, closes on Escape, and restores the trigger', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><Harness /></ConfirmProvider>)
    const trigger = screen.getByRole('button', { name: 'Open' })

    await user.click(trigger)
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    const confirmButton = screen.getByRole('button', { name: 'Confirm' })
    expect(cancel).toHaveFocus()

    await user.tab({ shift: true })
    expect(confirmButton).toHaveFocus()
    await user.tab()
    expect(cancel).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

function TypedHarness() {
  const confirm = useConfirm()
  const [result, setResult] = useState('pending')
  return <><button onClick={async () => setResult(String(await confirm({
    title: 'Disconnect Google for the whole firm?',
    message: 'Everyone loses access.',
    details: ['Document saves stop.', 'Personal connections are removed.'],
    requireText: 'disconnect Google',
    confirmLabel: 'Disconnect Google',
    destructive: true,
  })))}>Open typed</button><output>{result}</output></>
}

describe('ConfirmProvider typed confirmation', () => {
  it('lists the consequences and enables Confirm only after the phrase is typed', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><TypedHarness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open typed' }))

    const dialog = screen.getByRole('alertdialog', { name: 'Disconnect Google for the whole firm?' })
    expect(screen.getByTestId('confirm-details')).toHaveTextContent('Document saves stop.')
    const phrase = screen.getByLabelText(/Type disconnect Google to confirm/)
    const confirmButton = screen.getByRole('button', { name: 'Disconnect Google' })
    // The field has focus so the person can start typing straight away.
    expect(phrase).toHaveFocus()
    expect(confirmButton).toBeDisabled()

    // Enter does nothing until the phrase matches.
    await user.type(phrase, 'disconnect Gogle{Enter}')
    expect(dialog).toBeInTheDocument()
    expect(confirmButton).toBeDisabled()

    await user.clear(phrase)
    await user.type(phrase, '  Disconnect google  ')
    expect(confirmButton).toBeEnabled()
    await user.click(confirmButton)
    expect(screen.getByText('true')).toBeInTheDocument()
  })

  it('clears the typed phrase between requests', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><TypedHarness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open typed' }))
    await user.type(screen.getByLabelText(/to confirm/), 'disconnect google')
    await user.keyboard('{Escape}')
    expect(screen.getByText('false')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Open typed' }))
    expect(screen.getByLabelText(/to confirm/)).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Disconnect Google' })).toBeDisabled()
  })
})

function OptionsHarness({ options }) {
  const confirm = useConfirm()
  const [result, setResult] = useState('pending')
  return <><button onClick={async () => setResult(String(await confirm(options)))}>Ask</button><output>{result}</output></>
}

describe('ConfirmProvider typed confirmation keyboard', () => {
  it('confirms with Enter once the phrase matches and closes the dialog', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><TypedHarness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open typed' }))

    await user.type(screen.getByLabelText(/to confirm/), '  DISCONNECT GOOGLE {Enter}')

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('true')
  })

  it('leaves the request open on Enter with a wrong phrase and on other keys with the right one', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><TypedHarness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open typed' }))
    const phrase = screen.getByLabelText(/to confirm/)

    await user.type(phrase, 'disconnect Gogle{Enter}')
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('pending')

    await user.clear(phrase)
    await user.type(phrase, 'disconnect google{ArrowLeft}{Home}{Shift}{Control}')
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(phrase).toHaveValue('disconnect google')
    expect(screen.getByRole('status')).toHaveTextContent('pending')

    await user.keyboard('{Enter}')
    expect(screen.getByRole('status')).toHaveTextContent('true')
  })

  it.each([
    ['disconnectgoogle'],
    ['disconnect  google'],
    ['disconnect google!'],
    ['disconnect'],
  ])('keeps Confirm disabled for the near miss %j', async (attempt) => {
    const user = userEvent.setup()
    render(<ConfirmProvider><TypedHarness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open typed' }))

    await user.type(screen.getByLabelText(/to confirm/), `${attempt}{Enter}`)

    expect(screen.getByRole('button', { name: 'Disconnect Google' })).toBeDisabled()
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('pending')
  })

  it('cancels with Escape even after the phrase matches', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><TypedHarness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open typed' }))
    await user.type(screen.getByLabelText(/to confirm/), 'disconnect google')
    expect(screen.getByRole('button', { name: 'Disconnect Google' })).toBeEnabled()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('false')
  })

  it('starts the next request with an empty field after a confirmed one', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><TypedHarness /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Open typed' }))
    await user.type(screen.getByLabelText(/to confirm/), 'disconnect google{Enter}')
    expect(screen.getByRole('status')).toHaveTextContent('true')

    await user.click(screen.getByRole('button', { name: 'Open typed' }))
    const phrase = screen.getByLabelText(/to confirm/)
    expect(phrase).toHaveValue('')
    expect(phrase).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Disconnect Google' })).toBeDisabled()
  })
})

describe('ConfirmProvider options', () => {
  it('renders every consequence as its own list item and drops empty entries', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><OptionsHarness options={{
      title: 'Remove storage root?',
      message: 'Matters stop saving here.',
      details: ['Uploads pause.', '', null, 'Links stay valid.'],
    }} /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    const items = within(screen.getByTestId('confirm-details')).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual(['Uploads pause.', 'Links stay valid.'])
    expect(screen.getByRole('alertdialog')).toHaveAccessibleDescription('Matters stop saving here. Uploads pause. Links stay valid.')
  })

  it('omits the consequence list when there are no details', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><OptionsHarness options={{ title: 'Archive?', message: 'It can be restored.', details: 'not a list' }} /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(screen.getByText('It can be restored.')).toBeInTheDocument()
    expect(screen.queryByTestId('confirm-details')).not.toBeInTheDocument()
  })

  it('treats a blank phrase as an ordinary confirmation with Cancel focused', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><OptionsHarness options={{ title: 'Send now?', requireText: '   ', confirmLabel: 'Send' }} /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
    const send = screen.getByRole('button', { name: 'Send' })
    expect(send).toBeEnabled()
    await user.click(send)
    expect(screen.getByRole('status')).toHaveTextContent('true')
  })

  it('asks for the trimmed phrase and accepts it', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><OptionsHarness options={{ title: 'Purge?', requireText: '  purge all  ', confirmLabel: 'Purge' }} /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    const phrase = screen.getByRole('textbox', { name: 'Type purge all to confirm' })
    expect(phrase).toHaveFocus()
    await user.type(phrase, 'purge all')
    await user.click(screen.getByRole('button', { name: 'Purge' }))
    expect(screen.getByRole('status')).toHaveTextContent('true')
  })

  it('accepts a bare message string with the default title and label', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><OptionsHarness options="Discard the draft?" /></ConfirmProvider>)
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(screen.getByRole('alertdialog', { name: 'Confirm action' })).toHaveAccessibleDescription('Discard the draft?')
    expect(screen.queryByTestId('confirm-details')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(screen.getByRole('status')).toHaveTextContent('true')
  })
})
