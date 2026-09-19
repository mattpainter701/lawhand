import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import PrepareStepper, { prepareSteps } from './PrepareStepper'

afterEach(cleanup)

const template = { id: 't', title: 'Fee agreement' }
const progress = { completed: 3, total: 5 }

describe('prepare steps', () => {
  it('walks from template to save, one current step at a time', () => {
    const states = (args) => prepareSteps(args).map((s) => s.state)
    expect(states({ template: null })).toEqual(['current', 'todo', 'todo', 'todo', 'todo'])
    expect(states({ template, matterId: '' })).toEqual(['done', 'current', 'todo', 'todo', 'todo'])
    expect(states({ template, matterId: 'm', progress, requiredMissing: 1 })).toEqual(['done', 'done', 'current', 'todo', 'todo'])
    expect(states({ template, matterId: 'm', progress, requiredMissing: 0 })).toEqual(['done', 'done', 'done', 'current', 'todo'])
    expect(states({ template, matterId: 'm', progress, requiredMissing: 0, previewReady: true })).toEqual(['done', 'done', 'done', 'done', 'current'])
    expect(states({ template, matterId: 'm', progress, requiredMissing: 0, previewReady: true, saved: true })).toEqual(['done', 'done', 'done', 'done', 'done'])
  })

  it('shows the fill counts the progress bar shows, from the same numbers', () => {
    render(<PrepareStepper steps={prepareSteps({ template, matterId: 'm', progress, requiredMissing: 2 })} />)
    const nav = screen.getByRole('navigation', { name: 'Prepare steps' })
    expect(nav).toHaveTextContent('3 of 5 filled, 2 required missing')
    expect(screen.getByText('3. Populate').closest('li')).toHaveAttribute('aria-current', 'step')
  })
})
