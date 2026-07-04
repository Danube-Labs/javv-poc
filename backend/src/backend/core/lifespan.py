"""App lifespan: hold the single `AsyncOpenSearch` client for the process (STACK-BEST-PRACTICES:
one client, no per-request clients), and enforce the boot contract (observability.md):

  ping OpenSearch → run the versioned index bootstrap → serve.

**Fail-fast at startup** (D9): if OpenSearch is unreachable at boot, raise — the process exits
non-zero with a clear message rather than serving a broken app. At *runtime* the app stays up and
degrades (`/readyz` → 503) instead of crashing. Set `JAVV_BOOTSTRAP_ON_STARTUP=false` to skip the
ping+bootstrap (used by unit tests that run the app without an OpenSearch).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from opensearchpy import AsyncOpenSearch

from backend.auth.bootstrap_admin import seed_bootstrap_admin
from backend.core.bootstrap import bootstrap
from backend.core.settings import get_settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
    app.state.opensearch = client

    if settings.bootstrap_on_startup:
        try:
            await client.info()  # fail-fast: unreachable OpenSearch at boot is fatal
        except Exception as exc:
            await client.close()
            raise RuntimeError(
                f"OpenSearch unreachable at startup ({settings.opensearch_url}): {exc!r}"
            ) from exc
        results = await bootstrap(client)  # idempotent + version-gated
        log.info("bootstrap complete", indexes=results)
        # M5a/SEC-6: seed the bootstrap admin exactly once (no-op unless the secret is mounted)
        log.info("bootstrap admin", outcome=await seed_bootstrap_admin(client))

    try:
        yield
    finally:
        await client.close()
