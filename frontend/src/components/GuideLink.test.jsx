import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import GuideLink from './GuideLink'

describe('GuideLink', () => {
  afterEach(cleanup)

  it('links a panel to the user guide section that explains it', () => {
    render(
      <MemoryRouter>
        <GuideLink chapter="time-billing-and-reports" anchor="record-matter-expenses">How expenses work</GuideLink>
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'How expenses work' }))
      .toHaveAttribute('href', '/guide/time-billing-and-reports#record-matter-expenses')
  })

  it('opens administrator chapters inside Administration', () => {
    render(
      <MemoryRouter>
        <GuideLink audience="admin" chapter="email-intake" variant="pill" />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Guide' }))
      .toHaveAttribute('href', '/admin?tab=guide&chapter=email-intake')
  })

  it('still renders a working link when a panel is shown without a router', () => {
    render(<GuideLink chapter="email-intake">How email tasks work</GuideLink>)
    expect(screen.getByRole('link', { name: 'How email tasks work' }))
      .toHaveAttribute('href', '/guide/email-intake')
  })
})
