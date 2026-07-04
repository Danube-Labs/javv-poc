"""Admin user/role management (audit task D, #141) — the `can_manage_users`-gated surface that
closes the M5a FR-18 gap. Rulings (recorded on #141): bootstrap stays secret-only (no default
credential); a created/reset user gets an admin-set temp password and starts `must_change: true`
(the same SEC-6 server-enforced first-login change the bootstrap admin gets); a role change
updates `role` + the denormalized `capabilities` together and REVOKES every session of the user
(D33 — role/permission changes must not ride an old session); disable also revokes. The LAST
enabled admin can be neither demoted nor disabled (409 — no self-bricking; recovery would be
manual index surgery). Role-bundle EDITING is out of scope (assignment of `system-roles` bundles
only); external (`oidc`/`ldap`) users' passwords are their IdP's business (403 on reset).

Every route registers in the standing RBAC/IDOR suite (`tests/security/test_rbac_idor_contract.py`)
and every mutation is journaled (D17)."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from opensearchpy import NotFoundError
from opensearchpy.exceptions import ConflictError
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_auth_event
from backend.auth.capabilities import ROLES_INDEX, require_capability
from backend.auth.passwords import check_policy, hash_password
from backend.auth.principal import Principal
from backend.auth.sessions import revoke_all_for_user

router = APIRouter(prefix="/api/v1/admin/users", tags=["user-admin"])

USERS_INDEX = "system-users"
_PUBLIC_FIELDS = (  # never password_hash — the hash never leaves the server
    "username",
    "role",
    "capabilities",
    "must_change",
    "disabled",
    "auth_source",
    "created_at",
)

ManageUsers = Annotated[Principal, Depends(require_capability("can_manage_users"))]


class CreateUser(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    temp_password: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=64)


class RolePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1, max_length=64)


class DisabledPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disabled: bool


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temp_password: str = Field(min_length=1, max_length=256)


def _os(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: doc.get(k) for k in _PUBLIC_FIELDS}


def _check_policy_or_422(password: str) -> None:
    try:
        check_policy(password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


async def _role_capabilities_or_422(client: Any, role: str) -> list[str]:
    """The role's bundle — an unknown role is a caller error (422), never fail-open."""
    try:
        doc = (await client.get(index=ROLES_INDEX, id=role))["_source"]
    except NotFoundError:
        raise HTTPException(422, f"unknown role {role!r}") from None
    return list(doc.get("capabilities", []))


async def _load_user(client: Any, username: str) -> dict[str, Any]:
    try:
        return (await client.get(index=USERS_INDEX, id=username))["_source"]
    except NotFoundError:
        raise HTTPException(404, "user not found") from None


async def _assert_not_last_admin(client: Any, username: str) -> None:
    """Refuse to remove the final enabled admin — another one must exist first."""
    hits = await client.search(
        index=USERS_INDEX,
        body={
            "size": 0,
            "query": {
                "bool": {
                    "filter": [{"term": {"role": "admin"}}],
                    "must_not": [
                        {"term": {"disabled": True}},
                        {"term": {"username": username}},
                    ],
                }
            },
        },
    )
    if hits["hits"]["total"]["value"] == 0:
        raise HTTPException(409, "cannot demote or disable the last enabled admin")


@router.get("")
async def list_users(request: Request, principal: ManageUsers) -> dict[str, Any]:
    # size cap mirrors the token list (audit task E tracks pagination for both)
    hits = await _os(request).search(
        index=USERS_INDEX, body={"size": 10_000, "query": {"match_all": {}}}
    )
    return {"users": [_public(h["_source"]) for h in hits["hits"]["hits"]]}


@router.post("", status_code=201)
async def create_user(request: Request, body: CreateUser, principal: ManageUsers) -> dict[str, Any]:
    client = _os(request)
    _check_policy_or_422(body.temp_password)
    capabilities = await _role_capabilities_or_422(client, body.role)
    doc = {
        "username": body.username,
        "password_hash": hash_password(body.temp_password),
        "role": body.role,
        "capabilities": capabilities,  # denormalized from the bundle (kept in step on role change)
        "must_change": True,  # SEC-6: the temp password is not a real one
        "disabled": False,
        "auth_source": "local",
        "external_id": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        await client.index(
            index=USERS_INDEX,
            id=body.username,
            body=doc,
            params={"op_type": "create", "refresh": "true"},  # an existing user is NEVER clobbered
        )
    except ConflictError:
        raise HTTPException(409, "user already exists") from None
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="user_create",
        entity_type="user",
        entity_id=body.username,
    )
    return {"user": _public(doc)}


@router.patch("/{username}/role")
async def set_role(
    request: Request, username: str, body: RolePatch, principal: ManageUsers
) -> dict[str, Any]:
    client = _os(request)
    user = await _load_user(client, username)
    if user.get("role") == body.role:
        return {"user": _public(user)}  # no-op: nothing changes, sessions survive
    capabilities = await _role_capabilities_or_422(client, body.role)
    if user.get("role") == "admin":
        await _assert_not_last_admin(client, username)
    await client.update(
        index=USERS_INDEX,
        id=username,
        body={"doc": {"role": body.role, "capabilities": capabilities}},
        params={"refresh": "true"},
    )
    await revoke_all_for_user(client, username)  # D33: a new role never rides an old session
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="role_change",
        entity_type="user",
        entity_id=username,
    )
    return {"user": _public({**user, "role": body.role, "capabilities": capabilities})}


@router.patch("/{username}/disabled")
async def set_disabled(
    request: Request, username: str, body: DisabledPatch, principal: ManageUsers
) -> dict[str, Any]:
    client = _os(request)
    user = await _load_user(client, username)
    if bool(user.get("disabled")) == body.disabled:
        return {"user": _public(user)}  # no-op
    if body.disabled and user.get("role") == "admin":
        await _assert_not_last_admin(client, username)
    await client.update(
        index=USERS_INDEX,
        id=username,
        body={"doc": {"disabled": body.disabled}},
        params={"refresh": "true"},
    )
    if body.disabled:
        await revoke_all_for_user(client, username)  # dead account = dead sessions, immediately
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="user_disable" if body.disabled else "user_enable",
        entity_type="user",
        entity_id=username,
    )
    return {"user": _public({**user, "disabled": body.disabled})}


@router.post("/{username}/password-reset")
async def password_reset(
    request: Request, username: str, body: PasswordReset, principal: ManageUsers
) -> dict[str, Any]:
    client = _os(request)
    user = await _load_user(client, username)
    if user.get("auth_source", "local") != "local":
        raise HTTPException(403, "password is managed by the identity provider")
    _check_policy_or_422(body.temp_password)
    await client.update(
        index=USERS_INDEX,
        id=username,
        body={"doc": {"password_hash": hash_password(body.temp_password), "must_change": True}},
        params={"refresh": "true"},
    )
    await revoke_all_for_user(client, username)  # a possibly-compromised account starts clean
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="pwd_reset",
        entity_type="user",
        entity_id=username,
    )
    return {"user": _public({**user, "must_change": True})}
