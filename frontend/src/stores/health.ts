/**
 * Global backend health (observability.md §2/§3): /readyz polled while the app is open; any API
 * 502, 503 or 504 flips `degraded` immediately (via the client interceptor), with the reason. The banner is
 * dismissible-but-recurring — dismissal survives until the NEXT degraded signal, and everything
 * auto-clears when /readyz returns 200. Chrome stays up; data areas show degraded states.
 */
import { defineStore } from 'pinia'
import { logger } from '@/lib/logger'

export const POLL_MS = 30_000

/** What is down: the backend itself, or the store behind a backend that still answers. */
export type DownReason = 'backend' | 'store'

/**
 * Reads one failed answer. The backend answers a 503 itself when OpenSearch is unreachable
 * (`/readyz` says `degraded`; data routes send the error envelope), so a 503 means the store.
 * No answer at all, or any other failure, comes from in front of the backend (a proxy's 502 or
 * 504, a dev server with nothing behind it): the backend is gone.
 */
export function downReason(status: number | undefined): DownReason {
  return status === 503 ? 'store' : 'backend'
}

export const useHealthStore = defineStore('health', {
  state: () => ({ degraded: false, reason: null as DownReason | null, dismissed: false, pollHandle: 0 as ReturnType<typeof setInterval> | 0 }),
  getters: {
    bannerVisible: (s) => s.degraded && !s.dismissed,
    /** The sidebar footer's one-line status. */
    statusLabel: (s) =>
      !s.degraded ? 'Store healthy' : s.reason === 'backend' ? 'Backend not answering' : 'Store degraded',
  },
  actions: {
    markDegraded(reason: DownReason, source: 'api' | 'readyz') {
      if (!this.degraded || this.reason !== reason) logger.warn('backend degraded', { source, reason })
      this.degraded = true
      this.reason = reason
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
          this.reason = null
        } else {
          this.markDegraded(downReason(res.status), 'readyz')
        }
      } catch {
        this.markDegraded(downReason(undefined), 'readyz')
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
