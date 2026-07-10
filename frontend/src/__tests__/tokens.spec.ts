import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import {
  CHART_PTYPE_RAMP,
  CHART_SCANNER,
  CHART_SEV,
  CHART_UI,
  SEV_COLOR,
  SEVERITIES,
  STATE_COLOR,
  STATES,
} from '@/styles/tokens'

const tokensCss = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

describe('severity token map (D46 vocabulary)', () => {
  it('carries exactly the six canonical severities', () => {
    expect(SEVERITIES).toEqual(['critical', 'high', 'medium', 'low', 'negligible', 'unknown'])
  })

  it.each(SEVERITIES)('%s round-trips to CSS custom properties that exist', (sev) => {
    for (const part of ['fg', 'bg', 'line', 'solid'] as const) {
      expect(SEV_COLOR[sev][part]).toBe(`var(--sev-${sev}-${part})`)
      expect(tokensCss).toContain(`--sev-${sev}-${part}:`)
    }
  })

  it.each(SEVERITIES)('CHART_SEV.%s is pinned to the same hex as the CSS solid token', (sev) => {
    const m = tokensCss.match(new RegExp(`--sev-${sev}-solid:\\s*(#[0-9a-f]{6})`, 'i'))
    const hex = m?.[1]
    expect(hex, `--sev-${sev}-solid missing from tokens.css`).toBeDefined()
    expect(CHART_SEV[sev].toLowerCase()).toBe(hex!.toLowerCase())
  })

  it('negligible is muted, never red (A-1 ruling)', () => {
    const m = tokensCss.match(/--sev-negligible-solid:\s*#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i)
    expect(m).not.toBeNull()
    const [r = 0, g = 0, b = 0] = (m ?? []).slice(1).map((h) => parseInt(h, 16))
    expect(r, 'negligible must not read as red').toBeLessThanOrEqual(g + 16)
    expect(r).toBeLessThanOrEqual(b + 32)
  })
})

describe('chart literals stay pinned to the CSS tokens (M9c)', () => {
  const cssHex = (name: string): string | undefined =>
    tokensCss.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1]?.toLowerCase()

  it('scanner series colors equal --scanner-*-fg', () => {
    expect(CHART_SCANNER.trivy.toLowerCase()).toBe(cssHex('--scanner-trivy-fg'))
    expect(CHART_SCANNER.grype.toLowerCase()).toBe(cssHex('--scanner-grype-fg'))
  })

  it('chart chrome literals equal their named tokens', () => {
    expect(CHART_UI.axisLine.toLowerCase()).toBe(cssHex('--line'))
    expect(CHART_UI.splitLine.toLowerCase()).toBe(cssHex('--line2'))
    expect(CHART_UI.label.toLowerCase()).toBe(cssHex('--soft'))
    expect(CHART_UI.tooltipBg.toLowerCase()).toBe(cssHex('--slate'))
    expect(CHART_UI.tooltipFg.toLowerCase()).toBe(cssHex('--side-brand-fg'))
    expect(CHART_UI.segBorder.toLowerCase()).toBe(cssHex('--card'))
  })

  it('the ptype ramp anchors on --teal (brand-info categorical, never severity)', () => {
    expect(CHART_PTYPE_RAMP[0].toLowerCase()).toBe(cssHex('--teal'))
    expect(CHART_PTYPE_RAMP.length).toBeGreaterThanOrEqual(8) // covers the 8 live ptype buckets
  })
})

describe('state token map', () => {
  it.each(STATES)('%s round-trips to CSS custom properties that exist', (state) => {
    for (const part of ['fg', 'bg', 'line'] as const) {
      expect(STATE_COLOR[state][part]).toBe(`var(--state-${state}-${part})`)
      expect(tokensCss).toContain(`--state-${state}-${part}:`)
    }
  })
})
