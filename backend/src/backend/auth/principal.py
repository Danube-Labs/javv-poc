"""Principal resolution (M5a, D33) — session cookie → the authenticated human + their effective
capabilities. Routes never touch cookies or user docs; they depend on `require_capability(cap)`
(capabilities.py) and receive a `Principal`. This is also the provider-agnostic half of the
OIDC/LDAP seam: however the user authenticated, a session resolves the same way."""

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from opensearchpy import NotFoundError

from backend.auth.sessions import COOKIE_NAME, lookup_session
from backend.core.metrics import AUTH_FAILURES

USERS_INDEX = "system-users"


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    role: str | None
    capabilities: frozenset[str]  # effective; "*" = Admin holds all (D33)


async def get_current_principal(request: Request) -> Principal:
    """Session → user → Principal, else generic 401 (dead session and deleted/disabled user are
    indistinguishable on purpose). A `must_change` user is refused here, so every session route
    shares one gate, reads included (issue 803). `/auth/*` resolves the session through its own
    `require_session`, which keeps the way to change the password open."""
    client: Any = request.app.state.opensearch
    session = await lookup_session(client, request.cookies.get(COOKIE_NAME, ""))
    if session is None:
        AUTH_FAILURES.labels("expired_session").inc()  # M-5 (#220): no/dead session on a route
        raise HTTPException(401, "invalid credentials")
    try:
        user = (await client.get(index=USERS_INDEX, id=session["user_id"]))["_source"]
    except NotFoundError:
        raise HTTPException(401, "invalid credentials") from None
    if user.get("disabled"):
        raise HTTPException(401, "invalid credentials")
    if user.get("must_change"):
        raise HTTPException(403, "password change required")

    capabilities = user.get("capabilities")
    if capabilities is None and user.get("role"):  # not denormalized → resolve the role bundle
        from backend.auth.capabilities import resolve_role_capabilities

        capabilities = await resolve_role_capabilities(client, user["role"])
    return Principal(
        user_id=session["user_id"],
        username=user["username"],
        role=user.get("role"),
        capabilities=frozenset(capabilities or []),
    )
