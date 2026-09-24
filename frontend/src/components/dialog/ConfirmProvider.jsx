import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

const ConfirmContext = createContext(null)

// Typed confirmation ignores case and surrounding spaces: the point is a
// deliberate act, not an exact-keystroke test.
const phraseMatches = (typed, phrase) => typed.trim().toLowerCase() === phrase.trim().toLowerCase()

/**
 * App-wide confirmation dialog. `confirm(options)` resolves true or false.
 *
 * Options: title, message, confirmLabel, destructive, plus two for actions
 * with wide consequences:
 *   details     — list of consequences shown under the message.
 *   requireText — a phrase the person must type before Confirm is enabled.
 */
export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null)
  const [typed, setTyped] = useState('')
  const cancelRef = useRef(null)
  const inputRef = useRef(null)
  const dialogRef = useRef(null)
  const previousFocusRef = useRef(null)

  const confirm = useCallback((options) => new Promise((resolve) => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setTyped('')
    setRequest({
      title: options?.title || 'Confirm action',
      message: typeof options === 'string' ? options : options?.message,
      details: Array.isArray(options?.details) ? options.details.filter(Boolean) : [],
      requireText: typeof options?.requireText === 'string' && options.requireText.trim() ? options.requireText.trim() : null,
      confirmLabel: options?.confirmLabel || 'Confirm',
      destructive: Boolean(options?.destructive),
      resolve,
    })
  }), [])

  const confirmReady = !request?.requireText || phraseMatches(typed, request.requireText)

  const finish = useCallback((value) => {
    request?.resolve(value)
    setRequest(null)
    setTyped('')
    queueMicrotask(() => previousFocusRef.current?.focus())
  }, [request])

  useEffect(() => {
    if (!request) return undefined
    // A typed confirmation starts in its field; otherwise the safe choice has focus.
    if (request.requireText) inputRef.current?.focus()
    else cancelRef.current?.focus()

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        finish(false)
        return
      }
      if (event.key !== 'Tab') return

      const focusable = Array.from(dialogRef.current?.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      ) || [])
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [finish, request])

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-brand-ink/50 p-4" onMouseDown={(event) => event.target === event.currentTarget && finish(false)}>
          <div ref={dialogRef} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message" className="w-full max-w-md rounded-2xl border border-brand-line bg-white p-6 shadow-xl">
            <h2 id="confirm-title" className="font-serif text-xl text-brand-ink">{request.title}</h2>
            <div id="confirm-message" className="mt-3 text-sm leading-6 text-brand-ink-2">
              {request.message && <p>{request.message}</p>}
              {request.details.length > 0 && (
                <ul className="mt-3 list-disc space-y-1.5 pl-5" data-testid="confirm-details">
                  {request.details.map((detail) => <li key={detail}>{detail}</li>)}
                </ul>
              )}
            </div>
            {request.requireText && (
              <div className="mt-5">
                <label htmlFor="confirm-phrase" className="block text-sm font-semibold text-brand-ink">
                  Type <span className="font-mono">{request.requireText}</span> to confirm
                </label>
                <input
                  ref={inputRef}
                  id="confirm-phrase"
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && confirmReady) {
                      event.preventDefault()
                      finish(true)
                    }
                  }}
                  className="mt-2 w-full rounded-lg border border-brand-line px-3 py-2 text-sm text-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-ink/20"
                />
              </div>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button ref={cancelRef} type="button" onClick={() => finish(false)} className="min-h-11 rounded-lg border border-brand-line px-4 py-2 text-sm font-semibold text-brand-ink">Cancel</button>
              <button
                type="button"
                onClick={() => confirmReady && finish(true)}
                disabled={!confirmReady}
                className={`min-h-11 rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 ${request.destructive ? 'bg-brand-rose' : 'bg-brand-ink'}`}
              >
                {request.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  const value = useContext(ConfirmContext)
  if (!value) throw new Error('useConfirm must be used within ConfirmProvider')
  return value
}
