/**
 * Live staleness timers (FR-6/D20, M9e banner rewire): the freshness banner and the fleet
 * health chips threshold on what the settings panel ACTUALLY edits — never a build-time knob.
 * Two reads off `GET /api/v1/settings/staleness` (any authenticated session): the selected
 * cluster's EFFECTIVE timers (its override if one exists, else the fleet default) for the
 * banner, and the fleet default once for the all-clusters view. D20 defaults hold while a
 * read is in flight or failed — the same values the backend seeds.
 */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import { getStalenessApiV1SettingsStalenessGet } from '@/api/generated'
import { logger } from '@/lib/logger'
import { D20_FRESHNESS_DEFAULT_S } from '@/system/freshness'

interface StalenessTimers {
  freshness_days: number
  scanner_down_days: number
}

interface StalenessBody {
  staleness: StalenessTimers
  per_cluster_override: boolean
}

export const useStalenessStore = defineStore('staleness', {
  state: () => ({
    effective: null as StalenessTimers | null, // the selected cluster's effective timers
    effectiveFor: null as string | null,
    fleet: null as StalenessTimers | null,
  }),
  getters: {
    /** The banner window for the selected cluster, in seconds (D20 default until loaded). */
    bannerThresholdS: (s) =>
      s.effective !== null ? s.effective.freshness_days * 86_400 : D20_FRESHNESS_DEFAULT_S,
    /** The fleet-default window for cross-cluster surfaces (all-clusters health chips). */
    fleetThresholdS: (s) =>
      s.fleet !== null ? s.fleet.freshness_days * 86_400 : D20_FRESHNESS_DEFAULT_S,
  },
  actions: {
    async loadFor(clusterId: string): Promise<void> {
      if (this.effectiveFor === clusterId && this.effective !== null) return
      const { data, response } = await getStalenessApiV1SettingsStalenessGet({
        client,
        query: { cluster_id: clusterId },
      })
      if (response?.ok && data) {
        this.effective = (data as unknown as StalenessBody).staleness
        this.effectiveFor = clusterId
      } else {
        // the D20 default getter keeps the banner honest-ish; log so silence isn't a bug
        logger.warn('staleness_timers_fetch_failed', { status: response?.status })
      }
    },
    async loadFleet(): Promise<void> {
      if (this.fleet !== null) return
      const { data, response } = await getStalenessApiV1SettingsStalenessGet({ client })
      if (response?.ok && data) {
        this.fleet = (data as unknown as StalenessBody).staleness
      } else {
        logger.warn('staleness_fleet_fetch_failed', { status: response?.status })
      }
    },
    /** Called after the settings panel saves timers — the next read must not serve the cache. */
    invalidate(): void {
      this.effective = null
      this.effectiveFor = null
      this.fleet = null
    },
  },
})
