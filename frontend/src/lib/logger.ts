/**
 * Frontend structured logger — the FE analog of the javv-common structlog pipeline
 * (observability.md §1): one leveled, structured emitter for all app code. Raw `console.*` is
 * ESLint-banned everywhere else, exactly like `print()` on the backend.
 *
 * Shape mirrors the backend stream (timestamp → level → event → fields) so a browser console line
 * reads like a backend.log line. Level threshold: `VITE_LOG_LEVEL` (build-time), defaulting to
 * `debug` in dev and `warn` in production builds.
 *
 * Never log secrets (NFR-5): no tokens, no cookie values, no raw response bodies — log
 * shapes/sizes/ids. The session cookie is httpOnly, but the rule stands for anything in scope.
 *
 * ## The client-events beacon (issue 453)
 *
 * A browser console is write-only from the operator's side: close the tab and the evidence is
 * gone. So `warn`/`error` emissions are ALSO queued and shipped to `POST /api/v1/client-events`,
 * where the backend re-emits them into its own stdout stream. Call sites are unchanged and
 * unaware — the transport lives entirely behind `emit`.
 *
 * It is telemetry, so it is deliberately lossy, and each of these is a property rather than an
 * accident:
 *
 * - **Never retried.** A failed send is dropped. A logging outage must not become traffic, and a
 *   retry queue is how a degraded backend gets a self-inflicted thundering herd.
 * - **Bounded send rate, not bounded latency.** The queue caps at one batch and flushes on a
 *   fixed window, so an error storm (a render loop calling `logger.error`) drops events instead
 *   of bursting requests. At most one send per window keeps a normal session far under the
 *   server's per-principal rate cap, whose 429 would itself be silent loss.
 * - **Lossy, but never silently so.** A window that dropped events leads its next batch with a
 *   `beacon events dropped` summary carrying the count, so an operator can tell "this session
 *   had no errors" apart from "this session had so many we stopped shipping them" — which is
 *   the case most worth knowing about, and the one a bare gap in the stream hides.
 * - **No loop.** Nothing in the transport calls `logger` or `console`, so a transport failure
 *   cannot generate the very events it failed to send.
 *
 * Field values are clipped to the server's per-value cap on the way in, because the values that
 * can actually grow are supplied from outside the app (a `?cluster=` deep link, a typed store
 * path) rather than being call-site literals, and one oversized value would 422 its whole batch.
 *
 * Off in dev, on in production builds, overridable with `VITE_CLIENT_EVENTS`.
 */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 }

function threshold(): number {
  const configured = import.meta.env.VITE_LOG_LEVEL as LogLevel | undefined
  if (configured && configured in ORDER) return ORDER[configured]
  return import.meta.env.DEV ? ORDER.debug : ORDER.warn
}

export type LogFields = Record<string, unknown>

const BEACON_PATH = '/api/v1/client-events'
const BEACON_BATCH = 20 // the server's own batch cap — one full queue is one legal request
const BEACON_WINDOW_MS = 5000
/** The server's event-name contract. A name it would 422 poisons the whole batch it rides in. */
const BEACON_EVENT_NAME = /^[a-z0-9][a-z0-9 ._-]{0,63}$/
/** The server's per-value cap, mirrored so an oversized value cannot 422 its whole batch. */
const BEACON_MAX_VALUE_CHARS = 512
const BEACON_DROPPED_EVENT = 'beacon events dropped'

type BeaconEvent = { level: 'warn' | 'error'; event: string; fields?: LogFields }

let queue: BeaconEvent[] = []
let dropped = 0
let timer: ReturnType<typeof setTimeout> | null = null

function beaconEnabled(): boolean {
  const configured = import.meta.env.VITE_CLIENT_EVENTS as string | undefined
  if (configured !== undefined) return configured !== 'false' && configured !== '0'
  return !import.meta.env.DEV
}

function send(events: BeaconEvent[]): void {
  const body = JSON.stringify({ events })
  try {
    // sendBeacon survives the unload that would cancel a normal fetch; it returns false when the
    // user agent's queue is full, which is a fall-through, not a failure
    if (navigator.sendBeacon?.(BEACON_PATH, new Blob([body], { type: 'application/json' }))) return
  } catch {
    // unavailable or refused the payload — fall through
  }
  try {
    void fetch(BEACON_PATH, {
      method: 'POST',
      body,
      headers: { 'content-type': 'application/json' },
      keepalive: true,
      credentials: 'same-origin',
    }).catch(() => undefined) // dropped: fire-and-forget, and never retried
  } catch {
    // no transport at all — the events are gone, which beats growing an unbounded queue
  }
}

/** Clip strings to the server's per-value cap, recursing so a nested or in-array value is bound
 *  too. Only strings are clipped: depth, key count and list length are static properties of a
 *  call site, but a value can arrive from outside the app (a `?cluster=` deep link, a typed
 *  store path) and one oversized value would 422 the batch it rides in, taking its neighbours. */
function clip(value: unknown): unknown {
  if (typeof value === 'string') return value.slice(0, BEACON_MAX_VALUE_CHARS)
  if (Array.isArray(value)) return value.map(clip)
  if (value !== null && typeof value === 'object') return clipFields(value as LogFields)
  return value
}

function clipFields(fields: LogFields): LogFields {
  return Object.fromEntries(Object.entries(fields).map(([key, value]) => [key, clip(value)]))
}

function flush(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
  if (queue.length === 0 && dropped === 0) return
  let batch = queue
  if (dropped > 0) {
    // A drop only happens against a FULL queue, so the summary needs a slot made for it: evict
    // the newest event and fold it into the count. Prepending without evicting would post 21
    // events, and the server's max_length of 20 would 422 the whole batch — losing the very
    // window this line exists to report on.
    const kept = batch.slice(0, BEACON_BATCH - 1)
    const count = dropped + (batch.length - kept.length)
    batch = [{ level: 'warn', event: BEACON_DROPPED_EVENT, fields: { count } }, ...kept]
  }
  queue = []
  dropped = 0
  send(batch)
}

function enqueue(level: 'warn' | 'error', event: string, fields?: LogFields): void {
  if (!beaconEnabled()) return
  // Drop the one bad event rather than the batch it would have poisoned: a non-conforming name is
  // a static property of its call site, so it would fail forever and take its neighbours with it.
  // That is also why it must NOT count as a drop below — a permanent fault would otherwise
  // report itself as a fresh storm on every load of that screen.
  if (!BEACON_EVENT_NAME.test(event)) return
  // Full window = an error storm. Keep the earliest events (a cascade's first error is the
  // causal one) and drop the rest, so the send RATE stays flat no matter the event rate.
  if (queue.length >= BEACON_BATCH) {
    dropped += 1
    return
  }
  queue.push(fields === undefined ? { level, event } : { level, event, fields: clipFields(fields) })
  if (timer === null) timer = setTimeout(flush, BEACON_WINDOW_MS)
}

if (typeof window !== 'undefined') {
  // `pagehide` is the unload signal that actually fires on mobile Safari; the visibility check
  // catches a backgrounded tab the browser may never resume.
  window.addEventListener('pagehide', flush)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush()
  })
}

function emit(level: LogLevel, event: string, fields?: LogFields): void {
  if (ORDER[level] < threshold()) return
  const line: LogFields = { timestamp: new Date().toISOString(), level, event, ...fields }
  // the single sanctioned console touchpoint (see module docblock)
  // eslint-disable-next-line no-console
  console[level](line)
  if (level === 'warn' || level === 'error') enqueue(level, event, fields)
}

export const logger = {
  debug: (event: string, fields?: LogFields) => emit('debug', event, fields),
  info: (event: string, fields?: LogFields) => emit('info', event, fields),
  warn: (event: string, fields?: LogFields) => emit('warn', event, fields),
  error: (event: string, fields?: LogFields) => emit('error', event, fields),
}
