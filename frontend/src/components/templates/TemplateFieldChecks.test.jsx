import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import TemplateFieldChecks from './TemplateFieldChecks'

afterEach(cleanup)

const fill = { name: 'email', message: "'Email' would fill with the client's email because of its name." }
const warning = { name: 'text3', message: "'Text3' does not say what goes in this field." }

describe('TemplateFieldChecks', () => {
  it('renders nothing for a clean template', () => {
    const { container } = render(<TemplateFieldChecks quality={{ accidental_fills: [], warnings: [] }} format="pdf" />)
    expect(container).toBeEmptyDOMElement()
    render(<TemplateFieldChecks quality={null} format="pdf" />)
    expect(screen.queryByLabelText('Field checks')).not.toBeInTheDocument()
  })

  it('says a PDF cannot publish while a field would fill the client by name', () => {
    render(<TemplateFieldChecks quality={{ accidental_fills: [fill], warnings: [warning, { ...warning, name: 'text4' }] }} format="PDF" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Publishing is blocked: 1 field would fill')
    expect(screen.getByText(fill.message)).toBeInTheDocument()
    expect(screen.getByText('2 field labels need attention')).toBeInTheDocument()
  })

  it('only informs for a Word template, which is not gated', () => {
    render(<TemplateFieldChecks quality={{ accidental_fills: [fill, { ...fill, name: 'phone' }], warnings: [warning] }} format="docx" />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText("2 fields will fill with the client's details by name")).toBeInTheDocument()
    expect(screen.getByText('1 field label needs attention')).toBeInTheDocument()
  })
})
