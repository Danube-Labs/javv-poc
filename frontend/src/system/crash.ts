/**
 * A page that fails while it is drawn is replaced by the error page (issue 675). Vue names the
 * phase an error came from: a readable string in dev, a link ending in a short code in a
 * production build. Only a failed draw replaces the page. An error in a click handler or a
 * watcher leaves a working page on screen, so it is logged and nothing else.
 */
import { ref } from 'vue'

/** Set by the boundary around the routed page, and by the router when a page's file fails to
 * load; cleared on the next navigation or by "Try again". */
export const pageCrashed = ref(false)

const DRAW_PHASES = new Set([
  'setup function',
  'render function',
  'component update',
  'beforeMount hook',
  // the same four as production codes (vuejs.org/error-reference)
  '0',
  '1',
  '15',
  'bm',
])

export function replacesPage(info: string): boolean {
  const marker = '#runtime-'
  const at = info.lastIndexOf(marker)
  return DRAW_PHASES.has(at === -1 ? info : info.slice(at + marker.length))
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}
