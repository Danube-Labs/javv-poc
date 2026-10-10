/**
 * The global range and cluster ride every screen's URL (restorable-state rule, audit 343; issue
 * 433): this keeps `t`, `win` and `cluster` stamped on whatever route is showing. The shell
 * calls it once; restoring the state FROM a deep link stays in the shell, before views mount.
 */
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { trackNavigations } from '@/router/navigating'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { restampLocation, ttToQuery } from '@/system/globalUrl'

export function useGlobalUrlStamp(): void {
  const clusterStore = useClusterStore()
  const timeTravel = useTimeTravelStore()
  const router = useRouter()
  const route = useRoute()
  const navigating = trackNavigations(router)

  // every stamp writes ALL global keys from the live state onto the settled route, so the
  // latest replace is always complete and two in a row can't leave a key behind
  function restamp() {
    // a replace started now would cancel the navigation under way; its landing stamps instead
    if (navigating.value > 0) return
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
  // fleet row, a saved view) starts this replace BEFORE its push, so the push supersedes it
  // (issue 666). A change that comes while a navigation is under way (the cluster list
  // arriving mid-click, or a handler that navigates first) waits for it (issue 669).
  watch(() => [timeTravel.t, timeTravel.windowDays, clusterStore.selectedId] as const, restamp, {
    flush: 'sync',
  })
  // the landing of every navigation, query-only ones included
  watch(
    navigating,
    (count) => {
      if (count === 0) restamp()
    },
    { flush: 'sync' },
  )
}
