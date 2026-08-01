"""The one per-key sliding-window rate limiter (issue 516).

Two byte-identical copies of this used to sit inline in `routers/ingest.py` and
`routers/client_events.py`. They were never two shapes: both bound a request RATE per key with an
in-memory `dict[str, deque[float]]` of hit timestamps, a bounded key map, and a per-minute limit
read from settings.

**One instance per caller, never a shared module-level map.** The key spaces must stay separate —
an ingest token hash and a session user id must never draw on the same budget, or a token flood
would eat the UI's allowance — and each surface reads its own knob and owns its own metric.

`auth/lockout.py` and `query/pit_guard.py` are deliberately NOT folded in here: the first counts
failures per username, the second holds slots rather than a rate. Same word, different shapes.

In-memory per pod, like every other JAVV limiter, so N replicas ⇒ N× the budget. That is the
accepted MVP bound: these guard volume rather than a correctness invariant, and the no-broker
constraint rules out a shared counter.
"""

import time
from collections import defaultdict, deque

_WINDOW_S = 60.0
_MAX_KEYS = 100_000


class SlidingWindowLimiter:
    """Bounds how often one key may act within a rolling window."""

    def __init__(self, *, window_s: float = _WINDOW_S, max_keys: int = _MAX_KEYS) -> None:
        self._window_s = window_s
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _sweep_drained(self, now: float) -> None:
        """Drop keys whose window has fully drained. Without this an unauthenticated flood of
        distinct keys leaves a permanent empty deque behind for each one (m-4)."""
        drained = [k for k, dq in self._hits.items() if not dq or now - dq[-1] > self._window_s]
        for key in drained:
            del self._hits[key]

    def is_limited(self, key: str, limit: int) -> bool:
        """True when `key` has already used its allowance for the current window."""
        now = time.monotonic()
        if len(self._hits) > self._max_keys:  # cheap: only once the map has actually grown large
            self._sweep_drained(now)
        hits = self._hits[key]
        while hits and now - hits[0] > self._window_s:
            hits.popleft()
        if len(hits) >= limit:
            return True
        hits.append(now)
        return False

    def reset(self) -> None:
        """Forget every key. For tests, which share a process across cases."""
        self._hits.clear()


__all__ = ["SlidingWindowLimiter"]
