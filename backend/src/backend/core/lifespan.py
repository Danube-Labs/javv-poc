"""App lifespan: hold the single `AsyncOpenSearch` client for the process, injected via the app
state and `await`-closed on shutdown (STACK-BEST-PRACTICES: one client, no per-request clients).

Note: the client is created lazily-connecting — constructing it does not open a socket, so the app
boots without OpenSearch. Startup fail-fast (clear error + non-zero exit when unreachable) and the
`/readyz` degrade path land with the observability/bootstrap slice; kept out of the skeleton so the
Backend CI job stays green before an OpenSearch service container is wired.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opensearchpy import AsyncOpenSearch

from backend.core.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    client = AsyncOpenSearch(hosts=[settings.opensearch_url], timeout=settings.request_timeout)
    app.state.opensearch = client
    try:
        yield
    finally:
        await client.close()
