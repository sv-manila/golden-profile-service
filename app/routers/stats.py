"""Observability endpoint — cache hit-rate and sync counters."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import metrics
from ..security import require_api_key

router = APIRouter(prefix="/api/v1/stats", tags=["meta"], dependencies=[Depends(require_api_key)])


@router.get("")
def stats():
    """Monotonic in-process counters + derived search hit-rate.

    Resets on restart. Poll this to watch cache effectiveness and to alert on
    silent degradation (e.g. hit_rate collapsing to 0 after a schema drift)."""
    return metrics.snapshot()
