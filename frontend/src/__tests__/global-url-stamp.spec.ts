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

// a navigation the test holds open: `?hold=` waits at the guard until `release()`, and
// `?hold=abort` is then refused. Issue 669: the cluster list can land while one is under way.
let release: () => void = () => {}
let gate: Promise<void> = Promise.resolve()

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
  router.beforeEach(async (to) => {
    await Promise.resolve()
    if (to.query.hold) {
      await gate
      return to.query.hold !== 'abort'
    }
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
    gate = new Promise((resolve) => {
      release = resolve
    })
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

  // issue 666: the stamp must never cancel a navigation the same click started
  it('picking a cluster and then navigating lands on the target, with the new cluster', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/clusters?cluster=c-1')
    useClusterStore().select('c-2')
    void router.push('/overview')
    await flushPromises()
    expect(where(router).path).toBe('/overview')
    expect(where(router).query.cluster).toBe('c-2')
  })

  it('changing the window and then navigating lands on the target, with the new window', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/views?cluster=c-1')
    useTimeTravelStore().setWindow(7, 'Last 7 days')
    void router.push({ path: '/findings', query: { severity: 'critical' } })
    await flushPromises()
    expect(where(router).path).toBe('/findings')
    expect(where(router).query).toEqual({ severity: 'critical', cluster: 'c-1', win: '7' })
  })

  // issue 669, case 2: the cluster list lands while a click's navigation is still resolving
  it('a cluster chosen while a navigation is under way: it lands on the target, with that cluster', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/clusters?cluster=c-1')
    void router.push('/guide?hold=1')
    await flushPromises()
    useClusterStore().selectedId = 'c-2'
    await flushPromises()
    release()
    await flushPromises()
    expect(where(router).path).toBe('/guide')
    expect(where(router).query).toEqual({ hold: '1', cluster: 'c-2' })
  })

  // issue 669, case 1: a handler that navigates first and then changes the cluster
  it('navigating and then picking a cluster lands on the target, with the new cluster', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/clusters?cluster=c-1')
    void router.push('/overview')
    useClusterStore().select('c-2')
    await flushPromises()
    expect(where(router).path).toBe('/overview')
    expect(where(router).query.cluster).toBe('c-2')
  })

  it('a window change during a query-only navigation keeps both the new query and the window', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/clusters?cluster=c-1')
    void router.push({ path: '/clusters', query: { cluster: 'c-1', hold: '1', severity: 'high' } })
    await flushPromises()
    useTimeTravelStore().setWindow(7)
    await flushPromises()
    release()
    await flushPromises()
    expect(where(router).path).toBe('/clusters')
    expect(where(router).query).toEqual({ cluster: 'c-1', hold: '1', severity: 'high', win: '7' })
  })

  it('a navigation a guard refuses still leaves the current page stamped', async () => {
    useClusterStore().selectedId = 'c-1'
    const router = await mountAt('/clusters?cluster=c-1')
    void router.push('/guide?hold=abort')
    await flushPromises()
    useClusterStore().select('c-2')
    release()
    await flushPromises()
    expect(where(router).path).toBe('/clusters')
    expect(where(router).query.cluster).toBe('c-2')
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
