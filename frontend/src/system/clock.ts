/** The display clock under time-travel (D28): every "days left / ago" countdown measures from
 * the global T when rewound, from the wall clock at now — a screen answering "as of T" must
 * not count down from today (the SLA cells showed 0d/-1 for deadlines that were still open at
 * T). Pure; callers pass the store's `t`. */

export function refNowMs(t: string | null, wallMs: number = Date.now()): number {
  if (!t) return wallMs
  const parsed = Date.parse(t)
  return Number.isFinite(parsed) ? parsed : wallMs
}
