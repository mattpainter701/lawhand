import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, ChevronDown, ChevronRight, Download, Eye, LibraryBig, Loader2, Search } from 'lucide-react'
import { getSampleTemplates, getSampleTemplateSource } from '../../api'
import SampleFillDialog from './SampleFillDialog'
import PdfPreviewDialog from './PdfPreviewDialog'

// The catalog API returns an unordered flat list. Present samples grouped by
// document type, with the paperwork every matter opens with first, the
// catch-all "other" last, and within each type ordered by jurisdiction then
// title so a firm can find its state's form quickly.
const CATEGORY_ORDER = [
  'engagement_letter',
  'intake',
  'advance_directive',
  'bill_of_sale',
  'contract',
  'court_form',
  'lease',
  'power_of_attorney',
  'will',
  'other',
]

const CATEGORY_LABELS = {
  engagement_letter: 'Fee Agreement',
  intake: 'Client Intake',
  advance_directive: 'Advance Directive',
  bill_of_sale: 'Bill of Sale',
  contract: 'Contract',
  court_form: 'Court Form',
  lease: 'Lease',
  power_of_attorney: 'Power of Attorney',
  will: 'Will',
  other: 'Other',
}

const categoryLabel = (category) => (
  CATEGORY_LABELS[category] || String(category || 'other').replace(/_/g, ' ')
)

const categoryRank = (category) => {
  const index = CATEGORY_ORDER.indexOf(category)
  return index === -1 ? CATEGORY_ORDER.length : index
}

const jurisdictionLabel = (sample) => {
  const list = sample.jurisdictions || []
  return list.length ? list.join(', ') : 'General'
}

const asText = (value) => (Array.isArray(value) ? value.join(', ') : value || '')

// What the import source said about this form. Nothing is inferred: a form
// whose source recorded no edition shows no edition.
const provenanceLabel = (sample) => {
  const provenance = sample.provenance || {}
  return [asText(provenance.source_name), asText(provenance.edition)]
    .filter(Boolean)
    .join(' · ')
}

// Four titles repeat across the catalog and the files behind them are
// genuinely different, so a title alone does not identify a form. Show the
// differences that exist rather than inventing a label that would read as
// authoritative on the page where a form is picked for filing.
const buildVariantIndex = (samples) => {
  const byTitle = new Map()
  samples.forEach((sample) => {
    const key = String(sample.title || '').trim().toLowerCase()
    if (!key) return
    if (!byTitle.has(key)) byTitle.set(key, [])
    byTitle.get(key).push(sample)
  })
  const index = new Map()
  byTitle.forEach((group) => {
    if (group.length < 2) return
    // Ordered by field count so "9 fields" and "91 fields" read as a series
    // rather than an arbitrary pair.
    const ordered = [...group].sort(
      (a, b) => (a.field_count || 0) - (b.field_count || 0)
        || String(a.slug || '').localeCompare(String(b.slug || '')),
    )
    ordered.forEach((sample, position) => {
      index.set(sample.id, { position: position + 1, total: ordered.length })
    })
  })
  return index
}

// Shared, platform-owned sample forms available to every tenant. The catalog is
// read-only: users can preview the source PDF or fill it ad hoc, but samples
// never become tenant templates and never appear in the firm library queues.
export default function SampleLibraryCard() {
  const [samples, setSamples] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [category, setCategory] = useState('all')
  const [jurisdiction, setJurisdiction] = useState('all')
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(() => new Set())
  const [preview, setPreview] = useState(null)
  const [filling, setFilling] = useState(null)
  const previewRequest = useRef(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      previewRequest.current += 1
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getSampleTemplates()
      setSamples(data.items || [])
    } catch {
      setError('The sample library could not be loaded. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const categories = useMemo(
    () => [...new Set(samples.map((sample) => sample.category).filter(Boolean))].sort(),
    [samples],
  )
  const jurisdictions = useMemo(
    () => [...new Set(samples.flatMap((sample) => sample.jurisdictions || []))].sort(),
    [samples],
  )

  const normalizedQuery = query.trim().toLowerCase()
  const searching = normalizedQuery.length > 0
  const visible = useMemo(() => samples.filter((sample) => {
    if (category !== 'all' && sample.category !== category) return false
    if (jurisdiction !== 'all' && !(sample.jurisdictions || []).includes(jurisdiction)) return false
    if (normalizedQuery) {
      const haystack = `${sample.title || ''} ${jurisdictionLabel(sample)} ${provenanceLabel(sample)}`.toLowerCase()
      if (!haystack.includes(normalizedQuery)) return false
    }
    return true
  }), [samples, category, jurisdiction, normalizedQuery])

  const variantIndex = useMemo(() => buildVariantIndex(samples), [samples])

  const groups = useMemo(() => {
    const byCategory = new Map()
    visible.forEach((sample) => {
      const key = sample.category || 'other'
      if (!byCategory.has(key)) byCategory.set(key, [])
      byCategory.get(key).push(sample)
    })
    return [...byCategory.entries()]
      .sort(([a], [b]) => categoryRank(a) - categoryRank(b) || a.localeCompare(b))
      .map(([key, items]) => ({
        key,
        label: categoryLabel(key),
        items: [...items].sort((a, b) => {
          const byJurisdiction = jurisdictionLabel(a).localeCompare(jurisdictionLabel(b))
          return byJurisdiction !== 0 ? byJurisdiction : String(a.title || '').localeCompare(String(b.title || ''))
        }),
      }))
  }, [visible])

  const isGroupOpen = (key) => searching || expanded.has(key)

  const toggleGroup = (key) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const setAllGroups = (open) => {
    setExpanded(open ? new Set(groups.map((group) => group.key)) : new Set())
  }

  const loadPreview = async (sample, requestId = previewRequest.current) => {
    try {
      const blob = await getSampleTemplateSource(sample.id)
      if (!mounted.current || requestId !== previewRequest.current) return
      setPreview((current) => current?.sample.id === sample.id ? { ...current, source: blob, loading: false, error: '' } : current)
    } catch {
      if (!mounted.current || requestId !== previewRequest.current) return
      setPreview((current) => current?.sample.id === sample.id ? { ...current, loading: false, error: `The preview for “${sample.title}” could not be loaded. Please try again.` } : current)
    }
  }

  const openPreview = (sample) => {
    const requestId = previewRequest.current + 1
    previewRequest.current = requestId
    setPreview({ sample, source: null, loading: true, error: '' })
    loadPreview(sample, requestId)
  }

  const closePreview = () => {
    previewRequest.current += 1
    setPreview(null)
  }

  return (
    <section aria-labelledby="sample-library-heading" className="rounded-xl border border-brand-line bg-brand-surface-2 p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 id="sample-library-heading" className="flex items-center gap-2 text-sm font-semibold text-brand-ink">
          <LibraryBig size={16} aria-hidden="true" /> Sample form library
        </h2>
        <span className="rounded-full bg-brand-bg px-2 py-0.5 text-xs font-semibold text-brand-muted" aria-label={`${samples.length} total`}>{samples.length}</span>
      </div>
      <p className="mt-1 text-sm text-brand-muted">
        Reference forms shared across every workspace — wills, powers of attorney, leases, and court forms. Preview the source and review jurisdiction, wording, and field labels before downloading a filled copy. Your own templates are never changed.
      </p>

      {samples.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs font-semibold text-brand-muted">
            Type
            <select value={category} onChange={(event) => setCategory(event.target.value)} className="rounded-lg border border-brand-line bg-brand-bg px-2 py-1 text-xs text-brand-ink">
              <option value="all">All</option>
              {categories.map((value) => <option key={value} value={value}>{value.replace(/_/g, ' ')}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs font-semibold text-brand-muted">
            Jurisdiction
            <select value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} className="rounded-lg border border-brand-line bg-brand-bg px-2 py-1 text-xs text-brand-ink">
              <option value="all">All</option>
              {jurisdictions.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label htmlFor="sample-library-search" className="flex items-center gap-1.5 text-xs font-semibold text-brand-muted">
            <Search size={13} aria-hidden="true" /> Search
          </label>
          <input
            id="sample-library-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by form title"
            className="min-w-[12rem] flex-1 rounded-lg border border-brand-line bg-brand-bg px-2 py-1 text-xs text-brand-ink"
          />
          <div className="ml-auto flex items-center gap-2 text-xs font-semibold text-brand-accent">
            <button type="button" onClick={() => setAllGroups(true)} className="hover:underline">Expand all</button>
            <span className="text-brand-muted" aria-hidden="true">·</span>
            <button type="button" onClick={() => setAllGroups(false)} className="hover:underline">Collapse all</button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="mt-3 flex items-center gap-2 rounded-lg border border-dashed border-brand-line px-3 py-4 text-xs text-brand-muted" role="status">
          <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Loading the sample library…
        </p>
      ) : error && !samples.length ? (
        <p role="alert" className="mt-3 rounded-lg border border-dashed border-brand-line px-3 py-4 text-xs leading-5 text-brand-muted">
          {error}
        </p>
      ) : visible.length ? (
        <div className="mt-3 space-y-2">
          {groups.map((group) => {
            const open = isGroupOpen(group.key)
            const panelId = `sample-group-${group.key}`
            return (
              <section key={group.key} aria-label={`${group.label} forms`} className="rounded-lg border border-brand-line">
                <div className="flex items-center justify-between gap-2 px-2">
                  <h3 className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.key)}
                      aria-expanded={open}
                      aria-controls={panelId}
                      aria-label={group.label}
                      className="flex min-h-[36px] w-full items-center gap-1.5 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-brand-muted hover:text-brand-ink"
                    >
                      {open ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
                      <span className="truncate">{group.label}</span>
                    </button>
                  </h3>
                  <span className="text-[11px] font-semibold text-brand-muted" aria-label={`${group.items.length} forms`}>{group.items.length}</span>
                </div>
                <ul id={panelId} hidden={!open} className="divide-y divide-brand-line border-t border-brand-line">
                  {group.items.map((sample) => {
                    const variant = variantIndex.get(sample.id)
                    const provenance = provenanceLabel(sample)
                    return (
                      <li key={sample.id} className="flex items-center justify-between gap-3 px-3 py-2">
                        <div className="min-w-0">
                          <p title={sample.title} className="truncate text-sm font-semibold text-brand-ink">
                            {sample.title}
                            {variant && (
                              <span className="ml-1.5 rounded bg-brand-bg px-1.5 py-0.5 align-middle text-[10px] font-semibold uppercase tracking-wide text-brand-muted">
                                Version {variant.position} of {variant.total}
                              </span>
                            )}
                          </p>
                          <p className="truncate text-xs text-brand-muted">
                            {jurisdictionLabel(sample)}
                            {sample.field_count ? ` · ${sample.field_count} fields` : ''}
                            {provenance ? ` · ${provenance}` : ''}
                          </p>
                          {!provenance && (
                            <p className="text-[11px] leading-snug text-amber-800">
                              Source details were not recorded; attorney review is required before use.
                            </p>
                          )}
                          {variant && !provenance && (
                            <p className="text-[11px] leading-snug text-brand-muted">
                              {variant.total} forms share this title and their contents differ. Source file: {sample.source_filename || sample.slug || 'not recorded'} — preview before filing.
                            </p>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => openPreview(sample)}
                            className="inline-flex items-center gap-1 rounded-lg border border-brand-line px-2.5 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand-bg disabled:opacity-50"
                          >
                            <Eye size={13} aria-hidden="true" />
                            Preview
                          </button>
                          <button
                            type="button"
                            onClick={() => setFilling(sample)}
                            className="inline-flex items-center gap-1 rounded-lg bg-brand-ink px-2.5 py-1.5 text-xs font-semibold text-white"
                          >
                            <Download size={13} aria-hidden="true" /> Fill
                          </button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </section>
            )
          })}
        </div>
      ) : (
        <p className="mt-3 rounded-lg border border-dashed border-brand-line px-3 py-4 text-xs leading-5 text-brand-muted">
          No sample forms match this filter.
        </p>
      )}

      {error && samples.length > 0 && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}

      {filling && <SampleFillDialog sample={filling} onClose={() => setFilling(null)} />}
      {preview && (
        <PdfPreviewDialog
          title={preview.sample.title}
          source={preview.source}
          loading={preview.loading}
          error={preview.error}
          filename={preview.sample.source_filename || `${preview.sample.slug || preview.sample.id}.pdf`}
          onClose={closePreview}
          onRetry={() => {
            const requestId = previewRequest.current + 1
            previewRequest.current = requestId
            setPreview((current) => current ? { ...current, source: null, loading: true, error: '' } : current)
            loadPreview(preview.sample, requestId)
          }}
        />
      )}
      <p className="mt-3 flex items-center gap-1.5 text-xs text-brand-muted">
        <BookOpen size={12} aria-hidden="true" /> Samples are reference forms, not legal advice; review jurisdiction-specific requirements before use.
      </p>
    </section>
  )
}
