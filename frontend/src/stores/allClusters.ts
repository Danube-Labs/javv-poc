/** All-clusters fleet state (M9c slice 2; SCREENS-v5 §1). Every number is a per-cluster SERVER
 * aggregation — facets + freshness + the committed-inventory read, one set per cluster row —
 * kept per-scanner (never merged across scanners). I3 guard (D38/M16, D39/M11-r2): at `T<now`
 * this store flips `limited` and emits NO query — there is no historical all-clusters read in
 * MVP, and no code path may attempt one. */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import {
  facetFindingsApiV1FindingsFacetsGet,
  listClustersApiV1ClustersGet,
  listRunningImagesApiV1ImagesGet,
  scannerFreshnessApiV1ScannersFreshnessGet,
} from '@/api/generated'
import { logger } from '@/lib/logger'
import type { FacetBucket } from '@/stores/overview'
import type { FreshnessRow } from '@/system/freshness'

type Facets = Record<string, FacetBucket[]>

export interface ClusterRow {
  cluster_id: string
  cluster_name: string
  facets: Facets
  freshness: FreshnessRow[]
  /** null = no committed inventory yet — unknown, not an empty cluster (M8c contract). */
  imagesCount: number | null
  replicas: number | null
  failed: boolean
}

interface ClusterEntry {
  cluster_id: string
  cluster_name: string
}

export const useAllClustersStore = defineStore('allClusters', {
  state: () => ({
    rows: [] as ClusterRow[],
    loading: false,
    failed: false,
    limited: false,
  }),
  actions: {
    /** One load per (T). The I3 branch must stay first: `as_of` present → no API call, ever. */
    async load(asOf: string | null) {
      if (asOf !== null) {
        this.limited = true
        this.rows = []
        return
      }
      this.limited = false
      this.loading = true
      this.failed = false
      const list = await listClustersApiV1ClustersGet({ client })
      if (!list.response?.ok || !list.data) {
        this.loading = false
        this.failed = true
        logger.warn('all_clusters_list_failed', { status: list.response?.status })
        return
      }
      const clusters = (list.data as { clusters: ClusterEntry[] }).clusters ?? []
      this.rows = await Promise.all(clusters.map((c) => this.loadRow(c)))
      this.loading = false
    },

    /** One cluster's row — a failed cluster degrades its own row, never the fleet. */
    async loadRow(c: ClusterEntry): Promise<ClusterRow> {
      const query = { cluster_id: c.cluster_id }
      const [facets, fresh, images] = await Promise.all([
        facetFindingsApiV1FindingsFacetsGet({ client, query: query as never }),
        scannerFreshnessApiV1ScannersFreshnessGet({ client, query }),
        listRunningImagesApiV1ImagesGet({ client, query }),
      ])
      const row: ClusterRow = {
        cluster_id: c.cluster_id,
        cluster_name: c.cluster_name,
        facets: {},
        freshness: [],
        imagesCount: null,
        replicas: null,
        failed: false,
      }
      if (facets.response?.ok && facets.data) {
        row.facets = (facets.data as { facets: Facets }).facets ?? {}
      } else {
        row.failed = true
        logger.warn('all_clusters_row_failed', {
          cluster_id: c.cluster_id,
          status: facets.response?.status,
        })
      }
      if (fresh.response?.ok && fresh.data) {
        row.freshness = (fresh.data as { scanners: FreshnessRow[] }).scanners ?? []
      }
      if (images.response?.ok && images.data) {
        const body = images.data as { inventory: unknown; images: { replicas?: number }[] }
        if (body.inventory !== null) {
          row.imagesCount = body.images.length
          row.replicas = body.images.reduce((n, i) => n + (i.replicas ?? 0), 0)
        }
      }
      return row
    },
  },
})
