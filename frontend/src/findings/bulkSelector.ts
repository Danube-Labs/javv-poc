/**
 * Grid lens → M5d bulk selector (M9b slice 4). The shipped contract is SELECTOR-based (a frozen
 * server-side id-set from cve_id/image_digest/severity/state/assignee predicates) — NOT a list
 * of checked rows. Anything the selector can't express (scanner, KEV/fixable/disagree flags,
 * namespace, image_repo, ptype, multi-value severity/state) must BLOCK the bulk action, never
 * silently widen it: a selector that ignores an active filter would triage MORE rows than the
 * operator is looking at.
 */
import type { FilterField } from '@/filters/fields.config'

export interface BulkSelector {
  severity?: string
  state?: string
  assignee?: string
}

export interface LensResult {
  selector: BulkSelector | null
  /** User-facing reason the current lens is not bulk-expressible (null = expressible). */
  blocked: string | null
}

/** Selector-expressible filter keys and how they map. */
const EXPRESSIBLE: Record<string, keyof BulkSelector> = {
  severity: 'severity',
  state: 'state',
  assignee: 'assignee',
}

export function lensToSelector(
  fields: readonly FilterField[],
  selections: Record<string, string[]>,
): LensResult {
  const selector: BulkSelector = {}
  const inexpressible: string[] = []
  let multi: string | null = null

  for (const field of fields) {
    const values = selections[field.key] ?? []
    if (values.length === 0) continue
    const target = EXPRESSIBLE[field.key]
    if (!target) {
      inexpressible.push(field.label)
    } else if (values.length > 1) {
      multi = field.label
    } else {
      selector[target] = values[0]
    }
  }

  if (inexpressible.length > 0) {
    return {
      selector: null,
      blocked:
        `${inexpressible.join(', ')} ${inexpressible.length === 1 ? 'is' : 'are'} not part of ` +
        'the bulk selector — bulk would apply wider than what you see. Clear those filters first.',
    }
  }
  if (multi) {
    return {
      selector: null,
      blocked: `bulk takes exactly one ${multi} value — narrow to a single selection`,
    }
  }
  if (Object.keys(selector).length === 0) {
    return {
      selector: null,
      blocked: 'no filters active — bulk over the whole cluster is refused. Filter first.',
    }
  }
  return { selector, blocked: null }
}
