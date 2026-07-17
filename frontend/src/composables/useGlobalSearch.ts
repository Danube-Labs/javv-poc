/**
 * Global search (M9f / SCREENS.md §15): composed findings-GROUPS queries, never a bespoke
 * endpoint — three parallel `GET /findings/groups?by=…&q=<text>` calls give server-aggregated,
 * deduped buckets (distinct CVEs / image repos / namespaces matching the contains-search).
 * Package-name results: `q` MATCHES package_name (rows land in the other groups) but it is not
 * a GROUP_FIELDS dim, so per the §15 ruling that result group is dropped, not client-filtered.
 * Debounced ≥2 chars; a sequence stamp drops stale responses (fast typing must never let an
 * older answer overwrite a newer one).
 */
import { ref } from 'vue'

import { client } from '@/api/client'
import { groupFindingsApiV1FindingsGroupsGet } from '@/api/generated'
import { logger } from '@/lib/logger'

export interface SearchBucket {
  key: string
  count: number
}

export interface SearchResults {
  cves: SearchBucket[]
  images: SearchBucket[]
  namespaces: SearchBucket[]
}

const EMPTY: SearchResults = { cves: [], images: [], namespaces: [] }
const DEBOUNCE_MS = 250
export const MIN_CHARS = 2
export const GROUP_SIZE = 5

/** The by-dims, in render order — exported so the spec pins the emitted params. */
export const SEARCH_DIMS = [
  ['cves', 'cve_id'],
  ['images', 'image_repo'],
  ['namespaces', 'namespaces'],
] as const

export function useGlobalSearch(clusterId: () => string | null) {
  const results = ref<SearchResults>(EMPTY)
  const searching = ref(false)
  const failed = ref(false)

  let timer: ReturnType<typeof setTimeout> | undefined
  let seq = 0

  async function run(text: string) {
    const cluster_id = clusterId()
    const mine = ++seq
    if (!cluster_id) return
    searching.value = true
    const settled = await Promise.all(
      SEARCH_DIMS.map(([, by]) =>
        groupFindingsApiV1FindingsGroupsGet({
          client,
          query: { cluster_id, by, q: text, size: GROUP_SIZE },
        }),
      ),
    )
    if (mine !== seq) return // a newer keystroke owns the state now
    searching.value = false
    if (settled.some((r) => !r.response?.ok)) {
      failed.value = true
      results.value = EMPTY
      logger.warn('global_search_failed', {
        statuses: settled.map((r) => r.response?.status ?? 0),
      })
      return
    }
    failed.value = false
    // §15 semantics: each group lists IDENTIFIERS matching the text. `q` matches rows on ANY
    // field, so a memcached search also returns buckets of CVEs *found on* memcached — keep
    // only buckets whose own key matches (mirrors the server's per-field wildcard; the server
    // still owns dedup/count/tenancy).
    const needle = text.toLowerCase()
    const [cves, images, namespaces] = settled.map((r) =>
      ((r.data as { data: SearchBucket[] }).data ?? [])
        .filter((b) => b.key.toLowerCase().includes(needle))
        .map(({ key, count }) => ({ key, count })),
    )
    results.value = { cves: cves ?? [], images: images ?? [], namespaces: namespaces ?? [] }
  }

  function search(text: string) {
    clearTimeout(timer)
    if (text.trim().length < MIN_CHARS) {
      seq++ // orphan any in-flight answer
      results.value = EMPTY
      searching.value = false
      failed.value = false
      return
    }
    timer = setTimeout(() => void run(text.trim()), DEBOUNCE_MS)
  }

  function reset() {
    clearTimeout(timer)
    seq++
    results.value = EMPTY
    searching.value = false
    failed.value = false
  }

  return { results, searching, failed, search, reset }
}
