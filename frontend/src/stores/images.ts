/** Running-images inventory state (M9c slice 3; SCREENS §7) — the committed-inventory read,
 * keyed by the global cluster + T (D28 rides in via `as_of`, served by the same backend
 * primitives as the time-travel reader). Rows are the server's image docs verbatim: severity
 * buckets belong to the doc's OWN scanner(s), and the D5b `trivy_count/grype_count/count_delta`
 * pair is the cross-scanner signal — nothing here merges scanners. `inventory: null` means no
 * committed inventory at T — unknown, never an empty cluster. */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import { listRunningImagesApiV1ImagesGet } from '@/api/generated'
import { logger } from '@/lib/logger'

export interface ImageRow {
  image_digest: string
  image_repo: string
  tag: string
  namespaces: string[]
  scanners: string[]
  crit: number
  high: number
  med: number
  low: number
  negligible: number
  unknown: number
  total: number
  fixable: number
  replicas: number
  trivy_count?: number | null
  grype_count?: number | null
  count_delta?: number | null
  /** every scanner's latest committed counts for this digest (server-decorated, R-CATALOG) —
   * the doc's own buckets above are the committing scanner's alone */
  severity_by_scanner?: Record<
    string,
    { crit: number; high: number; med: number; low: number; negligible: number; unknown: number; total: number; fixable: number }
  >
  '@timestamp': string
}

export interface InventoryManifest {
  inventory_run_id: string
  inventory_order: number
  started_at: string | null
  completed_at: string | null
}

export const useImagesStore = defineStore('images', {
  state: () => ({
    images: [] as ImageRow[],
    inventory: null as InventoryManifest | null,
    loading: false,
    failed: false,
  }),
  getters: {
    /** No committed inventory at T — unknown ≠ an empty (zero-image) committed run. */
    unknown: (s) => !s.loading && !s.failed && s.inventory === null,
  },
  actions: {
    async load(params: { cluster_id: string; as_of?: string }) {
      this.loading = true
      this.failed = false
      const { data, response } = await listRunningImagesApiV1ImagesGet({
        client,
        query: params as never,
      })
      this.loading = false
      if (!response?.ok || !data) {
        this.failed = true
        logger.warn('images_load_failed', { status: response?.status })
        return
      }
      const body = data as { inventory: InventoryManifest | null; images: ImageRow[] }
      this.inventory = body.inventory
      this.images = body.images ?? []
    },
  },
})
