"""The shared `_bulk` writer — the only flow control without a broker, so it is deliberately
strict: always inspect `response["errors"]` + per-item status; retry ONLY 429/503 items with
exponential backoff + full jitter; anything else raises. sleep/rng injected for tests."""

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, overload

from opensearchpy import AsyncOpenSearch

from backend.core.metrics import OS_BACKOFF_RETRIES, OS_REQUEST_ERRORS

RETRYABLE = {429, 503}


class BulkError(Exception):
    """Non-retryable item failures (or retries exhausted). Carries the failed items."""

    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        super().__init__(f"bulk write failed for {len(items)} item(s)")


@overload
async def bulk_write(
    client: AsyncOpenSearch,
    actions: Sequence[dict[str, Any]],
    *,
    max_retries: int = ...,
    base_delay: float = ...,
    sleep: Callable[[float], Awaitable[None]] | None = ...,
    rng: random.Random | None = ...,
    collect_conflicts: Literal[False] = ...,
) -> int: ...
@overload
async def bulk_write(
    client: AsyncOpenSearch,
    actions: Sequence[dict[str, Any]],
    *,
    max_retries: int = ...,
    base_delay: float = ...,
    sleep: Callable[[float], Awaitable[None]] | None = ...,
    rng: random.Random | None = ...,
    collect_conflicts: Literal[True],
) -> tuple[int, list[dict[str, Any]]]: ...
async def bulk_write(
    client: AsyncOpenSearch,
    actions: Sequence[dict[str, Any]],
    *,
    max_retries: int = 4,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    rng: random.Random | None = None,
    collect_conflicts: bool = False,
) -> int | tuple[int, list[dict[str, Any]]]:
    """Submit action/doc pairs; return docs written. Retries 429/503 items; raises BulkError.

    `collect_conflicts=True` (reproject's guarded RMW, audit #186) returns `(written, conflicts)`
    where `conflicts` are the per-item results that came back **409 version_conflict** — they are
    NOT retried here and NOT raised; the caller re-reads them, re-checks ownership, and retries.
    This is scoped, opt-in behaviour — `RETRYABLE` is unchanged, so ingest still hard-fails on 409.
    """
    if not actions:
        return (0, []) if collect_conflicts else 0
    sleep = sleep or asyncio.sleep  # real backoff in prod; tests inject a no-op (M-4)
    rng = rng or random.Random()
    pending = list(actions)
    written = 0
    conflicts: list[dict[str, Any]] = []

    for attempt in range(max_retries + 1):
        response = await client.bulk(body=pending)
        if not response.get("errors"):
            written += len(pending) // 2
            return (written, conflicts) if collect_conflicts else written

        retry: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for i, item in enumerate(response["items"]):
            (_, result), *_ = item.items()
            status = result.get("status", 500)
            pair = pending[2 * i : 2 * i + 2]  # action line + doc line
            if status < 300:
                written += 1
            elif status in RETRYABLE:
                OS_REQUEST_ERRORS.labels(str(status)).inc()  # M-2 (#220): 429 rate = saturation
                retry.extend(pair)
            elif collect_conflicts and status == 409:
                conflicts.append(result)  # caller re-reads + re-checks ownership + retries
            else:
                failed.append(result)
        if failed:
            raise BulkError(failed)
        if not retry:
            return (written, conflicts) if collect_conflicts else written
        if attempt == max_retries:
            raise BulkError([{"status": "retries_exhausted", "count": len(retry) // 2}])
        # exponential backoff + full jitter
        OS_BACKOFF_RETRIES.inc(len(retry) // 2)  # M-2 (#220): per retried item
        await sleep(rng.uniform(0, base_delay * (2**attempt)))
        pending = retry

    raise AssertionError("unreachable")
