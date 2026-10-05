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
 * Reads one failed answer. The backend answers a 503 itself when OpenSearch is unreachable, and
 * says so in JSON: `/readyz` with `{"status":"degraded"}`, data routes with the error envelope.
 * Only that 503 means the store. Anything else comes from in front of the backend: the frontend
 * server's 502, a proxy's or an ingress's 502, 503 or 504 page (for a frontend pod that is gone,
 * say), or no answer at all. Then the backend is what is missing (issue 725).
 */
export function downReason(status: number | undefined, fromBackend: boolean): DownReason {
  return status === 503 && fromBackend ? 'store' : 'backend'
}

/** True when an answer is the backend's own JSON, not a proxy's HTML or text page. */
export function isBackendJson(response: Response): boolean {
  return /[/+]json\b/.test(response.headers.get('content-type') ?? '')
}

/** True when a /readyz answer is the backend reporting its store down. */
async function readyzSaysDegraded(response: Response): Promise<boolean> {
  if (response.status !== 503 || !isBackendJson(response)) return false
  try {
    return ((await response.json()) as { status?: unknown }).status === 'degraded'
  } catch {
    return false
  }
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
          this.markDegraded(downReason(res.status, await readyzSaysDegraded(res)), 'readyz')
        }
      } catch {
        this.markDegraded(downReason(undefined, false), 'readyz')
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
