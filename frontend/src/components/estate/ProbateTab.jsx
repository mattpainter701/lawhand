import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, CalendarClock, CheckCircle2, ClipboardList, FileText, Printer, RefreshCw, Send, Upload } from 'lucide-react'
import {
  getProbate, getTemplate, installProbateForms, pullProbateFactsFromIntake,
  recomputeProbate, saveProbateAnchors, saveProbateFacts, syncProbateDeadlines,
} from '../../api'
import { reportError } from '../../utils/reportError'

const RenderModal = lazy(() => import('../../pages/TemplatesPage').then(module => ({ default: module.RenderModal })))

const CARD = 'bg-brand-surface border border-brand-line rounded-2xl p-6 shadow-sm'
const INPUT = 'w-full border border-brand-line rounded-lg px-3 py-2 text-[14px] font-sans text-brand-ink focus:outline-none focus:border-brand-accent focus:ring-1 focus:ring-brand-accent bg-brand-surface'
const LABEL = 'block text-[11px] font-bold text-brand-ink uppercase tracking-widest mb-1'
const BUTTON = 'inline-flex items-center gap-1.5 px-4 py-2 text-sm font-sans font-medium rounded-xl border transition-all disabled:opacity-50'
const PRIMARY = `${BUTTON} bg-brand-ink text-white border-brand-ink hover:bg-brand-ink-2`
const SECONDARY = `${BUTTON} bg-brand-surface text-brand-ink border-brand-line hover:bg-brand-bg-soft hover:border-brand-ink`

export const TRACK_TONES = {
  informal_testate: 'bg-brand-green/10 text-brand-green',
  informal_intestate: 'bg-brand-green/10 text-brand-green',
  small_estate_affidavit: 'bg-brand-accent/10 text-brand-accent',
  formal_testate_late: 'bg-brand-amber/10 text-brand-amber',
  formal_intestate_late: 'bg-brand-amber/10 text-brand-amber',
  not_nd_domicile: 'bg-brand-rose/10 text-brand-rose',
  undetermined: 'bg-brand-bg-soft text-brand-ink-2',
}

// The staff-side facts form asks the same questions the client's
// questionnaire does, in the same order, so the office can complete an intake
// over the phone with the client reading from their paper copy.
export const FACT_FIELDS = [
  { key: 'decedent_name', label: 'Full legal name of the person who died', kind: 'text' },
  { key: 'decedent_aka', label: 'Other names they used', kind: 'text' },
  { key: 'date_of_death', label: 'Date of death', kind: 'date' },
  { key: 'date_of_birth', label: 'Date of birth', kind: 'date' },
  { key: 'domicile_state', label: 'State they lived in at death', kind: 'text' },
  { key: 'domicile_county', label: 'County they lived in', kind: 'text' },
  { key: 'will_exists', label: 'Did they leave a will?', kind: 'yes_no' },
  { key: 'will_original_available', label: 'Is the original signed will in hand?', kind: 'yes_no' },
  { key: 'will_execution_date', label: 'Date the will was signed', kind: 'date' },
  { key: 'real_property_in_nd', label: 'Land, house, farmland or minerals in ND in their own name?', kind: 'yes_no' },
  { key: 'nd_property_counties', label: 'ND counties where that property is (comma-separated)', kind: 'list' },
  { key: 'probate_property_value', label: 'Rough value of everything in their own name, net of loans', kind: 'money' },
  { key: 'applicant_name', label: 'Applicant (person asking to open the estate)', kind: 'text' },
  { key: 'applicant_relationship', label: 'Applicant relationship to the decedent', kind: 'text' },
  { key: 'applicant_is_nominee', label: 'Does the will name the applicant as personal representative?', kind: 'yes_no' },
  { key: 'applicant_address', label: 'Applicant mailing address', kind: 'text' },
  { key: 'applicant_phone', label: 'Applicant phone', kind: 'text' },
  { key: 'applicant_email', label: 'Applicant email', kind: 'text' },
  { key: 'persons_with_prior_or_equal_priority', label: 'People with an equal or better right to serve (comma-separated)', kind: 'list' },
  { key: 'prior_appointment', label: 'Has a court already appointed someone for this estate?', kind: 'yes_no' },
  { key: 'prior_appointment_details', label: 'If yes: who, when, which county and state', kind: 'text' },
  { key: 'probate_opened_elsewhere', label: 'Probate opened in another court?', kind: 'yes_no' },
  { key: 'demand_for_notice', label: 'Demand for notice on file?', kind: 'yes_no' },
  { key: 'demand_for_notice_details', label: 'If yes: who filed it and where', kind: 'text' },
  { key: 'bond_amount', label: 'Bond amount (0 if none)', kind: 'money' },
  { key: 'assets_summary', label: 'What they owned', kind: 'textarea' },
  { key: 'debts_summary', label: 'What they owed', kind: 'textarea' },
  { key: 'funeral_expenses', label: 'Funeral and burial costs', kind: 'money' },
  { key: 'notes', label: 'Attorney notes (never printed on a form)', kind: 'textarea' },
]

const ANCHORS = [
  { key: 'date_of_death', label: 'Date of death' },
  { key: 'appointment_date', label: 'Appointment date' },
  { key: 'letters_issued_date', label: 'Letters issued' },
  { key: 'first_publication_date', label: 'First publication of notice to creditors' },
  { key: 'closing_statement_filed_date', label: 'Closing statement filed' },
]

export function factsToForm(facts) {
  const form = {}
  for (const field of FACT_FIELDS) {
    const value = facts?.[field.key]
    if (field.kind === 'yes_no') form[field.key] = value === true ? 'yes' : value === false ? 'no' : ''
    else if (field.kind === 'list') form[field.key] = Array.isArray(value) ? value.join(', ') : (value || '')
    else form[field.key] = value ?? ''
  }
  form.heirs = (facts?.heirs || []).map(row => [row.name, row.age, row.relationship, row.address].filter(Boolean).join('; ')).join('\n')
  return form
}

export function formToFacts(form) {
  const payload = {}
  for (const field of FACT_FIELDS) {
    const raw = form[field.key]
    if (field.kind === 'yes_no') payload[field.key] = raw === 'yes' ? true : raw === 'no' ? false : null
    else if (field.kind === 'list') payload[field.key] = String(raw || '').split(/[,\n;]+/).map(item => item.trim()).filter(Boolean)
    else payload[field.key] = raw === '' || raw === undefined ? null : raw
  }
  payload.heirs = String(form.heirs || '').split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const [name = '', age = '', relationship = '', ...rest] = line.split(/\s*;\s*/)
    return { name, age, relationship, address: rest.join('; ') }
  }).filter(row => row.name)
  return payload
}

export function printHint(row) {
  if (!row?.pages) return ''
  const [first, last] = row.pages
  return first === last ? `print page ${first}` : `print pages ${first}–${last}`
}

function Section({ icon: Icon, title, children, aside }) {
  return (
    <section className={CARD} aria-label={title}>
      <div className="flex items-start justify-between gap-4 mb-4">
        <h2 className="font-serif font-bold text-xl text-brand-ink flex items-center gap-2"><Icon size={20} className="text-brand-accent" /> {title}</h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

function Determination({ determination, determinedAt, onRecompute, busy }) {
  if (!determination) {
    return <p className="text-sm text-brand-ink-2">No determination yet. Enter the facts below, or pull them from the client's questionnaire, and the track is worked out from them.</p>
  }
  const tone = TRACK_TONES[determination.track] || TRACK_TONES.undetermined
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${tone}`}>{determination.label}</span>
        {determinedAt && <span className="text-xs text-brand-muted">as of {new Date(determinedAt).toLocaleString()}</span>}
        <button type="button" className={SECONDARY} onClick={onRecompute} disabled={busy}><RefreshCw size={14} /> Recompute</button>
      </div>
      {determination.venue_county && <p className="text-sm text-brand-ink-2"><strong>Venue:</strong> {determination.venue_county} County — {determination.venue_basis}.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className={LABEL}>Why</p>
          <ul className="list-disc pl-5 text-sm text-brand-ink-2 space-y-1">{determination.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
        </div>
        <div className="space-y-3">
          {determination.warnings.length > 0 && (
            <div>
              <p className={LABEL}>Check before filing</p>
              <ul className="space-y-1 text-sm text-brand-amber">{determination.warnings.map(warning => <li key={warning} className="flex gap-2"><AlertTriangle size={14} className="mt-0.5 shrink-0" />{warning}</li>)}</ul>
            </div>
          )}
          {determination.missing_facts.length > 0 && (
            <p className="text-sm text-brand-ink-2"><strong>Still needed:</strong> {determination.missing_facts.map(key => key.replace(/_/g, ' ')).join(', ')}.</p>
          )}
          {determination.alternatives.length > 0 && (
            <p className="text-sm text-brand-ink-2"><strong>Also possible:</strong> {determination.alternatives.map(track => track.replace(/_/g, ' ')).join(', ')}.</p>
          )}
          {determination.waiver_required && <p className="text-sm text-brand-ink-2">A Waiver of Right to Appointment (Form 9) is needed from each person with an equal or higher right to serve.</p>}
        </div>
      </div>
    </div>
  )
}

function FactsForm({ facts, onSave, onPull, hasMatter, busy }) {
  const [form, setForm] = useState(() => factsToForm(facts))
  const [overwrite, setOverwrite] = useState(false)
  useEffect(() => { setForm(factsToForm(facts)) }, [facts])
  const set = (key, value) => setForm(previous => ({ ...previous, [key]: value }))
  return (
    <form className="space-y-4" onSubmit={event => { event.preventDefault(); onSave(formToFacts(form)) }}>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={SECONDARY} disabled={!hasMatter || busy} onClick={() => onPull(overwrite)} title={hasMatter ? '' : 'Link this estate to a matter first'}>
          <ClipboardList size={14} /> Pull from client questionnaire
        </button>
        <label className="text-sm text-brand-ink-2 flex items-center gap-2"><input type="checkbox" checked={overwrite} onChange={event => setOverwrite(event.target.checked)} /> Replace what is entered here with the client's answers</label>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {FACT_FIELDS.map(field => (
          <div key={field.key} className={field.kind === 'textarea' ? 'md:col-span-2' : ''}>
            <label htmlFor={`probate-${field.key}`} className={LABEL}>{field.label}</label>
            {field.kind === 'yes_no' ? (
              <select id={`probate-${field.key}`} className={INPUT} value={form[field.key]} onChange={event => set(field.key, event.target.value)}>
                <option value="">Unknown</option><option value="yes">Yes</option><option value="no">No</option>
              </select>
            ) : field.kind === 'textarea' ? (
              <textarea id={`probate-${field.key}`} className={INPUT} rows={3} value={form[field.key]} onChange={event => set(field.key, event.target.value)} />
            ) : (
              <input id={`probate-${field.key}`} className={INPUT} type={field.kind === 'date' ? 'date' : 'text'} inputMode={field.kind === 'money' ? 'decimal' : undefined} value={form[field.key]} onChange={event => set(field.key, event.target.value)} />
            )}
          </div>
        ))}
        <div className="md:col-span-2">
          <label htmlFor="probate-heirs" className={LABEL}>Surviving spouse, children, heirs and devisees — one per line: name; age; relationship; address</label>
          <textarea id="probate-heirs" className={INPUT} rows={4} value={form.heirs} onChange={event => set('heirs', event.target.value)} placeholder={'Ann Olson; 70; spouse; 1 Main St, Fargo ND 58102\nBob Olson; 45; son; 2 Elm St, Moorhead MN'} />
        </div>
      </div>
      <button type="submit" className={PRIMARY} disabled={busy}><CheckCircle2 size={14} /> Save facts and determine track</button>
    </form>
  )
}

function FormsList({ state, onInstall, onGenerate, busy }) {
  const determination = state?.determination
  const rows = state?.forms || []
  const guidebookRows = rows.filter(row => row.number)
  const companions = rows.filter(row => !row.number)
  const installed = guidebookRows.some(row => row.template_id)
  const published = guidebookRows.some(row => row.published)
  const required = new Set(determination?.forms || [])
  const optional = new Set(determination?.optional_forms || [])
  const visible = guidebookRows.filter(row => required.has(row.number) || optional.has(row.number))
  const formal = determination?.checklist?.length ? determination.checklist : null
  const generateHint = !state?.matter_id ? 'Link this estate to a matter to generate.' : !installed ? 'Install the ND probate pack first.' : !published ? 'Publish the packet in Templates first — it installs as a draft until an attorney activates it.' : ''
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {!installed && <button type="button" className={SECONDARY} onClick={onInstall} disabled={busy}><FileText size={14} /> Install ND probate pack</button>}
        <button type="button" className={PRIMARY} onClick={onGenerate} disabled={busy || Boolean(generateHint)} title={generateHint}><Printer size={14} /> Generate filled packet</button>
        {generateHint && <span className="text-xs text-brand-muted">{generateHint}</span>}
      </div>
      {formal && (
        <div>
          <p className="text-sm text-brand-ink-2 mb-2">The court publishes no forms for this proceeding. The firm's own pleadings are used; upload each as a template and generate it from the estate like any other.</p>
          <ul className="divide-y divide-brand-line border border-brand-line rounded-xl">
            {formal.map(item => (
              <li key={item} className="flex items-center justify-between gap-3 px-4 py-2 text-sm text-brand-ink">
                <span>{item}</span>
                <a href="/templates" className="inline-flex items-center gap-1 text-brand-accent hover:underline text-xs"><Upload size={12} /> Upload as template</a>
              </li>
            ))}
          </ul>
        </div>
      )}
      {visible.length > 0 && (
        <ul className="divide-y divide-brand-line border border-brand-line rounded-xl">
          {visible.map(row => (
            <li key={row.key} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 text-sm">
              <span className="text-brand-ink"><strong>Form {row.number}</strong> — {row.title}{row.statute ? <span className="text-brand-muted"> (N.D.C.C. {row.statute})</span> : null}</span>
              <span className="flex items-center gap-3 text-xs">
                <span className={`px-2 py-0.5 rounded-full ${required.has(row.number) ? 'bg-brand-ink/10 text-brand-ink' : 'bg-brand-bg-soft text-brand-ink-2'}`}>{required.has(row.number) ? 'required' : 'when needed'}</span>
                <span className="text-brand-muted">{printHint(row)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {!formal && visible.length === 0 && <p className="text-sm text-brand-ink-2">Save the facts to see which forms this estate files.</p>}
      {companions.length > 0 && (
        <p className="text-xs text-brand-muted">Also in the pack: {companions.map(row => row.title).join('; ')}.</p>
      )}
    </div>
  )
}

function Clock({ state, onSaveAnchors, onBuild, busy }) {
  const [form, setForm] = useState(() => ({ ...state?.anchors }))
  const [mirror, setMirror] = useState(true)
  useEffect(() => { setForm({ ...state?.anchors }) }, [state?.anchors])
  const preview = state?.deadlines_preview
  const waiting = preview?.waiting_on || {}
  return (
    <div className="space-y-4">
      <form className="grid gap-4 md:grid-cols-3" onSubmit={event => { event.preventDefault(); onSaveAnchors(Object.fromEntries(ANCHORS.map(anchor => [anchor.key, form[anchor.key] || null]))) }}>
        {ANCHORS.map(anchor => (
          <div key={anchor.key}>
            <label htmlFor={`anchor-${anchor.key}`} className={LABEL}>{anchor.label}</label>
            <input id={`anchor-${anchor.key}`} type="date" className={INPUT} value={form[anchor.key] || ''} onChange={event => setForm(previous => ({ ...previous, [anchor.key]: event.target.value }))} />
          </div>
        ))}
        <div className="flex items-end gap-3 md:col-span-3">
          <button type="submit" className={SECONDARY} disabled={busy}>Save dates</button>
          <button type="button" className={PRIMARY} disabled={busy || !state?.anchors?.date_of_death} onClick={() => onBuild(mirror)}><CalendarClock size={14} /> Build deadlines</button>
          <label className="text-sm text-brand-ink-2 flex items-center gap-2"><input type="checkbox" checked={mirror} onChange={event => setMirror(event.target.checked)} /> Also create matter tasks</label>
        </div>
      </form>
      {preview?.deadlines?.length > 0 && (
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] uppercase tracking-widest text-brand-muted"><th className="py-1">Deadline</th><th className="py-1">Due</th><th className="py-1">Authority</th></tr></thead>
          <tbody>
            {preview.deadlines.map(item => (
              <tr key={item.deadline_type} className="border-t border-brand-line/60">
                <td className="py-1.5 pr-3 text-brand-ink">{item.title}</td>
                <td className="py-1.5 pr-3 whitespace-nowrap font-semibold text-brand-ink-2">{item.due_date}</td>
                <td className="py-1.5 text-brand-muted">{item.statute}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {Object.keys(waiting).length > 0 && (
        <p className="text-xs text-brand-muted">Waiting on: {Object.entries(waiting).map(([anchor, types]) => `${anchor.replace(/_/g, ' ')} (${types.length})`).join('; ')}.</p>
      )}
    </div>
  )
}

export default function ProbateTab({ estate, onChanged }) {
  const navigate = useNavigate()
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [generating, setGenerating] = useState(null)

  const load = useCallback(async () => {
    try { setState(await getProbate(estate.id)); setError('') }
    catch (err) { setError('The probate workbench could not load.'); reportError(err) }
  }, [estate.id])
  useEffect(() => { load() }, [load])

  async function run(action, success) {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await action()
      if (result && result.estate_id) setState(result)
      if (success) setNotice(success)
      onChanged?.()
      return result
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'That did not work. Try again.')
      reportError(err)
      return null
    } finally { setBusy(false) }
  }

  const templateId = useMemo(() => state?.forms?.find(row => row.number && row.template_id)?.template_id, [state])

  async function generate() {
    if (!templateId) return
    setBusy(true); setError('')
    try { setGenerating(await getTemplate(templateId)) }
    catch (err) { setError('Could not open the packet template.'); reportError(err) }
    finally { setBusy(false) }
  }

  function sendIntake() {
    if (!estate.matter_id) return
    navigate(`/matters/${estate.matter_id}?paperwork=probate`)
  }

  if (error && !state) return <p role="alert" className="text-sm text-brand-rose">{error}</p>
  if (!state) return <p role="status" className="text-sm text-brand-muted">Loading the probate workbench…</p>

  return (
    <div className="space-y-6">
      {error && <p role="alert" className="text-sm text-brand-rose bg-brand-rose/10 px-3 py-2 rounded border border-brand-rose/20">{error}</p>}
      {notice && <p role="status" className="text-sm text-brand-green">{notice}</p>}
      <Section icon={CheckCircle2} title="Which probate does this estate need?" aside={
        <button type="button" className={SECONDARY} onClick={sendIntake} disabled={!estate.matter_id} title={estate.matter_id ? '' : 'Link this estate to a matter to send paperwork'}>
          <Send size={14} /> Send probate intake
        </button>
      }>
        <Determination determination={state.determination} determinedAt={state.determined_at} busy={busy} onRecompute={() => run(() => recomputeProbate(estate.id))} />
        {!estate.matter_id && <p className="mt-3 text-xs text-brand-muted">Link this estate to a matter to send the probate questionnaire, pull answers back, and generate forms into the matter's documents.</p>}
      </Section>
      <Section icon={ClipboardList} title="Facts">
        <FactsForm
          facts={state.facts}
          hasMatter={Boolean(estate.matter_id)}
          busy={busy}
          onSave={facts => run(() => saveProbateFacts(estate.id, facts), 'Facts saved.')}
          onPull={overwrite => run(() => pullProbateFactsFromIntake(estate.id, { overwrite }), 'Client answers pulled in.')}
        />
        {state.sources?.length > 0 && <p className="mt-3 text-xs text-brand-muted">Sources: {state.sources.map(source => source.kind === 'returned_pdf' ? `returned form ${source.filename}` : 'portal questionnaire').join('; ')}.</p>}
      </Section>
      <Section icon={FileText} title="Court forms">
        <FormsList state={state} busy={busy} onInstall={() => run(async () => { await installProbateForms(); return getProbate(estate.id) }, 'ND probate pack installed as drafts.')} onGenerate={generate} />
      </Section>
      <Section icon={CalendarClock} title="Deadline clock">
        <Clock state={state} busy={busy} onSaveAnchors={anchors => run(() => saveProbateAnchors(estate.id, anchors), 'Dates saved.')} onBuild={mirror => run(async () => { const result = await syncProbateDeadlines(estate.id, { mirror_tasks: mirror }); const next = await getProbate(estate.id); setNotice(`${result.created.length} deadline(s) created, ${result.updated.length} moved.`); return next })} />
      </Section>
      {generating && (
        <Suspense fallback={<p role="status">Opening document editor…</p>}>
          <RenderModal key={`${estate.matter_id}:${generating.id}`} template={generating} fixedMatterId={estate.matter_id} onSaved={() => { setGenerating(null); onChanged?.() }} onClose={() => setGenerating(null)} />
        </Suspense>
      )}
    </div>
  )
}
