"""The one copy of the OpenSearch test setup (#368 conftest dedup, the #384 remainder).

Every integration test file used to carry its own OS_URL constant, reachability probe, and
skip guard (63 copies). They import from here instead; the probe result is cached so a suite
run costs one HTTP round-trip, not one per module.
"""

import contextlib
import os
from functools import cache
from typing import Any

import httpx
import pytest
from opensearchpy import NotFoundError

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


@cache
def opensearch_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not opensearch_up(), reason=f"OpenSearch not reachable at {OS_URL}"
)


async def drop_prefix(client: Any, prefix: str) -> None:
    """Tear down everything a `bootstrap(client, prefix=...)` made: its indices AND its index
    templates. Templates outlive their indices, and each one left behind grows the cluster state
    that every later index or template write republishes (issue 550: 51k leaked templates made
    the shared dev store ~5x slower per test). Safe to call when nothing is left."""
    with contextlib.suppress(NotFoundError):
        await client.indices.delete(index=f"{prefix}*", params={"expand_wildcards": "all"})
    with contextlib.suppress(NotFoundError):
        await client.indices.delete_index_template(name=f"{prefix}*")
