/**
 * The FR-7 panel gates: justification chips appear iff not_affected is the target; Save stays
 * disabled until the draft is legal; no can_triage → everything read-only; T<now → read-only
 * with the history note; risk-accept button exists only with can_accept_audit_final.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TriagePanel from '@/components/triage/TriagePanel.vue'
import type { FindingRow } from '@/stores/findings'

const finding: FindingRow = {
  finding_key: 'k1',
  cve_id: 'CVE-2024-0001',
  scanner: 'trivy',
  severity: 'HIGH',
  severity_canonical: 'high',
  image_repo: 'nginx',
  tag: '1.25',
  package_name: 'openssl',
  installed_version: '3.0.1',
  fixed_version: null,
  fixable: false,
  epss: null,
  kev: false,
  ptype: null,
  state: 'open',
  overdue: false,
  due_at: null,
}

function panel(over: Record<string, unknown> = {}) {
  return mount(TriagePanel, {
    props: {
      finding,
      canTriage: true,
      canAcceptFinal: false,
      historical: false,
      saving: false,
      error: null,
      currentUser: 'admin',
      ...over,
    },
  })
}

const save = (w: ReturnType<typeof panel>) => w.find('.btn-primary')

describe('TriagePanel (FR-7 gates)', () => {
  it('vex chips appear only when not_affected is the target; save blocked until one is picked', async () => {
    const w = panel()
    expect(w.find('.vex-chips').exists()).toBe(false)
    await w.findAll('.state-opt').find((b) => b.text() === 'Not affected')!.trigger('click')
    expect(w.find('.vex-chips').exists()).toBe(true)
    expect((save(w).element as HTMLButtonElement).disabled).toBe(true)
    expect(w.text()).toContain('requires a justification')

    await w.findAll('.vex-chip')[0]!.trigger('click')
    expect((save(w).element as HTMLButtonElement).disabled).toBe(false)
    await save(w).trigger('click')
    expect(w.emitted('save')![0]![0]).toEqual({
      state: 'not_affected',
      vex_justification: 'component_not_present',
    })
  })

  it('switching away from not_affected clears the justification from the draft', async () => {
    const w = panel()
    await w.findAll('.state-opt').find((b) => b.text() === 'Not affected')!.trigger('click')
    await w.findAll('.vex-chip')[0]!.trigger('click')
    await w.findAll('.state-opt').find((b) => b.text() === 'Acknowledge')!.trigger('click')
    expect(w.find('.vex-chips').exists()).toBe(false)
    await save(w).trigger('click')
    expect(w.emitted('save')![0]![0]).toEqual({ state: 'acknowledged' })
  })

  it('no can_triage → controls disabled and the locked note names the capability', () => {
    const w = panel({ canTriage: false })
    expect(w.text()).toContain('can_triage')
    for (const b of w.findAll('.state-opt'))
      expect((b.element as HTMLButtonElement).disabled).toBe(true)
    expect((save(w).element as HTMLButtonElement).disabled).toBe(true)
  })

  it('T<now → read-only with the history note, even with can_triage', () => {
    const w = panel({ historical: true })
    expect(w.text()).toContain('Viewing history')
    expect((save(w).element as HTMLButtonElement).disabled).toBe(true)
  })

  it('risk-accept button renders only with can_accept_audit_final', () => {
    expect(panel().find('.btn-ghost').exists()).toBe(false)
    const w = panel({ canAcceptFinal: true })
    expect(w.find('.btn-ghost').text()).toContain('Risk-accept')
  })

  it('notes-only draft saves without a state change', async () => {
    const w = panel()
    await w.find('#triage-notes').setValue('looked into it')
    await save(w).trigger('click')
    expect(w.emitted('save')![0]![0]).toEqual({ notes: 'looked into it' })
  })
})
