/**
 * The router's scroll rule: only ARRIVING at a `#section` scrolls (the Guide's anchors). A
 * query-only replace that keeps the same hash (the shell re-stamping the range or the cluster)
 * must not pull the reader back to it, and every other navigation keeps its scroll position,
 * as it did before this rule existed. The 16px offset is the page's top padding, so a
 * section's heading isn't flush with the viewport edge.
 */
interface Place {
  path: string
  hash: string
}

export function hashScroll(to: Place, from: Place): { el: string; top: number } | false {
  return to.hash && (to.hash !== from.hash || to.path !== from.path) ? { el: to.hash, top: 16 } : false
}
