/**
 * A reply that arrives OK with no body (issue 749). The generated client catches a failed body
 * read or a failed parse and hands back the response it already had, so `response.ok` is true
 * while `data` is missing. Every reader of `data` relies on this shape, and `okWithoutBody()`
 * copies it for the component specs: if the client changes, this file fails first.
 */
import { describe, expect, it } from 'vitest'

import { createClient } from '@/api/generated/client'

import { okWithoutBody } from './helpers/okWithoutBody'

function clientServing(body: BodyInit) {
  return createClient({
    baseUrl: 'http://backend.test',
    throwOnError: false,
    fetch: async () =>
      new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } }),
  })
}

describe('the generated client, given a 200 whose body never arrives whole', () => {
  it('a body read that fails part way leaves response.ok true and data missing', async () => {
    const cut = new ReadableStream({
      start(c) {
        c.enqueue(new TextEncoder().encode('{"series":'))
        c.error(new DOMException('The user aborted a request.', 'AbortError'))
      },
    })
    const r = (await clientServing(cut).get({ url: '/api/v1/trends/scans' })) as {
      data?: unknown
      error?: unknown
      response: Response
    }
    expect(r.response.ok).toBe(true)
    expect(r.data).toBeUndefined()
    expect(String(r.error)).toContain('AbortError')
  })

  it('a body that is not whole JSON does the same', async () => {
    const r = (await clientServing('{"series":').get({ url: '/api/v1/trends/scans' })) as {
      data?: unknown
      response: Response
    }
    expect(r.response.ok).toBe(true)
    expect(r.data).toBeUndefined()
  })

  it('okWithoutBody() has that shape', () => {
    const r = okWithoutBody() as { data?: unknown; error: unknown; response: { ok: boolean } }
    expect(r.response.ok).toBe(true)
    expect(r.data).toBeUndefined()
    expect(r.error).toBeDefined()
  })
})
