import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'

import { useGlobalUrlStamp } from '@/composables/useGlobalUrlStamp'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'

const Page = { render: () => h('div') }
// the app's routes are lazy and its auth guard is async, so a navigation resolves over several
// ticks: the window in which a re-stamp can land on top of it (issue 666)
const lazy = () => Promise.resolve(Page)

function makeRouter(): Router {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/clusters', component: Page },
      { path: '/views', component: Page },
      { path: '/guide', component: Page },
      { path: '/overview', component: lazy },
      { path: '/findings', component: lazy },
    ],
  })
  router.beforeEach(async () => {
    await Promise.resolve()
    return true
  })
  return router
}

const Shell = defineComponent({
  setup() {
    useGlobalUrlStamp()
    return () => h(RouterView)
  },
})

async function mountAt(path: string): Promise<Router> {
  const router = makeRouter()
  await router.push(path)
  mount(Shell, { global: { plugins: [router] } })
  await flushPromises()
  return router
}

const where = (router: Router) => router.currentRoute.value

describe('useGlobalUrlStamp: the global range and cluster ride the URL', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('selecting a cluster stamps it on the current page and stays there', async () => {
    const router = await mountAt('/clusters')
    useClusterStore().select('c-1')
    await flushPromises()
    expect(where(router).path).toBe('/clusters')
    expect(where(router).query.cluster).toBe('c-1')
  })

  it('landing on a bare URL gets the globals stamped', async () => {
    useClusterStore().selectedId = 'c-1'
    useTimeTravelStore().setWindow(7)
    const router = await mountAt('/clusters?cluster=c-1&win=7')
    await router.push('/findings')
    await flushPromises()
    expect(where(router).path).toBe('/findings')
    expect(where(router).query).toEqual({ cluster: 'c-1', win: '7' })
  })

  it('a stamp keeps the hash, so a guide section link survives a range change', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/guide?cluster=c-1#glossary')
    useTimeTravelStore().setWindow(7)
    await flushPromises()
    expect(where(router).hash).toBe('#glossary')
    expect(where(router).query).toEqual({ cluster: 'c-1', win: '7' })
  })

  it('replaces nothing when the URL already carries the globals', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/clusters?cluster=c-1')
    const replace = vi.spyOn(router, 'replace')
    await router.push('/overview?cluster=c-1')
    await flushPromises()
    expect(where(router).fullPath).toBe('/overview?cluster=c-1')
    expect(replace).not.toHaveBeenCalled()
  })
})
