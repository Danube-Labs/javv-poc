/** Pure filter layer for the Running-images screen (unit-tested): the committed inventory is
 * one run's rows, fully served — matching + bucket counts derive from those rows (IMAGE
 * counts). Severity buckets use the canonical vocabulary mapped from the doc's short keys. */
import type { Selections } from '@/filters/fields.config'
import type { ImageRow } from '@/stores/images'
import type { Severity } from '@/styles/tokens'

const SEV_OF_DOC: readonly [Severity, keyof ImageRow][] = [
  ['critical', 'crit'],
  ['high', 'high'],
  ['medium', 'med'],
  ['low', 'low'],
  ['negligible', 'negligible'],
  ['unknown', 'unknown'],
]

const sevCount = (row: ImageRow, sev: Severity): number => {
  const key = SEV_OF_DOC.find(([s]) => s === sev)![1]
  return (row[key] as number) ?? 0
}

interface Bucket {
  key: string
  count: number
  by_scanner: Record<string, number>
}

/** FacetsResponse-shaped buckets for the rail/bar — counts are images, not findings. */
export function imagesFacets(rows: ImageRow[]): Record<string, Bucket[]> {
  const bucket = (key: string, count: number): Bucket => ({ key, count, by_scanner: {} })
  const severity = SEV_OF_DOC.map(([sev]) =>
    bucket(sev, rows.filter((r) => sevCount(r, sev) > 0).length),
  ).filter((b) => b.count > 0)
  const scanners = ['trivy', 'grype'].map((s) =>
    bucket(s, rows.filter((r) => r.scanners.includes(s)).length),
  )
  const nsCounts = new Map<string, number>()
  for (const r of rows) for (const ns of r.namespaces) nsCounts.set(ns, (nsCounts.get(ns) ?? 0) + 1)
  const namespaces = [...nsCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([ns, n]) => bucket(ns, n))
  return { severity, scanner: scanners, namespaces }
}

/** Selections → the matching inventory rows. Multi-value fields OR within, AND across. */
export function filterImages(rows: ImageRow[], sel: Selections): ImageRow[] {
  const q = (sel.q?.[0] ?? '').toLowerCase()
  const sevs = (sel.severity ?? []) as Severity[]
  const scanners = sel.scanner ?? []
  const attrs = sel.attr ?? []
  const namespaces = sel.namespace ?? []
  return rows.filter((r) => {
    if (q && !`${r.image_repo} ${r.tag} ${r.namespaces.join(' ')}`.toLowerCase().includes(q))
      return false
    if (sevs.length > 0 && !sevs.some((s) => sevCount(r, s) > 0)) return false
    if (scanners.length > 0 && !scanners.some((s) => r.scanners.includes(s))) return false
    if (attrs.includes('fixable') && !(r.fixable > 0)) return false
    if (namespaces.length > 0 && !namespaces.some((ns) => r.namespaces.includes(ns))) return false
    return true
  })
}

/** The filtered rows as CSV (the list export — inventory rows, already served). */
export function imagesCsv(rows: ImageRow[]): string {
  const esc = (v: unknown) => {
    const s = String(v ?? '')
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s
  }
  const header = [
    'image_repo', 'tag', 'image_digest', 'namespaces', 'scanners', 'critical', 'high', 'medium',
    'low', 'negligible', 'unknown', 'total', 'fixable', 'trivy_count', 'grype_count',
    'count_delta', 'replicas', 'last_seen',
  ]
  const line = (r: ImageRow) =>
    [
      r.image_repo, r.tag, r.image_digest, r.namespaces.join(' '), r.scanners.join(' '), r.crit,
      r.high, r.med, r.low, r.negligible, r.unknown, r.total, r.fixable, r.trivy_count ?? '',
      r.grype_count ?? '', r.count_delta ?? '', r.replicas, r['@timestamp'],
    ]
      .map(esc)
      .join(',')
  return [header.join(','), ...rows.map(line)].join('\n')
}
