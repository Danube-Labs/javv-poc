/** Display formatting shared by the finding-detail panels (24h everywhere, null-tolerant). */

export function fmtAt(iso: unknown): string {
  if (typeof iso !== 'string') return '—'
  return new Date(iso).toLocaleString('en-GB', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function num(v: unknown): string {
  return typeof v === 'number' ? String(v) : '—'
}
