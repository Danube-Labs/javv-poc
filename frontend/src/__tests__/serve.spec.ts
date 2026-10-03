// @vitest-environment node
/**
 * The frontend container's server (server/serve.mjs, issue 452), run for real: a fake backend on
 * a free port, a throwaway dist/, and fetch against the frontend server.
 */
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createLogger } from '../../server/log.mjs'
import { createFrontendServer } from '../../server/serve.mjs'

type Seen = { method?: string; url?: string; headers: http.IncomingHttpHeaders; body: string }

let dist: string
let backend: http.Server
let backendUrl: string
let seen: Seen[] = []
let lines: string[] = []
const servers: http.Server[] = []

const listen = (server: http.Server): Promise<string> =>
  new Promise((resolve) =>
    server.listen(0, '127.0.0.1', () =>
      resolve(`http://127.0.0.1:${(server.address() as AddressInfo).port}`),
    ),
  )

async function frontend(url = backendUrl, warnWindowMs?: number): Promise<string> {
  const log = createLogger('info', (line) => lines.push(line))
  const server = createFrontendServer({ backendUrl: url, distDir: dist, log, warnWindowMs })
  servers.push(server)
  return listen(server)
}

beforeAll(async () => {
  dist = mkdtempSync(join(tmpdir(), 'javv-dist-'))
  mkdirSync(join(dist, 'assets'))
  writeFileSync(join(dist, 'index.html'), '<!doctype html><div id="app"></div>')
  writeFileSync(join(dist, 'assets', 'index-abc123.js'), 'console.log(1)')
  writeFileSync(join(dist, 'favicon.ico'), 'icon')

  backend = http.createServer((req, res) => {
    let body = ''
    req.on('data', (chunk: Buffer) => (body += chunk.toString()))
    req.on('end', () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body })
      if (req.url?.startsWith('/api/v1/missing')) {
        res.writeHead(404, { 'content-type': 'application/problem+json' })
        res.end('{"title":"Not Found","status":404}')
      } else if (req.url === '/auth/login') {
        res.writeHead(200, { 'set-cookie': ['javv_session=abc; HttpOnly; Path=/', 'other=1; Path=/'] })
        res.end('{"user":{}}')
      } else if (req.url === '/api/v1/stream') {
        res.writeHead(200, { 'content-type': 'text/csv' })
        res.write('a,b\n')
        setTimeout(() => res.end('1,2\n'), 20)
      } else {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(`{"echo":${JSON.stringify(body)}}`)
      }
    })
  })
  backendUrl = await listen(backend)
})

afterEach(async () => {
  await Promise.all(servers.splice(0).map((s) => new Promise((r) => s.close(r))))
  seen = []
  lines = []
})

afterAll(async () => {
  await new Promise((r) => backend.close(r))
  rmSync(dist, { recursive: true, force: true })
})

describe('the static files', () => {
  it('serves index.html for a history-mode route, never cached', async () => {
    const res = await fetch(`${await frontend()}/findings`)
    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toMatch(/^text\/html/)
    expect(res.headers.get('cache-control')).toBe('no-cache')
    expect(await res.text()).toContain('id="app"')
  })

  it('serves a hashed asset as immutable, with its own type', async () => {
    const res = await fetch(`${await frontend()}/assets/index-abc123.js`)
    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toMatch(/^text\/javascript/)
    expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable')
  })

  it('answers HEAD with the headers and no body', async () => {
    const res = await fetch(`${await frontend()}/assets/index-abc123.js`, { method: 'HEAD' })
    expect(res.status).toBe(200)
    expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable')
    expect(await res.text()).toBe('')
  })

  it('serves other root files uncached', async () => {
    const res = await fetch(`${await frontend()}/favicon.ico`)
    expect(res.headers.get('cache-control')).toBe('no-cache')
  })

  it('answers 404 for a missing hashed asset, not index.html as script', async () => {
    const res = await fetch(`${await frontend()}/assets/index-gone.js`)
    expect(res.status).toBe(404)
    expect(await res.text()).not.toContain('id="app"')
  })

  it('never serves a file from outside dist', async () => {
    // fetch would normalize dot segments; an encoded slash survives the URL parser and decodes
    // to ../ in the server, so send the raw path
    const { port } = new URL(await frontend())
    const body = await new Promise<string>((resolve, reject) => {
      http
        .get({ host: '127.0.0.1', port, path: '/..%2f..%2f..%2f..%2fetc%2fpasswd' }, (res) => {
          let text = ''
          res.on('data', (c: Buffer) => (text += c.toString()))
          res.on('end', () => resolve(text))
        })
        .on('error', reject)
    })
    expect(body).toContain('id="app"') // the SPA, not the file
    expect(body).not.toContain('root:')
  })

  it('refuses a write to a static path', async () => {
    const res = await fetch(`${await frontend()}/findings`, { method: 'POST' })
    expect(res.status).toBe(405)
  })
})

describe('the forward to the backend', () => {
  it('forwards /api, /auth and /readyz with method, query and body', async () => {
    const base = await frontend()
    await fetch(`${base}/api/v1/findings?cluster_id=c1&q=x`, { method: 'POST', body: '{"a":1}' })
    await fetch(`${base}/readyz`)
    expect(seen.map((s) => `${s.method} ${s.url}`)).toEqual([
      'POST /api/v1/findings?cluster_id=c1&q=x',
      'GET /readyz',
    ])
    expect(seen[0]!.body).toBe('{"a":1}')
  })

  it('passes every Set-Cookie from the backend through, and the browser cookie to it', async () => {
    const res = await fetch(`${await frontend()}/auth/login`, {
      method: 'POST',
      headers: { cookie: 'javv_session=old' },
    })
    expect(res.headers.getSetCookie()).toEqual(['javv_session=abc; HttpOnly; Path=/', 'other=1; Path=/'])
    expect(seen[0]!.headers.cookie).toBe('javv_session=old')
  })

  it('passes a backend 404 under /api through, instead of the SPA', async () => {
    const res = await fetch(`${await frontend()}/api/v1/missing`)
    expect(res.status).toBe(404)
    expect(await res.json()).toEqual({ title: 'Not Found', status: 404 })
  })

  it('does not forward a path that only starts with the same letters', async () => {
    const res = await fetch(`${await frontend()}/apiary`)
    expect(seen).toHaveLength(0)
    expect(await res.text()).toContain('id="app"')
  })

  it('streams a response body through', async () => {
    const res = await fetch(`${await frontend()}/api/v1/stream`)
    expect(await res.text()).toBe('a,b\n1,2\n')
  })

  it('keeps a valid request id, and mints one when there is none', async () => {
    const base = await frontend()
    await fetch(`${base}/api/v1/x`, { headers: { 'x-request-id': 'trace-123' } })
    await fetch(`${base}/api/v1/x`, { headers: { 'x-request-id': 'bad id!' } })
    expect(seen[0]!.headers['x-request-id']).toBe('trace-123')
    expect(seen[1]!.headers['x-request-id']).toMatch(/^[0-9a-f]{16}$/)
  })
})

async function deadBackend(): Promise<string> {
  const dead = http.createServer()
  const url = await listen(dead)
  await new Promise((r) => dead.close(r)) // the port is now closed: connection refused
  return url
}

describe('a backend that does not answer', () => {
  it('gets a 502 with the error envelope, and one warning line', async () => {
    const deadUrl = await deadBackend()

    const res = await fetch(`${await frontend(deadUrl)}/readyz?x=secret`, {
      headers: { 'x-request-id': 'rid-1', authorization: 'Bearer t0ken', cookie: 'javv_session=s3' },
    })

    expect(res.status).toBe(502) // the SPA reads 502 as the backend, 503 as the store
    expect(res.headers.get('content-type')).toBe('application/problem+json')
    expect(await res.json()).toEqual({
      type: 'about:blank',
      title: 'Backend unavailable',
      status: 502,
      detail: 'The JAVV backend did not answer.',
      request_id: 'rid-1',
    })
    expect(lines).toHaveLength(1)
    const line = JSON.parse(lines[0]!)
    expect(Object.keys(line).slice(0, 3)).toEqual(['timestamp', 'level', 'event'])
    expect(line).toMatchObject({
      level: 'warning',
      event: 'backend unreachable',
      path: '/readyz',
      status: 502,
      held_back: 0,
    })
    // no query string, header or credential reaches the log
    expect(lines[0]).not.toMatch(/secret|t0ken|s3|Bearer|cookie|authorization/i)
  })

  it('logs a burst of 502s once per window, with the count it held back', async () => {
    const base = await frontend(await deadBackend(), 60_000)
    for (let i = 0; i < 3; i++) expect((await fetch(`${base}/readyz`)).status).toBe(502)
    expect(lines).toHaveLength(1) // any sender can repeat a 502 while the backend is down

    lines = []
    const every = await frontend(await deadBackend(), 0)
    await fetch(`${every}/readyz`)
    await fetch(`${every}/readyz`)
    expect(lines.map((l) => JSON.parse(l).held_back)).toEqual([0, 0])
  })
})

describe('the log lines', () => {
  it('follow JAVV_LOG_LEVEL, and an unknown level stops the server at start', () => {
    const out: string[] = []
    const log = createLogger('warning', (l) => out.push(l))
    log.info('quiet')
    log.warning('loud', { n: 1 })
    expect(out).toHaveLength(1)
    expect(() => createLogger('verbose')).toThrow(/unknown log level/)
  })

  it('never carry a header or a body: no log call in the server reads one', () => {
    const source = readFileSync(new URL('../../server/serve.mjs', import.meta.url), 'utf8')
    const calls = [...source.matchAll(/log\.(?:debug|info|warning|error)\(([\s\S]*?)\)\n/g)]
    expect(calls.length).toBeGreaterThan(0)
    for (const [call] of calls) expect(call).not.toMatch(/headers|cookie|authorization|body|req\.url/i)
  })
})
