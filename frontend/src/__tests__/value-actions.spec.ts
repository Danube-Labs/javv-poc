import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

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

  /**
   * The pixel-grid snap (issue 349 §2). The grid puts this bar on a fractional origin, which
   * smeared its 2px marks across three device pixels — differently per axis, so the plus's two
   * strokes read as different weights. jsdom has no layout, so the ARITHMETIC is pinned here
   * and the real geometry in `tests/e2e/value-actions.spec.ts`.
   */
  describe('pixel-grid snap', () => {
    const mountIn = (rect: { left: number; top: number }) => {
      const host = document.createElement('td')
      document.body.appendChild(host)
      const w = mount(ValueActions, { props: base, attachTo: host })
      const el = w.element as HTMLElement
      // jsdom always reports zeroes, so the fractional origin is supplied
      vi.spyOn(el, 'getBoundingClientRect').mockImplementation(
        () =>
          ({
            left: rect.left - (parseFloat(el.style.getPropertyValue('--snap-x')) || 0) * -1,
            top: rect.top - (parseFloat(el.style.getPropertyValue('--snap-y')) || 0) * -1,
          }) as DOMRect,
      )
      host.dispatchEvent(new MouseEvent('mouseenter'))
      return el
    }

    it('offsets by the negative fraction, so the bar lands on a whole pixel', () => {
      const el = mountIn({ left: 695.36, top: 410.25 })
      expect(el.style.getPropertyValue('--snap-x')).toBe('-0.36px')
      expect(el.style.getPropertyValue('--snap-y')).toBe('-0.25px')
    })

    it('is a no-op when the origin is already whole — no phantom transform', () => {
      const el = mountIn({ left: 700, top: 400 })
      expect(parseFloat(el.style.getPropertyValue('--snap-x'))).toBe(0)
      expect(parseFloat(el.style.getPropertyValue('--snap-y'))).toBe(0)
    })

    /** The rect it measures ALREADY includes the previous translate; without subtracting that
     *  back out, each pass would snap relative to the last and walk the bar off position. */
    it('re-measuring does not drift — the second pass agrees with the first', () => {
      const host = document.createElement('td')
      document.body.appendChild(host)
      const w = mount(ValueActions, { props: base, attachTo: host })
      const el = w.element as HTMLElement
      vi.spyOn(el, 'getBoundingClientRect').mockImplementation(() => {
        const applied = parseFloat(el.style.getPropertyValue('--snap-x')) || 0
        const appliedY = parseFloat(el.style.getPropertyValue('--snap-y')) || 0
        return { left: 695.36 + applied, top: 410.25 + appliedY } as DOMRect
      })
      host.dispatchEvent(new MouseEvent('mouseenter'))
      const first = el.style.getPropertyValue('--snap-x')
      host.dispatchEvent(new MouseEvent('mouseenter'))
      host.dispatchEvent(new MouseEvent('mouseenter'))
      expect(el.style.getPropertyValue('--snap-x')).toBe(first)
    })
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
