"""Capability gate (M5a, D33/SEC-2/SEC-9) — `require_capability(cap)` is THE enforcement
chokepoint: every mutating/protected route declares it and receives a `Principal`. 401 answers
"who are you"; 403 answers "you may not" — including any `must_change` session touching anything
beyond the /auth/* escape hatch (SEC-6). Admin holds all via the `"*"` marker.

Role bundles live in `system-roles` (doc `_id` = role); the defaults below seed once
(`op_type=create`) so an operator's customized bundle is never clobbered. Destructive caps
(`can_manage_*`, `can_restore_snapshot`, `can_drop_index`, `can_rebuild_state`) are Admin-only by
default and stay journaled (D17)."""

from typing import Annotated, Any

from fastapi import Depends, HTTPException
from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConflictError

from backend.auth.principal import Principal, get_current_principal

ROLES_INDEX = "system-roles"

# the D33 defaults — Admin's "*" means every capability, present and future
ROLE_BUNDLES: dict[str, list[str]] = {
    "viewer": [],
    "triager": ["can_triage"],
    "security_lead": ["can_triage", "can_accept_audit_final"],  # SEC-2: gates risk-accept
    "admin": ["*"],
}


def require_capability(capability: str):
    """Dependency factory: `Depends(require_capability("can_triage"))` → the Principal."""

    async def _gate(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.must_change:
            raise HTTPException(403, "password change required")  # SEC-6 restricted session
        if "*" not in principal.capabilities and capability not in principal.capabilities:
            raise HTTPException(403, "missing capability")
        return principal

    return _gate


async def resolve_role_capabilities(
    client: AsyncOpenSearch, role: str, *, prefix: str = ""
) -> list[str]:
    """A role's bundle from `system-roles`; unknown role = no capabilities (fail closed)."""
    try:
        doc = (await client.get(index=f"{prefix}{ROLES_INDEX}", id=role))["_source"]
    except NotFoundError:
        return []
    return list(doc.get("capabilities", []))


async def seed_default_roles(client: Any, *, prefix: str = "") -> int:
    """Seed the D33 default bundles once; existing (possibly customized) roles are untouched.
    Returns how many were created."""
    created = 0
    for role, capabilities in ROLE_BUNDLES.items():
        try:
            await client.index(
                index=f"{prefix}{ROLES_INDEX}",
                id=role,
                body={"role": role, "capabilities": capabilities},
                params={"op_type": "create", "refresh": "true"},
            )
            created += 1
        except ConflictError:
            continue
    return created
