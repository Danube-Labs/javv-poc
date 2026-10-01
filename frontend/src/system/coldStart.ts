/**
 * The zero-clusters cold start (M9f): the registry answered fine but is EMPTY — no scanner has
 * ever enrolled, so every data screen would fetch nothing forever and shows onboarding instead.
 * Two sections stay live: `configure` (Settings → Tokens IS the way out) and `help` (the About
 * page is what a new install needs most, issue 341).
 */
const LIVE_WITHOUT_CLUSTERS = new Set(['configure', 'help'])

export function isColdStart(state: {
  loaded: boolean
  failed: boolean
  clusterCount: number
  section: string | undefined
}): boolean {
  return (
    state.loaded &&
    !state.failed &&
    state.clusterCount === 0 &&
    !LIVE_WITHOUT_CLUSTERS.has(state.section ?? '')
  )
}
