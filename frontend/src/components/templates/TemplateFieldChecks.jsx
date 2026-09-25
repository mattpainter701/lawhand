import { AlertTriangle, Info } from 'lucide-react'

// Server-derived field checks (backend/app/services/template_field_quality.py).
// An accidental fill blocks publishing a PDF: its generic name ("Email",
// "Address") would put the client's details into a box that may belong to
// someone else. Label and option warnings make a template hard to fill, so
// they are listed for the author without blocking anything.
export default function TemplateFieldChecks({ quality, format }) {
  const fills = quality?.accidental_fills || []
  const warnings = quality?.warnings || []
  if (!fills.length && !warnings.length) return null
  const blocks = fills.length > 0 && ['pdf', 'image'].includes(String(format || '').toLowerCase())
  return (
    <section aria-label="Field checks" className="space-y-2 md:col-span-3">
      {fills.length > 0 && (
        <div role={blocks ? 'alert' : undefined} className="flex gap-3 rounded-xl border border-brand-amber/40 bg-brand-amber/10 p-4">
          <AlertTriangle className="mt-0.5 shrink-0 text-brand-amber" size={18} aria-hidden="true" />
          <div className="min-w-0 text-sm text-brand-ink">
            <p className="font-semibold">
              {blocks
                ? `Publishing is blocked: ${fills.length} ${fills.length === 1 ? 'field' : 'fields'} would fill with the client's details by name`
                : `${fills.length} ${fills.length === 1 ? 'field' : 'fields'} will fill with the client's details by name`}
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {fills.map(item => <li key={item.name}>{item.message}</li>)}
            </ul>
          </div>
        </div>
      )}
      {warnings.length > 0 && (
        <details className="rounded-xl border border-brand-line bg-brand-surface-2 p-4 text-sm text-brand-ink">
          <summary className="flex cursor-pointer items-center gap-2 font-semibold">
            <Info size={16} className="shrink-0 text-brand-muted" aria-hidden="true" />
            {warnings.length} {warnings.length === 1 ? 'field label needs' : 'field labels need'} attention
          </summary>
          <ul className="mt-2 list-disc space-y-0.5 pl-5 text-brand-muted">
            {warnings.map((item, index) => <li key={`${item.name}-${index}`}>{item.message}</li>)}
          </ul>
        </details>
      )}
    </section>
  )
}
