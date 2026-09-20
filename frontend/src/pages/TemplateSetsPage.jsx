import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Layers, Plus, Trash2 } from 'lucide-react'
import { createTemplateSet, deleteTemplateSet, getTemplates, listTemplateSets, replaceTemplateSet } from '../api'
import { buildPrepareTarget } from '../components/prepare/prepareRouting'
import { getErrorMessage } from '../components/prepare/prepareHelpers'

const normalizeItems = (data) => (Array.isArray(data) ? data : (data?.items || []))
const blank = () => ({ title: '', description: '', module: '', jurisdiction: '', items: [] })

// Sets: the templates a firm drafts together. The editor is deliberately
// small: a name, an ordered list of published templates, and per member
// whether it follows the published version or pins one.
export default function TemplateSetsPage() {
  const navigate = useNavigate()
  const [sets, setSets] = useState([])
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null) // null | { id?: string, ...form }
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [listed, library] = await Promise.all([listTemplateSets({ page_size: 100 }), getTemplates({ page_size: 200 })])
      setSets(normalizeItems(listed))
      setTemplates(normalizeItems(library).filter((tpl) => tpl.is_active))
    } catch (err) {
      setError(getErrorMessage(err, 'Template sets could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const templateById = useMemo(() => Object.fromEntries(templates.map((tpl) => [tpl.id, tpl])), [templates])

  const startEdit = (record) => setEditing(record ? {
    id: record.id, title: record.title || '', description: record.description || '', module: record.module || '', jurisdiction: record.jurisdiction || '',
    items: (record.items || []).map((item) => ({ template_id: item.template_id, pinned_version_no: item.pinned_version_no || null })),
  } : blank())

  const save = async (event) => {
    event.preventDefault()
    if (!editing) return
    setBusy(true); setError('')
    const payload = {
      title: editing.title.trim(), description: editing.description.trim() || null, module: editing.module.trim() || null, jurisdiction: editing.jurisdiction.trim() || null,
      items: editing.items.map((item) => ({ template_id: item.template_id, ...(item.pinned_version_no ? { pinned_version_no: item.pinned_version_no } : {}) })),
    }
    try {
      if (editing.id) await replaceTemplateSet(editing.id, payload)
      else await createTemplateSet(payload)
      setEditing(null)
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'The set could not be saved.'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (record) => {
    setBusy(true); setError('')
    try { await deleteTemplateSet(record.id); await load() } catch (err) { setError(getErrorMessage(err, 'The set could not be deleted.')) } finally { setBusy(false) }
  }

  const addMember = (templateId) => {
    if (!templateId || editing.items.some((item) => item.template_id === templateId)) return
    setEditing({ ...editing, items: [...editing.items, { template_id: templateId, pinned_version_no: null }] })
  }
  const move = (index, delta) => {
    const items = [...editing.items]
    const target = index + delta
    if (target < 0 || target >= items.length) return
    ;[items[index], items[target]] = [items[target], items[index]]
    setEditing({ ...editing, items })
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to="/templates" className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-muted hover:text-brand-ink"><ArrowLeft size={16} aria-hidden="true" /> Template Studio</Link>
        <h1 className="text-lg font-semibold text-brand-ink"><Layers size={18} className="mr-1 inline" aria-hidden="true" />Template sets</h1>
        <button type="button" onClick={() => startEdit(null)} className="inline-flex items-center gap-1 rounded-lg bg-brand-ink px-3 py-2 text-xs font-semibold text-white"><Plus size={14} aria-hidden="true" /> New set</button>
      </div>
      <p className="text-sm text-brand-muted">A set is drafted together from one interview: the caption is asked once and every document in the packet is previewed, saved and sent from one page.</p>
      {error && <p role="alert" className="text-sm text-brand-rose">{error}</p>}
      {editing && (
        <form onSubmit={save} aria-label={editing.id ? 'Edit set' : 'New set'} className="space-y-3 rounded-xl border border-brand-line bg-brand-surface p-4">
          <label className="block text-sm">Name<input aria-label="Set name" value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} required className="mt-1 w-full rounded border border-brand-line px-3 py-2 text-sm" /></label>
          <label className="block text-sm">Description<input aria-label="Set description" value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} className="mt-1 w-full rounded border border-brand-line px-3 py-2 text-sm" /></label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">Module<input aria-label="Set module" value={editing.module} onChange={(e) => setEditing({ ...editing, module: e.target.value })} className="mt-1 w-full rounded border border-brand-line px-3 py-2 text-sm" /></label>
            <label className="block text-sm">Jurisdiction<input aria-label="Set jurisdiction" value={editing.jurisdiction} onChange={(e) => setEditing({ ...editing, jurisdiction: e.target.value })} className="mt-1 w-full rounded border border-brand-line px-3 py-2 text-sm" /></label>
          </div>
          <div>
            <p className="text-sm font-semibold text-brand-ink">Documents, in the order they are produced</p>
            <ol className="mt-2 space-y-2">
              {editing.items.map((item, index) => {
                const tpl = templateById[item.template_id]
                return (
                  <li key={item.template_id} className="flex flex-wrap items-center gap-2 rounded border border-brand-line px-3 py-2 text-sm">
                    <span className="min-w-0 flex-1 truncate">{index + 1}. {tpl?.title || item.template_id}</span>
                    <select aria-label={`Version for ${tpl?.title || item.template_id}`} value={item.pinned_version_no || ''} onChange={(e) => setEditing({ ...editing, items: editing.items.map((entry, i) => (i === index ? { ...entry, pinned_version_no: e.target.value ? Number(e.target.value) : null } : entry)) })} className="rounded border border-brand-line px-2 py-1 text-xs">
                      <option value="">Follow published</option>
                      {tpl?.published_version_no ? <option value={tpl.published_version_no}>Pin v{tpl.published_version_no}</option> : null}
                    </select>
                    <button type="button" onClick={() => move(index, -1)} className="text-xs underline">Up</button>
                    <button type="button" onClick={() => move(index, 1)} className="text-xs underline">Down</button>
                    <button type="button" aria-label={`Remove ${tpl?.title || item.template_id}`} onClick={() => setEditing({ ...editing, items: editing.items.filter((_, i) => i !== index) })} className="text-xs text-brand-rose underline">Remove</button>
                  </li>
                )
              })}
            </ol>
            <label className="mt-2 block text-sm">Add a published template
              <select aria-label="Add a published template" value="" onChange={(e) => addMember(e.target.value)} className="mt-1 w-full rounded border border-brand-line px-3 py-2 text-sm">
                <option value="">Choose a template…</option>
                {templates.filter((tpl) => !editing.items.some((item) => item.template_id === tpl.id)).map((tpl) => <option key={tpl.id} value={tpl.id}>{tpl.title}</option>)}
              </select>
            </label>
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !editing.title.trim()} className="rounded-lg bg-brand-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{editing.id ? 'Save set' : 'Create set'}</button>
            <button type="button" onClick={() => setEditing(null)} className="rounded-lg border border-brand-line px-4 py-2 text-sm">Cancel</button>
          </div>
        </form>
      )}
      {loading ? <p role="status" className="text-sm text-brand-muted">Loading sets…</p> : sets.length === 0 ? (
        <p className="rounded-xl border border-dashed border-brand-line p-6 text-center text-sm text-brand-muted">No sets yet. Create one from the published templates you file together.</p>
      ) : (
        <ul aria-label="Template sets" className="space-y-2">
          {sets.map((record) => (
            <li key={record.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-brand-line bg-brand-surface px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-brand-ink">{record.title}</p>
                <p className="text-xs text-brand-muted">{(record.items || []).length} document{(record.items || []).length === 1 ? '' : 's'}{record.jurisdiction ? ` · ${record.jurisdiction}` : ''}{(record.items || []).some((item) => item.unavailable_reason) ? ' · one or more members cannot be drafted' : ''}</p>
              </div>
              <button type="button" onClick={() => navigate(buildPrepareTarget({ setId: record.id }).url)} disabled={!(record.items || []).length} className="rounded-lg border border-brand-accent px-3 py-2 text-xs font-semibold text-brand-ink hover:bg-brand-bg disabled:opacity-40">Prepare on a matter</button>
              <button type="button" onClick={() => startEdit(record)} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-semibold">Edit</button>
              <button type="button" aria-label={`Delete ${record.title}`} onClick={() => remove(record)} disabled={busy} className="rounded-lg border border-brand-line px-2 py-2 text-brand-rose"><Trash2 size={14} aria-hidden="true" /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
