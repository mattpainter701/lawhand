import { Check, Circle, CircleDot, Lock } from 'lucide-react'

// The route's progress rail. Every state is derived from the fill hook, so
// the rail, the progress bar and the Save button can never disagree about
// how far along a document is (one derivation, one number).
// `signing`, when given, appends a Send step: `{ pdf, sent }` says whether the
// output being prepared can be sent for signature (only a PDF can) and
// whether the request has gone out.
export function prepareSteps({ template, matterId, progress, requiredMissing, previewReady, saved, signing = null }) {
  const hasTemplate = Boolean(template)
  const hasMatter = Boolean(String(matterId || '').trim())
  const populated = hasMatter && requiredMissing === 0
  const steps = [
    { key: 'select', label: 'Template', state: hasTemplate ? 'done' : 'current', note: template?.title || 'Choose a published template' },
    { key: 'matter', label: 'Matter', state: !hasTemplate ? 'todo' : hasMatter ? 'done' : 'current', note: hasMatter ? 'Chosen' : 'Choose the destination matter' },
    {
      key: 'populate',
      label: 'Populate',
      state: !hasMatter ? 'todo' : populated ? 'done' : 'current',
      note: !hasMatter ? '' : progress ? `${progress.completed} of ${progress.total} filled${requiredMissing ? `, ${requiredMissing} required missing` : ''}` : '',
    },
    { key: 'review', label: 'Review', state: !populated ? 'todo' : previewReady ? 'done' : 'current', note: previewReady ? 'Previewed' : 'Preview the exact document' },
    { key: 'save', label: 'Save', state: !previewReady ? 'todo' : saved ? 'done' : 'current', note: saved ? 'Saved to the matter' : 'Save to the matter' },
  ]
  if (signing) {
    steps.push({
      key: 'send',
      label: 'Send',
      state: signing.sent ? 'done' : saved && signing.pdf ? 'current' : 'todo',
      note: signing.sent ? 'Sent for signature' : signing.pdf ? 'Send for signature' : 'Needs PDF output to send for signature',
    })
  }
  return steps
}

const ICONS = { done: Check, current: CircleDot, todo: Circle, blocked: Lock }

export default function PrepareStepper({ steps }) {
  return (
    <nav aria-label="Prepare steps" className="rounded-xl border border-brand-line bg-brand-surface-2 px-3 py-2">
      <ol className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {steps.map((step, index) => {
          const Icon = ICONS[step.state] || Circle
          return (
            <li key={step.key} aria-current={step.state === 'current' ? 'step' : undefined} className={`flex items-center gap-2 ${step.state === 'todo' ? 'text-brand-muted' : 'text-brand-ink'}`}>
              <Icon size={15} aria-hidden="true" className={step.state === 'done' ? 'text-brand-green' : step.state === 'current' ? 'text-brand-accent' : ''} />
              <span className="font-semibold">{index + 1}. {step.label}</span>
              {step.note && <span className="text-xs text-brand-muted">{step.note}</span>}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
