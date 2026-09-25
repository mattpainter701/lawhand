import { useEffect, useRef, useState } from 'react'
import { getTemplateSource } from '../../api'

// The stored source PDF of a template, loaded the first time a view needs it
// and kept while the template is unchanged, so switching views does not
// download it again. `failed` lets the caller fall back to a view that does
// not need the file.
export default function useTemplateSourceBlob(template, enabled) {
  const key = template?.id ? `${template.id}:${template.source_sha256 || ''}:${template.source_filename || ''}` : ''
  const [state, setState] = useState({ key: '', blob: null, failed: false })
  const requested = useRef('')
  const loaded = useRef('')
  useEffect(() => {
    if (!enabled || !key || requested.current === key || loaded.current === key) return undefined
    requested.current = key
    let cancelled = false
    getTemplateSource(template.id, template.source_filename)
      .then((blob) => { if (!cancelled) { loaded.current = key; setState({ key, blob, failed: false }) } })
      .catch(() => { if (!cancelled) { loaded.current = key; setState({ key, blob: null, failed: true }) } })
    return () => {
      cancelled = true
      // A load abandoned by a template change may be requested again later.
      if (requested.current === key) requested.current = ''
    }
  }, [enabled, key, template?.id, template?.source_filename])
  return state.key === key ? { blob: state.blob, failed: state.failed } : { blob: null, failed: false }
}
