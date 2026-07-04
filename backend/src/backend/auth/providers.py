"""Identity providers (M5a) — THE OIDC/LDAP seam (see the bolt README's auth design).

`IdentityProvider.authenticate` answers exactly one question: "is this human authentic, and which
`system-users` row are they?" Everything after — session mint, capabilities, auditing, logout — is
provider-agnostic and never forks per provider. Post-MVP `OidcProvider`/`LdapProvider` implement
this same protocol (verifying an IdP assertion / doing an LDAP bind + JIT-provisioning the user
row with `auth_source`/`external_id`) and the rest of the app doesn't change.

`LocalPasswordProvider` (the only MVP implementation) fails with one indistinct `None` for
unknown user / wrong password / non-local user / disabled account — and ALWAYS runs an argon2id
verify (against `DUMMY_HASH` when there's no real one), so response timing never reveals which
case it was."""

from dataclasses import dataclass
from typing import Any, Protocol

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.auth.passwords import DUMMY_HASH, verify_password

USERS_INDEX = "system-users"


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)


@dataclass(frozen=True)
class AuthResult:
    user_id: str  # == the system-users doc _id (username)
    user: dict[str, Any]  # the _source — callers must strip password_hash before responding


class IdentityProvider(Protocol):
    async def authenticate(
        self, client: AsyncOpenSearch, creds: LoginCredentials, *, prefix: str = ""
    ) -> AuthResult | None: ...


class LocalPasswordProvider:
    """argon2id against `system-users` (auth_source=local)."""

    async def authenticate(
        self, client: AsyncOpenSearch, creds: LoginCredentials, *, prefix: str = ""
    ) -> AuthResult | None:
        try:
            doc = (await client.get(index=f"{prefix}{USERS_INDEX}", id=creds.username))["_source"]
        except NotFoundError:
            verify_password(creds.password, DUMMY_HASH)  # timing equalizer — no user oracle
            return None
        stored = doc.get("password_hash")
        if doc.get("auth_source", "local") != "local" or not stored:
            verify_password(creds.password, DUMMY_HASH)  # external users have no local password
            return None
        if not verify_password(creds.password, stored) or doc.get("disabled"):
            return None
        return AuthResult(user_id=creds.username, user=doc)
