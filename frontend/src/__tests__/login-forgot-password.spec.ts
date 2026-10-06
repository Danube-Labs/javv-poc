/**
 * The sign-in screen says what to do about a forgotten password (issue 761): ask an admin, and if
 * no admin can sign in, the deploy guide's reset command. The note is the same for every visitor,
 * so it says nothing about whether a user exists, and the forced-change screen does not carry it.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/auth'
import LoginView from '@/views/LoginView.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {}),
)
vi.mock('@/api/client', () => ({ client: {} }))
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRouter: () => ({ push: vi.fn<(to: unknown) => Promise<void>>() }),
}))

const NOTE =
  'Forgot your password? Ask an admin to reset it. If no admin can sign in, the deploy guide ' +
  '(DEPLOYING.md) shows how to reset one.'

const noteText = (wrapper: ReturnType<typeof mount>) =>
  wrapper.find('.note').exists() ? wrapper.find('.note').text().replace(/\s+/g, ' ') : null

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('the forgotten-password note', () => {
  it('shows under Sign in on the sign-in screen', () => {
    const wrapper = mount(LoginView)
    expect(noteText(wrapper)).toBe(NOTE)
    const order = wrapper.findAll('button, .note').map((el) => el.text().slice(0, 7))
    expect(order).toEqual(['Sign in', 'Forgot '])
  })

  it('is not on the forced password change', () => {
    useAuthStore().user = { username: 'admin', role: 'admin', capabilities: ['*'], must_change: true }
    const wrapper = mount(LoginView)
    expect(wrapper.find('button').text()).toBe('Change password')
    expect(noteText(wrapper)).toBeNull()
  })
})
