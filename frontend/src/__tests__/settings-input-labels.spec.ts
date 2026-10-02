/**
 * Every settings input announces a name (issue 674: fourteen number fields were a bare text
 * field to a screen reader, because the visible label sits beside the control, not around it).
 */
import { mount } from '@vue/test-utils'
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'

import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'

const row = (props: Record<string, unknown>, slots: Record<string, () => unknown> = {}) =>
  mount(
    defineComponent({
      render: () =>
        h(SettingsRow, props, { default: () => h(SettingsInput, { modelValue: '7', num: true }), ...slots }),
    }),
  )

/** the text a screen reader reads for an `aria-labelledby` / `aria-describedby` reference */
const referenced = (w: ReturnType<typeof row>, attr: string) =>
  w.get(`[id="${w.get('input').attributes(attr)}"]`).text()

describe('a SettingsInput inside a SettingsRow', () => {
  it('is named by the row title', () => {
    const w = row({ label: 'Max age' })
    expect(referenced(w, 'aria-labelledby')).toBe('Max age')
  })

  it('is described by the row hint when there is one', () => {
    const w = row({ label: 'KEV override', hint: 'Fractions work: 0.5 is 12 hours.' })
    expect(referenced(w, 'aria-describedby')).toBe('Fractions work: 0.5 is 12 hours.')
  })

  it('points at no hint when the row has none', () => {
    expect(row({ label: 'Max docs' }).get('input').attributes('aria-describedby')).toBeUndefined()
  })

  it('is named by a rich label slot too (the SLA rows use a severity chip)', () => {
    const w = row({}, { label: () => h('b', 'critical') })
    expect(referenced(w, 'aria-labelledby')).toBe('critical')
  })

  it('two rows on one page get different ids', () => {
    const w = mount(
      defineComponent({
        render: () =>
          h('div', [
            h(SettingsRow, { label: 'A' }, () => h(SettingsInput, { modelValue: '1' })),
            h(SettingsRow, { label: 'B' }, () => h(SettingsInput, { modelValue: '2' })),
          ]),
      }),
    )
    const [a, b] = w.findAll('input').map((i) => i.attributes('aria-labelledby'))
    expect(a).toBeTruthy()
    expect(a).not.toBe(b)
  })
})

describe('a SettingsInput outside a row', () => {
  it('claims no row label, so the caller must bind one', () => {
    const w = mount(SettingsInput, { props: { modelValue: 'x', id: 'inv-name' } })
    expect(w.get('input').attributes('aria-labelledby')).toBeUndefined()
    expect(w.get('input').attributes('id')).toBe('inv-name')
  })

  it('every such use in the settings views carries an id that a label points at', () => {
    const dir = resolve(process.cwd(), 'src/views/settings')
    const loose: string[] = []
    for (const file of readdirSync(dir).filter((f) => f.endsWith('.vue'))) {
      const src = readFileSync(resolve(dir, file), 'utf8')
      // drop every row with its contents; what is left must be labelled by hand
      const outsideRows = src.replace(/<SettingsRow[\s\S]*?<\/SettingsRow>/g, '')
      for (const m of outsideRows.matchAll(/<SettingsInput\b([^>]*)>/g)) {
        const id = m[1]!.match(/\bid="([^"]+)"/)?.[1]
        if (!id || !src.includes(`for="${id}"`)) loose.push(`${file}: <SettingsInput${m[1]!.slice(0, 40)}`)
      }
    }
    expect(loose).toEqual([])
  })
})
