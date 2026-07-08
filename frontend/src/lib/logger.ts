/**
 * Frontend structured logger — the FE analog of the javv-common structlog pipeline
 * (observability.md §1): one leveled, structured emitter for all app code. Raw `console.*` is
 * ESLint-banned everywhere else, exactly like `print()` on the backend.
 *
 * Shape mirrors the backend stream (timestamp → level → event → fields) so a browser console line
 * reads like a backend.log line. Level threshold: `VITE_LOG_LEVEL` (build-time), defaulting to
 * `debug` in dev and `warn` in production builds.
 *
 * Never log secrets (NFR-5): no tokens, no cookie values, no raw response bodies — log
 * shapes/sizes/ids. The session cookie is httpOnly, but the rule stands for anything in scope.
 */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 }

function threshold(): number {
  const configured = import.meta.env.VITE_LOG_LEVEL as LogLevel | undefined
  if (configured && configured in ORDER) return ORDER[configured]
  return import.meta.env.DEV ? ORDER.debug : ORDER.warn
}

export type LogFields = Record<string, unknown>

function emit(level: LogLevel, event: string, fields?: LogFields): void {
  if (ORDER[level] < threshold()) return
  const line: LogFields = { timestamp: new Date().toISOString(), level, event, ...fields }
  // the single sanctioned console touchpoint (see module docblock)
  // eslint-disable-next-line no-console
  console[level](line)
}

export const logger = {
  debug: (event: string, fields?: LogFields) => emit('debug', event, fields),
  info: (event: string, fields?: LogFields) => emit('info', event, fields),
  warn: (event: string, fields?: LogFields) => emit('warn', event, fields),
  error: (event: string, fields?: LogFields) => emit('error', event, fields),
}
