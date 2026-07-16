"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the project root (parent of app/), not the current
# working directory — so the service loads the same config no matter where it is
# launched from (e.g. a launcher whose cwd is a parent directory).
_ENV_FILE = str(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://root:root@127.0.0.1:33066/streamline_local"
    # Comma-separated list of accepted API keys. Empty => auth disabled (dev only).
    api_keys: str = "dev-cami-key"
    # Comma-separated credential-match statuses treated as a valid cached result.
    valid_match_statuses: str = "VALID,ACTIVE,CLEAR,PASS,VERIFIED"
    hash_secret: str = "change-me"

    # Cache freshness (TTL). A credential search will only serve a cached match
    # whose age (check_date, else date_created) is within this many days;
    # anything older is treated as a miss so CAMI re-scrapes for fresh data.
    # 0 disables the TTL check entirely (serve any age — the prior behaviour).
    credential_ttl_days: int = 0
    # Per-registry TTL overrides as a JSON object keyed by registry prefix, e.g.
    # '{"nursysny": 30, "oig": 180}'. Prefixes are matched case-insensitively.
    # Volatile registries (state boards) warrant short TTLs; static lists long.
    credential_ttl_overrides: str = ""

    # Credential `status` values representing a NO-MATCH determination — never
    # stored (no usable cached answer). Comma-separated; "2" is
    # CredentialMatch::NO_MATCH as serialized by the client.
    no_match_statuses: str = "2"

    # Resolution scoring: a candidate pair auto-merges into one canonical
    # identity at or above this score; falls into the review-only suggestions
    # band between here and resolve_suggest_threshold; below that, unrelated.
    resolve_merge_threshold: float = 0.85
    resolve_suggest_threshold: float = 0.5

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def no_match_status_set(self) -> set[str]:
        return {s.strip().upper() for s in self.no_match_statuses.split(",") if s.strip()}

    @property
    def valid_status_set(self) -> set[str]:
        return {s.strip().upper() for s in self.valid_match_statuses.split(",") if s.strip()}

    @property
    def ttl_override_map(self) -> dict[str, int]:
        """Registry-prefix -> TTL-days overrides. Malformed JSON => no overrides."""
        raw = (self.credential_ttl_overrides or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        if not isinstance(parsed, dict):
            return {}
        out: dict[str, int] = {}
        for key, value in parsed.items():
            try:
                out[str(key).strip().lower()] = int(value)
            except (ValueError, TypeError):
                continue
        return out

    def ttl_for_prefix(self, prefix: str | None) -> int:
        """Effective TTL in days for a registry prefix (0 => disabled)."""
        if prefix:
            override = self.ttl_override_map.get(prefix.strip().lower())
            if override is not None:
                return override
        return self.credential_ttl_days


@lru_cache
def get_settings() -> Settings:
    return Settings()
