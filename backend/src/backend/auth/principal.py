"""Principal resolution (M5a, D33) — session cookie → the authenticated human + their effective
capabilities. Routes never touch cookies or user docs; they depend on `require_capability(cap)`
(capabilities.py) and receive a `Principal`. This is also the provider-agnostic half of the
OIDC/LDAP seam: however the user authenticated, a session resolves the same way."""

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from opensearchpy import NotFoundError

from backend.auth.sessions import COOKIE_NAME, lookup_session

USERS_INDEX = "system-users"


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    role: str | None
    capabilities: frozenset[str]  # effective; "*" = Admin holds all (D33)
    must_change: bool  # SEC-6: True locks everything but the /auth/* escape hatch


async def get_current_principal(request: Request) -> Principal:
    """Session → user → Principal, else generic 401 (dead session and deleted/disabled user are
    indistinguishable on purpose)."""
    client: Any = request.app.state.opensearch
    session = await lookup_session(client, request.cookies.get(COOKIE_NAME, ""))
    if session is None:
        raise HTTPException(401, "invalid credentials")
    try:
        user = (await client.get(index=USERS_INDEX, id=session["user_id"]))["_source"]
    except NotFoundError:
        raise HTTPException(401, "invalid credentials") from None
    if user.get("disabled"):
        raise HTTPException(401, "invalid credentials")

    capabilities = user.get("capabilities")
    if capabilities is None and user.get("role"):  # not denormalized → resolve the role bundle
        from backend.auth.capabilities import resolve_role_capabilities

        capabilities = await resolve_role_capabilities(client, user["role"])
    return Principal(
        user_id=session["user_id"],
        username=user["username"],
        role=user.get("role"),
        capabilities=frozenset(capabilities or []),
        must_change=bool(user.get("must_change")),
    )
