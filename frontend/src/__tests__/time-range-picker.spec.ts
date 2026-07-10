/**
 * Pins the range-control semantics (#300/#301): range END → global as_of (minute-precise,
 * null when ending now), range SPAN → whole-day windowDays (sub-day quick-selects round UP),
 * strict 24h HH:mm validation, 24-hour labels — never AM/PM.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import GlobalTimePicker from '@/components/time-travel/GlobalTimePicker.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'

async function open(w: ReturnType<typeof mount>) {
  await w.find('.time-range').trigger('click')
}

describe('GlobalTimePicker (single range control)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useRealTimers()
  })

  it('quick select rounds sub-day spans UP to one day but keeps the exact label', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    await open(w)
    await w.find('input[aria-label="Range length"]').setValue(90)
    await w.find('select[aria-label="Range unit"]').setValue('minutes')
    await w.find('.time-rel .time-apply').trigger('click')
    expect(store.windowDays).toBe(1) // trends contract: int days ≥1
    expect(store.windowLabel).toBe('Last 90 minutes')
    expect(store.t).toBeNull() // quick selects end now — no as_of
  })

  it('weeks multiply into days; presets set span and end-now', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    await open(w)
    await w.find('input[aria-label="Range length"]').setValue(2)
    await w.find('select[aria-label="Range unit"]').setValue('weeks')
    await w.find('.time-rel .time-apply').trigger('click')
    expect(store.windowDays).toBe(14)

    await open(w)
    const preset = w.findAll('.time-preset').find((b) => b.text() === 'Last 90 days')
    await preset?.trigger('click')
    expect(store.windowDays).toBe(90)
    expect(store.windowLabel).toBe('Last 90 days')
    expect(store.t).toBeNull()
  })

  it('an absolute range ending in the past sets minute-precise as_of + the day span', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    await open(w)
    await w.find('input[aria-label="Range start date"]').setValue('2026-07-01')
    await w.find('input[aria-label="Range start time (24h)"]').setValue('08:00')
    await w.find('input[aria-label="Range end date"]').setValue('2026-07-08')
    await w.find('input[aria-label="Range end time (24h)"]').setValue('14:30')
    await w.find('.time-abs .time-apply').trigger('click')
    expect(store.t).toBe(new Date('2026-07-08T14:30:00').toISOString())
    expect(store.windowDays).toBe(7)
    expect(store.windowLabel).not.toMatch(/AM|PM/i) // 24h labels, never AM/PM
    expect(store.windowLabel).toContain('14:30')
  })

  it('an absolute range ending in the future stays at T=now (no as_of)', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    const future = new Date(Date.now() + 3_600_000) // +1h local
    const pad = (n: number) => String(n).padStart(2, '0')
    const d = `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(future.getDate())}`
    const hm = `${pad(future.getHours())}:${pad(future.getMinutes())}`
    await open(w)
    await w.find('input[aria-label="Range start date"]').setValue(d)
    await w.find('input[aria-label="Range start time (24h)"]').setValue('00:00')
    await w.find('input[aria-label="Range end date"]').setValue(d)
    await w.find('input[aria-label="Range end time (24h)"]').setValue(hm)
    await w.find('.time-abs .time-apply').trigger('click')
    expect(store.t).toBeNull() // ends ahead of now → current state, no as_of
    expect(store.windowLabel).not.toMatch(/AM|PM/i)
  })

  it('rejects invalid 24h times — Apply stays disabled', async () => {
    const w = mount(GlobalTimePicker)
    await open(w)
    await w.find('input[aria-label="Range start date"]').setValue('2026-07-01')
    await w.find('input[aria-label="Range start time (24h)"]').setValue('25:00') // invalid hour
    await w.find('input[aria-label="Range end date"]').setValue('2026-07-02')
    await w.find('input[aria-label="Range end time (24h)"]').setValue('9:75') // invalid minutes
    expect((w.find('.time-abs .time-apply').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('back-to-now clears as_of and restores the default window', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    store.rewindTo('2026-07-08T14:30:00.000Z')
    store.setWindow(7, 'Jul 1, 08:00 → Jul 8, 14:30')
    await open(w)
    await w.find('.back-now').trigger('click')
    expect(store.t).toBeNull()
    expect(store.windowDays).toBe(30)
    expect(store.windowLabel).toBe('Last 30 days')
  })
})
