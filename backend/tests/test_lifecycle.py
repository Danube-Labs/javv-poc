"""Lifecycle sweep (M4 slice 2, D8/D26 via the CronJob — Option A): one daily job rolls each
per-cluster series write alias when the configured conditions are met (`_rollover` + `conditions`,
evaluated server-side by OpenSearch) and drops whole expired NON-write backing indices per the
per-cluster `retention_days`. Never `delete_by_query`; never the write index. Knobs are tier-③
runtime config in `system-config` (fleet default + per-cluster override), like the D20 staleness
timers. Retention age = the index's newest `@timestamp` (data age) — NOT `creation_date`, which
would delete fresh data out of a long-lived just-rolled index. Real OpenSearch."""

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
from backend.jobs.lifecycle import (
    LifecycleKnobs,
    read_lifecycle_knobs,
    run_lifecycle_sweep,
    write_lifecycle_knobs,
)
from backend.services.aliases import ensure_write_alias

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")
CLUSTER = GOLDEN["cluster_id"]
NOW = datetime.now(UTC)  # real now: creation_date fallback compares against wall-clock


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


async def _seed_event(client, alias: str, *, at: datetime, run_id: str = "r1") -> None:
    """One minimal scan-events doc through the write alias, refreshed."""
    await client.index(
        index=alias,
        body={"@timestamp": at.isoformat(), "scan_run_id": run_id, "cluster_id": CLUSTER},
        params={"refresh": "true"},
    )


async def _write_index(client, alias: str) -> str:
    got = await client.indices.get_alias(name=alias)
    return next(i for i, m in got.items() if m["aliases"][alias].get("is_write_index"))


# --- config: UI-configurable knobs, defaults when unset -------------------------


@requires_opensearch
async def test_knobs_default_then_read_back_from_config(real_os) -> None:
    client, prefix = real_os
    assert await read_lifecycle_knobs(client, prefix=prefix) == LifecycleKnobs()
    await write_lifecycle_knobs(
        client, LifecycleKnobs(retention_days=30, max_docs=100), updated_by="t", prefix=prefix
    )
    got = await read_lifecycle_knobs(client, prefix=prefix)
    assert got.retention_days == 30 and got.max_docs == 100


@requires_opensearch
async def test_per_cluster_knobs_override_the_fleet_default(real_os) -> None:
    client, prefix = real_os
    await write_lifecycle_knobs(
        client, LifecycleKnobs(retention_days=10), updated_by="t", prefix=prefix
    )
    await write_lifecycle_knobs(
        client,
        LifecycleKnobs(retention_days=365),
        updated_by="t",
        cluster_id=CLUSTER,
        prefix=prefix,
    )
    mine = await read_lifecycle_knobs(client, cluster_id=CLUSTER, prefix=prefix)
    other = await read_lifecycle_knobs(client, cluster_id="other-cluster-9x", prefix=prefix)
    assert mine.retention_days == 365 and other.retention_days == 10


# --- rollover ---------------------------------------------------------------------


@requires_opensearch
async def test_rollover_fires_when_max_docs_is_met(real_os) -> None:
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await _seed_event(client, alias, at=NOW)
    await write_lifecycle_knobs(client, LifecycleKnobs(max_docs=1), updated_by="t", prefix=prefix)

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["rolled"] == 1
    assert await _write_index(client, alias) == f"{alias}-000002"  # writes retargeted


@requires_opensearch
async def test_rollover_holds_under_the_thresholds(real_os) -> None:
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await _seed_event(client, alias, at=NOW)  # defaults: 5M docs / 30d / 50gb — nowhere near

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["rolled"] == 0
    assert await _write_index(client, alias) == f"{alias}-000001"


@requires_opensearch
async def test_sweep_manages_both_series(real_os) -> None:
    client, prefix = real_os
    for series in ("javv-scan-events", "javv-images"):
        alias = f"{prefix}{series}-{CLUSTER}"
        await ensure_write_alias(client, alias)
        await _seed_event(client, alias, at=NOW)
    await write_lifecycle_knobs(client, LifecycleKnobs(max_docs=1), updated_by="t", prefix=prefix)

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["rolled"] == 2  # scan-events AND images rolled


# --- retention --------------------------------------------------------------------


@requires_opensearch
async def test_retention_drops_an_expired_rolled_index(real_os) -> None:
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await _seed_event(client, alias, at=NOW - timedelta(days=200))  # data well past retention(90)
    await client.indices.rollover(alias=alias)  # -000001 is now a non-write, expired index

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["dropped"] == 1
    assert not await client.indices.exists(index=f"{alias}-000001")  # whole index dropped
    assert await client.indices.exists(index=f"{alias}-000002")  # the live one untouched


@requires_opensearch
async def test_retention_never_touches_the_write_index(real_os) -> None:
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await _seed_event(client, alias, at=NOW - timedelta(days=200))  # expired data, but write index

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["dropped"] == 0
    assert await client.indices.exists(index=f"{alias}-000001")


@requires_opensearch
async def test_retention_keeps_a_rolled_index_with_recent_data(real_os) -> None:
    # data age, not creation age: a just-rolled index holds fresh docs and must survive
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await _seed_event(client, alias, at=NOW - timedelta(days=1))
    await client.indices.rollover(alias=alias)

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["dropped"] == 0
    assert await client.indices.exists(index=f"{alias}-000001")


@requires_opensearch
async def test_retention_honors_the_per_cluster_override(real_os) -> None:
    client, prefix = real_os
    keep_cluster = "cluster-keep-9x"
    for cl in (CLUSTER, keep_cluster):
        alias = f"{prefix}javv-scan-events-{cl}"
        await ensure_write_alias(client, alias)
        await client.index(
            index=alias,
            body={"@timestamp": (NOW - timedelta(days=200)).isoformat(), "cluster_id": cl},
            params={"refresh": "true"},
        )
        await client.indices.rollover(alias=alias)
    # fleet default 90d would drop both; keep_cluster's override says hold for 10 years
    await write_lifecycle_knobs(
        client,
        LifecycleKnobs(retention_days=3650),
        updated_by="t",
        cluster_id=keep_cluster,
        prefix=prefix,
    )

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["dropped"] == 1
    assert not await client.indices.exists(index=f"{prefix}javv-scan-events-{CLUSTER}-000001")
    assert await client.indices.exists(index=f"{prefix}javv-scan-events-{keep_cluster}-000001")


@requires_opensearch
async def test_empty_rolled_index_falls_back_to_creation_date(real_os) -> None:
    # an empty index has no @timestamp to age it — creation_date (just now) keeps it alive
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await client.indices.rollover(alias=alias)  # -000001 rolled while still empty

    result = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert result["dropped"] == 0
    assert await client.indices.exists(index=f"{alias}-000001")


# --- idempotence ------------------------------------------------------------------


@requires_opensearch
async def test_sweep_is_idempotent(real_os) -> None:
    client, prefix = real_os
    alias = f"{prefix}javv-scan-events-{CLUSTER}"
    await ensure_write_alias(client, alias)
    await _seed_event(client, alias, at=NOW - timedelta(days=200))
    await client.indices.rollover(alias=alias)

    first = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)
    second = await run_lifecycle_sweep(client, now=NOW, prefix=prefix)

    assert first["dropped"] == 1 and second["dropped"] == 0  # nothing left to drop
    assert first["rolled"] == 0 and second["rolled"] == 0  # empty write index — no re-roll storm
