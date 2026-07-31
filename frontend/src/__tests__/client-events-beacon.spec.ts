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
async function sentEvents(sendBeacon: Beacon): Promise<unknown[]> {
  const blob = sendBeacon.mock.calls[0]![1] as Blob
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
    const events = (await sentEvents(sendBeacon)) as { fields: { i: number } }[]
    expect(events).toHaveLength(20)
    expect(events[0]!.fields.i).toBe(0) // the earliest kept — a cascade's first error is causal
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
