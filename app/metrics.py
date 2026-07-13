"""In-process counters for Golden Profile observability.

Deliberately dependency-free: a thread-safe dict of monotonic counters exposed
via GET /api/v1/stats. Counters reset on process restart — enough to watch cache
hit-rate and sync health, and to catch silent degradation (e.g. a search that
suddenly serves 0 hits). For long-term history, scrape /api/v1/stats into an
external time-series store.

Sync endpoints run in FastAPI's threadpool, so increments are guarded by a lock.
"""
from __future__ import annotations

import threading
from collections import defaultdict

# Known counter names — search decisions and sync outcomes.
SEARCH_HIT = "search.hit"                    # returned a usable cached result
SEARCH_MISS = "search.miss"                  # nothing usable -> trigger_scrape
SEARCH_STALE = "search.stale"                # a valid match existed but was past TTL
SEARCH_RESOLVE = "search.auto_resolve"       # served via a name-mismatch resolution
SYNC_CREDENTIAL_OK = "sync.credential.ok"
SYNC_CREDENTIAL_BULK_OK = "sync.credential.bulk_ok"

_lock = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
# Rolling age (in days) of the most recent search hits, for a coarse freshness gauge.
_last_hit_age_days: list[int] = []
_MAX_AGE_SAMPLES = 200


def incr(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] += amount


def record_hit_age(age_days: int | None) -> None:
    if age_days is None:
        return
    with _lock:
        _last_hit_age_days.append(age_days)
        if len(_last_hit_age_days) > _MAX_AGE_SAMPLES:
            del _last_hit_age_days[0]


def snapshot() -> dict:
    """A JSON-serializable view of all counters + derived hit-rate."""
    with _lock:
        counters = dict(_counters)
        ages = list(_last_hit_age_days)

    hit = counters.get(SEARCH_HIT, 0)
    miss = counters.get(SEARCH_MISS, 0)
    total = hit + miss
    hit_rate = round(hit / total, 4) if total else None
    avg_age = round(sum(ages) / len(ages), 1) if ages else None

    return {
        "counters": counters,
        "derived": {
            "search_total": total,
            "search_hit_rate": hit_rate,
            "recent_hit_avg_age_days": avg_age,
            "recent_hit_samples": len(ages),
        },
    }


def reset() -> None:
    """Test helper — clear all counters."""
    with _lock:
        _counters.clear()
        _last_hit_age_days.clear()
