import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterLink, RouterView, type Router } from 'vue-router'

import { trackNavigations } from '@/router/navigating'

const Page = { render: () => h('div') }

/** A route whose page loads only when the test says so: the navigation stays under way until then. */
function heldPage() {
  let release: () => void = () => {}
  const ready = new Promise<typeof Page>((resolve) => {
    release = () => resolve(Page)
  })
  const held = {
    loads: 0,
    load: () => {
      held.loads++
      return ready
    },
    release: () => release(),
  }
  return held
}

async function makeRouter(extra: Parameters<typeof createRouter>[0]['routes'] = []): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/home', component: Page },
      { path: '/other', component: Page },
      { path: '/blocked', component: Page },
      ...extra,
    ],
  })
  router.beforeEach((to) => to.path !== '/blocked')
  await router.push('/home')
  return router
}

describe('trackNavigations: a navigation is under way until it settles', () => {
  it('counts a navigation from the moment it starts until it lands', async () => {
    const held = heldPage()
    const router = await makeRouter([{ path: '/held', component: held.load }])
    const inFlight = trackNavigations(router)
    void router.push('/held')
    expect(inFlight.value).toBe(1)
    await flushPromises()
    expect(inFlight.value).toBe(1)
    held.release()
    await flushPromises()
    expect(inFlight.value).toBe(0)
    expect(router.currentRoute.value.path).toBe('/held')
  })

  it('counts replace like push', async () => {
    const router = await makeRouter()
    const inFlight = trackNavigations(router)
    const done = router.replace('/other')
    expect(inFlight.value).toBe(1)
    await done
    expect(inFlight.value).toBe(0)
  })

  it('a navigation a guard aborts, and a duplicate, settle too', async () => {
    const router = await makeRouter()
    const inFlight = trackNavigations(router)
    const aborted = router.push('/blocked')
    expect(inFlight.value).toBe(1)
    await aborted
    expect(inFlight.value).toBe(0)
    expect(router.currentRoute.value.path).toBe('/home')
    const duplicate = router.push('/home')
    expect(inFlight.value).toBe(1)
    await duplicate
    expect(inFlight.value).toBe(0)
  })

  it('a page that fails to load settles, and the caller still gets the error', async () => {
    const router = await makeRouter([
      { path: '/broken', component: () => Promise.reject(new Error('chunk failed')) },
    ])
    const inFlight = trackNavigations(router)
    const failed = router.push('/broken')
    expect(inFlight.value).toBe(1)
    await expect(failed).rejects.toThrow('chunk failed')
    expect(inFlight.value).toBe(0)
  })

  it('a navigation a newer one cancels stays counted until it settles', async () => {
    const held = heldPage()
    const router = await makeRouter([{ path: '/held', component: held.load }])
    const inFlight = trackNavigations(router)
    void router.push('/held')
    await flushPromises()
    expect(held.loads).toBe(1) // the older navigation is waiting for its page, as in issue 669
    void router.push('/other')
    expect(inFlight.value).toBe(2)
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/other')
    expect(inFlight.value).toBe(1)
    held.release()
    await flushPromises()
    expect(inFlight.value).toBe(0)
    expect(router.currentRoute.value.path).toBe('/other')
  })

  it('counts a RouterLink click', async () => {
    const held = heldPage()
    const router = await makeRouter([{ path: '/held', component: held.load }])
    const inFlight = trackNavigations(router)
    const Shell = defineComponent({
      setup: () => () => [h(RouterLink, { to: '/held' }, () => 'go'), h(RouterView)],
    })
    const wrapper = mount(Shell, { global: { plugins: [router] } })
    await wrapper.find('a').trigger('click')
    expect(inFlight.value).toBe(1)
    held.release()
    await flushPromises()
    expect(inFlight.value).toBe(0)
  })

  it('wraps the router once, however often it is asked', async () => {
    const router = await makeRouter()
    const first = trackNavigations(router)
    expect(trackNavigations(router)).toBe(first)
    void router.push('/other')
    expect(first.value).toBe(1)
  })
})
