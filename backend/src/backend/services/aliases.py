"""Write aliases for the per-cluster append series (M4 slice 1, audit n-2).

INDEX-MAP naming rule: "ISM rollover creates numbered backing indices behind a write-alias".
Ingest writes to the bare series alias (`javv-scan-events-<cluster>`); the backing indices are
`-000001`, `-000002`, … and rollover retargets `is_write_index` — no code change per roll. Clusters
appear dynamically (any authorized token can push), so the alias is ensured lazily at ingest, not
in `bootstrap` (which can't know the cluster set). The check is one cheap HEAD per series per
envelope — measure before caching it in-process.

Reads are untouched: they use the `-<cluster>-*` wildcard, which matches the backing indices but
not the (suffix-less) alias, so nothing is double-counted.
"""

from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import RequestError

FIRST_SUFFIX = "-000001"


async def ensure_write_alias(client: AsyncOpenSearch, alias: str) -> None:
    """Idempotently ensure `alias` exists and targets a write index.

    Fresh series → create `<alias>-000001` carrying the alias (the template pins its mapping).
    Legacy series (pre-M4 bare `-000001`, or a racing pod won the create) → attach the alias to
    the existing index instead; `put_alias` is itself idempotent, so concurrent pods are safe.
    """
    if await client.indices.exists_alias(name=alias):
        return
    first = alias + FIRST_SUFFIX
    try:
        await client.indices.create(
            index=first, body={"aliases": {alias: {"is_write_index": True}}}
        )
    except RequestError as exc:
        if exc.error != "resource_already_exists_exception":
            raise
        await client.indices.put_alias(index=first, name=alias, body={"is_write_index": True})
