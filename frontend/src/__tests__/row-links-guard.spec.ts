/**
 * A row that opens something on click must also offer a real link (issue 674): nine tables
 * shipped mouse-only before anyone tried the keyboard. This reads the source, so a new
 * clickable row without a link fails here instead of in an accessibility review.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = resolve(process.cwd(), 'src')
function vueFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return vueFiles(path)
    return name.endsWith('.vue') ? [path] : []
  })
}

describe('clickable rows carry a link', () => {
  const files = vueFiles(SRC).map((path) => ({ rel: relative(SRC, path), src: readFileSync(path, 'utf8') }))

  it('every hand-built row with a click handler has a RowLink in it', () => {
    const missing = files
      .filter(({ src }) => /<tr\b[^>]*@click=/.test(src))
      .filter(({ src }) => !src.includes('<RowLink'))
      .map(({ rel }) => rel)
    expect(missing).toEqual([])
  })

  it('every grid that emits a row click is given the route its identifier links to', () => {
    // the grid components themselves own the RowLink; their USERS must pass `row-to`
    // (an attribute can hold `=>`, so the tag is not matched up to its `>`)
    const users = files.filter(({ src }) => /<(FindingsTable|ImagesTable|AuditTable)\b/.test(src) && src.includes('@row-click='))
    const missing = users.filter(({ src }) => !/:row-to=/.test(src)).map(({ rel }) => rel)
    expect(users.length).toBeGreaterThanOrEqual(4) // guards against a hollow pass
    expect(missing).toEqual([])
  })

  it('each grid that takes `rowTo` renders its identifier through RowLink', () => {
    for (const name of ['findings/FindingsTable.vue', 'images/ImagesTable.vue', 'audit/AuditTable.vue']) {
      const src = files.find((f) => f.rel === `components/${name}`)!.src
      expect(src).toMatch(/<RowLink v-if="[^"]*rowTo/)
    }
  })
})
