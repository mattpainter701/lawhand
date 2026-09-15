import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PrepareFormWorkspace, { canvasToOverlayRect, overlayToCanvasRect } from './PrepareFormWorkspace'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('PrepareFormWorkspace', () => {
  it('converts PDF bottom-left rectangles to canvas top-left coordinates and back', () => {
    const page = { width: 612, height: 792 }
    const canvas = overlayToCanvasRect({ rect: [72, 600, 220, 624] }, page)
    expect(canvas).toEqual({ x: 72, y: 168, width: 148, height: 24 })
    expect(canvasToOverlayRect(canvas, page)).toEqual([72, 600, 220, 624])
  })

  it('creates a manual field and exposes editable properties and inclusion', () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:source')
    const onFieldsChange = vi.fn()
    render(<PrepareFormWorkspace file={new File(['image'], 'form.png', { type: 'image/png' })} analysis={{ suggested_variable_schema: { pages: [{ page: 1, width: 612, height: 792 }] } }} fields={[]} onFieldsChange={onFieldsChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'text', exact: true }))
    const created = onFieldsChange.mock.calls[0][0][0]
    expect(created.name).toMatch(/^field_/)
    expect(created.pdf_source_key).toMatch(/^manual:/)
    expect(created.pdf_overlay.source_kind).toBe('manual')
    expect(created.included).toBe(true)
  })

  it('stores paragraph fields as supported text overlays with multiline behavior', () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:source')
    const onFieldsChange = vi.fn()
    render(<PrepareFormWorkspace file={new File(['image'], 'form.png', { type: 'image/png' })} analysis={{ suggested_variable_schema: { pages: [{ page: 1, width: 612, height: 792 }] } }} fields={[]} onFieldsChange={onFieldsChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'multiline' }))

    expect(onFieldsChange.mock.calls[0][0][0]).toEqual(expect.objectContaining({
      field_type: 'text',
      multiline: true,
    }))
  })

  it('shows every repeated placement on its page and asks for review on OCR-only analysis', () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:source')
    const field = {
      name: 'client_name',
      label: 'Client name',
      pdf_source_key: 'overlay:client-name',
      confidence: 0.7,
      pdf_overlays: [
        { page: 1, rect: [72, 600, 220, 624], source_kind: 'ocr' },
        { page: 2, rect: [80, 500, 240, 524], source_kind: 'ocr' },
      ],
    }
    const onReviewConfirmed = vi.fn()
    render(<PrepareFormWorkspace file={new File(['image'], 'form.png', { type: 'image/png' })} analysis={{ suggested_variable_schema: { detection: { method: 'ocr' }, pages: [{ page: 1, width: 612, height: 792 }, { page: 2, width: 612, height: 792 }] } }} fields={[field]} onFieldsChange={vi.fn()} onReviewConfirmed={onReviewConfirmed} />)

    expect(screen.getByRole('button', { name: 'Select Client name' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(screen.getByRole('button', { name: 'Select Client name' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Confirm source comparison' }))
    expect(onReviewConfirmed).toHaveBeenCalledWith(true)
  })

  it('updates inclusion through the property inspector', () => {
    const field = { name: 'client_name', label: 'Client name', page: 1, included: true, pdf_overlay: { page: 1, rect: [72, 600, 220, 624], source_kind: 'ocr', erase_source: false }, pdf_overlays: [{ page: 1, rect: [72, 600, 220, 624], source_kind: 'ocr', erase_source: false }], confidence: 0.5, review_required: true }
    const onFieldsChange = vi.fn()
    render(<PrepareFormWorkspace file={new File(['image'], 'form.png', { type: 'image/png' })} analysis={{ suggested_variable_schema: { pages: [{ page: 1, width: 612, height: 792 }] } }} fields={[field]} onFieldsChange={onFieldsChange} />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include in template' }))
    expect(onFieldsChange.mock.calls.at(-1)[0][0].included).toBe(false)
  })

  it('locks Required when the source PDF asserts it, except on a checkbox', () => {
    // The server ORs a source-required field with the submitted value, so
    // unticking this for a text field silently reverted. Checkboxes are the
    // exception the server honours, so theirs stays editable.
    // The workspace selects the first field on mount, so each case leads.
    const base = { page: 1, included: true, pdf_field_name: 'f', confidence: 1 }
    const requiredText = { ...base, name: 'must_type', label: 'Must type', field_type: 'text', required: true, source_required: true }
    const requiredCheckbox = { ...base, name: 'opt_in', label: 'Opt in', field_type: 'checkbox', required: true, source_required: true }
    const plainText = { ...base, name: 'free_text', label: 'Free text', field_type: 'text', required: false, source_required: false }
    const props = {
      file: new File(['image'], 'form.png', { type: 'image/png' }),
      analysis: { suggested_variable_schema: { pages: [{ page: 1, width: 612, height: 792 }] } },
    }

    const onFieldsChange = vi.fn()
    const { unmount } = render(<PrepareFormWorkspace {...props} fields={[requiredText]} onFieldsChange={onFieldsChange} />)
    expect(screen.getByRole('checkbox', { name: /Required/ })).toBeDisabled()
    expect(screen.getByText(/cannot be made optional here/)).toBeInTheDocument()
    unmount()

    render(<PrepareFormWorkspace {...props} fields={[requiredCheckbox]} onFieldsChange={onFieldsChange} />)
    const checkboxRequired = screen.getByRole('checkbox', { name: /Required/ })
    expect(checkboxRequired).not.toBeDisabled()
    fireEvent.click(checkboxRequired)
    expect(onFieldsChange.mock.calls.at(-1)[0][0].required).toBe(false)
    cleanup()

    render(<PrepareFormWorkspace {...props} fields={[plainText]} onFieldsChange={onFieldsChange} />)
    expect(screen.getByRole('checkbox', { name: /Required/ })).not.toBeDisabled()
    expect(screen.queryByText(/cannot be made optional here/)).not.toBeInTheDocument()
  })

  it('keeps the same field selected while its automation key is renamed', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:source')
    const onFieldsChange = vi.fn()
    const fields = [
      { name: 'first_name', _bodyName: 'first_name', label: 'First field', pdf_overlay: { page: 1, rect: [40, 680, 180, 706], source_kind: 'text' } },
      { name: 'second_name', _bodyName: 'second_name', label: 'Second field', pdf_overlay: { page: 1, rect: [40, 630, 180, 656], source_kind: 'text' } },
    ]
    const props = {
      file: new File(['image'], 'form.png', { type: 'image/png' }),
      analysis: { suggested_variable_schema: { pages: [{ page: 1, width: 612, height: 792 }] } },
      onFieldsChange,
    }
    const { rerender } = render(<PrepareFormWorkspace {...props} fields={fields} />)
    fireEvent.click(screen.getByRole('button', { name: 'Select Second field' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Automation key' }), { target: { value: 'renamed_field' } })
    const updated = onFieldsChange.mock.calls.at(-1)[0]

    rerender(<PrepareFormWorkspace {...props} fields={updated} />)

    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Automation key' })).toHaveValue('renamed_field'))
    expect(screen.getByRole('textbox', { name: 'Label' })).toHaveValue('Second field')
  })

  // The upload flow is where a firm first sees its own form with every
  // discovered field highlighted. Until these controls existed it was also the
  // one screen that could not say where a field's value comes from, so every
  // template a firm without premium AI uploaded arrived with nothing bound.
  describe('fill source', () => {
    const catalogue = {
      cards: [{ key: 'client', label: 'Client', kind: 'person', group: 'Client', max_instances: 1, instance_count: null, fields: [{ key: 'full_name', label: 'Full name', path: 'client.full_name', value_kind: 'text' }] }],
      bindings: [{ path: 'client.name', label: 'Client name', group: 'Client' }],
      smartFillNames: ['client_name'],
      catalogueLoaded: true,
    }
    const analysis = { suggested_variable_schema: { pages: [{ page: 1, width: 612, height: 792 }] } }
    const fieldAt = (name, extra = {}) => ({
      name,
      label: name,
      pdf_source_key: `overlay:${name}`,
      confidence: 1,
      pdf_overlays: [{ page: 1, rect: [72, 600, 220, 624], source_kind: 'acroform' }],
      ...extra,
    })

    const renderWorkspace = (fields, props = {}) => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:source')
      return render(
        <PrepareFormWorkspace
          file={new File(['image'], 'form.png', { type: 'image/png' })}
          analysis={analysis}
          fields={fields}
          onFieldsChange={vi.fn()}
          catalogue={catalogue}
          {...props}
        />,
      )
    }

    it('binds the selected field to a data source', () => {
      const onFieldsChange = vi.fn()
      renderWorkspace([fieldAt('signer')], { onFieldsChange })

      fireEvent.click(screen.getByRole('button', { name: /Matched by field name/ }))
      fireEvent.click(screen.getByRole('button', { name: 'Client' }))
      fireEvent.click(screen.getByRole('button', { name: 'Full name' }))

      expect(onFieldsChange.mock.calls.at(-1)[0][0].binding).toBe('client.full_name')
    })

    it('counts how much of the form fills itself', () => {
      // One bound, one filling by name alone, one nobody can fill.
      renderWorkspace([
        fieldAt('signer', { binding: 'client.full_name' }),
        fieldAt('client_name'),
        fieldAt('injury_description'),
      ])

      expect(screen.getByRole('status')).toHaveTextContent('2 of 3 fill from the record')
    })

    it('says a name match will break on a rename, because nothing else does', () => {
      renderWorkspace([fieldAt('client_name')])

      expect(screen.getByText(/Rename it and the fill stops/)).toBeInTheDocument()
    })

    it('recolours the page by fill source only when asked', () => {
      renderWorkspace([fieldAt('client_name')])
      // Review status and fill source are different questions; the review
      // highlight is a compliance step and must not be overwritten by default.
      expect(screen.getByRole('button', { name: 'Select client_name' })).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Fill source' }))

      expect(screen.getByRole('button', { name: 'Select client_name — Fills by field name' })).toBeInTheDocument()
      expect(screen.getByText('Fills by field name 1')).toBeInTheDocument()
    })

    it('withholds the fill highlight until the catalogue has loaded', () => {
      // Every bound field would read as broken against an empty catalogue.
      renderWorkspace([fieldAt('client_name')], { catalogue: {} })

      expect(screen.getByRole('button', { name: 'Fill source' })).toBeDisabled()
      expect(screen.getByRole('status')).not.toHaveTextContent('fill from the record')
    })
  })

  it('requires opening the original when the PDF page preview fails', async () => {
    const onReviewConfirmed = vi.fn()
    const onSourceReviewReadyChange = vi.fn()
    render(
      <PrepareFormWorkspace
        file={new File(['not a valid PDF'], 'form.pdf', { type: 'application/pdf' })}
        previewUrl="blob:source"
        analysis={{ suggested_variable_schema: { detection: { method: 'ocr' }, pages: [{ page: 1, width: 612, height: 792 }] } }}
        fields={[]}
        onFieldsChange={vi.fn()}
        onReviewConfirmed={onReviewConfirmed}
        onSourceReviewReadyChange={onSourceReviewReadyChange}
      />,
    )

    const openOriginal = await screen.findByRole('link', { name: 'Open original in a new tab' })
    expect(screen.getByRole('checkbox', { name: 'Confirm source comparison' })).toBeDisabled()
    fireEvent.click(openOriginal)
    expect(screen.getByRole('checkbox', { name: 'Confirm source comparison' })).toBeEnabled()
    expect(onSourceReviewReadyChange).toHaveBeenLastCalledWith(true)
  })
})
