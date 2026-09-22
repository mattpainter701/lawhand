// Keep Studio's field catalogue aligned with the renderer for legacy
// Markdown templates whose body contains placeholders but whose schema is
// empty. Explicit schema entries win, including an excluded entry.
export function extractTemplateVariables(body) {
  const variables = []
  const seen = new Set()
  const pattern = /\{\{\s*([^{}]+?)\s*\}\}/g
  for (const match of String(body || '').matchAll(pattern)) {
    const name = match[1].trim()
    if (!name || name.startsWith('#') || name.startsWith('/')) continue
    if (!seen.has(name)) { seen.add(name); variables.push(name) }
  }
  return variables
}

export function schemaFields(template) {
  const raw = template?.variable_schema?.fields
  const fields = Array.isArray(raw) ? [...raw] : []
  const known = new Set(fields.map(field => String(field?.name || '').trim()).filter(Boolean))
  for (const name of extractTemplateVariables(template?.body)) {
    if (!known.has(name)) fields.push({ name, label: name, required: true, field_type: 'text' })
  }
  return fields
}
