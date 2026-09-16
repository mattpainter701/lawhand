import { useEffect, useState } from 'react'

import { getTemplateBindings, getTemplateCards } from '../../api'

/**
 * Load the binding catalogue once and group it for the picker.
 *
 * The catalogue is static server-owned vocabulary, so a failure to load it
 * degrades to name matching rather than blocking the editor.
 *
 * Cards and the flat catalogue are loaded together and neither is required:
 * cards drive the picker, while the flat catalogue still supplies tenant custom
 * fields, the collections a repeating section may iterate, and the scenario
 * lookup. Either request failing leaves the other usable.
 *
 * Shared by both visual editors. It used to live inside the Studio editor,
 * which is why for a long time the upload flow — the screen a firm reaches
 * first — had no way to say where a field's value comes from.
 *
 * `catalogueLoaded` says both requests succeeded, and it gates the fill
 * coverage read-out rather than the picker. Classification needs the flat
 * paths, the card paths and the Smart Fill vocabulary together; with any of
 * them missing every bound field looks unresolvable and every name match looks
 * like nothing, so a read-out drawn too early would tell a firm their template
 * is broken when it is fine.
 */
export default function useBindingCatalogue() {
  const [catalogue, setCatalogue] = useState({
    groups: {},
    collections: [],
    bindings: [],
    cards: [],
    smartFillNames: [],
    catalogueLoaded: false,
  })

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([getTemplateBindings(), getTemplateCards()])
      .then(([flat, cards]) => {
        if (cancelled) return
        const loaded = flat.status === 'fulfilled' ? flat.value : null
        const groups = {}
        for (const entry of loaded?.bindings || []) {
          if (!entry?.path) continue
          ;(groups[entry.group || 'Other'] ||= []).push(entry)
        }
        setCatalogue({
          groups,
          collections: loaded?.collections || [],
          bindings: loaded?.bindings || [],
          cards: cards.status === 'fulfilled' ? (cards.value?.cards || []) : [],
          smartFillNames: loaded?.smart_fill_names || [],
          catalogueLoaded: flat.status === 'fulfilled' && cards.status === 'fulfilled',
        })
      })
    return () => { cancelled = true }
  }, [])

  return catalogue
}
