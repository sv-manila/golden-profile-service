"""Credential-match sync must be idempotent per check event.

A single CAMI check event is identified by (cami_credential_match_id, check_date).
The observer, a controller-level bulk push, and the reconcile safety-net can all
push the same event; without dedup each push appends a duplicate snapshot (and
the reconciler would double the whole recent window). Same event => one row.
"""


def _match(cami_id, check_date, **over):
    base = {
        "cami_employee_id": 9400,
        "cami_credential_match_id": cami_id,
        "params_first_name": "Ida",
        "params_last_name": "Idem",
        "params_credential_id": "NY-IDEM",
        "params_license_type": "RN",
        "registry": "idem-ny",
        "match_summary_status": "Valid",
        "status": "VALID",
        "match": "{\"response_code\":2}",
        "check_date": check_date,
    }
    base.update(over)
    return base


def test_same_check_event_syncs_once(client):
    p = _match(70001, "2026-06-01T00:00:00")
    r1 = client.post("/api/v1/credential-matches", json=p)
    r2 = client.post("/api/v1/credential-matches", json=p)
    assert r1.status_code == 201 and r2.status_code == 201
    # Second push of the same event returns the existing snapshot, not a new one.
    assert r2.json()["id"] == r1.json()["id"]


def test_new_check_date_creates_new_snapshot(client):
    r1 = client.post("/api/v1/credential-matches", json=_match(70002, "2026-06-01T00:00:00"))
    r2 = client.post("/api/v1/credential-matches", json=_match(70002, "2026-07-01T00:00:00"))
    assert r2.json()["id"] != r1.json()["id"]


def test_null_cami_id_always_appends(client):
    # Without a CAMI match id we cannot dedup safely -> append (no regression).
    p = _match(None, "2026-06-01T00:00:00")
    r1 = client.post("/api/v1/credential-matches", json=p)
    r2 = client.post("/api/v1/credential-matches", json=p)
    assert r2.json()["id"] != r1.json()["id"]


def test_bulk_collapses_duplicate_events(client):
    p = _match(70003, "2026-06-01T00:00:00")
    body = {"items": [p, p]}
    r = client.post("/api/v1/credential-matches/bulk", json=body)
    assert r.status_code in (200, 201), r.text
    ids = [row["id"] for row in r.json()["results"]]
    # Both items refer to the same event -> same row id.
    assert ids[0] == ids[1]
