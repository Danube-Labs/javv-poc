"""Runtime configuration. All env vars are `JAVV_`-prefixed; unknown ones are ignored (this is a
process-level config, not an untrusted request model — those are `extra="forbid"`)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JAVV_", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
