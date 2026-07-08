/**
 * Typed mirror of the severity/status token maps in tokens.css — the ONLY sanctioned way to
 * reference severity/status colors from script (chart option-builders, dynamic styles).
 * Severity is DATA ONLY (never brand); the six keys are the D46 canonical vocabulary.
 */
export const SEVERITIES = [
  'critical',
  'high',
  'medium',
  'low',
  'negligible',
  'unknown',
] as const
export type Severity = (typeof SEVERITIES)[number]

export interface SeverityTokens {
  fg: string
  bg: string
  line: string
  solid: string
}

const sevVar = (s: Severity, part: keyof SeverityTokens): string => `var(--sev-${s}-${part})`

export const SEV_COLOR: Record<Severity, SeverityTokens> = Object.fromEntries(
  SEVERITIES.map((s) => [
    s,
    { fg: sevVar(s, 'fg'), bg: sevVar(s, 'bg'), line: sevVar(s, 'line'), solid: sevVar(s, 'solid') },
  ]),
) as Record<Severity, SeverityTokens>

/**
 * Chart series colors (ECharts SVG can't resolve CSS vars in every context, so charts use the
 * literal solid values — same hexes as tokens.css, pinned equal by the tokens unit test).
 */
export const CHART_SEV: Record<Severity, string> = {
  critical: '#c0271d',
  high: '#e2640f',
  medium: '#c68a12',
  low: '#3d7da6',
  negligible: '#6f8378',
  unknown: '#74808a',
}

export const STATES = ['open', 'stale', 'ack', 'resolved'] as const
export type StateTone = (typeof STATES)[number]

export const STATE_COLOR: Record<StateTone, { fg: string; bg: string; line: string }> =
  Object.fromEntries(
    STATES.map((s) => [
      s,
      { fg: `var(--state-${s}-fg)`, bg: `var(--state-${s}-bg)`, line: `var(--state-${s}-line)` },
    ]),
  ) as Record<StateTone, { fg: string; bg: string; line: string }>

export const SCANNER_COLOR = {
  trivy: { fg: 'var(--scanner-trivy-fg)', bg: 'var(--scanner-trivy-bg)' },
  grype: { fg: 'var(--scanner-grype-fg)', bg: 'var(--scanner-grype-bg)' },
} as const
