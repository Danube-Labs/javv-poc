"""Server-side sessions (M5a, SEC-5) — mint/lookup/revoke against `system-sessions`.

Sessions, not JWTs: revocation is a hard requirement (logout-all + revoke-on-role-change, D33),
and OpenSearch is the single store — a session lookup is one `GET` by `_id`. The raw session id is
a 256-bit random value that exists only in the httpOnly cookie; the store holds its **peppered
SHA-256** (domain-separated from ingest tokens), so a leaked index can't replay sessions — the
same never-store-the-raw-secret rule as `system-tokens`. `expires_at` is the authoritative TTL
(`JAVV_SESSION_TTL_HOURS`, default 24); the cookie's own lifetime is advisory.

Cookie handling (Set-Cookie flags) lives with the routes; this module is storage + lifecycle only,
shared by every identity provider — external IdPs (OIDC/LDAP, post-MVP) still mint THESE sessions.
"""

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings

COOKIE_NAME = "javv_session"
INDEX = "system-sessions"


def _session_hash(raw: str) -> str:
    # domain separation: a session hash can never collide with an ingest-token hash
    return hash_token(f"session:{raw}", pepper=get_settings().token_pepper)


async def mint_session(
    client: AsyncOpenSearch,
    user_id: str,
    *,
    now: datetime | None = None,
    prefix: str = "",
) -> str:
    """Create a session; returns the RAW id (cookie value) — it never exists server-side again."""
    now = now or datetime.now(UTC)
    raw = mint_token()  # 256-bit random, same primitive as ingest tokens
    hashed = _session_hash(raw)
    await client.index(
        index=f"{prefix}{INDEX}",
        id=hashed,
        body={
            "session_id": hashed,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=get_settings().session_ttl_hours)).isoformat(),
            "revoked": False,
        },
        params={"refresh": "true"},  # a session must be usable on the very next request
    )
    return raw


async def lookup_session(
    client: AsyncOpenSearch, raw: str, *, now: datetime | None = None, prefix: str = ""
) -> dict[str, Any] | None:
    """The session doc for a cookie value — None when absent, expired, or revoked (the caller
    answers the same generic 401 for all three; no distinguishing oracle)."""
    if not raw:
        return None
    now = now or datetime.now(UTC)
    try:
        doc = (await client.get(index=f"{prefix}{INDEX}", id=_session_hash(raw)))["_source"]
    except NotFoundError:
        return None
    if doc.get("revoked") or datetime.fromisoformat(doc["expires_at"]) <= now:
        return None
    return doc


async def revoke_session(client: AsyncOpenSearch, raw: str, *, prefix: str = "") -> None:
    """Logout: server-side kill of one session (idempotent; unknown cookie is a no-op)."""
    with contextlib.suppress(NotFoundError):
        await client.update(
            index=f"{prefix}{INDEX}",
            id=_session_hash(raw),
            body={"doc": {"revoked": True}},
            params={"refresh": "true"},
        )


async def revoke_all_for_user(client: AsyncOpenSearch, user_id: str, *, prefix: str = "") -> int:
    """Logout-all / revoke-on-role-change (D33): kill every live session of the user.

    Retried until ZERO version conflicts (task C m-2, #140): with `conflicts=proceed` alone, a
    doc that raced a concurrent write is silently skipped — a stolen session could survive
    logout-all. The query re-selects only still-unrevoked docs, so retrying converges."""
    total = 0
    for _ in range(8):
        resp = await client.update_by_query(
            index=f"{prefix}{INDEX}",
            body={
                "query": {
                    "bool": {
                        "filter": [{"term": {"user_id": user_id}}],
                        "must_not": [{"term": {"revoked": True}}],
                    }
                },
                "script": {"lang": "painless", "source": "ctx._source.revoked = true;"},
            },
            params={"conflicts": "proceed", "refresh": "true"},
        )
        total += int(resp.get("updated", 0))
        if int(resp.get("version_conflicts", 0)) == 0:
            return total
    raise RuntimeError(f"revoke_all_for_user: conflicts did not drain for {user_id}")
