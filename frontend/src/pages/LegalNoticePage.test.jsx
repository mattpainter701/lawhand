import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import LegalNoticePage, { termsContent } from './LegalNoticePage'

const EMAIL = 'support@getlawhand.com'

function renderNotice(type) {
  return render(
    <MemoryRouter initialEntries={['/' + type]}>
      <LegalNoticePage type={type} />
    </MemoryRouter>,
  )
}

describe('LegalNoticePage', () => {
  afterEach(() => cleanup())

  it('renders the substantive privacy policy with navigation and contact links', () => {
    renderNotice('privacy')
    expect(screen.getByRole('heading', { level: 1, name: 'Privacy Policy' })).toBeInTheDocument()
    expect(screen.getByText('Last updated September 13, 2026')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Information we handle' })).toBeInTheDocument()
    expect(screen.getByText(/model provider configured for that workspace/i)).toBeInTheDocument()
    expect(screen.getByText(/subscription agreement, data processing agreement, and privacy notices/i)).toBeInTheDocument()

    const toc = screen.getByRole('navigation', { name: 'Privacy Policy table of contents' })
    expect(within(toc).getByRole('link', { name: /Your organization’s role/ })).toHaveAttribute('href', '#organization-role')
    expect(within(toc).getByRole('link', { name: /Contact/ })).toHaveAttribute('href', '#contact')
    expect(screen.getByRole('link', { name: 'Terms of Use' })).toHaveAttribute('href', '/terms')
    expect(screen.getByRole('link', { name: EMAIL })).toHaveAttribute('href', 'mailto:' + EMAIL)
  })

  it('carries the Google Limited Use disclosure required for restricted scopes', () => {
    renderNotice('privacy')

    // Google looks for this statement close to verbatim. Keep the wording intact.
    expect(
      screen.getByText(/will adhere to the Google API Services User Data Policy, including the Limited Use requirements/i),
    ).toBeInTheDocument()

    // The policy must be referenced as a reachable link, not bare text.
    expect(
      screen.getByRole('link', { name: 'https://developers.google.com/terms/api-services-user-data-policy' }),
    ).toHaveAttribute('href', 'https://developers.google.com/terms/api-services-user-data-policy')
    expect(
      screen.getByRole('link', { name: 'https://myaccount.google.com/permissions' }),
    ).toHaveAttribute('href', 'https://myaccount.google.com/permissions')

    // Each restricted and sensitive scope needs a stated purpose.
    expect(screen.getByText(/Gmail read access/i)).toBeInTheDocument()
    expect(screen.getByText(/Google Drive read and write access/i)).toBeInTheDocument()
    expect(screen.getByText(/not used to develop, improve, or train generalized artificial intelligence/i)).toBeInTheDocument()
    expect(screen.getByText(/is not used for advertising, and it is not sold/i)).toBeInTheDocument()

    const toc = screen.getByRole('navigation', { name: 'Privacy Policy table of contents' })
    expect(within(toc).getByRole('link', { name: /Google user data and Limited Use/ })).toHaveAttribute('href', '#google-user-data')
  })

  it('does not put the Google disclosure on the terms notice', () => {
    renderNotice('terms')
    expect(screen.queryByText(/Limited Use requirements/i)).not.toBeInTheDocument()
  })

  it('renders the substantive terms with contract precedence and review guardrails', () => {
    renderNotice('terms')
    expect(screen.getByRole('heading', { level: 1, name: 'Terms of Use' })).toBeInTheDocument()
    expect(screen.getByText('Last updated July 27, 2026')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Organization agreements control' })).toBeInTheDocument()
    expect(screen.getByText(/Those organization-specific terms control if they conflict/i)).toBeInTheDocument()
    expect(screen.getByText(/does not create an attorney-client relationship/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Acceptable use' })).toBeInTheDocument()

    const toc = screen.getByRole('navigation', { name: 'Terms of Use table of contents' })
    expect(within(toc).getByRole('link', { name: /Professional responsibility/ })).toHaveAttribute('href', '#professional-responsibility')
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy')
    expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('heading', { level: 1, name: termsContent.title })).toBeInTheDocument()
    expect(screen.getByText(termsContent.intro)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: termsContent.sections[0][1] })).toBeInTheDocument()
  })
})
