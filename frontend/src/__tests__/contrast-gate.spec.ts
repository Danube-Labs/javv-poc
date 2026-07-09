/**
 * The contrast GATE (issue #301): stylelint + the ratchet police token USAGE; this test polices
 * token VALUES. It parses tokens.css and computes WCAG ratios for every text-bearing pair the
 * design uses — a PR that darkens a bg or adds a failing chip pair breaks CI, not the operator's
 * eyes. Ruled exceptions (DESIGN.md §9: white-on-coral action chips) are listed explicitly.
 *
 * Pairs follow the DESIGN.md §2 text-color rules: --soft is the floor on every light surface;
 * prose on tints is --ink; chips/tags pair their own fg/bg; the sidebar has its own ramp.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

const TOKEN_RE = /--([\w-]+):\s*(#[0-9a-fA-F]{6}|rgba?\([^)]*\))/g
const tokens: Record<string, string> = {}
for (const m of css.matchAll(TOKEN_RE)) tokens[m[1] as string] = m[2] as string

type RGB = [number, number, number]

function parseColor(v: string): { rgb: RGB; alpha: number } {
  if (v.startsWith('#')) {
    const h = v.slice(1)
    return {
      rgb: [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB,
      alpha: 1,
    }
  }
  const parts = v
    .replace(/rgba?\(/, '')
    .replace(')', '')
    .split(',')
    .map((x) => parseFloat(x))
  return { rgb: [parts[0]!, parts[1]!, parts[2]!] as RGB, alpha: parts[3] ?? 1 }
}

/** rgba washes blend over their host surface before the ratio is computed. */
function blend(fg: string, overHex: string): RGB {
  const { rgb, alpha } = parseColor(fg)
  const base = parseColor(overHex).rgb
  return rgb.map((c, i) => Math.round(alpha * c + (1 - alpha) * (base[i] as number))) as RGB
}

function luminance([r, g, b]: RGB): number {
  const f = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function ratio(fgToken: string, bgToken: string, blendOver = '#ffffff'): number {
  const bgRaw = tokens[bgToken]
  const fgRaw = tokens[fgToken]
  if (!bgRaw || !fgRaw) throw new Error(`unknown token: ${!fgRaw ? fgToken : bgToken}`)
  const bg = bgRaw.startsWith('#') ? parseColor(bgRaw).rgb : blend(bgRaw, blendOver)
  const fg = parseColor(fgRaw).rgb // text tokens are solid by rule
  const [l1, l2] = [luminance(fg), luminance(bg)].sort((a, b) => b - a) as [number, number]
  return (l1 + 0.05) / (l2 + 0.05)
}

const AA = 4.5
const LIGHT_SURFACES = ['card', 'panel', 'bg', 'line2'] as const

describe('contrast gate — every text pair computed ≥4.5:1 (AA)', () => {
  it('text floor: --ink and --soft pass on every light surface', () => {
    for (const s of LIGHT_SURFACES) {
      expect.soft(ratio('ink', s), `ink on --${s}`).toBeGreaterThanOrEqual(AA)
      expect.soft(ratio('soft', s), `soft on --${s}`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('prose on tinted panels/banners: --ink passes on every tint bg', () => {
    // solid-dark chips carry white text, not ink prose — asserted separately below
    const WHITE_TEXT_BGS = new Set(['kev-bg', 'sla-over-bg'])
    const tints = Object.keys(tokens).filter((t) => /-(bg)$/.test(t) && !WHITE_TEXT_BGS.has(t))
    for (const t of tints) {
      expect.soft(ratio('ink', t), `ink on --${t}`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('severity chips: each fg on its own bg', () => {
    for (const sev of ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']) {
      expect
        .soft(ratio(`sev-${sev}-fg`, `sev-${sev}-bg`), `sev-${sev}`)
        .toBeGreaterThanOrEqual(AA)
    }
  })

  it('state pills, scanner tags, health ramp, KEV, hist: each fg on its own bg', () => {
    for (const s of ['open', 'stale', 'ack', 'resolved', 'na', 'risk']) {
      expect.soft(ratio(`state-${s}-fg`, `state-${s}-bg`), `state-${s}`).toBeGreaterThanOrEqual(AA)
    }
    for (const sc of ['trivy', 'grype']) {
      expect
        .soft(ratio(`scanner-${sc}-fg`, `scanner-${sc}-bg`), `scanner-${sc}`)
        .toBeGreaterThanOrEqual(AA)
    }
    for (const h of ['ok', 'degraded', 'down']) {
      expect.soft(ratio(`health-${h}-fg`, `health-${h}-bg`), `health-${h}`).toBeGreaterThanOrEqual(AA)
    }
    expect.soft(ratio('kev-fg', 'kev-bg'), 'kev tag').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('kev-fg', 'sla-over-bg'), 'sla overdue pill').toBeGreaterThanOrEqual(AA)
    // the only AA-legal SOLID sev chip (DESIGN.md §2: solid = critical-only)
    expect.soft(ratio('kev-fg', 'sev-critical-solid'), 'solid critical chip').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('hist-fg', 'hist-bg'), 'hist control').toBeGreaterThanOrEqual(AA)
  })

  it('special text tokens on their surfaces', () => {
    for (const s of LIGHT_SURFACES) {
      expect.soft(ratio('coral-text', s), `coral-text on --${s}`).toBeGreaterThanOrEqual(AA)
      expect.soft(ratio('teal-text', s), `teal-text on --${s}`).toBeGreaterThanOrEqual(AA)
    }
    // selected-preset wash (rgba over card)
    expect
      .soft(ratio('coral-text', 'dd-on-bg', tokens['card']), 'coral-text on dd wash')
      .toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('ver-none-fg', 'card'), 'no-fix italic').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('sla-tight-fg', 'card'), 'sla tight').toBeGreaterThanOrEqual(AA)
  })

  it('dark chrome: the sidebar text ramp on the slate', () => {
    for (const t of ['side-fg', 'side-label', 'side-credit', 'side-foot-fg', 'side-foot-dim', 'side-version', 'side-brand-fg', 'side-fg-hover', 'side-foot-strong']) {
      expect.soft(ratio(t, 'slate'), `${t} on slate`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('documents the ruled exceptions instead of testing them', () => {
    // DESIGN.md §9: white-on-coral action/selected chips (login button, tt-on) are a recorded
    // brand-contract exception (≈2.7:1) — deliberately NOT asserted here.
    expect(ratio('kev-fg', 'coral')).toBeLessThan(AA) // proves the exception is real, not stale
  })
})
