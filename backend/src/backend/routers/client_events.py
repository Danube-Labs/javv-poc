"""Client-events beacon (issue 453) — the browser half of the log stream.

`@/lib/logger` is browser-only by design: close the tab and the evidence is gone. This is the
missing half — a session-authenticated, capped endpoint that re-emits browser `warn`/`error`
events as structured lines in the backend's own stdout stream. **No storage, no index**: the
container stdout stream IS the destination, so nothing here is owed to INDEX-MAP or
`MAPPING_VERSION`, and no audit row is written (telemetry is not a user action, and the journal
is a worse home than stdout for attacker-influenced strings).

Two properties make the untrusted half safe, both by construction rather than by discipline:

**Namespaced event names.** Every event is re-emitted as `client.<name>` (the ruled option A). A
client posting `event: "scan done"` cannot produce a line that collides with a real backend
event, so an operator's `grep` — or an alerting rule keyed on an event name — can never be fooled
by a forged one. The `client_event=true` tag is kept as well, but it only protects a reader who
remembers to filter on it; the namespace protects one who doesn't.

**Nested fields, never splatted.** Client keys land under a single `fields` key rather than as
sibling kwargs. Splatting would let `fields: {"username": "admin", "client_event": false}`
overwrite the server's own attribution and produce a line indistinguishable from a genuine
backend one — and a key named `event` or `level` would collide with structlog's own parameters
and raise `TypeError`, turning any field name into a 500. Nesting makes both unrepresentable
rather than filtered, and the redaction processor still recurses into the nested blob, so
`token`-ish keys and `Bearer …` values are masked there exactly as they are at the top level.

Shape caps are the request schema (422 at the Pydantic edge, no metric — a 422 is ordinary
validation). The **rate limiter alone** is the bounded path that owes ops parity: 429 +
`LIMIT_REJECTIONS` + a `log.warning`. It runs after body validation deliberately — its job is to
bound what reaches the LOG STREAM, and a rejected batch emits nothing.
"""

import time
from collections import defaultdict, deque
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.auth.principal import Principal, get_current_principal
from backend.core.metrics import LIMIT_REJECTIONS
from backend.core.settings import get_settings

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/client-events", tags=["client-events"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

# --- shape caps: request SCHEMA, not dials (docs/CONFIGURATION.md §8) -------------------------
_MAX_BATCH = 20  # events per POST — the beacon batches, it does not stream
_MAX_KEYS_PER_OBJECT = 25
_MAX_DEPTH = 3
_MAX_KEY_CHARS = 64
_MAX_VALUE_CHARS = 512
_MAX_LIST_ITEMS = 20

# Lowercase, must start alphanumeric, space allowed. The space is deliberate and load-bearing:
# it is the house event-name convention on BOTH stacks (`log.info("scan done", …)`), and the
# frontend already emits `backend degraded` — the 503 event, i.e. the one most worth shipping.
# What this refuses is what actually threatens the concatenation into `client.<name>`: newlines,
# tabs, quotes and control characters. Pydantic's Rust engine anchors `$` at end-of-haystack, so
# a trailing "\n" is refused — asserted directly, because Python's own `re` would allow it.
_EVENT_NAME = r"^[a-z0-9][a-z0-9 ._-]{0,63}$"


def check_fields_shape(value: Any, *, depth: int = 0) -> None:
    """Reject anything unbounded in a client `fields` blob. Raises `ValueError` (→ 422).

    An allowlist of value types, not a denylist: an unrecognized type is refused rather than
    walked past, so the recursion is total over whatever a client can send."""
    if depth > _MAX_DEPTH:
        raise ValueError(f"fields nested deeper than {_MAX_DEPTH}")
    if isinstance(value, str):
        if len(value) > _MAX_VALUE_CHARS:
            raise ValueError(f"a field value exceeds {_MAX_VALUE_CHARS} characters")
    elif isinstance(value, dict):
        if len(value) > _MAX_KEYS_PER_OBJECT:
            raise ValueError(f"more than {_MAX_KEYS_PER_OBJECT} keys in a fields object")
        for key, item in value.items():
            if len(key) > _MAX_KEY_CHARS:
                raise ValueError(f"a field key exceeds {_MAX_KEY_CHARS} characters")
            check_fields_shape(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > _MAX_LIST_ITEMS:
            raise ValueError(f"a field list exceeds {_MAX_LIST_ITEMS} items")
        for item in value:
            check_fields_shape(item, depth=depth + 1)
    elif not isinstance(value, bool | int | float | type(None)):
        raise ValueError(f"unsupported field value type {type(value).__name__}")


class ClientEvent(BaseModel):
    """One browser event. `level` is a `Literal`, so `debug`/`info` are UNREPRESENTABLE at the
    schema edge (a 422) rather than filtered in a branch — the issue's "never accept debug/info"
    becomes a property of the contract."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["warn", "error"]
    event: str = Field(pattern=_EVENT_NAME)
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        check_fields_shape(value)
        return value


class ClientEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[ClientEvent] = Field(min_length=1, max_length=_MAX_BATCH)


# In-process sliding window per principal. This is a literal duplicate of
# `routers/ingest.py::_rate_limited` (that one keys on a token hash, this one on a user id) —
# kept rather than extracted so a refactor of the untrusted ingest path stayed out of the PR that
# introduced this surface. Extracting both into one limiter is tracked as issue 516; fix them
# together, not one at a time. In-memory per pod like every other JAVV limiter, so N replicas ⇒
# N× the budget — the accepted MVP bound, since this guards log volume, not a correctness
# invariant.
_WINDOW_S = 60.0
_MAX_KEYS = 100_000  # bound the map so a spray of principals can't leak it
_hits: dict[str, deque[float]] = defaultdict(deque)


def _sweep_drained(now: float) -> None:
    for key in [k for k, dq in _hits.items() if not dq or now - dq[-1] > _WINDOW_S]:
        del _hits[key]


def _rate_limited(key: str, limit: int) -> bool:
    now = time.monotonic()
    if len(_hits) > _MAX_KEYS:  # cheap: only once the map has actually grown large
        _sweep_drained(now)
    q = _hits[key]
    while q and now - q[0] > _WINDOW_S:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


@router.post("", status_code=204)
async def receive_client_events(body: ClientEventBatch, principal: Authenticated) -> None:
    if principal.must_change:  # SEC-6 — a capability-EXEMPT route guards itself (views.py)
        raise HTTPException(403, "password change required")
    if _rate_limited(principal.user_id, get_settings().client_events_rate_limit_per_minute):
        LIMIT_REJECTIONS.labels("client_events").inc()  # M-4 ops parity: metric AND warning
        log.warning("client events rate-limited", username=principal.username)
        raise HTTPException(429, "too many client-event batches", headers={"Retry-After": "60"})
    for event in body.events:
        emit = log.warning if event.level == "warn" else log.error
        emit(
            f"client.{event.event}",
            client_event=True,
            username=principal.username,
            fields=event.fields,  # nested, never splatted — see the module docstring
        )


__all__ = ["ClientEvent", "ClientEventBatch", "check_fields_shape", "router"]
