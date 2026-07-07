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
from backend.auth.capabilities import seed_default_roles
from backend.core.bootstrap import bootstrap, summarize_actions
from backend.core.settings import assert_production_ready, get_settings
from backend.query.as_of import register_as_of_t
from backend.query.as_of_t import AsOfTQuery

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    assert_production_ready(settings)  # task C/Codex M3: dev secrets never survive a prod boot
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
        # names as list values keyed by action — as keys, `system-tokens` gets redacted (#156)
        log.info("bootstrap complete", **summarize_actions(results))
        # M5a/D33+SEC-6: default role bundles + the bootstrap admin — both seed-once
        # (op_type=create), so customized roles / a live admin are never overwritten
        roles_created = await seed_default_roles(client)
        log.info("bootstrap admin", outcome=await seed_bootstrap_admin(client), roles=roles_created)

    # D28/FR-23: the whole-app time-travel reader goes live with the app (M8b slice 4 — the
    # protocol is fully implemented; before this, a past-T read was 501 at the seam)
    register_as_of_t(AsOfTQuery())

    try:
        yield
    finally:
        await client.close()
