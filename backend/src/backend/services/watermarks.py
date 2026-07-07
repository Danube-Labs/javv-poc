"""Per-digest committed-scan watermark (D40) — the create-AND-update guard for the findings cache.

The watermark is the serialization point that makes newer-scan-wins safe *including creates*: a
per-doc `findings.last_scan_order` can only guard an UPDATE (the doc must already exist), so an
out-of-order older scan carrying a since-retired finding would re-create it. The per-digest
watermark closes that hole — a stale run (`scan_order < max_committed`) skips ALL cache writes.

One doc per `(cluster_id, scanner, image_digest)`, CAS-bumped at commit on
`_seq_no`/`_primary_term`; the losing racer re-reads and retries. Every finding in one envelope
shares `(image_digest, scan_order)`, so the per-digest decision covers the whole run — the guard is
digest-grained by construction (CORRECTNESS-CONTRACT §3). History (occurrences/scan-events) is NEVER
guarded: appends are idempotent by `_id` and ordered by `scan_order`, so a stale append is harmless.

The watermark is DERIVED, not authoritative: `rebuild-state` wipes and recomputes it from the
catalog (unlike `javv-scan-orders`, D45). Nothing here is a clock — ordering is `scan_order` (D40).
"""

import asyncio
import hashlib
import random
from datetime import datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, ConflictError, NotFoundError

from backend.core.metrics import CAS_CONFLICTS

INDEX = "javv-scan-watermarks"
# real contention is ~1 (one CronJob per scanner, Forbid); the ceiling covers pathological races
# (the keystone test drives concurrent commits for one digest with inverted scan_order)
_CAS_RETRIES = 32
log = structlog.get_logger()


def _doc_id(cluster_id: str, scanner: str, image_digest: str) -> str:
    return hashlib.sha256("|".join((cluster_id, scanner, image_digest)).encode()).hexdigest()


def _doc(cluster_id: str, scanner: str, image_digest: str, order: int, at: str) -> dict[str, Any]:
    return {
        "cluster_id": cluster_id,
        "scanner": scanner,
        "image_digest": image_digest,
        "max_committed_scan_order": order,
        "max_committed_scan_at": at,
        "schema_version": 1,
    }


async def advance_watermark(
    client: AsyncOpenSearch,
    cluster_id: str,
    scanner: str,
    image_digest: str,
    scan_order: int,
    committed_at: datetime | str,
    *,
    prefix: str = "",
) -> bool:
    """CAS-bump the digest watermark to `max(current, scan_order)` at commit (D40).

    Returns True when this run is the newest committed for the digest (→ proceed with the cache
    write), False when a strictly-newer scan already committed (→ skip ALL cache writes; history
    stays, it is idempotent and `scan_order`-ordered). Raises after exhausted CAS retries — the
    caller surfaces a 5xx and the scanner treats it as fail-closed.
    """
    index = f"{prefix}{INDEX}"
    doc_id = _doc_id(cluster_id, scanner, image_digest)
    at = committed_at.isoformat() if isinstance(committed_at, datetime) else committed_at

    for _ in range(_CAS_RETRIES):
        try:
            got = await client.get(index=index, id=doc_id)
        except NotFoundError:
            try:
                await client.index(
                    index=index,
                    id=doc_id,
                    body=_doc(cluster_id, scanner, image_digest, scan_order, at),
                    params={"op_type": "create", "refresh": "true"},
                )
                return True
            except ConflictError:
                continue  # another commit created it first — retry via the get path
        current = int(got["_source"]["max_committed_scan_order"])
        if scan_order < current:
            # the out-of-order guard doing its job (D40) — worth a trace when debugging ingest
            log.debug(
                "watermark: stale scan skipped",
                scanner=scanner,
                image_digest=image_digest,
                scan_order=scan_order,
                max_committed=current,
            )
            return False  # stale: a newer scan already committed for this digest
        if scan_order == current:
            return True  # idempotent replay of the newest run — merge is idempotent, no bump
        try:
            await client.index(
                index=index,
                id=doc_id,
                body=_doc(cluster_id, scanner, image_digest, scan_order, at),
                params={
                    "if_seq_no": got["_seq_no"],
                    "if_primary_term": got["_primary_term"],
                    "refresh": "true",
                },
            )
            return True
        except ConflictError:
            log.debug("watermark: CAS conflict, retrying", image_digest=image_digest)
            CAS_CONFLICTS.labels("watermarks").inc()  # M-3 (#220): contention early-warning
            await asyncio.sleep(random.uniform(0, 0.02))  # jitter so racers don't lockstep
            continue  # lost the CAS race — re-read and retry
    raise RuntimeError("watermark CAS: retries exhausted")
