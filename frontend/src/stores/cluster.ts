/**
 * Cluster context: the registry list (M8c, display names from system-config) + the selected
 * `cluster_id` — the tenant chokepoint value every data read carries (D38/H9). Selection
 * persists per browser; `cluster_id` (immutable) is the key, never the relabelable name.
 */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import { listClustersApiV1ClustersGet } from '@/api/generated'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

export interface ClusterEntry {
  cluster_id: string
  cluster_name: string
}

const STORAGE_KEY = 'javv.selected_cluster_id'

export const useClusterStore = defineStore('cluster', {
  state: () => ({
    clusters: [] as ClusterEntry[],
    selectedId: null as string | null,
    loaded: false,
    failed: false,
  }),
  getters: {
    selected: (s) => s.clusters.find((c) => c.cluster_id === s.selectedId) ?? null,
  },
  actions: {
    /** `preferredId` = a deep link's `?cluster=` (issue 433). Precedence: valid link > remembered
     * selection > first cluster. A link's choice is deliberately NOT persisted — opening a
     * colleague's beta link must not flip this browser's default; an unknown id falls back
     * loudly (toast) instead of rendering an empty app. */
    async fetchClusters(preferredId: string | null = null): Promise<void> {
      const { data, response } = await listClustersApiV1ClustersGet({ client })
      if (response?.ok && data) {
        this.clusters = (data as { clusters: ClusterEntry[] }).clusters ?? []
        const known = (id: string | null): id is string =>
          id !== null && this.clusters.some((c) => c.cluster_id === id)
        if (preferredId !== null && !known(preferredId)) {
          useToastStore().info('The link points at a cluster this store does not know — showing your default.')
          logger.warn('url_cluster_unknown', { cluster_id: preferredId })
        }
        const remembered = localStorage.getItem(STORAGE_KEY)
        this.selectedId = known(preferredId)
          ? preferredId
          : known(remembered)
            ? remembered
            : (this.clusters[0]?.cluster_id ?? null)
        this.failed = false
      } else {
        // silence-is-a-bug (audit 343): without the registry every screen renders empty —
        // the shell shows the alert off this flag
        this.failed = true
        logger.warn('clusters_fetch_failed', { status: response?.status })
      }
      this.loaded = true
    },
    select(clusterId: string) {
      this.selectedId = clusterId
      localStorage.setItem(STORAGE_KEY, clusterId)
    },
  },
})
