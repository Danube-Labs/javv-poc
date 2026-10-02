/**
 * Repair actions lists only the jobs that can be started from it. The jobs route returns every
 * background job (issue 556); the scheduled-only ones have no Run button and belong elsewhere.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as sdk from '@/api/generated'
import RepairActionsCard from '@/components/system/RepairActionsCard.vue'

vi.mock('@/api/generated', () => ({
  listJobsApiV1AdminJobsGet: vi.fn<() => Promise<unknown>>(),
  triggerJobApiV1AdminJobsKindRunPost: vi.fn<() => Promise<unknown>>(),
}))

const job = (kind: string, capability: string | null) => ({
  kind,
  status: 'idle',
  stale: false,
  capability,
  runnable: capability !== null,
  schedule: null,
  next_run_at: null,
  health: 'off',
})

describe('RepairActionsCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows a row for each runnable job and none for the scheduled-only ones', async () => {
    vi.mocked(sdk.listJobsApiV1AdminJobsGet).mockResolvedValue({
      response: { ok: true },
      data: {
        jobs: [
          job('rebuild_state', 'can_rebuild_state'),
          job('staleness_sweep', 'can_manage_settings'),
          job('lifecycle_sweep', 'can_drop_index'),
          job('findings_cleanup', null),
          job('session_sweep', null),
          job('report_sweep', null),
          job('report_drain', null),
        ],
      },
    } as never)
    const w = mount(RepairActionsCard)
    await flushPromises()
    const names = w.findAll('section')[0]!.findAll('.repair-name b').map((b) => b.text())
    expect(names).toEqual(['Rebuild state', 'Staleness sweep', 'Lifecycle sweep'])
  })
})
