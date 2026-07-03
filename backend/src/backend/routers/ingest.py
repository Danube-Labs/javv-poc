"""POST /api/v1/ingest/scan — the hardened untrusted-input surface (M1, SEC-3/D38).

Order of defenses: rate limit → bearer token (peppered-SHA-256 lookup, constant-time) → streamed
compressed-size cap (Content-Length is never trusted) → gzip decompression cap (zip bomb) → JSON
parse → full-envelope `extra="forbid"` validation → token↔payload scope binding (a team-A token
cannot push team-B data) → commit-then-cache writes. 401 is generic (no token-existence oracle);
tokens are never logged.
"""

import json
import time
import zlib
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from backend.core.metrics import FINDINGS_WRITTEN, INGEST_ACCEPTED, INGEST_REJECTED
from backend.core.security import hash_token, tokens_match
from backend.core.settings import get_settings
from backend.models.envelope import IngestEnvelope
from backend.repositories.bulk import BulkError
from backend.services.ingest import ingest_envelope

log = structlog.get_logger()


def _reject(status: int, reason: str, detail: str) -> HTTPException:
    """Count + raise. `reason` is a bounded metric label (never user input)."""
    INGEST_REJECTED.labels(reason=reason).inc()
    return HTTPException(status, detail)


router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

# in-process sliding window per token-hash — MVP single-pod (no broker by design)
_WINDOW_S = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(key: str, limit: int) -> bool:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > _WINDOW_S:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


async def _read_capped(request: Request, cap: int) -> bytes:
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > cap:  # enforced while reading — the header may lie
            raise _reject(413, "too_large", "compressed body too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _decompress_capped(raw: bytes, cap: int) -> bytes:
    d = zlib.decompressobj(wbits=31)  # gzip container
    try:
        out = d.decompress(raw, cap + 1)
    except zlib.error as exc:
        raise _reject(400, "bad_gzip", "invalid gzip body") from exc
    if len(out) > cap or d.unconsumed_tail:
        raise _reject(413, "too_large", "decompressed body too large")  # zip bomb
    return out


@router.post("/scan", status_code=202)
async def ingest_scan(request: Request) -> dict[str, Any]:
    settings = get_settings()
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) > 512:
        raise _reject(401, "bad_token", "invalid token")
    candidate = hash_token(auth.removeprefix("Bearer "), pepper=settings.token_pepper)

    if _rate_limited(candidate, settings.ingest_rate_limit_per_minute):
        raise _reject(429, "rate_limited", "rate limit exceeded")

    client = cast(Any, request.app.state.opensearch)
    hits = await client.search(
        index="system-tokens",
        body={"query": {"term": {"token_hash": candidate}}, "size": 1},
    )
    docs = hits["hits"]["hits"]
    token = docs[0]["_source"] if docs else None
    if (
        token is None
        or not tokens_match(candidate, token["token_hash"])  # constant-time, belt & braces
        or token.get("disabled")
    ):
        raise _reject(401, "bad_token", "invalid token")  # generic — no existence oracle

    raw = await _read_capped(request, settings.ingest_max_compressed_bytes)
    if request.headers.get("content-encoding", "").lower() == "gzip":
        raw = _decompress_capped(raw, settings.ingest_max_body_bytes)
    elif len(raw) > settings.ingest_max_body_bytes:
        raise _reject(413, "too_large", "body too large")

    try:
        env = IngestEnvelope.model_validate(json.loads(raw))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _reject(400, "bad_json", "body is not valid JSON") from exc
    except ValidationError as exc:
        raise _reject(
            422, "invalid_envelope", f"envelope rejected: {exc.error_count()} error(s)"
        ) from exc

    # authz binding (SEC-3): the token's scope must match the payload it pushes
    if env.cluster_id != token["cluster_id"] or env.scanner != token["scanner"]:
        raise _reject(403, "scope_mismatch", "token not valid for this cluster/scanner")

    structlog.contextvars.bind_contextvars(cluster_id=env.cluster_id, scanner=env.scanner)
    try:
        written = await ingest_envelope(client, env)
    except BulkError as exc:
        raise _reject(503, "storage_error", "storage temporarily unavailable") from exc

    INGEST_ACCEPTED.labels(scanner=env.scanner).inc()
    FINDINGS_WRITTEN.labels(scanner=env.scanner).inc(written)
    log.info("ingest committed", scan_run_id=env.scan_run_id, findings=written)

    # server-side timestamp — the scanner-down guard must not be gameable by a client clock (M-3);
    # this records when the backend last accepted a push, not the scanner's self-reported scan time
    await client.update(
        index="system-tokens",
        id=docs[0]["_id"],
        body={"doc": {"last_ingest_at": datetime.now(UTC).isoformat()}},
    )
    return {"accepted": True, "findings": written, "commit": env.scan_run_id}
