import { useState } from 'react'
import { Search } from 'lucide-react'
import { formatMatterLabel } from './prepareHelpers'

// The matter chooser shared by the Generate dialog and the Prepare route.
export default function MatterPicker({ matters, selectedMatterId, onSelect, loading, disabled = false }) {
  const [query, setQuery] = useState('')
  const [choosing, setChoosing] = useState(false)
  const selected = matters.find((matter) => matter.id === selectedMatterId)
  const filtered = matters.filter((matter) => {
    const q = query.trim().toLowerCase()
    if (!q) return true
    return (
      matter.matter_name?.toLowerCase().includes(q) ||
      matter.client_name?.toLowerCase().includes(q) ||
      matter.practice_area?.toLowerCase().includes(q) ||
      matter.id?.toLowerCase().includes(q)
    )
  }).slice(0, 8)

  if (selected && !choosing) return <div className="flex items-center justify-between gap-3 rounded border border-brand-line bg-brand-bg px-3 py-2 text-sm">
    <span className="min-w-0 truncate"><span className="mr-2 text-brand-muted">Matter</span>{formatMatterLabel(selected)}</span>
    <button type="button" disabled={disabled} onClick={() => setChoosing(true)} className="shrink-0 rounded border border-brand-line px-2 py-1 text-xs">Change matter</button>
  </div>

  return (
    <div className="border border-brand-line rounded bg-brand-bg p-3">
      <label htmlFor="templatespage-matter" className="block text-sm font-medium text-brand-ink mb-2">
        Matter
      </label>
      <div className="relative">
        <Search size={15} className="absolute left-3 top-2.5 text-brand-muted" />
        <input id="templatespage-matter"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
          className="w-full pl-9 pr-3 py-2 border border-brand-line rounded text-sm bg-brand-surface-2 text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent"
          placeholder={loading ? 'Loading matters...' : 'Search by matter, client, or practice area'}
        />
      </div>
      {selected && (
        <div className="mt-2 flex items-center justify-between gap-2 text-xs bg-brand-surface-2 border border-brand-line rounded px-3 py-2">
          <span className="text-brand-ink truncate">{formatMatterLabel(selected)}</span>
          <button
            type="button"
            onClick={() => onSelect('')}
            disabled={disabled}
            className="text-brand-muted hover:text-brand-ink"
          >
            Clear
          </button>
        </div>
      )}
      <div className="mt-2 max-h-48 overflow-y-auto space-y-1">
        {filtered.map((matter) => (
          <button
            key={matter.id}
            type="button"
            onClick={() => { onSelect(matter.id); setChoosing(false) }}
            disabled={disabled}
            className={`w-full text-left px-3 py-2 rounded border text-sm transition-colors ${
              selectedMatterId === matter.id
                ? 'border-brand-accent bg-brand-accent/10 text-brand-ink'
                : 'border-transparent hover:border-brand-line hover:bg-brand-surface-2 text-brand-ink'
            }`}
          >
            <span className="block font-medium truncate">{matter.matter_name || 'Untitled matter'}</span>
            <span className="block text-xs text-brand-muted truncate">
              {[matter.client_name, matter.practice_area, matter.status].filter(Boolean).join(' - ') || matter.id}
            </span>
          </button>
        ))}
        {!loading && filtered.length === 0 && (
          <p className="text-xs text-brand-muted px-1 py-2">
            No matching matters. Paste a matter UUID below if needed.
          </p>
        )}
      </div>
    </div>
  )
}
