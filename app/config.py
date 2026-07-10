"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./golden_profile.db"
    # Comma-separated list of accepted API keys. Empty => auth disabled (dev only).
    api_keys: str = "dev-cami-key"
    # Comma-separated credential-match statuses treated as a valid cached result.
    valid_match_statuses: str = "VALID,ACTIVE,CLEAR,PASS,VERIFIED"
    hash_secret: str = "change-me"

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def valid_status_set(self) -> set[str]:
        return {s.strip().upper() for s in self.valid_match_statuses.split(",") if s.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
