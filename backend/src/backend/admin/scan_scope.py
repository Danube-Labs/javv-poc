"""Scan scope (D43/FR-24) — which namespaces/images/kinds the scanner scans, per cluster. Stored in
`system-config` as one `scan_scope:<cluster_id>` doc; the scanner fetches it via
`GET /api/v1/scan-scope` and filters discovery *before* pull/scan. Runtime data (tier ③), edited
via the M9e UI or the interim CLI below — not env/GitOps (scanner *tuning*, #91) nor version (D41).

The wire shape (`ScanScope`) is **mirrored in `scanner/scope.py`** — keep the two in sync (same
coupling as the ingest envelope). Empty scope = scan everything (the default).
"""

from datetime import UTC, datetime

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict


def _doc_id(cluster_id: str) -> str:
    return f"scan_scope:{cluster_id}"


class ScanScope(BaseModel):
    """Non-secret scan-scope policy for one cluster. Empty everywhere = scan all."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    include_namespaces: tuple[str, ...] = ()  # allowlist; empty = all namespaces
    ignore_namespaces: tuple[str, ...] = ()  # denylist; wins over include
    exclude_images: tuple[str, ...] = ()  # image_ref globs to skip
    ignore_kinds: tuple[str, ...] = ()  # pod owner-reference kinds to skip (e.g. Job, DaemonSet)


async def read_scan_scope(
    client: AsyncOpenSearch, cluster_id: str, *, prefix: str = ""
) -> ScanScope:
    """The cluster's scan scope, or an empty scope (= scan everything) if none is configured."""
    try:
        got = await client.get(index=f"{prefix}system-config", id=_doc_id(cluster_id))
    except NotFoundError:
        return ScanScope()
    return ScanScope.model_validate(got["_source"]["value"])


async def write_scan_scope(
    client: AsyncOpenSearch,
    cluster_id: str,
    scope: ScanScope,
    *,
    updated_by: str,
    prefix: str = "",
) -> None:
    """Persist the cluster's scan scope in system-config (one doc per cluster)."""
    doc = {
        "key": _doc_id(cluster_id),
        "cluster_id": cluster_id,
        "value": scope.model_dump(),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": updated_by,
    }
    await client.index(
        index=f"{prefix}system-config",
        id=_doc_id(cluster_id),
        body=doc,
        params={"refresh": "true"},
    )


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(v.strip() for v in (value or "").split(",") if v.strip())


if __name__ == "__main__":  # interim admin write path until the M9e UI (FR-24); mirrors tokens.py
    import argparse
    import asyncio

    from backend.core.settings import get_settings

    ap = argparse.ArgumentParser(description="Set a cluster's scan scope in system-config")
    ap.add_argument("--cluster", required=True)
    ap.add_argument("--include-namespaces", help="comma-separated allowlist (empty = all)")
    ap.add_argument("--ignore-namespaces", help="comma-separated denylist")
    ap.add_argument("--exclude-images", help="comma-separated image_ref globs")
    ap.add_argument("--ignore-kinds", help="comma-separated owner kinds (Job,DaemonSet,…)")
    args = ap.parse_args()

    scope = ScanScope(
        include_namespaces=_csv(args.include_namespaces),
        ignore_namespaces=_csv(args.ignore_namespaces),
        exclude_images=_csv(args.exclude_images),
        ignore_kinds=_csv(args.ignore_kinds),
    )

    async def _main() -> None:
        settings = get_settings()
        client = AsyncOpenSearch(hosts=[settings.opensearch_url])
        try:
            await write_scan_scope(client, args.cluster, scope, updated_by="cli")
            print(f"scan_scope set for {args.cluster}: {scope.model_dump()}")
        finally:
            await client.close()

    asyncio.run(_main())
