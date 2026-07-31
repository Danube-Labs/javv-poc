/**
 * The client-events beacon transport (issue 453 slice 2) — the lossy half of the logger.
 *
 * Every assertion here is about a property that only holds if the mechanism is present, so each
 * test fails if its guard is deleted: batching, the fixed window, the queue cap that keeps an
 * error storm from bursting requests, the loop guard, and the knob.
 *
 * The transport keeps module-level state (queue + timer), so every test re-imports the module
 * through `vi.resetModules()` rather than sharing one instance.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const WINDOW_MS = 5000

type Beacon = ReturnType<typeof vi.fn<(url: string, body?: BodyInit) => boolean>>

function stubTransport({ beaconReturns = true }: { beaconReturns?: boolean } = {}) {
  const sendBeacon: Beacon = vi.fn<(url: string, body?: BodyInit) => boolean>(() => beaconReturns)
  const fetchSpy = vi.fn<(input: string, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(new Response(null, { status: 204 })),
  )
  vi.stubGlobal('navigator', { ...navigator, sendBeacon })
  vi.stubGlobal('fetch', fetchSpy)
  return { sendBeacon, fetchSpy }
}

/** The transport's only sink is the network; console is the logger's. Reading a sent batch back
 *  proves what actually left the building, not merely that something was called. */
async function sentEvents(sendBeacon: Beacon, call = 0): Promise<unknown[]> {
  const blob = sendBeacon.mock.calls[call]![1] as Blob
  return JSON.parse(await blob.text()).events
}

async function loadLogger() {
  vi.resetModules()
  return (await import('@/lib/logger')).logger
}

/** Counted in the mock rather than read back off `console`: a bare `console.error` member access
 *  is ESLint-banned, and the ban applies to specs too. */
let errorEmissions = 0

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubEnv('VITE_CLIENT_EVENTS', 'true') // dev default is OFF — asserted in its own test
  errorEmissions = 0
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {
    errorEmissions += 1
  })
  vi.spyOn(console, 'info').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  // the tab-hide test redefines this; jsdom's default is 'visible' and leaking 'hidden' would
  // silently arm the flush listener for every later test
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
})

describe('client-events beacon', () => {
  it('batches a window of events into ONE request', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    logger.warn('backend degraded', { source: 'api-503' })
    logger.error('findings_search_failed', { status: 500 })
    expect(sendBeacon).not.toHaveBeenCalled() // still throttled

    vi.advanceTimersByTime(WINDOW_MS)
    expect(sendBeacon).toHaveBeenCalledOnce()
    expect(await sentEvents(sendBeacon)).toEqual([
      { level: 'warn', event: 'backend degraded', fields: { source: 'api-503' } },
      { level: 'error', event: 'findings_search_failed', fields: { status: 500 } },
    ])
  })

  it('holds everything until the window elapses — nothing is sent per-event', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    logger.error('audit_load_failed')
    vi.advanceTimersByTime(WINDOW_MS - 1)
    expect(sendBeacon).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(sendBeacon).toHaveBeenCalledOnce()
  })

  it('an error storm drops events instead of bursting requests', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    for (let i = 0; i < 200; i++) logger.error('images_load_failed', { i })
    vi.advanceTimersByTime(WINDOW_MS)

    // the guard that matters: 200 events must not become 10 requests against a 60/min cap
    expect(sendBeacon).toHaveBeenCalledOnce()
    const events = (await sentEvents(sendBeacon)) as {
      event: string
      fields: { i?: number; count?: number }
    }[]
    // never MORE than 20 either: the server's max_length is 20, so a summary that grew the batch
    // to 21 would 422 the whole thing — the storm report has to be seated, not appended
    expect(events).toHaveLength(20)
    expect(events[0]!.event).toBe('beacon events dropped')
    expect(events[0]!.fields.count).toBe(181) // 180 refused entry, +1 evicted to seat this line
    expect(events[1]!.fields.i).toBe(0) // the earliest kept — a cascade's first error is causal
  })

  it('a full window that never overflowed ships no summary', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    for (let i = 0; i < 20; i++) logger.error('images_load_failed', { i })
    vi.advanceTimersByTime(WINDOW_MS)

    const events = (await sentEvents(sendBeacon)) as { event: string }[]
    expect(events).toHaveLength(20)
    expect(events.every((e) => e.event === 'images_load_failed')).toBe(true)
  })

  it('the drop count resets once reported, so a later quiet window reads clean', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    for (let i = 0; i < 200; i++) logger.error('images_load_failed', { i })
    vi.advanceTimersByTime(WINDOW_MS) // window 1: the storm, reported

    logger.error('audit_load_failed')
    vi.advanceTimersByTime(WINDOW_MS) // window 2: one event, nothing dropped

    expect(await sentEvents(sendBeacon, 1)).toEqual([
      { level: 'error', event: 'audit_load_failed' },
    ])
  })

  it('only warn and error are shipped', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    logger.debug('noise')
    logger.info('view mounted')
    vi.advanceTimersByTime(WINDOW_MS)
    expect(sendBeacon).not.toHaveBeenCalled()
  })

  it('drops a name the server would 422, keeping the rest of the batch', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    logger.error('Uppercase Name') // fails the server's pattern
    logger.error('has\nnewline')
    logger.error('audit_load_failed') // conforms
    vi.advanceTimersByTime(WINDOW_MS)

    const events = (await sentEvents(sendBeacon)) as { event: string }[]
    expect(events.map((e) => e.event)).toEqual(['audit_load_failed'])
  })

  it('flushes immediately on pagehide rather than losing the tail', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    logger.error('notifications_poll_failed')
    window.dispatchEvent(new Event('pagehide'))
    expect(sendBeacon).toHaveBeenCalledOnce() // no timer advance
  })

  it('flushes on tab-hide, and only when the tab is actually hidden', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    logger.error('notifications_poll_failed')
    document.dispatchEvent(new Event('visibilitychange')) // still visible — must NOT flush
    expect(sendBeacon).not.toHaveBeenCalled()

    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(sendBeacon).toHaveBeenCalledOnce() // no timer advance — a backgrounded tab may not resume
  })

  it('clips an oversized value instead of letting it 422 the batch it rides in', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    // the real shape: `?cluster=` off a deep link, logged on the branch that fires BECAUSE the
    // id is unknown — externally supplied, unbounded, and not a call-site literal
    logger.warn('url_cluster_unknown', { cluster_id: 'c-'.padEnd(600, 'x') })
    logger.error('audit_load_failed', { status: 500 })
    vi.advanceTimersByTime(WINDOW_MS)

    const events = (await sentEvents(sendBeacon)) as { fields: { cluster_id?: string } }[]
    expect(events[0]!.fields.cluster_id).toHaveLength(512) // the server's per-value cap
    expect(events).toHaveLength(2) // and the neighbour it would have taken down still shipped
  })

  it('clips nested and in-array strings, leaving non-strings untouched', async () => {
    const { sendBeacon } = stubTransport()
    const logger = await loadLogger()

    const long = 'y'.repeat(600)
    logger.error('inspect_rejected', { nested: { path: long }, list: [long], status: 422, ok: false })
    vi.advanceTimersByTime(WINDOW_MS)

    const [event] = (await sentEvents(sendBeacon)) as {
      fields: { nested: { path: string }; list: string[]; status: number; ok: boolean }
    }[]
    expect(event!.fields.nested.path).toHaveLength(512)
    expect(event!.fields.list[0]).toHaveLength(512)
    expect(event!.fields.status).toBe(422) // numbers survive the walk unchanged
    expect(event!.fields.ok).toBe(false)
  })

  it('falls back to fetch keepalive when sendBeacon refuses the payload', async () => {
    const { sendBeacon, fetchSpy } = stubTransport({ beaconReturns: false })
    const logger = await loadLogger()

    logger.error('export_schedule_failed')
    vi.advanceTimersByTime(WINDOW_MS)

    expect(sendBeacon).toHaveBeenCalledOnce()
    expect(fetchSpy).toHaveBeenCalledOnce()
    const init = fetchSpy.mock.calls[0]![1]!
    expect(init.keepalive).toBe(true)
    expect(init.credentials).toBe('same-origin') // the session cookie must ride along
  })

  it('a transport that throws never routes back through the logger (the loop guard)', async () => {
    const { fetchSpy } = stubTransport()
    vi.stubGlobal('navigator', {
      ...navigator,
      sendBeacon: () => {
        throw new Error('beacon exploded')
      },
    })
    fetchSpy.mockImplementation(() => Promise.reject(new Error('network down')))
    const logger = await loadLogger()

    logger.error('clusters_fetch_failed')
    const before = errorEmissions
    expect(() => vi.advanceTimersByTime(WINDOW_MS)).not.toThrow()
    await Promise.resolve()

    // one emission for the original call site, and NOTHING added by the failed transport —
    // otherwise a logging outage would manufacture the events it just failed to ship
    expect(before).toBe(1)
    expect(errorEmissions).toBe(before)
  })

  it('is off by default in dev, and the knob turns it off explicitly', async () => {
    vi.unstubAllEnvs() // VITE_CLIENT_EVENTS unset; vitest runs with DEV true
    const { sendBeacon, fetchSpy } = stubTransport()
    let logger = await loadLogger()
    logger.error('inspect_rejected')
    vi.advanceTimersByTime(WINDOW_MS)
    expect(sendBeacon).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()

    vi.stubEnv('VITE_CLIENT_EVENTS', 'false')
    logger = await loadLogger()
    logger.error('inspect_rejected')
    vi.advanceTimersByTime(WINDOW_MS)
    expect(sendBeacon).not.toHaveBeenCalled()
  })
})
