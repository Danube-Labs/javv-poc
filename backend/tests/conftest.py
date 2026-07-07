"""Session-wide test wiring (#221, major-audit 01 §2 S-1).

The suite's dominant cost was ~0.85 s of per-test *setup*: every integration fixture re-ran
`bootstrap(client)` (+ `seed_default_roles`) against the shared dev/CI OpenSearch — idempotent,
but a dozen round-trips × ~450 tests. Both are versioned/seed-once, so ONE run per session is
equivalent: this autouse fixture does it up front and the per-test fixtures just connect.

Event-loop edge case (01 §2): the suite runs per-test event loops (`asyncio_mode = "auto"`), so
this is a session-scoped **sync** fixture driving its own short-lived loop via `asyncio.run` —
an AsyncOpenSearch client is never shared across loops.

Deliberately NOT converted: the restore-drill / rollover / bootstrap tests keep their private
prefixes (they delete indices — sharing would poison the session), and anything prefix-isolated
stays as is."""

import asyncio
import os

import httpx
import pytest

OS_URL = os.environ.get("JAVV_OPENSEARCH_URL", "http://localhost:9200")


def _os_up() -> bool:
    try:
        return httpx.get(OS_URL, timeout=2.0).status_code == 200
    except Exception:
        return False


async def _bootstrap_once() -> None:
    from opensearchpy import AsyncOpenSearch

    from backend.auth.capabilities import seed_default_roles
    from backend.core.bootstrap import bootstrap

    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        await bootstrap(client)
        await seed_default_roles(client)
    finally:
        await client.close()


@pytest.fixture(scope="session", autouse=True)
def shared_bootstrap() -> None:
    """Bootstrap the real (unprefixed) indices + role seed ONCE per session. No-op (fast fail on
    the reachability probe) when OpenSearch is down — the integration tests skip themselves."""
    if _os_up():
        asyncio.run(_bootstrap_once())
