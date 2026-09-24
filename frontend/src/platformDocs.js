const userGuideModules = import.meta.glob('../platform_docs/user-guide/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
})

const administrativeGuideModules = import.meta.glob('../platform_docs/administrative-guide/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
})

const REQUIRED_FIELDS = ['slug', 'title', 'description', 'order', 'read_time', 'icon']

export function parseGuideChapter(source, sourcePath, audience) {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/)
  if (!match) throw new Error(`Guide chapter is missing front matter: ${sourcePath}`)

  const metadata = {}
  for (const line of match[1].split(/\r?\n/)) {
    const separator = line.indexOf(':')
    if (separator === -1) continue
    metadata[line.slice(0, separator).trim()] = line.slice(separator + 1).trim()
  }

  for (const field of REQUIRED_FIELDS) {
    if (!metadata[field]) throw new Error(`Guide chapter ${sourcePath} is missing ${field}`)
  }

  const content = source.slice(match[0].length).trim()
  const headings = Array.from(content.matchAll(/^##\s+(.+)$/gm), ([, title]) => ({
    title: plainHeadingText(title),
    id: slugifyHeading(title),
  }))
  const anchors = Array.from(content.matchAll(/^#{2,3}\s+(.+)$/gm), ([, title]) => slugifyHeading(title))

  return {
    ...metadata,
    audience,
    order: Number(metadata.order),
    content,
    headings,
    anchors,
    sourcePath,
    searchText: `${metadata.title} ${metadata.description} ${content}`.toLocaleLowerCase(),
  }
}

// Heading text as a reader sees it: inline links keep their label and
// Markdown emphasis/code markers are dropped.
function plainHeadingText(value) {
  return String(value || '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`]/g, '')
    .trim()
}

export function slugifyHeading(value) {
  const text = Array.isArray(value) ? value.join(' ') : String(value || '')
  return plainHeadingText(text)
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

const CALLOUT_MARKER = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\r?\n)?/i

function walkTree(node, visit) {
  visit(node)
  if (Array.isArray(node.children)) node.children.forEach((child) => walkTree(child, visit))
}

// Turns GitHub-style alert blockquotes (`> [!TIP]`) into tagged callouts that
// the guide renderer styles as Note, Tip, Important, Warning, or Caution.
export function remarkGuideCallouts() {
  return (tree) => {
    walkTree(tree, (node) => {
      if (node.type !== 'blockquote') return
      const paragraph = node.children?.[0]
      const first = paragraph?.type === 'paragraph' ? paragraph.children?.[0] : null
      if (first?.type !== 'text') return
      const marker = first.value.match(CALLOUT_MARKER)
      if (!marker) return
      first.value = first.value.slice(marker[0].length)
      if (!first.value) paragraph.children.shift()
      if (!paragraph.children.length) node.children.shift()
      node.data = {
        ...node.data,
        hProperties: { ...(node.data?.hProperties || {}), dataCallout: marker[1].toLowerCase() },
      }
    })
  }
}

function buildGuide(modules, audience) {
  return Object.entries(modules)
    .map(([sourcePath, source]) => parseGuideChapter(source, sourcePath, audience))
    .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))
}

export const USER_GUIDE = buildGuide(userGuideModules, 'user')
export const ADMINISTRATIVE_GUIDE = buildGuide(administrativeGuideModules, 'admin')
