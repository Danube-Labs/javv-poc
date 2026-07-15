/**
 * Scan-scope form logic (§13.1, D43/FR-24) — pure, unit-tested. The draft is four chip lists;
 * FR-24 semantics are fixed server-side (empty include = all, ignore wins) — the form only
 * normalizes (trim, drop empties, dedupe preserving order) and diffs.
 */
export interface ScopeDraft {
  include_namespaces: string[]
  ignore_namespaces: string[]
  exclude_images: string[]
  ignore_kinds: string[]
}

export const SCOPE_KEYS = [
  'include_namespaces',
  'ignore_namespaces',
  'exclude_images',
  'ignore_kinds',
] as const

export function emptyScope(): ScopeDraft {
  return { include_namespaces: [], ignore_namespaces: [], exclude_images: [], ignore_kinds: [] }
}

/** Add one chip: trimmed, non-empty, deduped. Returns the same array when nothing changes. */
export function addChip(items: string[], raw: string): string[] {
  const value = raw.trim()
  if (value === '' || items.includes(value)) return items
  return [...items, value]
}

export function removeChip(items: string[], value: string): string[] {
  return items.filter((item) => item !== value)
}

export function scopeDirty(draft: ScopeDraft, saved: ScopeDraft): boolean {
  return SCOPE_KEYS.some(
    (key) =>
      draft[key].length !== saved[key].length ||
      draft[key].some((item, i) => item !== saved[key][i]),
  )
}

export function cloneScope(scope: ScopeDraft): ScopeDraft {
  return {
    include_namespaces: [...scope.include_namespaces],
    ignore_namespaces: [...scope.ignore_namespaces],
    exclude_images: [...scope.exclude_images],
    ignore_kinds: [...scope.ignore_kinds],
  }
}
