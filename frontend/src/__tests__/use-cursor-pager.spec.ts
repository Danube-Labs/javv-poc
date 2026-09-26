import { describe, expect, it } from 'vitest'

import { useCursorPager } from '@/composables/useCursorPager'

describe('useCursorPager', () => {
  it('starts on page 0 with no cursor and nowhere to go', () => {
    const p = useCursorPager(10)
    expect(p.page.value).toBe(0)
    expect(p.size.value).toBe(10)
    expect(p.cursor.value).toBeNull()
    expect(p.hasPrev.value).toBe(false)
    expect(p.hasNext.value).toBe(false)
  })

  it('walks forward on the cursors the server handed back, and back on the remembered ones', () => {
    const p = useCursorPager()
    p.landed('c1')
    expect(p.hasNext.value).toBe(true)
    expect(p.next()).toBe(true)
    expect(p.page.value).toBe(1)
    expect(p.cursor.value).toBe('c1') // cursors[i] FETCHES page i
    expect(p.hasNext.value).toBe(false) // unknown until page 1 lands

    p.landed('c2')
    expect(p.next()).toBe(true)
    expect(p.cursor.value).toBe('c2')

    expect(p.prev()).toBe(true)
    expect(p.page.value).toBe(1)
    expect(p.cursor.value).toBe('c1') // back = the cursor that fetched page 1 the first time
    expect(p.prev()).toBe(true)
    expect(p.cursor.value).toBeNull()
  })

  it('refuses to move past either end — the caller must not fetch', () => {
    const p = useCursorPager()
    expect(p.prev()).toBe(false)
    p.landed(null) // the last page
    expect(p.next()).toBe(false)
    expect(p.page.value).toBe(0)
  })

  it('reset drops the stack — another query must not page through this one', () => {
    const p = useCursorPager()
    p.landed('c1')
    p.next()
    p.landed('c2')
    p.reset()
    expect(p.page.value).toBe(0)
    expect(p.cursor.value).toBeNull()
    expect(p.hasNext.value).toBe(false)
  })

  it('a new page size starts over from page 0', () => {
    const p = useCursorPager(10)
    p.landed('c1')
    p.next()
    p.setSize(50)
    expect(p.size.value).toBe(50)
    expect(p.page.value).toBe(0)
    expect(p.cursor.value).toBeNull()
  })
})
