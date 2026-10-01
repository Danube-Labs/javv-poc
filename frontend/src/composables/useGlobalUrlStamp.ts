/**
 * The global range and cluster ride every screen's URL (restorable-state rule, audit 343; issue
 * 433): this keeps `t`, `win` and `cluster` stamped on whatever route is showing. The shell
 * calls it once; restoring the state FROM a deep link stays in the shell, before views mount.
 */
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { restampLocation, ttToQuery } from '@/system/globalUrl'

export function useGlobalUrlStamp(): void {
  const clusterStore = useClusterStore()
  const timeTravel = useTimeTravelStore()
  const router = useRouter()
  const route = useRoute()

  // every stamp writes ALL global keys from the live state onto the settled route, so the
  // latest replace is always complete and two in a row can't leave a key behind
  function restamp() {
    const tt = ttToQuery(timeTravel.t, timeTravel.windowDays)
    const cluster = clusterStore.selectedId ?? undefined
    if (
      route.query.t === (tt.t ?? undefined) &&
      route.query.win === (tt.win ?? undefined) &&
      route.query.cluster === cluster
    )
      return
    void router.replace(restampLocation(route.query, route.hash, tt, cluster))
  }

  // re-stamp on NAVIGATION too — a bare next-page URL would lose the range on ITS refresh
  // (operator bug report: set 24h → navigate → refresh → back to 30 days)
  watch(() => route.path, restamp)
  // sync, not the default pre-flush: a handler that changes the state and then navigates (a
  // fleet row, a saved view) must have this replace start BEFORE its push, so the push
  // supersedes it. Deferred, the replace starts while the push is in flight and the router
  // cancels the push: the page stays and only its URL changes (issue 666). The landing is
  // stamped by the path watcher above.
  watch(() => [timeTravel.t, timeTravel.windowDays, clusterStore.selectedId] as const, restamp, {
    flush: 'sync',
  })
}
