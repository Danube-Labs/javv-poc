"""Lifecycle sweep (M4, D8/D26) — a daily `Forbid` CronJob that rolls + retires the per-cluster
append series (`javv-scan-events-<cluster>`, `javv-images-<cluster>`).

Mechanism decision (#26): the D8 contract — numbered backing indices behind a write alias, rollover
on doc/age/size, retention by **dropping whole indices**, never `delete_by_query` — is executed by
THIS job, not the ISM plugin. ISM's rollover action needs a per-index `rollover_alias` setting that
one shared template can't parameterize per cluster (the fix is per-cluster template machinery), its
policy edits don't live-apply (`change_policy` fan-out), and per-cluster `retention_days` doesn't
fit one static policy — while `_rollover` + `conditions` is evaluated server-side by OpenSearch
either way; this job only pulls the trigger (the Curator model). Rollover precision = job cadence,
which is noise at monthly-rollover scale.

Knobs are tier-③ runtime config in `system-config` (fleet-wide `lifecycle` doc + per-cluster
`lifecycle:<cluster_id>` override — edited in the M9e UI or the interim CLI below, never
hardcoded), read live on every run so a D26 edit applies at the next sweep.

Retention age = the newest of the index's **server-stamped `ingested_at`** and its `@timestamp`
(task F m-4, #143): `@timestamp` is client(scanner)-supplied, so a backdated clock could make
fresh data look expired — the server-side append stamp is the floor that prevents early deletion
(a FUTURE-dated `@timestamp` merely keeps an index longer: the safe direction). NOT
`creation_date`: an index created 100d ago that rolled yesterday holds day-old data, and
creation-age deletion would destroy it. Empty indices fall back to `creation_date`. The write
index is never dropped.

`system-audit-log` is ROLLOVER-ONLY (task F m-6): the append-only journal rolls on the fleet
knobs like any series but is NEVER retention-dropped — audit history has no expiry in MVP
(revisit only with an explicit compliance-driven window). A broken cluster (malformed knobs doc,
index-level error) is skipped and counted, never allowed to abort the sweep for every other
cluster (task F m-5) — and never silently swept with DEFAULT knobs, which could apply a shorter
retention than the operator configured (fail-closed beats fail-default for a destructive op).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

log = structlog.get_logger()

LIFECYCLE_KEY = "lifecycle"  # fleet-wide default doc _id; per-cluster is `lifecycle:<cluster_id>`
SERIES = ("javv-scan-events", "javv-images", "javv-finding-occurrences", "javv-inventory-runs")
ROLLOVER_ONLY = ("system-audit-log",)  # rolls, NEVER retention-dropped (task F m-6)


def _knobs_id(cluster_id: str | None) -> str:
    return LIFECYCLE_KEY if cluster_id is None else f"{LIFECYCLE_KEY}:{cluster_id}"


class LifecycleKnobs(BaseModel):
    """D26 rollover conditions + retention window. Tier-③ runtime config, M9e-editable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_age_days: float = Field(default=30, gt=0)  # INDEX-MAP: monthly rollover
    max_docs: int = Field(default=5_000_000, gt=0)
    max_size_gb: float = Field(default=50, gt=0)
    retention_days: float = Field(default=90, gt=0)  # per-cluster drop-whole-index window

    def rollover_conditions(self) -> dict[str, Any]:
        # sub-day units so fractional-day knobs stay exact (OpenSearch rejects "0.5d"-style sizes)
        return {
            "max_age": f"{int(self.max_age_days * 24 * 60)}m",
            "max_docs": self.max_docs,
            "max_size": f"{int(self.max_size_gb * 1024)}mb",
        }


async def _read_one(client: AsyncOpenSearch, doc_id: str, prefix: str) -> LifecycleKnobs | None:
    try:
        got = await client.get(index=f"{prefix}system-config", id=doc_id)
    except NotFoundError:
        return None
    return LifecycleKnobs.model_validate(got["_source"]["value"])


async def read_lifecycle_knobs(
    client: AsyncOpenSearch, *, cluster_id: str | None = None, prefix: str = ""
) -> LifecycleKnobs:
    """A cluster's knobs: per-cluster `lifecycle:<cluster_id>` if set, else the fleet-wide
    `lifecycle` default, else the D8/INDEX-MAP defaults (30d/5M/50gb roll, 90d retention)."""
    if cluster_id is not None:
        per_cluster = await _read_one(client, _knobs_id(cluster_id), prefix)
        if per_cluster is not None:
            return per_cluster
    return await _read_one(client, LIFECYCLE_KEY, prefix) or LifecycleKnobs()


async def write_lifecycle_knobs(
    client: AsyncOpenSearch,
    knobs: LifecycleKnobs,
    *,
    updated_by: str,
    cluster_id: str | None = None,
    prefix: str = "",
) -> None:
    """Persist the knobs in system-config (interim admin path until the M9e UI)."""
    doc_id = _knobs_id(cluster_id)
    await client.index(
        index=f"{prefix}system-config",
        id=doc_id,
        body={
            "key": doc_id,
            "value": knobs.model_dump(),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": updated_by,
        },
        params={"refresh": "true"},
    )


async def _series_aliases(client: AsyncOpenSearch, prefix: str) -> dict[str, dict[str, bool]]:
    """Discover the managed write aliases: {alias: {backing_index: is_write_index}}.

    An alias is "managed" iff it's the bare series-cluster name its backing indices extend
    (`javv-scan-events-<cluster>` over `…-<cluster>-000001`) — ad-hoc aliases an operator added
    are left alone."""
    found: dict[str, dict[str, bool]] = {}
    for series in SERIES:
        try:
            got = await client.indices.get_alias(index=f"{prefix}{series}-*")
        except NotFoundError:
            continue
        for index_name, meta in got.items():
            for alias_name, alias_meta in meta.get("aliases", {}).items():
                if index_name.startswith(alias_name + "-"):
                    found.setdefault(alias_name, {})[index_name] = bool(
                        alias_meta.get("is_write_index")
                    )
    return found


async def _newest_data_at(client: AsyncOpenSearch, index: str) -> datetime | None:
    """The newest of the index's server-stamped `ingested_at` and client `@timestamp` (None = no
    dated docs) — see the module docstring for why the server stamp is the floor (task F m-4).
    Refreshed first — a delete decision must see everything that was indexed."""
    await client.indices.refresh(index=index)
    resp = await client.search(
        index=index,
        body={
            "size": 0,
            "aggs": {
                "newest_ts": {"max": {"field": "@timestamp"}},
                "newest_ingested": {"max": {"field": "ingested_at"}},
            },
        },
    )
    values = [
        v
        for agg in ("newest_ts", "newest_ingested")
        if (v := resp["aggregations"][agg].get("value")) is not None
    ]
    return None if not values else datetime.fromtimestamp(max(values) / 1000, tz=UTC)


async def _created_at(client: AsyncOpenSearch, index: str) -> datetime:
    settings = await client.indices.get_settings(index=index)
    return datetime.fromtimestamp(
        int(settings[index]["settings"]["index"]["creation_date"]) / 1000, tz=UTC
    )


async def run_lifecycle_sweep(
    client: AsyncOpenSearch, *, now: datetime | None = None, prefix: str = ""
) -> dict[str, int]:
    """Roll + retire every managed series once. Returns counts {rolled, dropped, errors}.

    Retention evaluates the pre-rollover backing set, so an index that just rolled is first
    considered on the NEXT run — conservative by a day, never destructive. One broken cluster
    is skipped + counted, never fatal to the rest (task F m-5). `now` is injectable for tests."""
    now = now or datetime.now(UTC)
    rolled = dropped = errors = 0
    knobs_by_cluster: dict[str, LifecycleKnobs] = {}  # read once per cluster per run (D26 live)

    for alias, backing in (await _series_aliases(client, prefix)).items():
        series = next(s for s in SERIES if alias.startswith(f"{prefix}{s}-"))
        cluster_id = alias[len(f"{prefix}{series}-") :]
        try:
            if cluster_id not in knobs_by_cluster:
                knobs_by_cluster[cluster_id] = await read_lifecycle_knobs(
                    client, cluster_id=cluster_id, prefix=prefix
                )
            knobs = knobs_by_cluster[cluster_id]

            # 1) rollover — OpenSearch evaluates the conditions; no-op unless one is met
            resp = await client.indices.rollover(
                alias=alias, body={"conditions": knobs.rollover_conditions()}
            )
            if resp.get("rolled_over"):
                rolled += 1
                log.info(
                    "index rolled",
                    alias=alias,
                    old=resp.get("old_index"),
                    new=resp.get("new_index"),
                )

            # 2) retention — drop whole expired NON-write indices (never the write index, D8)
            cutoff = now - timedelta(days=knobs.retention_days)
            for index_name, is_write in backing.items():
                if is_write:
                    continue
                aged_at = await _newest_data_at(client, index_name) or await _created_at(
                    client, index_name
                )
                if aged_at < cutoff:
                    await client.indices.delete(index=index_name)
                    dropped += 1
                    # a destructive op must leave a trace saying WHY (#156): newest data age
                    # vs the retention window that condemned it
                    log.info(
                        "index dropped",
                        index=index_name,
                        newest_data_at=aged_at.isoformat(),
                        retention_days=knobs.retention_days,
                    )
        except Exception:  # noqa: BLE001 — m-5: isolate the broken cluster, sweep the rest
            log.exception("lifecycle sweep failed for alias", alias=alias, cluster=cluster_id)
            errors += 1

    # 3) rollover-only series (m-6): the audit journal rolls on the fleet knobs, NEVER retires
    for name in ROLLOVER_ONLY:
        alias = f"{prefix}{name}"
        if not await client.indices.exists_alias(name=alias):
            continue
        try:
            fleet = await read_lifecycle_knobs(client, prefix=prefix)
            resp = await client.indices.rollover(
                alias=alias, body={"conditions": fleet.rollover_conditions()}
            )
            if resp.get("rolled_over"):
                rolled += 1
                log.info(
                    "index rolled",
                    alias=alias,
                    old=resp.get("old_index"),
                    new=resp.get("new_index"),
                )
        except Exception:  # noqa: BLE001 — same isolation rule
            log.exception("lifecycle rollover failed for alias", alias=alias)
            errors += 1

    return {"rolled": rolled, "dropped": dropped, "errors": errors}


if __name__ == "__main__":  # daily CronJob entrypoint + interim knob-config CLI (until M9e UI)
    import argparse
    import asyncio

    from backend.core.settings import get_settings

    ap = argparse.ArgumentParser(description="Run the lifecycle sweep, or set the D26 knobs")
    ap.add_argument("--set-max-age-days", type=float, help="rollover: max index age (default 30)")
    ap.add_argument("--set-max-docs", type=int, help="rollover: max docs (default 5,000,000)")
    ap.add_argument("--set-max-size-gb", type=float, help="rollover: max size (default 50)")
    ap.add_argument("--set-retention-days", type=float, help="retention window (default 90)")
    ap.add_argument("--cluster", help="set the per-cluster override (default: fleet-wide)")
    args = ap.parse_args()

    async def _main() -> None:
        settings = get_settings()
        client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
        try:
            updates = {
                key: value
                for key, value in (
                    ("max_age_days", args.set_max_age_days),
                    ("max_docs", args.set_max_docs),
                    ("max_size_gb", args.set_max_size_gb),
                    ("retention_days", args.set_retention_days),
                )
                if value is not None
            }
            if updates:
                current = await read_lifecycle_knobs(client, cluster_id=args.cluster)
                knobs = current.model_copy(update=updates)
                await write_lifecycle_knobs(
                    client, knobs, updated_by="cli", cluster_id=args.cluster
                )
                scope = f"cluster {args.cluster}" if args.cluster else "fleet-wide"
                print(f"lifecycle knobs set ({scope}): {knobs.model_dump()}")
            else:
                print(f"lifecycle sweep: {await run_lifecycle_sweep(client)}")
        finally:
            await client.close()

    asyncio.run(_main())
