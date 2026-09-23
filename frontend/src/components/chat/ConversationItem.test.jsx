import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ConversationItem from './ConversationItem'

const conv = { id: 'conversation-1', title: 'Lease research' }

function renderItem(activity, handlers = {}) {
  return render(
    <ConversationItem
      conv={conv}
      index={0}
      isActive={false}
      isPinned={false}
      activity={activity}
      onClick={handlers.onClick || vi.fn()}
      onDelete={handlers.onDelete || vi.fn()}
      onTogglePin={handlers.onTogglePin || vi.fn()}
    />,
  )
}

describe('conversation rail activity', () => {
  afterEach(cleanup)

  it('shows a thread that is still answering, with its queued follow-ups', () => {
    renderItem({ responding: true, queued: 2, paused: false })
    expect(screen.getByTitle('Responding')).toHaveTextContent('Responding')
    expect(screen.getByTitle('2 queued')).toHaveTextContent('+2 queued')
  })

  it('marks a reply that finished while the thread was not open', () => {
    renderItem({ responding: false, replyReady: true, queued: 0 })
    expect(screen.getByTitle('New reply')).toHaveTextContent('New reply')
  })

  it('marks a failed answer and a queue held behind it', () => {
    const { rerender } = renderItem({ failed: true, queued: 0 })
    expect(screen.getByTitle('Response failed')).toBeInTheDocument()

    rerender(
      <ConversationItem
        conv={conv}
        index={0}
        isActive={false}
        isPinned={false}
        activity={{ failed: true, paused: true, queued: 1 }}
        onClick={vi.fn()}
        onDelete={vi.fn()}
        onTogglePin={vi.fn()}
      />,
    )
    expect(screen.getByText('Held')).toBeInTheDocument()
    expect(screen.queryByTitle('1 queued')).not.toBeInTheDocument()
  })

  it('stays quiet for an idle thread and keeps its actions reachable', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    const onDelete = vi.fn()
    renderItem({ responding: false, replyReady: false, failed: false, queued: 0, paused: false }, { onClick, onDelete })

    expect(screen.queryByTitle(/Responding|New reply|Response failed/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Lease research' }))
    expect(onClick).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Delete Lease research' }))
    expect(onDelete).toHaveBeenCalledWith('conversation-1')
  })
})
