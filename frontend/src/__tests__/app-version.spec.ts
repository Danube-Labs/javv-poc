/**
 * The frontend's own version (issue 341): `src/version.ts` is the release, bumped by release-please
 * the way `backend/src/backend/version.py` is. The About page shows both, so a rollout where the
 * two images differ is visible. A release PR that stops bumping this file fails here.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { APP_VERSION } from '@/version'

const repoRoot = resolve(process.cwd(), '..')
const readJson = (name: string) => JSON.parse(readFileSync(resolve(repoRoot, name), 'utf8'))

describe('frontend version', () => {
  it('equals the release-please manifest', () => {
    expect(APP_VERSION).toBe(readJson('.release-please-manifest.json')['.'])
  })

  it('is bumped by release-please on every release', () => {
    const extraFiles = readJson('release-please-config.json').packages['.']['extra-files']
    expect(extraFiles).toContainEqual({ type: 'generic', path: 'frontend/src/version.ts' })
  })

  it('carries the marker the generic updater rewrites', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/version.ts'), 'utf8')
    expect(source).toMatch(/APP_VERSION = '[^']+' \/\/ x-release-please-version/)
  })
})
