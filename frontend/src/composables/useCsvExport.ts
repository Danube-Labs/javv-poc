/**
 * The one inline-export handler (issue 509): fetch → blob → anchor download, with the busy flag
 * held for the WHOLE transfer inside a try/finally — a thrown fetch (backend down) or a slow
 * blob read can never strand the button at "Exporting…" or re-arm it mid-download. Surfaces
 * keep their own wording via the hooks: the 413 copy differs per screen on purpose, and
 * ExportDialog pivots tabs instead of toasting. Status 0 = a network-level rejection (the
 * useGlobalSearch convention).
 */
import { ref } from 'vue'

import { logger } from '@/lib/logger'

export interface CsvExportOptions {
  /** request path — a getter when it varies per run (ExportDialog's csv/vex switch) */
  path: string | (() => string)
  /** download name for today's stamp (YYYY-MM-DD) */
  filename: (stamp: string) => string
  /** logger.warn event on any failure, e.g. 'approvals_export_failed' */
  event: string
  /** 413 — the lens is over the inline cap; each surface words (and routes) this itself */
  onCapped: () => void
  /** non-2xx or a network-level rejection (status 0) */
  onFailed: (status: number) => void
  /** download landed; `name` is the file just saved */
  onDone?: (name: string) => void
}

export function useCsvExport(opts: CsvExportOptions) {
  const exporting = ref(false)

  async function run(params: Record<string, unknown>): Promise<void> {
    if (exporting.value) return
    exporting.value = true
    try {
      const qs = new URLSearchParams(
        Object.entries(params).flatMap(([k, v]) =>
          v === undefined || v === null
            ? []
            : Array.isArray(v)
              ? v.map((x) => [k, String(x)] as [string, string])
              : [[k, String(v)] as [string, string]],
        ),
      )
      const path = typeof opts.path === 'function' ? opts.path() : opts.path
      const resp = await fetch(`${path}?${qs}`, { credentials: 'same-origin' })
      if (resp.status === 413) {
        opts.onCapped()
        return
      }
      if (!resp.ok) {
        logger.warn(opts.event, { status: resp.status })
        opts.onFailed(resp.status)
        return
      }
      const blob = await resp.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = opts.filename(new Date().toISOString().slice(0, 10))
      a.click()
      URL.revokeObjectURL(a.href)
      opts.onDone?.(a.download)
    } catch {
      logger.warn(opts.event, { status: 0 })
      opts.onFailed(0)
    } finally {
      exporting.value = false
    }
  }

  return { exporting, run }
}
