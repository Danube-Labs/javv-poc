"""The cluster registry (D-5, M8c): one `system-config` doc, `cluster-registry`, mapping
`{cluster_id → cluster_name}`. `cluster_name` is display-only, never a query key. Shared by the
rename route and the cluster delete (issue 765)."""

from datetime import UTC, datetime

from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConflictError, NotFoundError

REGISTRY_KEY = "cluster-registry"


async def read_registry(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, str]:
    """The registry map `{cluster_id → cluster_name}`; empty until the first rename."""
    try:
        got = await client.get(index=f"{prefix}system-config", id=REGISTRY_KEY)
    except NotFoundError:
        return {}
    names = got["_source"].get("value") or {}
    return {k: v for k, v in names.items() if isinstance(v, str)}


async def set_registry_name(
    client: AsyncOpenSearch,
    cluster_id: str,
    name: str | None,
    *,
    actor: str,
    prefix: str = "",
) -> bool:
    """Set one cluster's display name, or remove its entry (`name=None`). False when the doc
    stayed contended for every attempt; the caller decides what that means.

    A guarded read-modify-write (the D40 rule: never a naked RMW on shared state): seq_no CAS,
    re-read and retry on conflict, so two concurrent writes for DIFFERENT clusters both land
    instead of one silently losing the doc race."""
    for _ in range(5):
        try:
            got = await client.get(index=f"{prefix}system-config", id=REGISTRY_KEY)
            names = {
                k: v for k, v in (got["_source"].get("value") or {}).items() if isinstance(v, str)
            }
            cas = {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}
        except NotFoundError:
            names, cas = {}, {"op_type": "create"}
        if name is None:
            if cluster_id not in names:
                return True  # nothing to remove
            del names[cluster_id]
        else:
            names[cluster_id] = name
        try:
            await client.index(
                index=f"{prefix}system-config",
                id=REGISTRY_KEY,
                body={
                    "key": REGISTRY_KEY,
                    "value": names,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "updated_by": actor,
                },
                params={"refresh": "true", **cas},
            )
        except ConflictError:
            continue  # someone else moved the doc: re-read and re-apply
        return True
    return False
