import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { getMattersV2 } from '../../api'
import { formatMatterLabel } from './prepareHelpers'

// The matter chooser shared by the Generate dialog and the Prepare route.
export default function MatterPicker({ matters = [], selectedMatterId, onSelect, loading, disabled = false }) {
  const [query, setQuery] = useState('')
  const [choosing, setChoosing] = useState(false)
  const [matches, setMatches] = useState(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState(false)
  const [chosen, setChosen] = useState(null)
  // Search the workspace, not just the first page of recent matters. Users
  // should never need an internal UUID to find an older client file.
  useEffect(() => {
    setMatches(null)
    setSearchError(false)
    const search = query.trim()
    if (!search) { setSearching(false); return undefined }
    let active = true
    setSearching(true)
    const timer = setTimeout(() => {
      getMattersV2({ search, page_size: 20, sort_by: 'updated_at', sort_dir: 'desc' })
        .then(result => { if (active) setMatches(Array.isArray(result) ? result : result.items || []) })
        .catch(() => { if (active) setSearchError(true) })
        .finally(() => { if (active) setSearching(false) })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query])
  const selected = [...matters, ...(matches || []), ...(chosen ? [chosen] : [])].find((matter) => matter.id === selectedMatterId)
  const filtered = (matches || matters.filter((matter) => {
    const q = query.trim().toLowerCase()
    if (!q) return true
    return (
      matter.matter_name?.toLowerCase().includes(q) ||
      matter.client_name?.toLowerCase().includes(q) ||
      matter.matter_number?.toLowerCase().includes(q) ||
      matter.practice_area?.toLowerCase().includes(q) ||
      matter.id?.toLowerCase().includes(q)
    )
  })).slice(0, 8)

  if (selected && !choosing) return <div className="flex items-center justify-between gap-3 rounded border border-brand-line bg-brand-bg px-3 py-2 text-sm">
    <span className="min-w-0 truncate"><span className="mr-2 text-brand-muted">Matter</span>{formatMatterLabel(selected)}</span>
    <button type="button" disabled={disabled} onClick={() => setChoosing(true)} className="shrink-0 rounded border border-brand-line px-2 py-1 text-xs">Change matter</button>
  </div>

  return (
    <div className="border border-brand-line rounded bg-brand-bg p-3">
      <label htmlFor="templatespage-matter" className="block text-sm font-medium text-brand-ink mb-2">
        Fill from a matter
      </label>
      <div className="relative">
        <Search size={15} className="absolute left-3 top-2.5 text-brand-muted" />
        <input id="templatespage-matter"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
          className="w-full pl-9 pr-3 py-2 border border-brand-line rounded text-sm bg-brand-surface-2 text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent"
          placeholder={loading ? 'Loading matters...' : 'Search by client, matter name or number'}
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
            onClick={() => { setChosen(matter); onSelect(matter.id); setChoosing(false) }}
            disabled={disabled}
            className={`w-full text-left px-3 py-2 rounded border text-sm transition-colors ${
              selectedMatterId === matter.id
                ? 'border-brand-accent bg-brand-accent/10 text-brand-ink'
                : 'border-transparent hover:border-brand-line hover:bg-brand-surface-2 text-brand-ink'
            }`}
          >
            <span className="block font-medium truncate">{matter.matter_name || 'Untitled matter'}</span>
            <span className="block text-xs text-brand-muted truncate">
              {[matter.matter_number, matter.client_name, matter.practice_area].filter(Boolean).join(' · ')}
            </span>
          </button>
        ))}
        {searching && <p role="status" className="text-xs text-brand-muted px-1 py-2">Searching matters…</p>}
        {searchError && <p role="alert" className="text-xs text-brand-rose px-1 py-2">We couldn’t search all matters. Check your connection and try again.</p>}
        {!loading && !searching && !searchError && filtered.length === 0 && (
          <p className="text-xs text-brand-muted px-1 py-2">
            {query.trim() ? 'No matching matters. Try the client’s name or matter number.' : 'Search to choose a matter.'}
          </p>
        )}
      </div>
    </div>
  )
}
