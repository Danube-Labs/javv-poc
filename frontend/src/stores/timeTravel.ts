/**
 * The global time-travel `T` (D28/FR-23): one Pinia store every data fetch reads, so one picker
 * rewinds the whole app. `t === null` means NOW — the emitted params then OMIT `as_of` entirely
 * (T=now reads materialized current state; T<now reconstructs — the branch must be observable
 * in the emitted params, per the bolt DoD). `windowDays` is the trend window, relative to T —
 * a separate, visibly distinct control (C-1).
 */
import { defineStore } from 'pinia'
import { logger } from '@/lib/logger'

export const useTimeTravelStore = defineStore('timeTravel', {
  state: () => ({ t: null as string | null, windowDays: 30, windowLabel: 'Last 30 days' }),
  getters: {
    isNow: (s) => s.t === null,
    /** Query-param fragment for every data read: {} at now, { as_of } in the past. */
    asOfParams: (s): { as_of?: string } => (s.t === null ? {} : { as_of: s.t }),
  },
  actions: {
    rewindTo(iso: string) {
      this.t = iso
      logger.info('time travel', { as_of: iso })
    },
    backToNow() {
      if (this.t !== null) logger.info('time travel', { as_of: 'now' })
      this.t = null
    },
    setWindow(days: number, label?: string) {
      this.windowDays = days
      this.windowLabel = label ?? `Last ${days} days`
    },
  },
})
