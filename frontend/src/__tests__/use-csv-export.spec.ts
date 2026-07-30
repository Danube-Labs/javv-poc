/**
 * useCsvExport pins (issue 509): the busy flag survives every exit — a REJECTED fetch (backend
 * down, not just a non-2xx) releases it, and it stays held until the blob is fully read, so a
 * second click can't start a second export against the same PIT budget mid-download.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useCsvExport } from '@/composables/useCsvExport'

vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn<() => void>(),
    info: vi.fn<() => void>(),
    warn: vi.fn<() => void>(),
    error: vi.fn<() => void>(),
  },
}))

function makeExport(overrides: Partial<Parameters<typeof useCsvExport>[0]> = {}) {
  const onCapped = vi.fn<() => void>()
  const onFailed = vi.fn<(status: number) => void>()
  const onDone = vi.fn<(name: string) => void>()
  const csv = useCsvExport({
    path: '/api/v1/things/export.csv',
    filename: (stamp) => `javv-things-${stamp}.csv`,
    event: 'things_export_failed',
    onCapped,
    onFailed,
    onDone,
    ...overrides,
  })
  return { ...csv, onCapped, onFailed, onDone }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useCsvExport', () => {
  it('a rejected fetch releases the flag and reports status 0 — the button stays clickable', async () => {
    vi.stubGlobal('fetch', vi.fn<() => Promise<unknown>>().mockRejectedValue(new TypeError('Failed to fetch')))
    const { exporting, run, onFailed } = makeExport()

    await run({ cluster_id: 'c1' })

    expect(exporting.value).toBe(false)
    expect(onFailed).toHaveBeenCalledWith(0)
  })

  it('the flag spans the WHOLE transfer: still true while the blob reads, false after', async () => {
    let releaseBlob!: (b: Blob) => void
    const blobPromise = new Promise<Blob>((resolve) => (releaseBlob = resolve))
    vi.stubGlobal(
      'fetch',
      vi.fn<() => Promise<unknown>>().mockResolvedValue({ ok: true, status: 200, blob: () => blobPromise }),
    )
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn<() => string>(() => 'blob:x'),
      revokeObjectURL: vi.fn<() => void>(),
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const { exporting, run, onDone } = makeExport()

    const running = run({ cluster_id: 'c1' })
    await vi.waitFor(() => expect(exporting.value).toBe(true))
    expect(exporting.value).toBe(true) // headers arrived, body still streaming — button stays off

    releaseBlob(new Blob(['a,b\n']))
    await running
    expect(exporting.value).toBe(false)
    expect(onDone).toHaveBeenCalledWith(expect.stringMatching(/^javv-things-\d{4}-\d{2}-\d{2}\.csv$/))
  })

  it('413 routes to onCapped without logging a failure; non-2xx routes to onFailed', async () => {
    const fetchMock = vi
      .fn<() => Promise<unknown>>()
      .mockResolvedValueOnce({ ok: false, status: 413 })
      .mockResolvedValueOnce({ ok: false, status: 503 })
    vi.stubGlobal('fetch', fetchMock)
    const { run, onCapped, onFailed, onDone } = makeExport()

    await run({})
    expect(onCapped).toHaveBeenCalledTimes(1)

    await run({})
    expect(onFailed).toHaveBeenCalledWith(503)
    expect(onDone).not.toHaveBeenCalled()
  })

  it('re-entry while exporting is a no-op — one fetch per download', async () => {
    let release!: (r: unknown) => void
    vi.stubGlobal(
      'fetch',
      vi.fn<() => Promise<unknown>>().mockReturnValue(new Promise((resolve) => (release = resolve))),
    )
    const { run } = makeExport()

    const first = run({})
    const second = run({})
    release({ ok: false, status: 500 })
    await Promise.all([first, second])
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('array params expand to repeated query keys; null/undefined are dropped', async () => {
    const fetchMock = vi
      .fn<(input: string) => Promise<unknown>>()
      .mockResolvedValue({ ok: false, status: 500 })
    vi.stubGlobal('fetch', fetchMock)
    const { run } = makeExport()

    await run({ severity: ['high', 'critical'], q: undefined, actor: null, size: 5 })
    const url = String(fetchMock.mock.calls[0]![0])
    expect(url).toContain('severity=high')
    expect(url).toContain('severity=critical')
    expect(url).toContain('size=5')
    expect(url).not.toContain('actor')
    expect(url).not.toContain('q=')
  })
})
