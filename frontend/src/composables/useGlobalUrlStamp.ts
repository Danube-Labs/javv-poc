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

  // re-stamp on NAVIGATION too — a bare next-page URL would lose the range on ITS refresh
  // (operator bug report: set 24h → navigate → refresh → back to 30 days). One watcher stamps
  // ALL global keys in a single replace — two racing replaces could overwrite each other.
  watch(
    () => [timeTravel.t, timeTravel.windowDays, clusterStore.selectedId, route.path] as const,
    ([t, win, cid]) => {
      const tt = ttToQuery(t, win)
      const cluster = cid ?? undefined
      if (
        route.query.t === (tt.t ?? undefined) &&
        route.query.win === (tt.win ?? undefined) &&
        route.query.cluster === cluster
      )
        return
      void router.replace(restampLocation(route.query, route.hash, tt, cluster))
    },
  )
}
