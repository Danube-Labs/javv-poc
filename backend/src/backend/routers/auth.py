"""Human auth routes (M5a slice 3, FR-18/SEC-6) — login/logout/me/password over the
provider-agnostic session layer. Failure discipline: unknown user, wrong password, disabled
account, and a dead session are all the SAME generic 401 (no oracle of any kind); lockout is 429
before credentials are even looked at. The session cookie is `HttpOnly; Secure; SameSite=Lax`
(localhost counts as a secure context in browsers, so dev works); its `Max-Age` mirrors the TTL
but the server-side `expires_at` is what actually decides.

`must_change` (SEC-6): a fresh bootstrap admin can log in, read `/auth/me`, change its password,
and log out — nothing else. The capability gate (slice 4, `require_capability`) rejects
`must_change` principals on every other protected route; nothing here needs to.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_auth_event
from backend.auth import lockout
from backend.auth.passwords import check_policy, hash_password, verify_password
from backend.auth.providers import USERS_INDEX, LocalPasswordProvider, LoginCredentials
from backend.auth.sessions import (
    COOKIE_NAME,
    lookup_session,
    mint_session,
    revoke_all_for_user,
    revoke_session,
)
from backend.core.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

_provider = LocalPasswordProvider()  # the IdentityProvider seam — OIDC/LDAP swap in post-MVP

_GENERIC_401 = HTTPException(401, "invalid credentials")  # one answer for every failure mode


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def _os(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    """The response shape — UI hints only (the server re-checks every call); never the hash."""
    return {
        "username": user["username"],
        "role": user.get("role"),
        "capabilities": user.get("capabilities", []),
        "must_change": bool(user.get("must_change")),
    }


def _set_session_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=int(get_settings().session_ttl_hours * 3600),  # advisory; expires_at decides
    )


async def require_session(request: Request) -> dict[str, Any]:
    """Cookie → live session doc, else the generic 401. Slice 4's principal resolution builds on
    this; auth routes only need the session's `user_id`."""
    session = await lookup_session(_os(request), request.cookies.get(COOKIE_NAME, ""))
    if session is None:
        raise _GENERIC_401
    return session


@router.post("/login")
async def login(request: Request, creds: LoginCredentials, response: Response) -> dict[str, Any]:
    if lockout.locked(creds.username):
        raise HTTPException(429, "too many attempts")  # budget spent — credentials unseen
    result = await _provider.authenticate(_os(request), creds)
    if result is None:
        lockout.record_failure(creds.username)
        raise _GENERIC_401
    lockout.clear(creds.username)
    _set_session_cookie(response, await mint_session(_os(request), result.user_id))
    await append_auth_event(
        _os(request),
        actor=result.user_id,
        action="login",
        entity_type="user",
        entity_id=result.user_id,
    )
    return {"user": _public_user(result.user)}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    raw = request.cookies.get(COOKIE_NAME, "")
    if raw:
        client = _os(request)
        session = await lookup_session(client, raw)
        await revoke_session(client, raw)  # server-side kill — the cookie is now inert
        if session is not None:
            await append_auth_event(
                client,
                actor=session["user_id"],
                action="logout",
                entity_type="user",
                entity_id=session["user_id"],
            )
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me")
async def me(
    request: Request, session: Annotated[dict[str, Any], Depends(require_session)]
) -> dict[str, Any]:
    user = await _load_user(request, session["user_id"])
    return {"user": _public_user(user)}


@router.post("/password")
async def change_password(
    request: Request,
    body: PasswordChange,
    response: Response,
    session: Annotated[dict[str, Any], Depends(require_session)],
) -> dict[str, Any]:
    """First-login `must_change` exit + regular self-service change. Verifies the CURRENT password
    (a hijacked cookie alone can't rotate credentials), then revokes every session of the user and
    mints a fresh one — a concurrently-stolen session dies with the old password."""
    client = _os(request)
    user = await _load_user(request, session["user_id"])
    if user.get("auth_source", "local") != "local":
        raise HTTPException(403, "password is managed by the identity provider")
    if not verify_password(body.current_password, user.get("password_hash") or ""):
        raise _GENERIC_401
    try:
        check_policy(body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await client.update(
        index=USERS_INDEX,
        id=session["user_id"],
        body={"doc": {"password_hash": hash_password(body.new_password), "must_change": False}},
        params={"refresh": "true"},
    )
    await revoke_all_for_user(client, session["user_id"])
    _set_session_cookie(response, await mint_session(client, session["user_id"]))
    await append_auth_event(
        client,
        actor=session["user_id"],
        action="pwd_change",
        entity_type="user",
        entity_id=session["user_id"],
    )
    return {"user": _public_user({**user, "must_change": False})}


async def _load_user(request: Request, user_id: str) -> dict[str, Any]:
    from opensearchpy import NotFoundError  # local import keeps the router surface tidy

    try:
        user = (await _os(request).get(index=USERS_INDEX, id=user_id))["_source"]
    except NotFoundError:  # user deleted while the session lived
        raise _GENERIC_401 from None
    if user.get("disabled"):
        raise _GENERIC_401
    return user
