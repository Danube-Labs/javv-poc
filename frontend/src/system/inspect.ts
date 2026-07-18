/**
 * Data inspector (issue 406) — the pure logic behind the screen: grouping the `_cat/indices`
 * rows into the INDEX-MAP rail (append-history families collapsed to one `-*` pattern with
 * summed counts), store-level stats, and the size formatting. The backend allowlist is the
 * authority; the DENIED list here only keeps un-inspectable credential indices out of the rail.
 */

export interface CatIndexRow {
  index: string
  'docs.count'?: string
  'store.size'?: string
  'pri.store.size'?: string
  health?: string
}

export interface RailEntry {
  /** what clicking inserts into the path box — a family pattern or a literal index name */
  pattern: string
  docs: number
}

export interface RailGroups {
  history: RailEntry[]
  state: RailEntry[]
  system: RailEntry[]
}

/** time-partitioned append families (INDEX-MAP §top) — many rollover indices, one rail row each */
const HISTORY_FAMILIES = [
  'javv-finding-occurrences',
  'javv-images',
  'javv-scan-events',
  'javv-inventory-runs',
  'system-audit-log',
  'javv-metrics',
] as const

/** denied by the backend allowlist (credential material) — showing them would be a dead click */
const DENIED = new Set(['system-users', 'system-sessions', 'system-tokens'])

export function groupIndices(rows: CatIndexRow[]): RailGroups {
  const history = new Map<string, number>()
  const state: RailEntry[] = []
  const system: RailEntry[] = []
  for (const row of rows) {
    const name = row.index
    if (name.startsWith('.') || DENIED.has(name)) continue
    const docs = Number(row['docs.count'] ?? 0) || 0
    const family = HISTORY_FAMILIES.find((f) => name === f || name.startsWith(`${f}-`))
    if (family) {
      history.set(family, (history.get(family) ?? 0) + docs)
    } else if (name.startsWith('system-') || name === 'system-config') {
      system.push({ pattern: name, docs })
    } else {
      state.push({ pattern: name, docs })
    }
  }
  return {
    history: HISTORY_FAMILIES.filter((f) => history.has(f)).map((f) => ({
      pattern: `${f}-*`,
      docs: history.get(f) ?? 0,
    })),
    state: state.sort((a, b) => b.docs - a.docs),
    system: system.sort((a, b) => a.pattern.localeCompare(b.pattern)),
  }
}

/** 1234 → "1.2k", 28400000 → "28.4M" — the rail's compact count */
export function fmtDocs(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  return String(n)
}

/** bytes → "612 KB" / "2.1 GB" — budget meter + head stat */
export function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1).replace(/\.0$/, '')} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

/** total store bytes from `_cat/indices` rows (pri.store.size strings like "1.2gb") */
export function totalStoreBytes(rows: CatIndexRow[]): number {
  const UNIT: Record<string, number> = { b: 1, kb: 1024, mb: 1024 ** 2, gb: 1024 ** 3, tb: 1024 ** 4 }
  let total = 0
  for (const row of rows) {
    const raw = row['store.size'] ?? row['pri.store.size']
    const m = raw ? /^([\d.]+)(b|kb|mb|gb|tb)$/.exec(raw) : null
    if (m) total += Number(m[1]) * (UNIT[m[2] ?? 'b'] ?? 1)
  }
  return total
}
