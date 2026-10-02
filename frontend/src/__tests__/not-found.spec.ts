/**
 * An address that matches no route used to render an empty body (issue 674). The catch-all
 * sits inside the shell, so the auth gate and the sidebar still apply.
 */
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'

import router from '@/router'
import { resolveGate } from '@/router/guards'
import NotFoundView from '@/views/NotFoundView.vue'

const push = vi.fn<(to: unknown) => void>()
const back = vi.fn<() => void>()
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRoute: () => ({ path: '/reports/old-link' }),
  useRouter: () => ({ push, back }),
}))

describe('the not-found route', () => {
  it('catches an unknown address, inside the shell', () => {
    const hit = router.resolve('/reports/old-link')
    expect(hit.name).toBe('not-found')
    expect(hit.matched[0]!.path).toBe('/')
  })

  it('catches a deep unknown address and an unknown settings page', () => {
    expect(router.resolve('/a/b/c').name).toBe('not-found')
    expect(router.resolve('/settings/no-such-tab').name).toBe('not-found')
  })

  it('leaves the real routes alone', () => {
    expect(router.resolve('/findings').name).toBe('findings')
    expect(router.resolve('/login').name).toBe('login')
    expect(router.resolve('/settings/sla').name).toBe('settings-sla')
  })

  it('still sends a signed-out visitor to login', () => {
    const to = router.resolve('/reports/old-link') as unknown as RouteLocationNormalized
    const signedOut = { isAuthed: false, mustChange: false, hasCapability: () => true }
    expect(resolveGate(signedOut, to)).toEqual({ name: 'login' })
  })
})

describe('NotFoundView', () => {
  beforeEach(() => {
    push.mockClear()
    back.mockClear()
    window.history.replaceState({}, '')
  })

  it('names the problem and shows the address that failed', () => {
    const w = mount(NotFoundView)
    expect(w.get('h1').text()).toBe('Page not found')
    expect(w.text()).toContain('/reports/old-link')
  })

  it('offers the way out to Overview', async () => {
    const w = mount(NotFoundView)
    await w.findAll('button').find((b) => b.text() === 'Back to Overview')!.trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'overview' })
  })

  it('opened cold, offers no "Go back" (there is nowhere to go back to)', () => {
    const w = mount(NotFoundView)
    expect(w.findAll('button').some((b) => b.text() === 'Go back')).toBe(false)
  })

  it('reached from inside the app, offers "Go back"', async () => {
    window.history.replaceState({ back: '/findings' }, '')
    const w = mount(NotFoundView)
    await w.findAll('button').find((b) => b.text() === 'Go back')!.trigger('click')
    expect(back).toHaveBeenCalled()
  })
})
