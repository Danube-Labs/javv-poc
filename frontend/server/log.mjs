// @ts-check
/**
 * The frontend server's log lines: JSON to stdout in the backend's shape (`timestamp`, `level`,
 * `event`, then the fields; javv_common/logging.py), so one log reader handles both containers.
 * Level from `JAVV_LOG_LEVEL`; an unknown name stops the server at start, as in the backend.
 * Callers pass named fields only: no header or body ever goes in a line (redaction by omission).
 */

/** @typedef {'debug' | 'info' | 'warning' | 'error'} Level */
/** @typedef {Record<string, string | number | boolean | null>} Fields */
/** @typedef {{ [L in Level]: (event: string, fields?: Fields) => void }} Logger */

/** @type {Record<Level, number>} */
const LEVELS = { debug: 10, info: 20, warning: 30, error: 40 }

/**
 * @param {string | undefined} name
 * @param {(line: string) => void} [write]
 * @returns {Logger}
 */
export function createLogger(name, write = (line) => process.stdout.write(line)) {
  const wanted = (name || 'info').toLowerCase()
  if (!(wanted in LEVELS)) {
    throw new Error(`unknown log level '${wanted}' (want ${Object.keys(LEVELS).join('/')})`)
  }
  const threshold = LEVELS[/** @type {Level} */ (wanted)]

  /** @param {Level} level */
  const at = (level) => (/** @type {string} */ event, /** @type {Fields} */ fields = {}) => {
    if (LEVELS[level] < threshold) return
    write(`${JSON.stringify({ timestamp: new Date().toISOString(), level, event, ...fields })}\n`)
  }
  return { debug: at('debug'), info: at('info'), warning: at('warning'), error: at('error') }
}
