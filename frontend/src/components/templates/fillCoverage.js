/**
 * Where each template field's value comes from, and how much of a form fills.
 *
 * Both editors already answer "what is this field?" — how many were found, how
 * many need review. Neither answered "and where does its value come from?",
 * which is the number that decides whether a template is worth having: how many
 * boxes arrive filled when a matter is named, and how many someone retypes
 * every time.
 *
 * This runs on the client because the read-out has to respond to an author
 * renaming a field or picking a data source in a schema nobody has saved yet; a
 * number fetched from the server can only ever describe the last save. The rule
 * is not reinvented here: the server serves the vocabulary a name match is
 * judged against (`smart_fill_names` on /templates/bindings) and the catalogue
 * of paths a binding may resolve through, and the branch order below is
 * `build_variable_suggestions`'s own.
 *
 * The Python half is `backend/app/services/template_fill_coverage.py`. Both
 * pin `backend/tests/fixtures/fill_coverage_contract.json` to the same split,
 * so the two implementations cannot drift apart quietly.
 */

/** Fills from a record the matter carries. Survives a rename of the field. */
export const BOUND = 'bound'
/**
 * No binding declared, but the field's name is one Smart Fill can produce.
 * Reported apart from BOUND on purpose: it works today and stops working the
 * moment somebody renames the field, and an author currently has no way to see
 * they are relying on it.
 */
export const NAME_MATCHED = 'name_matched'
/** Declared "always typed by hand", on purpose. Correct for an SSN. */
export const MANUAL = 'manual'
/** Signed rather than filled, so no data source applies. */
export const SIGNATURE = 'signature'
/** Declares a path the catalogue cannot resolve — already broken, silently. */
export const UNRESOLVED = 'unresolved'
/** Nothing behind it. Someone types this on every matter. */
export const UNBOUND = 'unbound'

export const FILL_STATES = [BOUND, NAME_MATCHED, MANUAL, SIGNATURE, UNRESOLVED, UNBOUND]

/** The states that put a value on the page without anyone typing it. */
export const FILLING_STATES = [BOUND, NAME_MATCHED]

const MANUAL_BINDING = 'manual'
const ITEM_BINDING_PREFIX = 'item.'
const CUSTOM_BINDING_PATTERN = /^custom\.(matter|contact)\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const SIGNING_TYPES = ['signature', 'initials']

/** Reduce a field name to the key Smart Fill's candidate map is built on. */
export const normalizeVariableName = (value) => String(value ?? '')
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '_')
  .replace(/^_+|_+$/g, '')

/**
 * Whether this field is signed rather than filled.
 *
 * A dated signature block is a date field carrying a signer role; an ordinary
 * filled date has no role. Same rule as `isSigningField` in
 * `templateFillReview.js`, which already keeps signing fields out of the fill
 * review's "how much is filled" rows.
 */
export const isSigningField = (field) => {
  const fieldType = String(field?.field_type || field?.type || '').toLowerCase()
  if (SIGNING_TYPES.includes(fieldType)) return true
  return fieldType === 'date' && Boolean(String(field?.signer_role || '').trim())
}

const INSTANCE_SEGMENT = /^(?:\*|[1-9][0-9]*)$/

/**
 * Index the card catalogue as `card key -> field keys`.
 *
 * Card paths are a superset of the flat catalogue and are what the card rail
 * actually emits, so a binding set through the primary control — `client.
 * full_name`, `defendant.2.full_name` — appears in no flat catalogue at all.
 * Judging those by the flat list would mark most bound fields broken.
 */
export const cardFieldIndex = (cards = []) => {
  const index = new Map()
  for (const card of cards) {
    if (!card?.key) continue
    const keys = index.get(card.key) || new Set()
    for (const field of card.fields || []) {
      if (field?.key) keys.add(field.key)
    }
    index.set(card.key, keys)
  }
  return index
}

const matchesCardPath = (binding, cardFields) => {
  const segments = binding.split('.')
  const fields = cardFields.get(segments[0])
  if (!fields) return false
  if (segments.length === 2) return fields.has(segments[1])
  // `card.instance.field` — an instance is a positive integer, or `*` for
  // "every instance, joined". The server validates the instance against the
  // card's ceiling on save; here it only has to not be a path segment.
  if (segments.length === 3) return INSTANCE_SEGMENT.test(segments[1]) && fields.has(segments[2])
  return false
}

/**
 * Whether a declared binding resolves against a record.
 *
 * Item bindings resolve per repeating-section iteration and custom bindings
 * through the custom-field service, so both fill without appearing in either
 * catalogue. Anything else has to be a path the server still serves — a path it
 * no longer describes renders blank, and saying so is the point of UNRESOLVED.
 */
export const bindingIsResolvable = (binding, { paths, cardFields }) => {
  if (!binding || binding === MANUAL_BINDING) return false
  if (binding.startsWith(ITEM_BINDING_PREFIX)) return true
  if (CUSTOM_BINDING_PATTERN.test(binding)) return true
  if (paths.has(binding)) return true
  return matchesCardPath(binding, cardFields)
}

/**
 * Whether this field is one a matter has to supply a value for.
 *
 * Excluded fields are not in the template. A field that copies another ("use
 * the same value as") is not separately answered, and counting it would report
 * one answer twice.
 */
export const countsTowardCoverage = (field) => {
  if (field?.included === false) return false
  if (String(field?.value_from || '').trim()) return false
  return Boolean(String(field?.name || '').trim())
}

/**
 * The fill state of one field.
 *
 * A declared binding is authoritative and never falls back to name matching:
 * falling back is exactly the surprise bindings exist to remove.
 */
export const classifyField = (field, catalogue) => {
  if (isSigningField(field)) return SIGNATURE
  const binding = String(field?.binding || '').trim()
  if (binding === MANUAL_BINDING) return MANUAL
  if (binding) return bindingIsResolvable(binding, catalogue) ? BOUND : UNRESOLVED
  return catalogue.names.has(normalizeVariableName(field?.name)) ? NAME_MATCHED : UNBOUND
}

const emptyCounts = () => Object.fromEntries(FILL_STATES.map((state) => [state, 0]))

/**
 * Classify every field of a schema.
 *
 * `smartFillNames` and `bindings` come from /templates/bindings and `cards`
 * from /templates/cards. Until both land they are empty, and every bound field
 * would read as UNRESOLVED and every name match as UNBOUND — so callers must
 * not show this until the catalogue has loaded. `useBindingCatalogue` reports
 * that as `catalogueLoaded`.
 */
export function fillCoverage(fields = [], { smartFillNames = [], bindings = [], cards = [] } = {}) {
  const catalogue = {
    names: new Set(smartFillNames),
    paths: new Set(bindings.map((entry) => entry?.path).filter(Boolean)),
    cardFields: cardFieldIndex(cards),
  }
  const counts = emptyCounts()
  const states = new Map()
  for (const field of fields) {
    if (!countsTowardCoverage(field)) continue
    const state = classifyField(field, catalogue)
    states.set(field.name, state)
    counts[state] += 1
  }
  const total = states.size
  const fills = FILLING_STATES.reduce((sum, state) => sum + counts[state], 0)
  return { total, fills, counts, states }
}

/** Plain words for one fill state, for a legend or a field inspector. */
export const FILL_STATE_LABELS = {
  [BOUND]: 'Fills from the record',
  [NAME_MATCHED]: 'Fills by field name',
  [MANUAL]: 'Typed by hand',
  [SIGNATURE]: 'Signed',
  [UNRESOLVED]: 'Source unavailable',
  [UNBOUND]: 'No source',
}

/**
 * Canvas colours for the fill-source highlight.
 *
 * Deliberately not the review palette: the two highlights answer different
 * questions and are never shown at once. Green is the same "this is handled"
 * green the review highlight uses, teal separates the name match that works but
 * is fragile, and red is kept for the one state that is already broken.
 */
export const FILL_STATE_COLORS = {
  [BOUND]: '#16a34a',
  [NAME_MATCHED]: '#0d9488',
  [MANUAL]: '#7c3aed',
  [SIGNATURE]: '#2563eb',
  [UNRESOLVED]: '#dc2626',
  [UNBOUND]: '#94a3b8',
}

/**
 * The one-line read-out, next to the existing "N fields · N need review".
 *
 * States nobody is in are left out: a form with no signature blocks should not
 * carry a "0 signed" that an author has to read past to find the number that
 * matters.
 */
export function coverageSummary(coverage) {
  if (!coverage.total) return 'No fields yet'
  const parts = FILL_STATES
    .filter((state) => coverage.counts[state] > 0)
    .map((state) => `${coverage.counts[state]} ${FILL_STATE_LABELS[state].toLowerCase()}`)
  return `${coverage.fills} of ${coverage.total} fill from the record — ${parts.join(', ')}`
}

/**
 * What this state means for this field, in the field inspector.
 *
 * Shared so both editors say the same thing about the same field. The
 * name-match sentence is the one that earns its place: it is the only state
 * that works now and stops working on a rename, and an author cannot otherwise
 * tell they are standing on it.
 */
export function fillStateHelp(field, state) {
  const binding = String(field?.binding || '').trim()
  if (state === BOUND && binding.startsWith('firm.')) {
    return 'Uses the shared firm profile in every matter.'
  }
  return {
    [BOUND]: 'Uses the selected data source, whatever this field is named.',
    [NAME_MATCHED]: 'Filled only because this field\u2019s name matches a known record. Rename it and the fill stops \u2014 choose a data source to make it permanent.',
    [MANUAL]: 'Never filled automatically.',
    [SIGNATURE]: 'Signed when the document is sent, so no data source applies.',
    [UNRESOLVED]: 'This names a data source that is no longer available. It renders blank until you choose another.',
    [UNBOUND]: 'Nothing fills this. Someone types it on every matter.',
  }[state] || ''
}
