"""Login lockout (M5a) — per-username failed-attempt throttle, the ingest rate-limiter pattern
(in-memory deque of timestamps per key, bounded map, audit m-4). Per-username because the threat
is brute-forcing ONE account; each attempt already costs the attacker (and us) an argon2id verify,
and IP-level flood control belongs to the ingress (M10), where the real client IP is known.

In-memory = per-pod, like the ingest limiter: with N pods an attacker gets N× the budget — an
accepted MVP bound (single-replica deploys today; revisit alongside the ingest limiter if that
changes). Knobs: `JAVV_LOGIN_MAX_ATTEMPTS` failures per `JAVV_LOGIN_LOCKOUT_MINUTES` sliding
window; a success clears the key."""

import time
from collections import deque

from backend.core.settings import get_settings

_MAX_KEYS = 100_000  # bound the map so a spray of garbage usernames can't leak it
_fails: dict[str, deque[float]] = {}


def _window_s() -> float:
    return get_settings().login_lockout_minutes * 60.0


def _sweep_drained(now: float) -> None:
    for k in [k for k, dq in _fails.items() if not dq or now - dq[-1] > _window_s()]:
        del _fails[k]


def locked(username: str) -> bool:
    """True while the failure budget is spent (login answers 429, credentials unseen)."""
    now = time.monotonic()
    q = _fails.get(username)
    if q is None:
        return False
    while q and now - q[0] > _window_s():
        q.popleft()
    return len(q) >= get_settings().login_max_attempts


def record_failure(username: str) -> None:
    now = time.monotonic()
    if len(_fails) >= _MAX_KEYS and username not in _fails:
        _sweep_drained(now)
        # task C m-1 (#140): a spray of unique usernames ALL inside the window leaves nothing
        # drained — hard-evict oldest-inserted (FIFO, O(1)) so the map can NEVER exceed the cap.
        # Tradeoff (accepted): a 100k-name spray can evict a live lockout entry and reset that
        # username's budget — but every spray request costs the attacker an argon2id verify.
        while len(_fails) >= _MAX_KEYS:
            del _fails[next(iter(_fails))]
    if username not in _fails:
        # the deque itself is bounded: only the last N failures matter for "≥N in window",
        # so one hammered username can't grow memory either (task C m-1)
        _fails[username] = deque(maxlen=get_settings().login_max_attempts)
    _fails[username].append(now)


def clear(username: str) -> None:
    _fails.pop(username, None)
