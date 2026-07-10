"""Deterministic hashing helpers for SSN / TIN when CAMI sends raw values."""
from __future__ import annotations

import hashlib

from .config import get_settings


def derive_hash(raw: str | None) -> str | None:
    """HMAC-style salted SHA-256 hex digest of a sensitive value."""
    if not raw:
        return None
    secret = get_settings().hash_secret.encode()
    return hashlib.sha256(secret + raw.encode()).hexdigest()


def last_four(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else None
