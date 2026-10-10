/**
 * A page that fails while it is drawn is replaced by the error page (issue 675). Vue names the
 * phase an error came from: a readable string in dev, a link ending in a short code in a
 * production build. Only a failed draw replaces the page. An error in a click handler or a
 * watcher leaves a working page on screen, so it is logged and nothing else.
 */
import { ref } from 'vue'

import { logger } from '@/lib/logger'

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

const STACK_FRAMES = 5

/** The first frames of an error's stack, without this page's origin, so a logged error names the
 * file that threw (issue 749: a message alone left two candidates open). A production build has
 * no source maps, so its frame names a hashed chunk and a position that a build of the same
 * commit maps back. */
export function errorStack(err: unknown, origin: string = globalThis.location?.origin ?? ''): string[] {
  if (!(err instanceof Error) || typeof err.stack !== 'string') return []
  const lines = err.stack.split('\n')
  // Chromium puts the message first and starts each frame with "at"; Firefox and Safari list
  // frames only
  const atFrames = lines.filter((line) => /^\s+at /.test(line))
  return (atFrames.length > 0 ? atFrames : lines)
    .map((line) => (origin ? line.split(origin).join('') : line).trim())
    .filter((line) => line !== '')
    .slice(0, STACK_FRAMES)
}

/** Logs a promise rejection nothing caught. Vue sees an error only when its own handler, hook or
 * watcher returns the promise, so a store action started with `void` from a watcher would
 * otherwise reach no log at all. */
export function logUnhandledRejections(target: EventTarget, routePath: () => string): void {
  target.addEventListener('unhandledrejection', (event) => {
    const reason: unknown = (event as PromiseRejectionEvent).reason
    logger.error('app error', {
      route: routePath(),
      info: 'unhandled rejection',
      message: errorMessage(reason),
      stack: errorStack(reason),
    })
  })
}
