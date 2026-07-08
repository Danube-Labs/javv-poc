/**
 * Global backend health (observability.md §2/§3): /readyz polled while the app is open; any API
 * 503 flips `degraded` immediately (via the client interceptor). The banner is
 * dismissible-but-recurring — dismissal survives until the NEXT degraded signal, and everything
 * auto-clears when /readyz returns 200. Chrome stays up; data areas show degraded states.
 */
import { defineStore } from 'pinia'
import { logger } from '@/lib/logger'

const POLL_MS = 30_000

export const useHealthStore = defineStore('health', {
  state: () => ({ degraded: false, dismissed: false, pollHandle: 0 as ReturnType<typeof setInterval> | 0 }),
  getters: {
    bannerVisible: (s) => s.degraded && !s.dismissed,
  },
  actions: {
    markDegraded() {
      if (!this.degraded) logger.warn('backend degraded', { source: 'api-503' })
      this.degraded = true
      this.dismissed = false
    },
    dismiss() {
      this.dismissed = true
    },
    async check() {
      try {
        const res = await fetch('/readyz', { credentials: 'same-origin' })
        if (res.ok) {
          if (this.degraded) logger.info('backend recovered')
          this.degraded = false
        } else {
          this.markDegraded()
        }
      } catch {
        this.markDegraded()
      }
    },
    startPolling() {
      if (this.pollHandle) return
      void this.check()
      this.pollHandle = setInterval(() => void this.check(), POLL_MS)
    },
    stopPolling() {
      if (this.pollHandle) clearInterval(this.pollHandle)
      this.pollHandle = 0
    },
  },
})
