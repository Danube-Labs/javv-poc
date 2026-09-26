"""POST /api/v1/ingest/scan — the hardened untrusted-input surface (M1, SEC-3/D38).

Order of defenses: rate limit → bearer token (peppered-SHA-256 lookup, constant-time) → streamed
compressed-size cap (Content-Length is never trusted) → gzip decompression cap (zip bomb) → JSON
parse → full-envelope `extra="forbid"` validation → token↔payload scope binding (a team-A token
cannot push team-B data) → commit-then-cache writes. 401 is generic (no token-existence oracle);
tokens are never logged.
"""

import json
import zlib
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from fastapi import APIRouter, HTTPException, Request
from opensearchpy.exceptions import ConflictError
from pydantic import ValidationError

from backend.core.metrics import FINDINGS_WRITTEN, INGEST_ACCEPTED, INGEST_REJECTED
from backend.core.rate_limit import SlidingWindowLimiter
from backend.core.security import hash_token, token_expired, tokens_match
from backend.core.settings import get_settings
from backend.models.envelope import IngestEnvelope
from backend.repositories.bulk import BulkError
from backend.services.ingest import ingest_envelope

log = structlog.get_logger()


def _reject(
    status: int, reason: str, detail: str, *, warn: bool = True, **fields: Any
) -> HTTPException:
    """Count + raise, and log a warning unless `warn=False`. `reason` is a bounded metric label
    (never user input). A rejection an unauthenticated sender can repeat with no budget (401)
    passes `warn=False`: a line per request would let it choose our log volume (logging.md)."""
    INGEST_REJECTED.labels(reason=reason).inc()
    if warn:
        log.warning("ingest rejected", reason=reason, status=status, **fields)
    return HTTPException(status, detail)


router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

# Its own instance, keyed on token hashes: an unauthenticated flood here must never spend the
# budget of a logged-in principal's telemetry (516). This is the map the m-1 hard eviction in
# `SlidingWindowLimiter` exists for — the key space is attacker-supplied and reached BEFORE the
# token is verified, so it grows on garbage.
_limiter = SlidingWindowLimiter()
# The 429 is decided before the token is verified, so its key is whatever a sender puts in the
# header. At most one warning per key per window; the metric still counts every rejection.
_rate_limit_warned = SlidingWindowLimiter()


async def _read_capped(request: Request, cap: int, scope: dict[str, str]) -> bytes:
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > cap:  # enforced while reading — the header may lie
            raise _reject(413, "too_large", "compressed body too large", limit_bytes=cap, **scope)
        chunks.append(chunk)
    return b"".join(chunks)


def _decompress_capped(raw: bytes, cap: int, scope: dict[str, str]) -> bytes:
    d = zlib.decompressobj(wbits=31)  # gzip container
    try:
        out = d.decompress(raw, cap + 1)
    except zlib.error as exc:
        raise _reject(400, "bad_gzip", "invalid gzip body", **scope) from exc
    if len(out) > cap or d.unconsumed_tail:
        raise _reject(  # zip bomb
            413, "too_large", "decompressed body too large", limit_bytes=cap, **scope
        )
    return out


@router.post("/scan", status_code=202)
async def ingest_scan(request: Request) -> dict[str, Any]:
    settings = get_settings()
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) > 512:
        raise _reject(401, "bad_token", "invalid token", warn=False)
    candidate = hash_token(auth.removeprefix("Bearer "), pepper=settings.token_pepper)

    if _limiter.is_limited(candidate, settings.ingest_rate_limit_per_minute):
        first_in_window = not _rate_limit_warned.is_limited(candidate, 1)
        raise _reject(429, "rate_limited", "rate limit exceeded", warn=first_in_window)

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
        or token_expired(token)  # lifecycle: an expired token is dead (audit m-3)
    ):
        raise _reject(401, "bad_token", "invalid token", warn=False)  # generic — no oracle

    # authenticated from here on, and already rate-limited per token: every rejection below logs
    # a bounded warning naming whose scanner it was (the token's scope, never the token)
    scope = {"cluster_id": token["cluster_id"], "scanner": token["scanner"]}
    raw = await _read_capped(request, settings.ingest_max_compressed_bytes, scope)
    if request.headers.get("content-encoding", "").lower() == "gzip":
        raw = _decompress_capped(raw, settings.ingest_max_body_bytes, scope)
    elif len(raw) > settings.ingest_max_body_bytes:
        raise _reject(
            413, "too_large", "body too large", limit_bytes=settings.ingest_max_body_bytes, **scope
        )

    try:
        env = IngestEnvelope.model_validate(json.loads(raw))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _reject(400, "bad_json", "body is not valid JSON", **scope) from exc
    except ValidationError as exc:
        raise _reject(
            422,
            "invalid_envelope",
            f"envelope rejected: {exc.error_count()} error(s)",
            errors=exc.error_count(),
            **scope,
        ) from exc

    # authz binding (SEC-3): the token's scope must match the payload it pushes
    if env.cluster_id != token["cluster_id"] or env.scanner != token["scanner"]:
        raise _reject(
            403,
            "scope_mismatch",
            "token not valid for this cluster/scanner",
            payload_cluster_id=env.cluster_id,
            payload_scanner=env.scanner,
            **scope,
        )

    structlog.contextvars.bind_contextvars(cluster_id=env.cluster_id, scanner=env.scanner)
    try:
        written = await ingest_envelope(client, env)
    except BulkError as exc:
        raise _reject(503, "storage_error", "storage temporarily unavailable", **scope) from exc

    INGEST_ACCEPTED.labels(scanner=env.scanner).inc()
    FINDINGS_WRITTEN.labels(scanner=env.scanner).inc(written)
    log.info("ingest committed", scan_run_id=env.scan_run_id, findings=written)

    # server-side timestamp — the scanner-down guard must not be gameable by a client clock (M-3);
    # this records when the backend last accepted a push, not the scanner's self-reported scan
    # time. Best-effort: the ingest is already committed, so a version conflict here (two
    # same-token pushes racing the stamp — found by the #117 bench) must not 500 an accepted
    # push; the racer just wrote an equally-fresh timestamp.
    try:
        await client.update(
            index="system-tokens",
            id=docs[0]["_id"],
            body={"doc": {"last_ingest_at": datetime.now(UTC).isoformat()}},
            params={"retry_on_conflict": "3"},
        )
    except ConflictError:
        log.warning("last_ingest_at stamp lost a write race — a racer stamped fresher")
    return {"accepted": True, "findings": written, "commit": env.scan_run_id}
