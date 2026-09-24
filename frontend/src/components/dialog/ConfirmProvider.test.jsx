import { useState } from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
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
