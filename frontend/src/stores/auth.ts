/**
 * Session + capabilities (D33/A-4): ALL client gating flows from the `capabilities` array on
 * /auth/me — never role names (role is display-only). `"*"` (admin) grants everything. The client
 * gate is convenience; the server is the authority. A `must_change` session is locked to the
 * password screen by the router guard.
 */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import {
  loginAuthLoginPost,
  logoutAuthLogoutPost,
  meAuthMeGet,
  changePasswordAuthPasswordPost,
} from '@/api/generated'
import { logger } from '@/lib/logger'

export interface SessionUser {
  username: string
  role: string
  capabilities: string[]
  must_change: boolean
}

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null as SessionUser | null, checked: false }),
  getters: {
    isAuthed: (s) => s.user !== null,
    mustChange: (s) => s.user?.must_change === true,
    hasCapability: (s) => (cap: string) =>
      s.user !== null && (s.user.capabilities.includes('*') || s.user.capabilities.includes(cap)),
  },
  actions: {
    async fetchMe(): Promise<void> {
      const { data, response } = await meAuthMeGet({ client })
      this.user =
        response?.ok && data ? ((data as { user: SessionUser }).user ?? null) : null
      this.checked = true
    },
    /** Returns null on success, or user-facing error copy (generic — no user-existence hints). */
    async login(username: string, password: string): Promise<string | null> {
      const { response } = await loginAuthLoginPost({ client, body: { username, password } })
      if (response?.status === 429) return 'Too many attempts — try again later.'
      if (!response?.ok) return 'Invalid username or password.'
      logger.info('login', { username })
      await this.fetchMe()
      return null
    },
    async changePassword(currentPassword: string, newPassword: string): Promise<string | null> {
      const { response } = await changePasswordAuthPasswordPost({
        client,
        body: { current_password: currentPassword, new_password: newPassword },
      })
      if (!response?.ok) return 'Password change failed — check the current password and policy.'
      logger.info('password changed')
      await this.fetchMe()
      return null
    },
    async logout(): Promise<void> {
      await logoutAuthLogoutPost({ client })
      logger.info('logout', { username: this.user?.username })
      this.user = null
    },
  },
})
