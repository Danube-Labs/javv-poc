"""Runtime configuration. All env vars are `JAVV_`-prefixed; unknown ones are ignored (this is a
process-level config, not an untrusted request model — those are `extra="forbid"`).

**Validated at construction (#219, major-audit 06 §2):** semantically-broken values (zero/negative
limits, garbage PIT grammar, inverted cap pairs) raise at the first `get_settings()` call — which
happens in the app lifespan, so a borked deployment CRASHES AT BOOT with the offending variable
named, instead of booting green and failing every request. `opensearch_url` stays a plain str (the
startup ping fail-fasts it with a better error); the pepper rule is owned by
`assert_production_ready` (env-profile aware), never duplicated here."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JAVV_", extra="ignore")

    # deployment profile (task C / Codex M3): "dev" keeps local-boot conveniences; anything
    # prod-like ("prod"/"production") turns them into startup FAILURES (assert_production_ready)
    env: str = "dev"
    opensearch_url: str = "http://localhost:9200"
    request_timeout: float = Field(default=30.0, gt=0)
    # startup contract: ping OpenSearch + run bootstrap before serving (fail-fast). Unit tests that
    # run the app without an OpenSearch set this false.
    bootstrap_on_startup: bool = True
    # ingest hardening (M1). The pepper MUST be set in any real deployment (D38/M14);
    # the dev default exists only so the app boots locally.
    token_pepper: str = "dev-only-pepper"
    ingest_max_compressed_bytes: int = Field(default=10 * 1024 * 1024, gt=0)  # 10 MiB on the wire
    ingest_max_body_bytes: int = Field(default=60 * 1024 * 1024, gt=0)  # decompressed (zip-bomb)
    ingest_rate_limit_per_minute: int = Field(default=120, ge=1)
    # human sessions (M5a/SEC-5): server-side TTL — the cookie's own lifetime is advisory
    session_ttl_hours: float = Field(default=24.0, gt=0)
    # login lockout (M5a): N failures per sliding window locks the username (429)
    login_max_attempts: int = Field(default=5, ge=1)
    login_lockout_minutes: float = Field(default=15.0, gt=0)
    # bulk triage (M5d, audit A-Mc/#189): bounded-synchronous. A frozen set at/under the inline
    # limit applies now (200 + result); above it → 413 (narrow, or M7's scheduled bulk). The freeze
    # itself never materializes more than bulk_max_targets ids (413 "selector too broad") — bounds
    # the freeze memory independently of the apply cost. No volatile 202/async path.
    bulk_inline_limit: int = Field(default=5000, ge=1)
    bulk_max_targets: int = Field(default=10000, ge=1)
    # findings search (M6): PIT keep-alive per page — an abandoned cursor's PIT self-expires.
    # OpenSearch time-unit grammar, one unit required (validated → pit_guard parses strictly)
    search_pit_keep_alive: str = Field(default="2m", pattern=r"^\d+(ms|s|m|h)$")
    # read-path DoS bounds (audit A-M6/A-m12/#189). Inline "run now" export (CSV + VEX) hard row
    # cap — past it the request 413s and points at narrower filters / M7 scheduled export. And a
    # per-principal concurrent-PIT cap (search cursors + exports) — past it → 429; in-memory per
    # pod like the ingest/login limiters (N replicas ⇒ N× budget).
    export_max_rows: int = Field(default=50000, ge=1)
    max_concurrent_pits_per_principal: int = Field(default=10, ge=1)
    # bootstrap admin (M5a/SEC-6): password from a mounted k8s Secret; empty = don't seed.
    # Seed-once — rotating the mounted value later has no effect on an existing admin by design.
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""
    # scheduled reports (M7/#32): results are stored IN OpenSearch (chunked) and TTL-swept.
    export_ttl_hours: int = Field(default=24, ge=1)  # completed export deleted this long after
    export_max_bytes: int = Field(default=500 * 1024 * 1024, ge=1)  # per-export ceiling → failed
    report_drain_sleep_ms: int = Field(default=200, ge=0)  # 0 = no throttle (legit in dev)
    report_lease_ttl_seconds: int = Field(default=300, ge=1)  # no heartbeat past it → reclaimable
    # data inspector (#406): the read-only store console. Hit ceiling per search, serialized
    # response byte cap (past it → 413, narrow the query), and a per-request timeout tighter
    # than the client default — an inspector query must never hog the store.
    inspect_max_hits: int = Field(default=500, ge=1)
    inspect_max_response_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    inspect_timeout_seconds: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def _cap_pairs_are_ordered(self) -> "Settings":
        # a compressed cap above the decompressed cap silently disables the zip-bomb guard
        if self.ingest_max_compressed_bytes > self.ingest_max_body_bytes:
            raise ValueError(
                "ingest_max_compressed_bytes must be ≤ ingest_max_body_bytes — the decompressed"
                " cap is the zip-bomb guard and must be the larger bound"
            )
        # an inline limit above the freeze cap makes the two 413s bite in a confusing order
        if self.bulk_inline_limit > self.bulk_max_targets:
            raise ValueError(
                "bulk_inline_limit must be ≤ bulk_max_targets — the freeze cap bounds what the"
                " inline path may ever be offered"
            )
        return self


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
