"""Two-timer staleness sweep (D20, M3 slice 6): a daily CronJob flags data the scanner stopped
refreshing — per-finding freshness (N days), scanner-down escalation (M days), the hold between
them, and revert-on-return. `stale` is a flag on `state`, never a delete; presence is never touched.
Timers are read from `system-config` (UI-configurable, never hardcoded). Real OpenSearch."""

import contextlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.jobs.staleness import (
    StalenessTimers,
    read_staleness_timers,
    run_staleness_sweep,
    write_staleness_timers,
)

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
CLUSTER = GOLDEN["cluster_id"]
NOW = datetime(2026, 7, 3, tzinfo=UTC)


def _opensearch_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _opensearch_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


@pytest.fixture
async def real_os():
    prefix = f"t-{uuid4().hex[:8]}-"
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client, prefix=prefix)
    yield client, prefix
    with contextlib.suppress(Exception):
        await client.indices.delete(index=f"{prefix}*", params={"expand_wildcards": "all"})
    await client.close()


async def _seed_token(client, prefix, *, scanner="trivy", last_ingest: datetime | None) -> None:
    body = {"cluster_id": CLUSTER, "scanner": scanner, "token_hash": "x", "disabled": False}
    if last_ingest is not None:
        body["last_ingest_at"] = last_ingest.isoformat()
    await client.index(
        index=f"{prefix}system-tokens",
        id=f"{CLUSTER}:{scanner}",
        body=body,
        params={"refresh": "true"},
    )


async def _seed_finding(
    client, prefix, fk, *, last_seen: datetime, state="open", present=True, pre_stale=None
) -> None:
    doc = {
        "finding_key": fk,
        "cluster_id": CLUSTER,
        "scanner": "trivy",
        "image_digest": GOLDEN["image_digest"],
        "last_seen_at": last_seen.isoformat(),
        "present": present,
        "state": state,
        "pre_stale_status": pre_stale,
    }
    await client.index(index=f"{prefix}findings", id=fk, body=doc, params={"refresh": "true"})


async def _get(client, prefix, fk) -> dict:
    return (await client.get(index=f"{prefix}findings", id=fk))["_source"]


# --- config: UI-configurable timers, defaults when unset -----------------------


@requires_opensearch
async def test_timers_default_then_read_back_from_config(real_os) -> None:
    client, prefix = real_os
    assert await read_staleness_timers(client, prefix=prefix) == StalenessTimers(
        freshness_days=3, scanner_down_days=7
    )
    await write_staleness_timers(
        client,
        StalenessTimers(freshness_days=1, scanner_down_days=5),
        updated_by="t",
        prefix=prefix,
    )
    got = await read_staleness_timers(client, prefix=prefix)
    assert got.freshness_days == 1 and got.scanner_down_days == 5


# --- per-finding freshness (scanner healthy) -----------------------------------


@requires_opensearch
async def test_per_finding_freshness_stales_old_and_saves_pre_status(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(hours=6))  # healthy
    await _seed_finding(
        client, prefix, "old", last_seen=NOW - timedelta(days=5), state="acknowledged"
    )
    await _seed_finding(client, prefix, "fresh", last_seen=NOW - timedelta(hours=12))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 1
    old = await _get(client, prefix, "old")
    assert (
        old["state"] == "stale" and old["pre_stale_status"] == "acknowledged"
    )  # prior state saved
    assert (await _get(client, prefix, "fresh"))["state"] == "open"  # within N — untouched


# --- scanner-down escalation ---------------------------------------------------


@requires_opensearch
async def test_scanner_down_stales_everything_even_fresh_looking(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(days=9))  # silent > M(7)
    await _seed_finding(client, prefix, "a", last_seen=NOW - timedelta(days=9))
    await _seed_finding(client, prefix, "b", last_seen=NOW - timedelta(days=9))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 2
    assert (await _get(client, prefix, "a"))["state"] == "stale"
    assert (await _get(client, prefix, "b"))["state"] == "stale"


# --- the hold between N and M --------------------------------------------------


@requires_opensearch
async def test_held_between_thresholds_does_not_stale(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(days=5))  # N(3) <= 5 < M(7): held
    await _seed_finding(client, prefix, "aging", last_seen=NOW - timedelta(days=5))

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["staled"] == 0  # a brief outage must not mass-stale one finding at a time
    assert (await _get(client, prefix, "aging"))["state"] == "open"


# --- revert-on-return ----------------------------------------------------------


@requires_opensearch
async def test_returned_finding_reverts_to_pre_stale_status(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(hours=1))  # healthy again
    # a previously-staled finding the scanner just re-reported (fresh last_seen, state still stale)
    await _seed_finding(
        client, prefix, "back", last_seen=NOW, state="stale", pre_stale="risk_accepted"
    )

    result = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert result["reverted"] == 1
    back = await _get(client, prefix, "back")
    assert back["state"] == "risk_accepted"  # prior human state restored
    assert back["pre_stale_status"] is None


# --- idempotence ---------------------------------------------------------------


@requires_opensearch
async def test_sweep_is_idempotent(real_os) -> None:
    client, prefix = real_os
    await _seed_token(client, prefix, last_ingest=NOW - timedelta(hours=6))
    await _seed_finding(client, prefix, "old", last_seen=NOW - timedelta(days=5), state="open")

    first = await run_staleness_sweep(client, now=NOW, prefix=prefix)
    second = await run_staleness_sweep(client, now=NOW, prefix=prefix)

    assert first["staled"] == 1 and second["staled"] == 0  # already stale — not re-marked
    old = await _get(client, prefix, "old")
    assert old["state"] == "stale" and old["pre_stale_status"] == "open"  # not clobbered to "stale"
