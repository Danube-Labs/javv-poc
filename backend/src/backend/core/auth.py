"""Shared read-side bearer-token auth (D43). A FastAPI dependency that resolves + validates a token
against `system-tokens` and returns its doc. Generic 401 (no token-existence oracle); tokens never
logged. Used by token-authenticated GETs (scan-scope, …).

The hardened ingest POST keeps its own inline auth on purpose — it interleaves rate-limiting and
rejection metrics with the lookup. This dependency is the lighter read-path equivalent. Real
capability-based RBAC replaces both in M5a (D33).
"""

from typing import Any, cast

from fastapi import HTTPException, Request

from backend.core.security import hash_token, tokens_match
from backend.core.settings import get_settings


async def require_token(request: Request) -> dict[str, Any]:
    """Resolve the `Authorization: Bearer <token>` header → its `system-tokens` doc, else 401."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) > 512:
        raise HTTPException(401, "invalid token")
    candidate = hash_token(auth.removeprefix("Bearer "), pepper=get_settings().token_pepper)
    client = cast(Any, request.app.state.opensearch)
    hits = await client.search(
        index="system-tokens",
        body={"query": {"term": {"token_hash": candidate}}, "size": 1},
    )
    docs = hits["hits"]["hits"]
    token = docs[0]["_source"] if docs else None
    if (
        token is None
        or not tokens_match(candidate, token["token_hash"])  # constant-time, belt & braces
        or token.get("disabled")
    ):
        raise HTTPException(401, "invalid token")  # generic — no existence oracle
    return token
