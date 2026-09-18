import { useState } from 'react'
import { Plus, Upload } from 'lucide-react'
import { addClientPortalEstateAsset, updateClientPortalEstateAsset, uploadClientPortalDocument } from '../../api'

// A short form, one item at a time, nothing required but a name. It is
// written for a client who is grieving and may never have used a website
// like this: large controls, plain words, and a way to stop and come back.
const INPUT = 'mt-1 block w-full border border-brand-line rounded-xl px-3 py-3 text-base font-sans focus:outline-none focus:ring-2 focus:ring-brand-accent/40'
const PRIMARY = 'inline-flex items-center gap-1.5 px-4 py-3 bg-brand-ink text-white text-base font-sans font-semibold rounded-xl hover:bg-brand-ink-2 transition-all disabled:opacity-50'
const SECONDARY = 'inline-flex items-center gap-1.5 px-4 py-3 border border-brand-line text-base font-sans font-medium rounded-xl text-brand-ink hover:bg-brand-bg-soft disabled:opacity-50'

const EMPTY = { name: '', category: 'other', ownership_type: 'unknown', approximate_value: '', institution: '', notes: '', artifact_document_id: null }

export function statusLabel(status) {
  if (status === 'verified') return 'Checked by the office'
  if (status === 'rejected') return 'The office will follow up'
  return 'Sent — the office will review it'
}

function AssetForm({ estate, initial, onSaved, onCancel }) {
  const [form, setForm] = useState({ ...EMPTY, ...initial })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [attachment, setAttachment] = useState(initial?.artifact_document_id ? 'A statement is attached.' : '')
  const set = (key, value) => setForm(previous => ({ ...previous, [key]: value }))
  const editing = Boolean(initial?.id)

  async function attach(file) {
    if (!file) return
    setBusy(true); setError('')
    try {
      const document = await uploadClientPortalDocument(file, `Estate inventory: ${form.name || 'statement'}`)
      set('artifact_document_id', document.id)
      setAttachment(`Attached: ${file.name}`)
    } catch { setError('The file could not be uploaded. You can send it later or bring it to the office.') }
    finally { setBusy(false) }
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError('')
    const payload = { ...form, approximate_value: form.approximate_value || null, institution: form.institution || null, notes: form.notes || null }
    try {
      const next = editing ? await updateClientPortalEstateAsset(initial.id, payload) : await addClientPortalEstateAsset(payload)
      onSaved(next)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'That did not save. Please try again, or call the office.')
    } finally { setBusy(false) }
  }

  return (
    <form className="space-y-4 border border-brand-line rounded-xl p-4" onSubmit={submit} aria-label={editing ? 'Change this item' : 'Add an item'}>
      <label className="block text-base text-brand-ink font-medium">What is it?
        <input className={INPUT} required maxLength={400} value={form.name} onChange={event => set('name', event.target.value)} placeholder="For example: checking account at Gate City Bank" />
      </label>
      <label className="block text-base text-brand-ink font-medium">What kind of thing is it?
        <select className={INPUT} value={form.category} onChange={event => set('category', event.target.value)}>
          {estate.categories.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
        </select>
      </label>
      <label className="block text-base text-brand-ink font-medium">Whose name is it in?
        <select className={INPUT} value={form.ownership_type} onChange={event => set('ownership_type', event.target.value)}>
          {estate.ownership_options.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
        </select>
      </label>
      <label className="block text-base text-brand-ink font-medium">Roughly what is it worth? (a best guess is fine)
        <input className={INPUT} inputMode="decimal" placeholder="$" value={form.approximate_value} onChange={event => set('approximate_value', event.target.value)} />
      </label>
      <label className="block text-base text-brand-ink font-medium">Bank, company, or where it is (if any)
        <input className={INPUT} maxLength={300} value={form.institution} onChange={event => set('institution', event.target.value)} />
      </label>
      <label className="block text-base text-brand-ink font-medium">Anything else we should know
        <textarea className={INPUT} rows={2} maxLength={2000} value={form.notes} onChange={event => set('notes', event.target.value)} />
      </label>
      <label className="flex flex-wrap items-center gap-2 text-base text-brand-ink">
        <Upload size={16} className="text-brand-ink-2" /> Attach a statement or photo (optional)
        <input className="text-sm" type="file" accept="application/pdf,image/*,.pdf,.png,.jpg,.jpeg,.heic" disabled={busy} onChange={event => attach(event.target.files?.[0])} />
        {attachment && <span className="text-sm text-brand-green">{attachment}</span>}
      </label>
      {error && <p role="alert" className="text-sm text-brand-rose">{error}</p>}
      <div className="flex flex-wrap gap-3">
        <button type="submit" className={PRIMARY} disabled={busy}>{busy ? 'Saving…' : editing ? 'Save changes' : 'Add this item'}</button>
        <button type="button" className={SECONDARY} onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  )
}

export default function ClientPortalEstateTab({ estate, onChange }) {
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const assets = Array.isArray(estate.assets) ? estate.assets : []

  function saved(next) {
    onChange(next)
    setAdding(false)
    setEditingId(null)
  }

  return (
    <div className="space-y-4" data-testid="client-portal-estate">
      <section className="bg-brand-surface border border-brand-line rounded-xl p-5 font-sans" aria-label="Estate inventory">
        <h2 className="font-serif font-bold text-lg text-brand-ink">What the estate owns</h2>
        <p className="text-base text-brand-ink-2 mt-2">
          {estate.decedent_name ? `Please list what ${estate.decedent_name} owned` : 'Please list what the estate owns'} — bank accounts, land, vehicles, investments, anything of value.
          One item at a time is fine. You do not need exact amounts, and you can bring statements to the office instead of uploading them.
        </p>
        {!estate.inventory_open && (
          <p className="mt-3 text-base text-brand-ink bg-brand-bg-soft rounded-xl px-4 py-3">This list opens once the court has appointed the personal representative. The office will let you know. If you already have statements, you are welcome to send them to the office now.</p>
        )}
      </section>

      {assets.length > 0 && (
        <section className="bg-brand-surface border border-brand-line rounded-xl p-5 font-sans" aria-label="Items you have listed">
          <h3 className="font-serif font-bold text-base text-brand-ink mb-3">Items you have listed</h3>
          <ul className="divide-y divide-brand-line">
            {assets.map(item => (
              <li key={item.id} className="py-3 first:pt-0 last:pb-0">
                {editingId === item.id ? (
                  <AssetForm estate={estate} initial={item} onSaved={saved} onCancel={() => setEditingId(null)} />
                ) : (
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-base font-medium text-brand-ink">{item.name}</p>
                      <p className="text-sm text-brand-ink-2">
                        {estate.categories.find(option => option.key === item.category)?.label || item.category}
                        {item.approximate_value ? ` · about $${item.approximate_value}` : ''}
                        {item.institution ? ` · ${item.institution}` : ''}
                      </p>
                      <p className="text-sm text-brand-ink-2">{statusLabel(item.verification_status)}</p>
                    </div>
                    {item.editable && estate.inventory_open && (
                      <button type="button" className={SECONDARY} onClick={() => setEditingId(item.id)}>Change</button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {estate.inventory_open && (adding
        ? <AssetForm estate={estate} onSaved={saved} onCancel={() => setAdding(false)} />
        : <button type="button" className={PRIMARY} onClick={() => setAdding(true)}><Plus size={16} /> Add an item</button>
      )}
    </div>
  )
}
