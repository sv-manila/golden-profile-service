"""Hot-path resolution can read the persisted graph, with a live fallback.

group_for_seeds(use_persisted=True) reads employee_canonical for seeds already
materialized and falls back to a live closure for seeds not yet rebuilt — so the
fast path matches the live result for rebuilt data and never drops fresh records,
though a rebuilt seed stays stale until the next rebuild.
"""
import json

from app.services import resolution


def _cm(client, *, emp, registry, npi):
    r = client.post("/api/v1/credential-matches", json={
        "cami_employee_id": emp, "registry": registry,
        "params_first_name": "Hot", "params_last_name": f"Path{emp}",
        "params_credential_id": f"L{emp}", "params_license_type": "RN",
        "match_summary_status": "Valid", "status": "VALID",
        "match": json.dumps({"npi": npi}), "check_date": "2026-06-01T00:00:00",
    })
    assert r.status_code == 201, r.text


def test_persisted_matches_live_after_rebuild(client, db):
    _cm(client, emp=8820, registry="hp-a", npi="1950000001")
    _cm(client, emp=8821, registry="hp-b", npi="1950000001")
    client.post("/api/v1/resolve/rebuild")

    live = resolution.group_for_seeds(db, {8820}, use_persisted=False)
    persisted = resolution.group_for_seeds(db, {8820}, use_persisted=True)
    assert live == persisted == {8820, 8821}


def test_persisted_falls_back_for_unrebuilt_seed(client, db):
    _cm(client, emp=8822, registry="hp-c", npi="1950000009")
    client.post("/api/v1/resolve/rebuild")
    # New linked record synced AFTER the rebuild — not yet in employee_canonical.
    _cm(client, emp=8823, registry="hp-d", npi="1950000009")

    # Seed not in the table -> live fallback finds the whole group.
    assert resolution.group_for_seeds(db, {8823}, use_persisted=True) == {8822, 8823}
    # Seed in the table -> served from the (stale) graph; misses 8823 til rebuild.
    assert resolution.group_for_seeds(db, {8822}, use_persisted=True) == {8822}
