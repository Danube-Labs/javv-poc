"""The one copy of the OpenSearch test wiring (#368 conftest dedup, the #384 remainder).

Every integration test file used to carry its own OS_URL constant, reachability probe, and
skip guard (63 copies). They import from here instead; the probe result is cached so a suite
run costs one HTTP round-trip, not one per module.
"""

import os
from functools import cache

import httpx
import pytest

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
