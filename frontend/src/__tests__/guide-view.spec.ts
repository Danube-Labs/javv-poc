/**
 * The Guide page (issue 341): every "On this page" row lands on a section the page renders, a
 * row keeps the range and the cluster in the URL, and the two routing rules that make a
 * `#section` link work: the shell's re-stamp keeps the hash, and only arriving at a hash scrolls.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { GUIDE_SECTIONS, guideHref } from '@/about/guide'
import { restampLocation } from '@/system/globalUrl'
import { hashScroll } from '@/system/hashScroll'
import GuideView from '@/views/GuideView.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

beforeEach(() => setActivePinia(createPinia()))

describe('GuideView', () => {
  async function mounted() {
    await router.push('/guide?cluster=c-1&win=7')
    const w = mount(GuideView, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }

  it('is titled How to read JAVV', async () => {
    expect((await mounted()).find('h1').text()).toBe('How to read JAVV')
  })

  it('renders one card per section, each under its anchor id', async () => {
    const w = await mounted()
    const titles = GUIDE_SECTIONS.map((s) => w.find(`#${s.id} h2`).text())
    expect(titles).toEqual(GUIDE_SECTIONS.map((s) => s.title))
  })

  it('every On this page row targets a section the page renders, in order', async () => {
    const w = await mounted()
    const nav = w.find('nav[aria-label="On this page"]')
    const rows = nav.findAll('a.snav-item')
    expect(rows.map((r) => r.text())).toEqual(GUIDE_SECTIONS.map((s) => s.title))
    const missing = rows
      .map((r) => r.attributes('href')!.split('#')[1]!)
      .filter((hash) => !w.find(`#${hash}`).exists())
    expect(missing).toEqual([])
  })

  it('a row keeps the range and the cluster in the URL', async () => {
    const href = (await mounted()).find('a.snav-item').attributes('href')!
    expect(href).toContain('cluster=c-1')
    expect(href).toContain('win=7')
  })

  it('links into the Guide by section id', () => {
    expect(guideHref('glossary')).toBe('/guide#glossary')
  })
})

describe('restampLocation', () => {
  it('keeps the hash while it sets the global keys', () => {
    const loc = restampLocation({ guide: 'x' }, '#glossary', { win: '7' }, 'c-1')
    expect(loc.hash).toBe('#glossary')
    expect(loc.query).toEqual({ guide: 'x', t: undefined, win: '7', cluster: 'c-1' })
  })
})

describe('hashScroll', () => {
  const at = (path: string, hash = '') => ({ path, hash })

  it('scrolls when arriving at a section from another page', () => {
    expect(hashScroll(at('/guide', '#triage'), at('/findings'))).toEqual({ el: '#triage', top: 16 })
  })
  it('scrolls when moving to another section on the same page', () => {
    expect(hashScroll(at('/guide', '#triage'), at('/guide', '#glossary'))).toEqual({
      el: '#triage',
      top: 16,
    })
  })
  it('does not scroll on a query-only replace that keeps the hash', () => {
    expect(hashScroll(at('/guide', '#triage'), at('/guide', '#triage'))).toBe(false)
  })
  it('leaves every other navigation where it was', () => {
    expect(hashScroll(at('/findings'), at('/guide', '#triage'))).toBe(false)
  })
})
