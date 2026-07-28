import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ValueActions from '@/components/filters/ValueActions.vue'

/**
 * The include/exclude pair (issue 349 §2). Tested as a pure unit — what it emits and what a
 * screen reader hears — never through a host screen.
 */
describe('ValueActions', () => {
  const base = { field: 'Namespace', value: 'kube-system' }
  const btns = (w: ReturnType<typeof mount>) => w.findAll('.val-act-btn')

  it('offers both sides and emits the mode it was asked for', async () => {
    const w = mount(ValueActions, { props: base })
    expect(btns(w)).toHaveLength(2)
    await btns(w)[0]!.trigger('click')
    await btns(w)[1]!.trigger('click')
    expect(w.emitted('pick')).toEqual([['is'], ['not']])
  })

  it('names the field AND the value, so the action is never a bare "exclude"', () => {
    const w = mount(ValueActions, { props: base })
    expect(btns(w)[0]!.attributes('aria-label')).toBe('Filter to Namespace kube-system')
    expect(btns(w)[1]!.attributes('aria-label')).toBe('Filter out Namespace kube-system')
  })

  it('the active side reads as pressed, and its label offers the undo', () => {
    const w = mount(ValueActions, { props: { ...base, active: 'not' } })
    expect(btns(w)[1]!.classes()).toContain('val-act-on')
    expect(btns(w)[1]!.attributes('aria-pressed')).toBe('true')
    expect(btns(w)[1]!.attributes('aria-label')).toBe(
      'Clear exclusion of Namespace kube-system',
    )
    expect(btns(w)[0]!.attributes('aria-pressed')).toBe('false')
  })

  it('drops the include side where the host already owns it (the rail row click)', () => {
    const w = mount(ValueActions, { props: { ...base, excludeOnly: true } })
    expect(btns(w)).toHaveLength(1)
    expect(btns(w)[0]!.attributes('aria-label')).toBe('Filter out Namespace kube-system')
  })

  /** `.fpill-x`, the pattern this follows, is mouse-only. This one must not repeat that. */
  it('is operable by keyboard, unlike the .fpill-x it is modelled on', async () => {
    const w = mount(ValueActions, { props: base })
    expect(btns(w)[1]!.attributes('tabindex')).toBe('0')
    await btns(w)[1]!.trigger('keydown.enter')
    await btns(w)[1]!.trigger('keydown.space')
    expect(w.emitted('pick')).toEqual([['not'], ['not']])
  })

  /** It nests inside the rail row's <button>; an un-stopped click would also toggle the row. */
  it('never lets its click reach the host row', async () => {
    let hostClicks = 0
    const w = mount(
      {
        components: { ValueActions },
        template: `<button @click="$emit('host')"><ValueActions v-bind="p" /></button>`,
        props: ['p'],
      },
      { props: { p: base }, attrs: { onHost: () => (hostClicks += 1) } },
    )
    await w.find('.val-act-btn').trigger('click')
    expect(hostClicks).toBe(0)
  })
})
