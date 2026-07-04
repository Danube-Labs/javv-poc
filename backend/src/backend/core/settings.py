"""Runtime configuration. All env vars are `JAVV_`-prefixed; unknown ones are ignored (this is a
process-level config, not an untrusted request model — those are `extra="forbid"`)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JAVV_", extra="ignore")

    # deployment profile (task C / Codex M3): "dev" keeps local-boot conveniences; anything
    # prod-like ("prod"/"production") turns them into startup FAILURES (assert_production_ready)
    env: str = "dev"
    opensearch_url: str = "http://localhost:9200"
    request_timeout: float = 30.0
    # startup contract: ping OpenSearch + run bootstrap before serving (fail-fast). Unit tests that
    # run the app without an OpenSearch set this false.
    bootstrap_on_startup: bool = True
    # ingest hardening (M1). The pepper MUST be set in any real deployment (D38/M14);
    # the dev default exists only so the app boots locally.
    token_pepper: str = "dev-only-pepper"
    ingest_max_compressed_bytes: int = 10 * 1024 * 1024  # 10 MiB on the wire
    ingest_max_body_bytes: int = 60 * 1024 * 1024  # 60 MiB decompressed (zip-bomb cap)
    ingest_rate_limit_per_minute: int = 120
    # human sessions (M5a/SEC-5): server-side TTL — the cookie's own lifetime is advisory
    session_ttl_hours: float = 24.0
    # login lockout (M5a): N failures per sliding window locks the username (429)
    login_max_attempts: int = 5
    login_lockout_minutes: float = 15.0
    # bootstrap admin (M5a/SEC-6): password from a mounted k8s Secret; empty = don't seed.
    # Seed-once — rotating the mounted value later has no effect on an existing admin by design.
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


_DEV_PEPPER = "dev-only-pepper"


def assert_production_ready(settings: Settings) -> None:
    """Fail-fast profile guard (task C / Codex M3): a prod-profile process must never run on the
    dev conveniences. Called at the top of the app lifespan — raising here aborts startup."""
    if settings.env.lower() not in ("prod", "production"):
        return
    if settings.token_pepper == _DEV_PEPPER:
        raise RuntimeError(
            "JAVV_ENV is production but JAVV_TOKEN_PEPPER is the dev default — every ingest-token"
            " and session hash would be forgeable-by-documentation. Set a real secret."
        )
