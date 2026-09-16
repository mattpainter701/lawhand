// Why a generated document has no signing placements, as the server recorded
// it at generation time.
//
// The block itself is not new; being told only "review signing positions" was.
// When the document is a Word file there is no review to open at all, because
// the placement canvas renders with pdf.js, so the UI has to offer the one
// action that works instead of a button that cannot help.

export const NO_PDF_OUTPUT = 'no_pdf_output'

const problemsOf = (document) => {
  const problems = document?.signing_placement_problems
  return Array.isArray(problems) ? problems.filter(Boolean) : []
}

export const placementReviewPossible = (document) => !problemsOf(document)
  .some((problem) => problem?.code === NO_PDF_OUTPUT)

export const placementProblemLines = (document) => problemsOf(document)
  .map((problem) => [problem?.detail, problem?.remedy]
    .map((part) => String(part || '').trim())
    .filter(Boolean)
    .join('. '))
  .filter(Boolean)
  // A page-level fault repeats once per field it stopped; say it once.
  .filter((line, index, lines) => lines.indexOf(line) === index)

export const placementBlocked = (document) => Boolean(
  document?.signing_placement_required
  && !(document?.positioned_fields || []).length,
)

// Documents generated before the server recorded reasons carry none, so the
// generic instruction stays as the fallback rather than an empty alert.
export const placementBlockMessage = (document) => {
  const lines = placementProblemLines(document)
  return lines.length
    ? lines.join(' ')
    : 'Review signing positions on the final PDF and add the required fields before sending.'
}
