"""API-key authentication for CAMI -> Golden Profile calls."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Validate the X-API-Key header against the configured key set.

    If no API keys are configured, auth is disabled (intended for local dev only).
    """
    settings = get_settings()
    keys = settings.api_key_set
    if not keys:
        return "anonymous"
    if x_api_key is None or x_api_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
    return x_api_key
