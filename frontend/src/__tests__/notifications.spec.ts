/**
 * Bell feed composable (M9f slice 3, FR-16/NFR-9): the badge is the SERVER's unread count and
 * pauses on a failed poll (SCREENS §14 — no stale count); mark-read is optimistic on the local
 * row but the count never goes negative.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useNotifications } from '@/composables/useNotifications'
import { useToastStore } from '@/stores/toast'

const listMock = vi.hoisted(() => vi.fn<() => unknown>())
const readMock = vi.hoisted(() => vi.fn<(opts: { path: Record<string, string> }) => unknown>())
vi.mock('@/api/generated', () => ({
  listNotificationsApiV1NotificationsGet: listMock,
  markReadApiV1NotificationsNotificationIdReadPatch: readMock,
}))
vi.mock('@/api/client', () => ({ client: {} }))

function feed(unread: number, items: Array<Record<string, unknown>>) {
  return { response: { ok: true }, data: { unread, items } }
}

const ITEM = {
  notification_id: 'n-1',
  type: 'report_ready',
  ref: 'r-1',
  cluster_id: 'c-1',
  created_at: '2026-07-17T06:00:00Z',
  read: false,
}

beforeEach(() => {
  vi.useFakeTimers()
  setActivePinia(createPinia())
  listMock.mockReset()
  readMock.mockReset()
})
afterEach(() => vi.useRealTimers())

describe('useNotifications', () => {
  it('badge mirrors the server unread count', async () => {
    listMock.mockResolvedValue(feed(3, [ITEM]) as never)
    const bell = useNotifications()
    await bell.refresh()
    expect(bell.badge.value).toBe(3)
    expect(bell.items.value).toHaveLength(1)
  })

  it('a failed poll pauses the badge — no stale count (SCREENS §14)', async () => {
    listMock.mockResolvedValueOnce(feed(3, [ITEM]) as never)
    const bell = useNotifications()
    await bell.refresh()
    listMock.mockResolvedValueOnce({ response: { ok: false, status: 503 }, data: null } as never)
    await bell.refresh()
    expect(bell.failed.value).toBe(true)
    expect(bell.badge.value).toBeNull()
  })

  it('polling fires on start and on the interval; stop halts it', async () => {
    listMock.mockResolvedValue(feed(0, []) as never)
    const bell = useNotifications()
    bell.startPolling()
    await vi.advanceTimersByTimeAsync(0)
    expect(listMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(listMock).toHaveBeenCalledTimes(2)
    bell.stopPolling()
    await vi.advanceTimersByTimeAsync(90_000)
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('markRead flips the row + decrements, never below zero', async () => {
    listMock.mockResolvedValue(feed(1, [{ ...ITEM }]) as never)
    readMock.mockResolvedValue({ response: { ok: true } } as never)
    const bell = useNotifications()
    await bell.refresh()
    await bell.markRead('n-1')
    expect(readMock).toHaveBeenCalledWith(
      expect.objectContaining({ path: { notification_id: 'n-1' } }),
    )
    expect(bell.items.value[0]?.read).toBe(true)
    expect(bell.unread.value).toBe(0)
    await bell.markRead('n-1') // second click on an already-read row
    expect(bell.unread.value).toBe(0)
  })

  it('toast echo: a notification ARRIVING mid-session pings once; the backlog never replays', async () => {
    const toast = useToastStore()
    listMock.mockResolvedValueOnce(feed(1, [ITEM]) as never)
    const bell = useNotifications()
    await bell.refresh() // first load = backlog, no echo
    expect(toast.toasts).toHaveLength(0)
    listMock.mockResolvedValueOnce(
      feed(2, [{ ...ITEM, notification_id: 'n-2', type: 'assignment' }, ITEM]) as never,
    )
    await bell.refresh()
    expect(toast.toasts).toHaveLength(1)
    expect(toast.toasts[0]?.message).toContain('assigned to you')
    listMock.mockResolvedValueOnce(
      feed(2, [{ ...ITEM, notification_id: 'n-2', type: 'assignment' }, ITEM]) as never,
    )
    await bell.refresh() // same feed again — no re-echo
    expect(toast.toasts).toHaveLength(1)
  })

  it('a 5xx markRead changes nothing locally', async () => {
    listMock.mockResolvedValue(feed(1, [{ ...ITEM }]) as never)
    readMock.mockResolvedValue({ response: { ok: false, status: 503 } } as never)
    const bell = useNotifications()
    await bell.refresh()
    await bell.markRead('n-1')
    expect(bell.items.value[0]?.read).toBe(false)
    expect(bell.unread.value).toBe(1)
  })

  it('a 404 markRead drops the stale row — already gone server-side (TTL sweep race)', async () => {
    listMock.mockResolvedValue(feed(1, [{ ...ITEM }]) as never)
    readMock.mockResolvedValue({ response: { ok: false, status: 404 } } as never)
    const bell = useNotifications()
    await bell.refresh()
    await bell.markRead('n-1')
    expect(bell.items.value).toHaveLength(0)
    expect(bell.unread.value).toBe(0)
  })
})
