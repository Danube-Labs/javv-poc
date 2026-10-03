import { vi } from 'vitest'

type Sdk = Record<string, unknown>

/**
 * The factory for `vi.mock('@/api/generated', ...)`: every function the real SDK exports, each a
 * `vi.fn` that rejects with its own name, with the spec's own entries laid over them. A spec can
 * then never leave out a call that the code it mounts imports (issue 707).
 */
export async function mockSdk(importOriginal: () => Promise<Sdk>, overrides: Sdk = {}): Promise<Sdk> {
  const real = await importOriginal()
  const stubs: Sdk = {}
  for (const [name, value] of Object.entries(real)) {
    if (typeof value === 'function') {
      stubs[name] = vi.fn<() => Promise<never>>(() => Promise.reject(new Error(`${name} is not mocked in this spec`)))
    }
  }
  return { ...stubs, ...overrides }
}
