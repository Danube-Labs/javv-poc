"""Runtime configuration. All env vars are `JAVV_`-prefixed; unknown ones are ignored (this is a
process-level config, not an untrusted request model — those are `extra="forbid"`)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JAVV_", extra="ignore")

    opensearch_url: str = "http://localhost:9200"
    request_timeout: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
