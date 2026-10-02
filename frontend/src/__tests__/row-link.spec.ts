/**
 * RowLink (issue 674): the identifier of a clickable row is a real link, so a row can be
 * opened from the keyboard, while the row keeps one way of opening.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'

import RowLink from '@/components/ui/RowLink.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { render: () => null } },
    { path: '/findings/:cveId', name: 'finding', component: { render: () => null } },
  ],
})
const to = { name: 'finding', params: { cveId: 'CVE-2024-1' }, query: { scanner: 'trivy' } }

function mountInRow() {
  const rowClick = vi.fn<() => void>()
  const open = vi.fn<() => void>()
  const w = mount(
    defineComponent({
      render: () => h('table', h('tbody', h('tr', { onClick: rowClick }, h('td', h(RowLink, { to, onOpen: open }, () => 'CVE-2024-1'))))),
    }),
    { global: { plugins: [router] }, attachTo: document.body },
  )
  return { w, rowClick, open, a: w.get('a') }
}

describe('RowLink', () => {
  it('is a real link to the route, so it can be focused, read as a link and opened in a new tab', () => {
    const { a } = mountInRow()
    expect(a.attributes('href')).toBe('/findings/CVE-2024-1?scanner=trivy')
    expect(a.text()).toBe('CVE-2024-1')
    ;(a.element as HTMLAnchorElement).focus()
    expect(document.activeElement).toBe(a.element)
  })

  it('a plain click opens through the row handler the caller passes, once', async () => {
    const { a, open, rowClick } = mountInRow()
    const e = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    a.element.dispatchEvent(e)
    expect(open).toHaveBeenCalledTimes(1)
    expect(e.defaultPrevented).toBe(true) // no full page load
    expect(rowClick).not.toHaveBeenCalled() // the row would have opened it a second time
  })

  it('Enter on the focused link is a click, so the keyboard opens the row', async () => {
    const { a, open } = mountInRow()
    // browsers turn Enter on a focused anchor into a click event
    await a.trigger('click')
    expect(open).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['ctrl', { ctrlKey: true }],
    ['meta', { metaKey: true }],
    ['shift', { shiftKey: true }],
    ['middle button', { button: 1 }],
  ])('a %s click is left to the browser (new tab) and opens nothing here', (_name, init) => {
    const { a, open, rowClick } = mountInRow()
    const e = new MouseEvent('click', { bubbles: true, cancelable: true, ...init })
    a.element.dispatchEvent(e)
    expect(open).not.toHaveBeenCalled()
    expect(e.defaultPrevented).toBe(false)
    expect(rowClick).not.toHaveBeenCalled()
  })
})
