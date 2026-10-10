/**
 * What the generated client returns when a reply arrives with status 200 but its body cannot be
 * read or parsed: `response.ok` is true, `data` is missing and `error` holds the failure (issue
 * 749). A code path that checks only `response.ok` before reading `data` throws on it.
 * `ok-without-body.spec.ts` checks this shape against the real client.
 */
export function okWithoutBody(): never {
  return {
    error: new DOMException('The user aborted a request.', 'AbortError'),
    request: {},
    response: { ok: true, status: 200 },
  } as never
}
