"""Observability counters exposed at /api/v1/stats."""
from __future__ import annotations

import json

from app import metrics


def _seed_valid(client, registry: str):
    client.post(
        "/api/v1/credential-matches",
        json={
            "cami_employee_id": 701,
            "registry_prefix": registry,
            "params_first_name": "Stat",
            "params_last_name": "Watcher",
            "params_credential_id": "L701",
            "params_license_type": "RN",
            "status": "VALID",
            "match": json.dumps({"response_code": "0"}),
        },
    )


def test_stats_tracks_hit_and_miss(client):
    metrics.reset()
    _seed_valid(client, "statreg")

    # One hit (seeded match) ...
    client.post(
        "/api/v1/search/credential",
        json={
            "registry_prefix": "statreg",
            "params_first_name": "Stat",
            "params_last_name": "Watcher",
            "params_credential_id": "L701",
            "params_license_type": "RN",
        },
    )
    # ... and one miss (unknown registry).
    client.post(
        "/api/v1/search/credential",
        json={
            "registry_prefix": "no-such-registry",
            "params_first_name": "Nobody",
            "params_last_name": "Here",
        },
    )

    body = client.get("/api/v1/stats").json()
    assert body["counters"]["search.hit"] == 1
    assert body["counters"]["search.miss"] == 1
    assert body["derived"]["search_total"] == 2
    assert body["derived"]["search_hit_rate"] == 0.5


def test_stats_counts_sync(client):
    metrics.reset()
    _seed_valid(client, "statreg2")
    body = client.get("/api/v1/stats").json()
    assert body["counters"].get("sync.credential.ok", 0) >= 1
