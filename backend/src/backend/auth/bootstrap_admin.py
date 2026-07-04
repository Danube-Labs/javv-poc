"""Bootstrap admin (M5a, FR-18/SEC-6) — seed-once from a mounted secret.

The deployment mounts the initial admin password as `JAVV_BOOTSTRAP_ADMIN_PASSWORD` (a k8s
Secret, never a ConfigMap/values file); at startup we create the admin user **exactly once**
(`op_type=create` — a concurrent pod or a restart is a clean no-op, and an existing admin is
NEVER overwritten, so rotating the mounted secret later has no effect by design). The seeded
account carries `must_change: true`: the first login gets a restricted session that can only
change its password (enforced server-side in the routes/capability gate, not by the UI)."""

from datetime import UTC, datetime

from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConflictError

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings

USERS_INDEX = "system-users"


async def seed_bootstrap_admin(client: AsyncOpenSearch, *, prefix: str = "") -> str:
    """Returns created | exists | skipped (skipped = no secret mounted; fine for tests/dev)."""
    settings = get_settings()
    if not settings.bootstrap_admin_password:
        return "skipped"
    try:
        await client.index(
            index=f"{prefix}{USERS_INDEX}",
            id=settings.bootstrap_admin_username,
            body={
                "username": settings.bootstrap_admin_username,
                "password_hash": hash_password(settings.bootstrap_admin_password),
                "role": "admin",
                "capabilities": ["*"],  # Admin holds all (D33); "*" is the pass-all marker
                "must_change": True,  # SEC-6 — forced first-login password change
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": datetime.now(UTC).isoformat(),
            },
            params={"op_type": "create", "refresh": "true"},
        )
    except ConflictError:
        return "exists"
    return "created"
