"""Reset a local user's password from a shell where the backend runs (issue 761): the way back when
no admin can sign in to reset it from Settings.

    docker compose exec backend python -m backend.auth.reset_password <username>
    kubectl exec deploy/<release>-backend -- python -m backend.auth.reset_password <username>

It does what an admin's `POST /api/v1/admin/users/{username}/password-reset` does: a temporary
password, `must_change`, every session of the user revoked, and a `pwd_reset` row journaled first
(D17). No user is signed in, so the row's actor is `system`, a name no human can take (A-m6). The
password is generated rather than typed, so it never reaches shell history; it is printed once and
never logged. A shell in the backend's container already holds the store's credentials, so the
command grants nothing that shell lacked.

Login lockout lives in the running backend's memory, which this process cannot reach."""

import secrets

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.audit.writer import append_auth_event
from backend.auth.passwords import check_policy, hash_password
from backend.auth.sessions import revoke_all_for_user

log = structlog.get_logger()

USERS_INDEX = "system-users"
ACTOR = "system"


class ResetRefused(Exception):
    """Nothing was changed; the message says why."""


def temporary_password() -> str:
    password = secrets.token_urlsafe(18)  # 24 characters
    check_policy(password)
    return password


async def reset_password(client: AsyncOpenSearch, username: str, *, prefix: str = "") -> str:
    """Set a temporary password the user must change at the next sign-in, and return it."""
    try:
        user = (await client.get(index=f"{prefix}{USERS_INDEX}", id=username))["_source"]
    except NotFoundError:
        raise ResetRefused(f"no user named {username!r}") from None
    if user.get("auth_source", "local") != "local":
        raise ResetRefused(
            f"{username!r} signs in through an identity provider, which owns its password"
        )
    password = temporary_password()
    await append_auth_event(
        client,
        actor=ACTOR,
        action="pwd_reset",
        entity_type="user",
        entity_id=username,
        strict=True,
        prefix=prefix,
    )
    await client.update(
        index=f"{prefix}{USERS_INDEX}",
        id=username,
        body={"doc": {"password_hash": hash_password(password), "must_change": True}},
        params={"refresh": "true"},
    )
    await revoke_all_for_user(client, username, prefix=prefix)
    log.info("password reset", username=username, actor=ACTOR)
    return password


if __name__ == "__main__":
    import argparse
    import asyncio
    import sys

    from backend.core.logging import configure_logging
    from backend.core.opensearch_client import build_client
    from backend.core.settings import get_settings

    ap = argparse.ArgumentParser(
        description="Give a JAVV user a temporary password, to be changed at the next sign-in"
    )
    ap.add_argument("username")
    args = ap.parse_args()

    configure_logging()
    # stdout carries the password alone; the log lines keep the pipeline's JSON on stderr
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(sys.stderr))

    async def _run() -> str:
        client = build_client(get_settings())
        try:
            return await reset_password(client, args.username)
        finally:
            await client.close()

    try:
        temp = asyncio.run(_run())
    except ResetRefused as exc:
        print(f"not reset: {exc}", file=sys.stderr)
        sys.exit(1)
    print(temp)  # shown once: hand it to the user, who must change it at the next sign-in
