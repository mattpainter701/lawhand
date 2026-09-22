import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'
import TemplateStudioWorkspace from './TemplateStudioWorkspace'
vi.mock('./TemplateStudioEditor', () => ({ default: ({ onDirtyChange }) => <><button onClick={() => onDirtyChange(true)}>Change field</button><button onClick={() => onDirtyChange(false)}>Save changes</button></> }))
vi.mock('./TemplateCopyAction', () => ({ default: () => <button>Create variation</button> }))
afterEach(cleanup)
function Location() { return <output aria-label="Location">{useLocation().pathname}</output> }
it('focuses the document and protects unsaved fields before switching Studio sections', () => {
  render(<MemoryRouter initialEntries={['/templates/one/studio']}><TemplateStudioWorkspace template={{ id: 'one', title: 'Example', format: 'markdown' }} onDerived={vi.fn()} /><Location /></MemoryRouter>)
  const shell = screen.getByRole('heading', { name: 'Example' }).closest('.studio-shell')
  expect(shell).toHaveAttribute('data-focused', 'true')
  fireEvent.click(screen.getByText('Show app navigation'))
  expect(shell).toHaveAttribute('data-focused', 'false')
  fireEvent.click(screen.getByText('Change field'))
  expect(screen.getByText('Template settings')).toBeDisabled()
  expect(screen.getByText('Preview draft')).toBeDisabled()
  expect(screen.queryByText('Create variation')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('link', { name: 'Test' }))
  expect(screen.getByLabelText('Location')).toHaveTextContent('/templates/one/studio')
  expect(screen.getByRole('alert')).toHaveTextContent('Save your field changes')
  fireEvent.click(screen.getByText('Save changes'))
  fireEvent.click(screen.getByRole('link', { name: 'Test' }))
  expect(screen.getByLabelText('Location')).toHaveTextContent('/templates/one/studio/test')
})

it('offers Use on a matter for a published template and explains why a draft cannot', () => {
  const onUseOnMatter = vi.fn()
  const { unmount } = render(<MemoryRouter initialEntries={['/templates/one/studio']}><TemplateStudioWorkspace template={{ id: 'one', title: 'Draft', format: 'markdown', is_active: false }} onUseOnMatter={onUseOnMatter} /></MemoryRouter>)
  const draftButton = screen.getByRole('button', { name: 'Use on a matter' })
  expect(draftButton).toBeDisabled()
  expect(draftButton).toHaveAttribute('title', 'Publish a tested version first.')
  unmount()
  render(<MemoryRouter initialEntries={['/templates/two/studio']}><TemplateStudioWorkspace template={{ id: 'two', title: 'Live', format: 'markdown', is_active: true, current_version_no: 1, published_version_no: 1 }} onUseOnMatter={onUseOnMatter} /></MemoryRouter>)
  fireEvent.click(screen.getByRole('button', { name: 'Use on a matter' }))
  expect(onUseOnMatter).toHaveBeenCalledTimes(1)
})

it('does not offer Use on a matter when the page gives it no destination', () => {
  render(<MemoryRouter initialEntries={['/templates/one/studio']}><TemplateStudioWorkspace template={{ id: 'one', title: 'Live', format: 'markdown', is_active: true }} /></MemoryRouter>)
  expect(screen.queryByRole('button', { name: 'Use on a matter' })).not.toBeInTheDocument()
})
