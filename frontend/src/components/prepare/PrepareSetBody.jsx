import { Wand2 } from 'lucide-react'
import MatterPicker from './MatterPicker'
import TemplateFillProgress from '../templates/TemplateFillProgress'
import { fillValue, suggestionConfidenceLabel, suggestionOriginLabel } from '../templates/templateFillReview'
import SendStep from './SendStep'
import { buildSavedTarget } from './prepareRouting'

const inputClass = 'w-full px-3 py-2 border border-brand-line rounded text-sm bg-brand-bg text-brand-ink focus:outline-none focus:ring-1 focus:ring-brand-accent'

const groupLabel = (question) => {
  if (question.card) return question.card.replace(/[_.]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return `${question.appears_in?.[0]?.template_title || 'This document'} only`
}

// The two panes of the Prepare route for a set: the interview on the left
// (asked once, grouped by card, each question saying how many documents it
// fills) and the packet on the right (one row per member with its preview
// and save state, then one Send card per saved PDF that can be signed).
export default function PrepareSetBody({ prep, matters, matterLoading, fixedMatterId, returnTo }) {
  const {
    questions, unavailable, availableMembers, error, matterId, selectMatter, answers, setAnswer, setReviewedValues,
    toggleVerified, fieldFilter, setFieldFilter, filteredKeys, nextField, progress, requiredUnresolvedNames,
    smartFillState, smartFillMessage, refresh, previewOf, saveOf, generating, saving, generateAll, saveAll, allPreviewed, allSaved, sendable,
    session, background, saveAllInBackground,
  } = prep
  const visible = questions.filter((question) => filteredKeys.includes(question.key))
  const groups = []
  for (const question of visible) {
    const label = groupLabel(question)
    const group = groups.find((entry) => entry.label === label)
    if (group) group.questions.push(question)
    else groups.push({ label, questions: [question] })
  }
  const failedPreviews = availableMembers.filter((member) => previewOf(member).status === 'failed').map((member) => member.template_id)
  const failedSaves = availableMembers.filter((member) => saveOf(member)?.status === 'failed').map((member) => member.template_id)
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(300px,420px)_minmax(0,1fr)]">
      <div className="space-y-4">
        {error && <div role="alert" className="text-sm text-brand-rose bg-brand-rose/10 border border-brand-rose/30 px-3 py-2">{error}</div>}
        {fixedMatterId ? <p className="text-sm font-semibold">Saving to this matter</p> : <MatterPicker matters={matters} selectedMatterId={matterId} onSelect={selectMatter} loading={matterLoading} disabled={saving || generating} />}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border border-brand-line rounded bg-brand-bg px-3 py-2">
          <div>
            <p className="text-sm font-medium text-brand-ink">Smart fill</p>
            <p className="text-xs text-brand-muted">Asks each question once for the whole packet. Your entries are kept on refresh.</p>
          </div>
          <button type="button" onClick={refresh} disabled={saving || generating || smartFillState === 'loading' || !matterId.trim()} className="flex shrink-0 items-center justify-center gap-2 whitespace-nowrap px-3 py-2 text-sm text-brand-ink border border-brand-line rounded hover:bg-brand-surface-2 disabled:opacity-50">
            <Wand2 size={15} />
            {smartFillState === 'loading' ? 'Filling...' : smartFillState === 'ready' ? 'Refresh matter values' : 'Smart Fill'}
          </button>
        </div>
        {smartFillMessage && <p role="status" className="text-xs text-brand-muted">{smartFillMessage}</p>}
        {questions.length > 0 && (
          <div>
            <div className="sticky top-0 z-20 bg-brand-surface pb-2">
              <TemplateFillProgress progress={progress} requiredMissing={requiredUnresolvedNames.length} filter={fieldFilter} onFilter={setFieldFilter} onNext={nextField} />
            </div>
            {groups.map((group) => (
              <section key={group.label} aria-label={group.label} className="mb-3">
                <h3 className="text-sm font-medium text-brand-ink mb-2">{group.label}</h3>
                <div className="space-y-2">
                  {group.questions.map((question) => {
                    const review = progress.rows.find((row) => row.name === question.key)
                    const count = review?.documents || 1
                    const inputId = `set-answer-${question.key}`
                    const value = fillValue(answers[question.key])
                    return (
                      <div key={question.key}>
                        <label htmlFor={inputId} className="block text-xs font-medium text-brand-muted mb-0.5">{question.label}{question.required ? ' *' : ''}{count > 1 ? <span className="ml-2 font-normal">· Appears in {count} documents</span> : ''}</label>
                        {review && !review.present && <p className={`mb-1 text-xs font-semibold ${question.required ? 'text-brand-rose' : 'text-brand-amber'}`}>{question.required ? 'Required — missing' : 'Optional — not filled'}</p>}
                        {review?.source && <p className="mb-1 text-xs text-brand-muted">{suggestionOriginLabel(review.source)}</p>}
                        {review?.source && <div className="mb-2 flex flex-wrap items-center gap-2 text-xs"><span>{suggestionConfidenceLabel(review)}</span>{review.needsReview ? <button type="button" disabled={saving} className="rounded border border-brand-line px-2 py-1" onClick={() => setReviewedValues((prev) => ({ ...prev, [question.key]: value }))}>Confirm {question.label}</button> : <span className="text-brand-green">Reviewed</span>}</div>}
                        {question.value_kind === 'checkbox' ? (
                          <label className="inline-flex items-center gap-2 text-sm text-brand-ink py-1"><input id={inputId} type="checkbox" checked={value === 'true'} onChange={(e) => setAnswer(question.key, e.target.checked ? 'true' : 'false')} disabled={saving || allSaved} />Checked</label>
                        ) : question.value_kind === 'multiline' ? (
                          <textarea id={inputId} rows={3} value={value} onChange={(e) => setAnswer(question.key, e.target.value)} disabled={saving || allSaved} className={inputClass} placeholder={`Enter ${question.label}`} />
                        ) : (
                          <input id={inputId} type="text" value={value} onChange={(e) => setAnswer(question.key, e.target.value)} disabled={saving || allSaved} className={inputClass} placeholder={`Enter ${question.label}`} />
                        )}
                        {review?.present && (
                          <label className={`mt-1 inline-flex items-center gap-2 text-xs ${review.verified ? 'text-brand-green' : 'text-brand-muted'}`}>
                            <input type="checkbox" aria-label={`Verified: ${question.label}`} checked={Boolean(review.verified)} onChange={() => toggleVerified(question.key)} disabled={saving} className="h-3.5 w-3.5" />
                            {review.verified ? 'Verified' : 'Verify'}
                          </label>
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>
            ))}
            {visible.length === 0 && <p role="status" className="py-3 text-sm text-brand-muted">{fieldFilter === 'remaining' ? 'No missing answers.' : fieldFilter === 'unverified' ? 'Every answer is verified.' : 'No suggestions waiting for review.'}</p>}
          </div>
        )}
      </div>
      <div className="space-y-4">
        <section aria-label="Packet" className="rounded-xl border border-brand-line bg-brand-surface p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-brand-ink">Packet</h2>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => generateAll()} disabled={generating || saving || !matterId.trim() || !availableMembers.length || allSaved} className="rounded-lg border border-brand-line px-3 py-2 text-xs font-semibold disabled:opacity-50">{generating ? 'Generating…' : allPreviewed ? 'Generate all again' : 'Generate all'}</button>
              {failedPreviews.length > 0 && !generating && <button type="button" onClick={() => generateAll(failedPreviews)} className="rounded-lg border border-brand-amber px-3 py-2 text-xs font-semibold">Retry failed previews</button>}
              <button type="button" onClick={() => saveAll()} disabled={saving || generating || !allPreviewed || allSaved || background === 'saving'} className="rounded-lg bg-brand-ink px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{saving ? 'Saving…' : 'Save all to matter'}</button>
              <button type="button" onClick={saveAllInBackground} disabled={saving || generating || !allPreviewed || allSaved || background === 'saving'} title="Queue the saves on the server so you can leave this page" className="rounded-lg border border-brand-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Save all in the background</button>
              {failedSaves.length > 0 && !saving && <button type="button" onClick={() => saveAll(failedSaves)} className="rounded-lg border border-brand-amber px-3 py-2 text-xs font-semibold">Retry failed saves</button>}
            </div>
          </div>
          {background === 'saving' && <p role="status" className="mt-2 text-xs text-brand-muted">Saving in the background. You can leave this page; the matter's Documents tab shows the packet under "in progress" until every document is saved.</p>}
          {background === 'failed' && session?.last_error && <p role="alert" className="mt-2 text-xs text-brand-rose">{session.last_error}</p>}
          {session?.id && background !== 'saving' && <p className="mt-2 text-xs text-brand-muted">Your answers are available for 14 days; resume from the matter's Documents tab.</p>}
          <ul className="mt-3 space-y-2">
            {availableMembers.map((member) => {
              const preview = previewOf(member)
              const save = saveOf(member)
              const state = save?.status === 'saved' ? 'Saved' : save?.status === 'saving' ? 'Saving…' : save?.status === 'failed' ? `Save failed: ${save.error}` : preview.status === 'ready' ? 'Preview ready' : preview.status === 'loading' ? 'Previewing…' : preview.status === 'failed' ? `Preview failed: ${preview.error}` : 'Not previewed yet'
              return (
                <li key={member.template_id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-brand-line px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate"><strong>{member.title}</strong> <span className="text-xs text-brand-muted">· {member.output.format.toUpperCase()}{member.resolved_version_no ? ` · v${member.resolved_version_no}` : ''}</span></span>
                  <span role="status" className={`text-xs ${save?.status === 'saved' ? 'text-brand-green' : preview.status === 'failed' || save?.status === 'failed' ? 'text-brand-rose' : 'text-brand-muted'}`}>{state}</span>
                  {preview.status === 'ready' && preview.blob && <button type="button" onClick={() => window.open(URL.createObjectURL(preview.blob), '_blank', 'noopener')} className="text-xs underline">Open preview</button>}
                </li>
              )
            })}
            {unavailable.map((item) => (
              <li key={item.template_id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-dashed border-brand-line px-3 py-2 text-sm text-brand-muted">
                <span><strong>{item.title}</strong> · skipped</span>
                <span role="alert" className="text-xs">{item.unavailable_reason}</span>
              </li>
            ))}
          </ul>
        </section>
        {allSaved && (
          <section aria-label="Saved packet" className="rounded-xl border border-brand-line bg-brand-surface p-4 text-sm">
            <p className="font-semibold text-brand-ink">Every document is saved to the matter.</p>
            <a className="text-brand-accent underline" href={buildSavedTarget({ matterId, documentId: sendable[0]?.id || null, returnTo })}>Open the matter's documents</a>
            {sendable.length === 0 && <p className="mt-1 text-brand-muted">No document in this packet has signature fields, so there is nothing to send for signature.</p>}
          </section>
        )}
        {allSaved && sendable.map((document) => (
          <SendStep key={document.id} matterId={matterId} document={document} savedTarget={buildSavedTarget({ matterId, documentId: document.id, returnTo })} />
        ))}
      </div>
    </div>
  )
}
