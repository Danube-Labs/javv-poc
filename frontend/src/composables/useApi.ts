/**
 * The global-params injector: every data read carries the selected `cluster_id` (tenant
 * chokepoint) and the time-travel `as_of` (omitted at T=now). Views build their own params and
 * spread `withGlobals()` in — so the D28 rewind and the tenant filter can never be forgotten
 * on a call site.
 */
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'

export function useApi() {
  const clusterStore = useClusterStore()
  const timeTravel = useTimeTravelStore()

  function withGlobals<T extends Record<string, unknown>>(
    params?: T,
  ): T & { cluster_id: string } & { as_of?: string } {
    if (!clusterStore.selectedId) throw new Error('no cluster selected — data reads need cluster_id')
    return {
      ...(params ?? ({} as T)),
      cluster_id: clusterStore.selectedId,
      ...timeTravel.asOfParams,
    }
  }

  return { withGlobals }
}
