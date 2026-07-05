"""Deliver an envelope to the backend ingest endpoint.

The body is gzipped with a fixed mtime so the same envelope produces byte-identical content —
combined with the backend's deterministic `_id`, a re-sent push double-counts nothing (D18).
Transient failures (transport errors, 429, 5xx) are retried with exponential backoff + full
jitter — the only flow control without a broker. Permanent failures (other 4xx) or exhausted
retries are written to a dead-letter sink so nothing is silently lost. Sync client: the scanner
is a batch CronJob, not an async request path.
"""

import gzip
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog

from scanner.envelope import Envelope

INGEST_PATH = "/api/v1/ingest/scan"  # must match the backend router (M1)


@dataclass(frozen=True)
class PushResult:
    delivered: bool
    attempts: int
    dead_lettered: bool


def _backoff(attempt: int, *, base: float, cap: float, rng: Callable[[], float]) -> float:
    ceiling = min(cap, base * 2 ** (attempt - 1))
    return rng() * ceiling  # full jitter


def _is_transient(resp: httpx.Response) -> bool:
    return resp.status_code == 429 or resp.is_server_error


log = structlog.get_logger()


def _dead_letter(envelope: Envelope, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(envelope.model_dump_json() + "\n")
    # an envelope falling out of delivery is an operator signal (#156) — replay is manual
    log.warning(
        "envelope dead-lettered",
        image_digest=envelope.image_digest,
        scan_run_id=envelope.scan_run_id,
        path=str(path),
    )


def push_envelope(
    envelope: Envelope,
    *,
    client: httpx.Client,
    dead_letter_path: Path,
    path: str = INGEST_PATH,
    token: str | None = None,
    max_attempts: int = 5,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
) -> PushResult:
    body = gzip.compress(envelope.model_dump_json().encode(), mtime=0)
    headers = {"Content-Encoding": "gzip", "Content-Type": "application/json"}
    if token:  # ingest bearer token (D38/M14); never logged
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.post(path, content=body, headers=headers)
        except httpx.RequestError:
            transient = True
        else:
            if resp.is_success:
                return PushResult(delivered=True, attempts=attempt, dead_lettered=False)
            if not _is_transient(resp):  # permanent client error (4xx, not 429)
                _dead_letter(envelope, dead_letter_path)
                return PushResult(delivered=False, attempts=attempt, dead_lettered=True)
            transient = True

        if transient and attempt < max_attempts:
            sleep(_backoff(attempt, base=base_delay, cap=max_delay, rng=rng))

    _dead_letter(envelope, dead_letter_path)
    return PushResult(delivered=False, attempts=max_attempts, dead_lettered=True)
