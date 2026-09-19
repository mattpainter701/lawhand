import { triggerBlobDownload } from '../../api'

// Helpers shared by the Generate dialog, the Prepare route and the
// templates page. Kept free of React so hooks and tests can import them.
export const getErrorMessage = (err, fallback) => (
  err?.response?.data?.detail || err?.message || fallback
)

export const getTemplateVariables = (template) => {
  const matches = template?.body?.match(/\{\{(.+?)\}\}/g) || []
  const schemaFields = template?.variable_schema?.fields || []
  const excludedNames = new Set(schemaFields
    .filter((field) => field?.included === false)
    .map((field) => field?.name)
    .filter(Boolean))
  const bodyNames = matches
    .map((m) => m.slice(2, -2).trim())
    .filter((name) => name && !excludedNames.has(name))
  const schemaNames = schemaFields
    .filter((field) => field?.included !== false)
    .map((field) => field?.name)
    .filter(Boolean)
  return [...new Set([...bodyNames, ...schemaNames])]
}

export const friendlyVariableLabel = (name) => name
  .replace(/[_-]+/g, ' ')
  .replace(/\b\w/g, (c) => c.toUpperCase())

export const formatMatterLabel = (matter) => {
  if (!matter) return ''
  const name = matter.matter_name || matter.title || matter.name || 'Untitled matter'
  return [name, matter.client_name, matter.practice_area, matter.status].filter(Boolean).join(' - ')
}

export const downloadRenderedText = (rendered, title) => {
  const filename = `${String(title || 'generated-document').replace(/[^a-z0-9._-]+/gi, '_')}.md`
  triggerBlobDownload(new Blob([String(rendered || '')], { type: 'text/markdown;charset=utf-8' }), filename)
}

