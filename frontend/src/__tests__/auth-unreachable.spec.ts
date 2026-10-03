/**
 * A server that does not answer is not "signed out" and not "wrong password" (issue 675): the
 * session check is not remembered, the sign-in form says the server is down, and the login page
 * goes back in on its own once the server returns with the session still good.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { logger } from '@/lib/logger'
import { loginFailure, SERVER_DOWN_COPY, serverFailed, useAuthStore } from '@/stores/auth'
import { POLL_MS } from '@/stores/health'
import LoginView from '@/views/LoginView.vue'

type Answer = { data?: unknown; response?: { ok: boolean; status: number } }
const me = vi.fn<() => Promise<Answer>>()
const login = vi.fn<() => Promise<Answer>>()
const changePassword = vi.fn<() => Promise<Answer>>()
vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    meAuthMeGet: () => me(),
    loginAuthLoginPost: () => login(),
    changePasswordAuthPasswordPost: () => changePassword(),
    logoutAuthLogoutPost: vi.fn<() => Promise<Answer>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

const push = vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve())
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRouter: () => ({ push }),
}))

const answer = (status: number, data?: unknown): Answer => ({
  data,
  response: { ok: status >= 200 && status < 300, status },
})
const noAnswer: Answer = { response: undefined }
const admin = { user: { username: 'admin', role: 'admin', capabilities: ['*'], must_change: false } }
const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})

beforeEach(() => {
  setActivePinia(createPinia())
  for (const m of [me, login, changePassword, push, warned]) m.mockClear()
})

describe('serverFailed / loginFailure', () => {
  it.each([undefined, 500, 502, 503, 504])('%s is the server failing', (status) => {
    expect(serverFailed(status)).toBe(true)
    expect(loginFailure(status)).toBe(SERVER_DOWN_COPY)
  })

  it('a 401 stays the generic message, with no hint about the user', () => {
    expect(serverFailed(401)).toBe(false)
    expect(loginFailure(401)).toBe('Invalid username or password.')
  })

  it('a 429 keeps the lockout message, and a 200 is no failure', () => {
    expect(loginFailure(429)).toBe('Too many attempts. Try again later.')
    expect(loginFailure(200)).toBeNull()
  })
})

describe('the session check', () => {
  it.each([
    ['a proxy error', answer(502)],
    ['no answer at all', noAnswer],
  ])('%s is not remembered as signed out', async (_name, failed) => {
    me.mockResolvedValueOnce(failed)
    const auth = useAuthStore()
    await auth.fetchMe()
    expect(auth.unreachable).toBe(true)
    expect(auth.checked).toBe(false)
    expect(auth.isAuthed).toBe(false)
    expect(warned).toHaveBeenCalledWith('session check failed', {
      status: failed.response?.status ?? null,
    })
  })

  it('a 401 is signed out, and remembered', async () => {
    me.mockResolvedValueOnce(answer(401))
    const auth = useAuthStore()
    await auth.fetchMe()
    expect(auth.unreachable).toBe(false)
    expect(auth.checked).toBe(true)
    expect(auth.isAuthed).toBe(false)
    expect(warned).not.toHaveBeenCalled()
  })

  it('a good answer after a failed one clears the flag', async () => {
    me.mockResolvedValueOnce(noAnswer).mockResolvedValueOnce(answer(200, admin))
    const auth = useAuthStore()
    await auth.fetchMe()
    await auth.fetchMe()
    expect(auth.unreachable).toBe(false)
    expect(auth.isAuthed).toBe(true)
  })
})

describe('signing in and changing the password', () => {
  it('a dead server is reported as the server, not the password', async () => {
    login.mockResolvedValueOnce(answer(502))
    const auth = useAuthStore()
    expect(await auth.login('admin', 'pw')).toBe(SERVER_DOWN_COPY)
    expect(auth.unreachable).toBe(true)
    expect(me).not.toHaveBeenCalled()
  })

  it('a wrong password is still a wrong password', async () => {
    login.mockResolvedValueOnce(answer(401))
    const auth = useAuthStore()
    expect(await auth.login('admin', 'nope')).toBe('Invalid username or password.')
    expect(auth.unreachable).toBe(false)
  })

  it('a dead server during a password change is reported as the server', async () => {
    changePassword.mockResolvedValueOnce(noAnswer)
    const auth = useAuthStore()
    expect(await auth.changePassword('a', 'b')).toBe(SERVER_DOWN_COPY)
    expect(auth.unreachable).toBe(true)
  })
})

describe('LoginView with a server that does not answer', () => {
  const fetchMock = vi.fn<(url: string) => Promise<{ ok: boolean; status: number }>>()
  beforeEach(() => {
    vi.useFakeTimers()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  function mountDown() {
    const auth = useAuthStore()
    auth.unreachable = true
    return { auth, w: mount(LoginView) }
  }

  it('says the server is not answering, in place of any password error', () => {
    const { w } = mountDown()
    expect(w.get('[role="alert"]').text()).toBe(SERVER_DOWN_COPY)
    expect(w.findAll('[role="alert"]')).toHaveLength(1)
  })

  it('shows nothing of the kind when the server answers', () => {
    const w = mount(LoginView)
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('a sign-in against a dead server shows the notice, not "Invalid username or password"', async () => {
    login.mockResolvedValueOnce(answer(504))
    const w = mount(LoginView)
    await w.get('#username').setValue('admin')
    await w.get('#password').setValue('pw')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('[role="alert"]').text()).toBe(SERVER_DOWN_COPY)
    expect(w.text()).not.toContain('Invalid username or password')
  })

  it('keeps asking, and goes back in when the server returns with the session still good', async () => {
    const { w } = mountDown()
    fetchMock.mockResolvedValueOnce({ ok: false, status: 502 })
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(me).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').exists()).toBe(true)

    fetchMock.mockResolvedValueOnce({ ok: true, status: 200 })
    me.mockResolvedValueOnce(answer(200, admin))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(push).toHaveBeenCalledWith('/overview')
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('stays on the form when the server returns but the session is gone', async () => {
    const { w } = mountDown()
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200 })
    me.mockResolvedValueOnce(answer(401))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(push).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').exists()).toBe(false)
    // and stops asking
    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('stops asking when the page is left', async () => {
    const { w } = mountDown()
    w.unmount()
    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
