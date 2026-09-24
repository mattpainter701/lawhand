import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GuideViewer from './GuideViewer'
import { ADMINISTRATIVE_GUIDE, USER_GUIDE, parseGuideChapter } from '../platformDocs'

function chapter(slug, title, body, order = 1) {
  return parseGuideChapter(
    `---\nslug: ${slug}\ntitle: ${title}\ndescription: About ${title}\norder: ${order}\nread_time: 2 min\nicon: compass\n---\n# ${title}\n\n${body}`,
    `${slug}.md`,
    'user',
  )
}

describe('GuideViewer', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('searches across chapter content and opens the result', () => {
    render(
      <MemoryRouter>
        <GuideViewer documents={USER_GUIDE} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Start here' })).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search this guide' }), {
      target: { value: 'specialized practice workflows' },
    })
    const chapterNavigation = within(screen.getByLabelText('Guide chapters'))
    expect(chapterNavigation.getByRole('button', { name: /Assistant & add-ons/ })).toBeInTheDocument()
    expect(chapterNavigation.queryByRole('button', { name: /Matters & documents/ })).not.toBeInTheDocument()
    fireEvent.click(chapterNavigation.getByRole('button', { name: /Assistant & add-ons/ }))
    expect(screen.getByRole('heading', { name: 'Assistant & add-ons' })).toBeInTheDocument()
  })

  it('renders admin deep links as application links', () => {
    render(
      <MemoryRouter>
        <GuideViewer documents={ADMINISTRATIVE_GUIDE} audience="admin" />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/admin?tab=users')
    expect(screen.getByLabelText('Administrative guide')).toBeInTheDocument()
  })

  it('opens the chapter named in the address and reports chapter changes', () => {
    const onSelect = vi.fn()
    render(
      <MemoryRouter>
        <GuideViewer documents={ADMINISTRATIVE_GUIDE} audience="admin" embedded activeSlug="support-and-escalation" onSelect={onSelect} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 2, name: 'Support and escalation' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByLabelText('Guide chapters')).getByRole('button', { name: /Firm email intake/ }))
    expect(onSelect).toHaveBeenCalledWith('email-intake', undefined)
  })

  it('scrolls a deep link to its section', async () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    const documents = [chapter('sample', 'Sample', '## First step\n\nText.\n\n### Fine detail\n\nMore.')]
    render(
      <MemoryRouter initialEntries={['/guide/sample#fine-detail']}>
        <GuideViewer documents={documents} activeSlug="sample" />
      </MemoryRouter>,
    )
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled())
    expect(scrollIntoView.mock.contexts[0]).toHaveAttribute('id', 'fine-detail')
    delete Element.prototype.scrollIntoView
  })

  it('renders callouts, screenshots, and links to the screens a chapter documents', () => {
    const documents = [chapter(
      'matters-and-documents',
      'Matters',
      '## Steps\n\n> [!TIP]\n> Save the contact once.\n\n> [!WARNING] Rejecting cannot be undone.\n\n> A plain quotation.\n\n![The matter list with the Board toggle](/guide-assets/example.webp "Matter list")',
    )]
    render(
      <MemoryRouter>
        <GuideViewer documents={documents} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('note', { name: 'Tip' })).toHaveTextContent('Save the contact once.')
    expect(screen.getByRole('note', { name: 'Warning' })).toHaveTextContent('Rejecting cannot be undone.')
    expect(screen.getByText('A plain quotation.').closest('blockquote')).not.toBeNull()

    const image = screen.getByRole('img', { name: 'The matter list with the Board toggle' })
    expect(image.closest('p')).toBeNull()
    expect(image.closest('figure')).toHaveTextContent('Matter list')
    expect(screen.getByRole('link', { name: 'Open full-size image: The matter list with the Board toggle' }))
      .toHaveAttribute('href', '/guide-assets/example.webp')

    const screens = within(screen.getByRole('navigation', { name: 'Open in LawHand' }))
    expect(screens.getByRole('link', { name: 'My Matters' })).toHaveAttribute('href', '/matters')
    expect(screens.getByRole('link', { name: 'Firm Memory' })).toHaveAttribute('href', '/firm-memory')
    expect(screens.queryByRole('link', { name: 'Research Workspace' })).toBeNull()
  })
})
