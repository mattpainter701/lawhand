import { useCallback, useEffect, useRef, useState } from 'react'
import { writeFillSession } from '../../api'

// One write at a time: an older response must never overwrite a newer answer,
// or create a second session while the first create is still in flight.
export default function useFillDraft({ payload, sessionRef, onCreated }) {
  const [status, setStatus] = useState('idle')
  const latest = useRef(null)
  const lastSaved = useRef('')
  const inFlight = useRef(null)
  const mounted = useRef(true)
  const created = useRef(onCreated)
  const flushRef = useRef(null)
  const key = payload ? JSON.stringify(payload) : ''
  useEffect(() => { created.current = onCreated }, [onCreated])

  const flush = useCallback(async () => {
    if (inFlight.current) return inFlight.current
    const operation = (async () => {
      while (true) {
        const snapshot = latest.current
        if (!snapshot || snapshot.key === lastSaved.current) return true
        if (mounted.current) setStatus('saving')
        try {
          const value = await writeFillSession({
            ...snapshot.payload,
            ...(sessionRef.current?.id ? { id: sessionRef.current.id } : {}),
          })
          sessionRef.current = value
          lastSaved.current = snapshot.key
          if (mounted.current) {
            setStatus('saved')
            created.current?.(value.id)
          }
        } catch {
          if (mounted.current) setStatus('error')
          return false
        }
        // Edits made during the request are queued, including a final edit made
        // immediately before navigating away. A failed unchanged write waits for Retry.
        if (!latest.current || latest.current.key === lastSaved.current) return true
      }
    })()
    inFlight.current = operation
    try {
      return await operation
    } finally {
      if (inFlight.current === operation) inFlight.current = null
    }
  }, [sessionRef])
  useEffect(() => { flushRef.current = flush }, [flush])

  useEffect(() => {
    latest.current = key ? { key, payload: JSON.parse(key) } : null
    if (!key || key === lastSaved.current) return undefined
    setStatus('pending')
    const timer = setTimeout(flush, 800)
    return () => clearTimeout(timer)
  }, [key, flush])

  useEffect(() => {
    mounted.current = true
    const beforeUnload = event => {
      if (latest.current && latest.current.key !== lastSaved.current) {
        event.preventDefault()
        event.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      mounted.current = false
      window.removeEventListener('beforeunload', beforeUnload)
      void flushRef.current?.()
    }
  }, [])

  return { status, retry: flush, flush }
}
