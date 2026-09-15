import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { cwd } from 'node:process'
import { describe, expect, it } from 'vitest'

import {
  BOUND,
  MANUAL,
  NAME_MATCHED,
  SIGNATURE,
  UNBOUND,
  UNRESOLVED,
  cardFieldIndex,
  classifyField,
  coverageSummary,
  fillCoverage,
  normalizeVariableName,
} from './fillCoverage'

// The same fixture the Python implementation pins. Read rather than copied:
// two implementations of one rule are only trustworthy while a single shared
// input proves they still agree.
const CONTRACT_PATH = 'backend/tests/fixtures/fill_coverage_contract.json'

/** Walk up to the repository root, so this passes from `frontend` or from it. */
const contractFile = () => {
  const start = cwd()
  let directory = start
  for (;;) {
    const candidate = resolve(directory, CONTRACT_PATH)
    if (existsSync(candidate)) return candidate
    const parent = dirname(directory)
    if (parent === directory) throw new Error(`${CONTRACT_PATH} not found above ${start}`)
    directory = parent
  }
}

const CONTRACT = JSON.parse(readFileSync(contractFile(), 'utf8'))

const catalogue = {
  smartFillNames: CONTRACT.catalogue.smart_fill_names,
  bindings: CONTRACT.catalogue.binding_paths.map((path) => ({ path })),
  cards: CONTRACT.catalogue.cards,
}
const contractFields = CONTRACT.variable_schema.fields

describe('the split shared with the server', () => {
  it('matches the recorded expectation', () => {
    const coverage = fillCoverage(contractFields, catalogue)
    expect(coverage.total).toBe(CONTRACT.expected.total)
    expect(coverage.fills).toBe(CONTRACT.expected.fills)
    for (const [state, count] of Object.entries(CONTRACT.expected)) {
      if (state === 'total' || state === 'fills') continue
      expect({ [state]: coverage.counts[state] }).toEqual({ [state]: count })
    }
  })

  it('lands every field in the recorded state', () => {
    const { states } = fillCoverage(contractFields, catalogue)
    expect(Object.fromEntries(states)).toEqual(CONTRACT.expected_states)
  })

  it('accounts for every counted field', () => {
    const coverage = fillCoverage(contractFields, catalogue)
    const counted = Object.values(coverage.counts).reduce((sum, count) => sum + count, 0)
    expect(counted).toBe(coverage.total)
  })
})

describe('classifying one field', () => {
  const classify = (field) => classifyField(field, {
    names: new Set(['case_number', 'client_email']),
    paths: new Set(['matter.case_number', 'client.name']),
    cardFields: cardFieldIndex(CONTRACT.catalogue.cards),
  })

  it('never falls back to name matching once a binding is declared', () => {
    // Named after a resolvable alias and bound to a path the catalogue no
    // longer describes. Reading it as name-matched would show a firm a filled
    // field that renders blank.
    expect(classify({ name: 'case_number' })).toBe(NAME_MATCHED)
    expect(classify({ name: 'case_number', binding: 'matter.gone' })).toBe(UNRESOLVED)
  })

  it('lets manual suppress a name that would otherwise match', () => {
    expect(classify({ name: 'client_email' })).toBe(NAME_MATCHED)
    expect(classify({ name: 'client_email', binding: 'manual' })).toBe(MANUAL)
  })

  it('treats a signing field as signed whatever it is bound to', () => {
    expect(classify({ name: 'x', field_type: 'signature', binding: 'client.name' })).toBe(SIGNATURE)
    expect(classify({ name: 'x', field_type: 'initials' })).toBe(SIGNATURE)
  })

  it('treats a date as signed only when it carries a signer role', () => {
    expect(classify({ name: 'filed_on', field_type: 'date' })).toBe(UNBOUND)
    expect(classify({ name: 'filed_on', field_type: 'date', signer_role: 'client' })).toBe(SIGNATURE)
  })

  it('resolves a card path, which is what the card rail actually emits', () => {
    // Not in the flat catalogue. Judging bindings by that list alone would
    // mark most bound fields broken, because the card rail is the control an
    // author binds with.
    for (const path of CONTRACT.catalogue.card_paths) {
      expect({ path, state: classify({ name: 'who', binding: path }) })
        .toEqual({ path, state: BOUND })
    }
    // A card that exists does not make every path under it real.
    expect(classify({ name: 'who', binding: 'client.invented' })).toBe(UNRESOLVED)
    expect(classify({ name: 'who', binding: 'client.address.street' })).toBe(UNRESOLVED)
  })

  it('resolves item and custom bindings without a catalogue entry', () => {
    expect(classify({ name: 'x', binding: 'item.party_name' })).toBe(BOUND)
    expect(classify({ name: 'x', binding: 'custom.matter.11111111-2222-3333-4444-555555555555' })).toBe(BOUND)
    // A path shaped like a custom field but not one: never silently resolvable.
    expect(classify({ name: 'x', binding: 'custom.matter.not-a-uuid' })).toBe(UNRESOLVED)
  })

  it('reads the legacy field type key as well as the current one', () => {
    expect(classify({ name: 'x', type: 'signature' })).toBe(SIGNATURE)
  })
})

describe('what counts', () => {
  it('leaves out excluded fields and copies of other fields', () => {
    const coverage = fillCoverage([
      { name: 'kept' },
      { name: 'dropped', included: false },
      { name: 'kept_copy', value_from: 'kept' },
      { name: '' },
    ], catalogue)
    expect(coverage.total).toBe(1)
  })

  it('survives a schema with no fields at all', () => {
    expect(fillCoverage(undefined, catalogue).total).toBe(0)
    expect(fillCoverage([], catalogue).total).toBe(0)
  })
})

describe('normalising a field name', () => {
  it('folds case and punctuation the way the server does', () => {
    expect(normalizeVariableName('Client Name')).toBe('client_name')
    expect(normalizeVariableName('client-name!')).toBe('client_name')
    expect(normalizeVariableName('__Client__Name__')).toBe('client_name')
    expect(normalizeVariableName(undefined)).toBe('')
  })
})

describe('the read-out', () => {
  it('names only the states fields are actually in', () => {
    const summary = coverageSummary(fillCoverage([
      { name: 'case_number' },
      { name: 'narrative' },
    ], catalogue))
    expect(summary).toBe('1 of 2 fill from the record — 1 fills by field name, 1 no source')
    expect(summary).not.toContain('signed')
  })

  it('says so plainly when there is nothing to report', () => {
    expect(coverageSummary(fillCoverage([], catalogue))).toBe('No fields yet')
  })
})
