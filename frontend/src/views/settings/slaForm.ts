/**
 * SLA policy form logic (§13.3) — draft strings ↔ the SlaPolicy contract, kept pure for unit
 * tests. Contract guards (ui-foundations audit rule 2): a window only builds into the PUT body
 * when it parses to a finite number > 0 (the backend's `gt=0`), so the request can never carry
 * a value the server would 422.
 */
import type { SlaPolicy } from '@/api/generated'

export const SLA_KEYS = [
  'critical_days',
  'high_days',
  'medium_days',
  'low_days',
  'kev_days',
] as const
export type SlaKey = (typeof SLA_KEYS)[number]

/** The four severity rows (kev renders as its own override row). */
export const SLA_SEVERITY_ROWS: readonly { key: SlaKey; severity: string }[] = [
  { key: 'critical_days', severity: 'critical' },
  { key: 'high_days', severity: 'high' },
  { key: 'medium_days', severity: 'medium' },
  { key: 'low_days', severity: 'low' },
]

export type SlaDraft = Record<SlaKey, string>

export function draftFromPolicy(policy: SlaPolicy): SlaDraft {
  const draft = {} as SlaDraft
  for (const key of SLA_KEYS) draft[key] = String(policy[key] ?? '')
  return draft
}

/** Positive finite days or null — the single parse used for validity, dirt and the PUT body. */
export function parseWindow(raw: string): number | null {
  if (raw.trim() === '') return null
  const n = Number(raw.trim())
  return Number.isFinite(n) && n > 0 ? n : null
}

/** Full policy from the draft, or null while any window is invalid. */
export function policyFromDraft(draft: SlaDraft): SlaPolicy | null {
  const policy: Record<string, number> = {}
  for (const key of SLA_KEYS) {
    const value = parseWindow(draft[key])
    if (value === null) return null
    policy[key] = value
  }
  return policy as SlaPolicy
}

/** Semantic dirt: a field is dirty when its parsed value differs from the saved policy
 * (so "7" → "7.0" stays clean, while any invalid edit reads dirty and blocks save). */
export function isDirty(draft: SlaDraft, saved: SlaPolicy): boolean {
  return SLA_KEYS.some((key) => parseWindow(draft[key]) !== (saved[key] ?? null))
}
