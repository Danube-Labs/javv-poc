/**
 * The Guide's "learn more" pointer (issue 341): both shapes land on the named section's
 * anchor, the popover shows that section's own title and summary (read from GUIDE_SECTIONS,
 * so a renamed section can't leave a stale popover), and following the link closes it.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { GUIDE_SECTIONS } from '@/about/guide'
import GuideLink from '@/components/about/GuideLink.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

const section = (id: string) => GUIDE_SECTIONS.find((s) => s.id === id)!

describe('GuideLink', () => {
  it('link: inline words pointing at the section anchor', async () => {
    const w = mount(GuideLink, {
      props: { section: 'scans-and-freshness', label: 'What this means' },
      global: { plugins: [router] },
    })
    await flushPromises()
    const a = w.find('a.gl-text')
    expect(a.text()).toBe('What this means')
    expect(a.attributes('href')).toBe('/guide#scans-and-freshness')
  })

  it('popover: closed until the icon is pressed, and the icon names the section', async () => {
    const w = mount(GuideLink, {
      props: { section: 'time-range', variant: 'popover' },
      global: { plugins: [router] },
    })
    const btn = w.find('button.gl-icon')
    expect(btn.attributes('aria-expanded')).toBe('false')
    expect(btn.attributes('aria-label')).toBe(`How to read this: ${section('time-range').title}`)
    expect(w.find('.gl-pop').exists()).toBe(false)
  })

  it("popover: shows the section's title and summary and links to its anchor", async () => {
    const w = mount(GuideLink, {
      props: { section: 'time-range', variant: 'popover' },
      global: { plugins: [router] },
    })
    await w.find('button.gl-icon').trigger('click')
    const pop = w.find('.gl-pop')
    expect(pop.attributes('role')).toBe('dialog')
    expect(pop.find('.gl-pop-title').text()).toBe(section('time-range').title)
    expect(pop.find('.gl-pop-body').text()).toBe(section('time-range').summary)
    expect(pop.find('a.gl-pop-link').attributes('href')).toBe('/guide#time-range')
    expect(w.find('button.gl-icon').attributes('aria-expanded')).toBe('true')
  })

  it('popover: following the link closes it', async () => {
    const w = mount(GuideLink, {
      props: { section: 'time-range', variant: 'popover' },
      global: { plugins: [router] },
    })
    await w.find('button.gl-icon').trigger('click')
    await w.find('a.gl-pop-link').trigger('click')
    await flushPromises()
    expect(w.find('button.gl-icon').attributes('aria-expanded')).toBe('false')
  })

  it('has no em dash in either shape', async () => {
    const link = mount(GuideLink, {
      props: { section: 'triage' },
      global: { plugins: [router] },
    })
    const pop = mount(GuideLink, {
      props: { section: 'triage', variant: 'popover' },
      global: { plugins: [router] },
    })
    await pop.find('button.gl-icon').trigger('click')
    expect(link.text()).not.toContain('—')
    expect(pop.text()).not.toContain('—')
  })
})
