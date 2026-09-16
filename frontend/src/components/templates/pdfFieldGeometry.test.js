import { describe, expect, it } from 'vitest'

import {
  canvasToOverlayRect,
  createManualField,
  firstPageFor,
  overlayToCanvasRect,
  placementsFor,
} from './pdfFieldGeometry'

// This module's header says the surfaces that place fields on a document must
// agree byte-for-byte on how a canvas rectangle becomes a stored rect. The
// contract used to be asserted through the intake editor, which was one of
// those surfaces; it is asserted here now that there is only one left.
describe('the coordinate contract', () => {
  it('converts PDF bottom-left rectangles to canvas top-left coordinates and back', () => {
    const page = { width: 612, height: 792 }
    const canvas = overlayToCanvasRect({ rect: [72, 600, 220, 624] }, page)
    expect(canvas).toEqual({ x: 72, y: 168, width: 148, height: 24 })
    expect(canvasToOverlayRect(canvas, page)).toEqual([72, 600, 220, 624])
  })

  it('scales both ways together, so a round trip at any zoom is lossless', () => {
    const page = { width: 612, height: 792 }
    const rect = [72, 600, 220, 624]
    for (const zoom of [0.5, 0.9, 1, 2.5]) {
      const canvas = overlayToCanvasRect({ rect }, page, null, zoom)
      expect(canvasToOverlayRect(canvas, page, null, zoom)).toEqual(rect)
    }
  })

  it('prefers a pdf.js viewport over a scale, because it carries page rotation', () => {
    const viewport = {
      convertToViewportRectangle: () => [10, 20, 110, 60],
      convertToPdfPoint: (x, y) => [x, y],
    }
    const canvas = overlayToCanvasRect({ rect: [0, 0, 1, 1] }, { height: 792 }, viewport, 99)
    expect(canvas).toEqual({ x: 10, y: 20, width: 100, height: 40 })
  })
})

describe('a manually placed field', () => {
  const page = { width: 612, height: 792 }

  it('stores a paragraph as text that wraps, which is what the renderer reads', () => {
    const field = createManualField('multiline', { page, pageNumber: 1, fields: [] })
    expect(field.field_type).toBe('text')
    expect(field.multiline).toBe(true)
  })

  it('lands inside the page it was placed on', () => {
    const field = createManualField('text', { page, pageNumber: 2, fields: [] })
    const [left, bottom, right, top] = field.pdf_overlay.rect
    expect(left).toBeGreaterThanOrEqual(0)
    expect(right).toBeLessThanOrEqual(page.width)
    expect(bottom).toBeGreaterThanOrEqual(0)
    expect(top).toBeLessThanOrEqual(page.height)
    expect(field.pdf_overlay.page).toBe(2)
  })

  it('takes a name nothing else on the template is using', () => {
    const existing = createManualField('text', { page, pageNumber: 1, fields: [] })
    const next = createManualField('text', { page, pageNumber: 1, fields: [existing] })
    expect(next.name).not.toBe(existing.name)
  })
})

describe('where a field sits', () => {
  it('reports every placement of a field repeated across pages', () => {
    const field = {
      name: 'client_name',
      pdf_overlays: [
        { page: 1, rect: [72, 600, 220, 624] },
        { page: 2, rect: [80, 500, 240, 524] },
      ],
    }
    expect(placementsFor(field)).toHaveLength(2)
    expect(firstPageFor(field)).toBe(1)
  })

  it('reads a single-placement field written the older way', () => {
    const field = { name: 'a', page: 3, pdf_overlay: { page: 3, rect: [1, 2, 3, 4] } }
    expect(placementsFor(field)).toHaveLength(1)
    expect(firstPageFor(field)).toBe(3)
  })
})
