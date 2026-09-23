// Shared helpers for shot definitions.

// The union of the bounding boxes of one or more locators, padded, so a shot
// can crop to "this heading through that table" without fixed coordinates.
export async function regionAround(page, targets, { pad = 16, maxHeight } = {}) {
  const boxes = []
  for (const target of targets) {
    const locator = typeof target === 'function' ? target(page) : page.locator(target)
    const box = await locator.first().boundingBox()
    if (!box) throw new Error(`Crop target not visible: ${target}`)
    boxes.push(box)
  }
  const viewport = page.viewportSize()
  const x = Math.max(0, Math.min(...boxes.map((box) => box.x)) - pad)
  const y = Math.max(0, Math.min(...boxes.map((box) => box.y)) - pad)
  const right = Math.min(viewport.width, Math.max(...boxes.map((box) => box.x + box.width)) + pad)
  const bottom = Math.min(viewport.height, Math.max(...boxes.map((box) => box.y + box.height)) + pad)
  const height = maxHeight ? Math.min(bottom - y, maxHeight) : bottom - y
  return { x, y, width: right - x, height }
}
