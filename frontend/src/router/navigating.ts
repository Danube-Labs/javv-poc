/**
 * Whether a navigation is under way (issue 669). A navigation started while an older one is still
 * resolving makes the router cancel the older one, and vue-router keeps its pending navigation
 * private. The URL stamp (useGlobalUrlStamp) must not start its replace in that window, and it must
 * know at once: a handler that pushes and then changes the cluster changes it before any guard of
 * the push has run. So this wraps the router's own push and replace, which RouterLink calls too,
 * and counts the navigations that have started and not yet settled (landed, cancelled, aborted,
 * duplicated or failed). Back and Forward come from the browser's history, not push, and are not
 * counted.
 */
import { shallowRef, type Ref } from 'vue'
import type { Router } from 'vue-router'

const tracked = new WeakMap<Router, Ref<number>>()

export function trackNavigations(router: Router): Readonly<Ref<number>> {
  const known = tracked.get(router)
  if (known) return known
  const inFlight = shallowRef(0)
  const { push, replace } = router
  const track = <T>(started: Promise<T>): Promise<T> => {
    inFlight.value++
    return started.finally(() => {
      inFlight.value--
    })
  }
  router.push = (to) => track(push(to))
  router.replace = (to) => track(replace(to))
  tracked.set(router, inFlight)
  return inFlight
}
