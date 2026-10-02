/**
 * The command palette's screen rows (issue 681): every screen showed the same grid icon, so the
 * list had to be read word by word. Each row now carries the icon the sidebar shows for that
 * screen, from the one nav model, so the two cannot drift apart.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import CommandPalette from '@/components/chrome/CommandPalette.vue'
import { visibleNav } from '@/components/chrome/navModel'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})
const AppIcon = { props: ['name'], template: '<i class="icon" :data-icon="name" />' }

async function palette(capabilities: string[]) {
  const auth = useAuthStore()
  auth.user = { username: 'a', role: 'x', capabilities, must_change: false } as never
  const w = mount(CommandPalette, {
    global: { plugins: [router], stubs: { AppIcon, Teleport: true } },
  })
  await flushPromises()
  return w
}
const screenRows = (w: Awaited<ReturnType<typeof palette>>) =>
  w.findAll('.cp-row').map((r) => [r.find('.cp-label').text(), r.find('.icon').attributes('data-icon')])

beforeEach(() => setActivePinia(createPinia()))

describe('CommandPalette screen rows', () => {
  it("shows each screen with the sidebar's own icon for it", async () => {
    const w = await palette(['can_manage_settings', 'can_inspect_store'])
    const nav = visibleNav(useAuthStore().hasCapability).flatMap((g) => g.items.map((i) => [i.label, i.icon]))
    expect(screenRows(w)).toEqual(nav)
    expect(new Set(nav.map(([, icon]) => icon)).size).toBeGreaterThan(5) // not one icon for all
  })

  it('lists only the screens the user may open, still with their own icons', async () => {
    const w = await palette([])
    const nav = visibleNav(() => false).flatMap((g) => g.items.map((i) => [i.label, i.icon]))
    expect(screenRows(w)).toEqual(nav)
    expect(screenRows(w).map(([label]) => label)).not.toContain('Settings')
  })
})
