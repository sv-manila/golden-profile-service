"""Persisted canonical graph: rebuild materializes canonical identities as rows,
and a fast per-employee lookup reads them without rescanning every match.
"""
import json


def _cm(client, *, emp, registry, cred, first, last, npi=None):
    match = {"npi": npi} if npi else {}
    r = client.post("/api/v1/credential-matches", json={
        "cami_employee_id": emp, "registry": registry,
        "params_first_name": first, "params_last_name": last,
        "params_credential_id": cred, "params_license_type": "RN",
        "match_summary_status": "Valid", "status": "VALID",
        "match": json.dumps(match), "check_date": "2026-06-01T00:00:00",
    })
    assert r.status_code == 201, r.text


def test_rebuild_then_fast_lookup(client):
    # 8810 & 8811 are one person (shared NPI); 8812 is a singleton.
    _cm(client, emp=8810, registry="cp-a", cred="A", first="Cy", last="Persist", npi="1960000001")
    _cm(client, emp=8811, registry="cp-b", cred="B", first="Cyrus", last="Persist", npi="1960000001")
    _cm(client, emp=8812, registry="cp-c", cred="C", first="Solo", last="PersistS")

    rb = client.post("/api/v1/resolve/rebuild").json()
    assert rb["employees"] >= 3
    assert rb["groups"] >= 2

    grouped = client.get("/api/v1/resolve/employee/8810").json()
    assert grouped["resolved"] is True
    assert grouped["match_basis"] == "persisted"
    assert sorted(grouped["canonical_employee_ids"]) == [8810, 8811]

    solo = client.get("/api/v1/resolve/employee/8812").json()
    assert sorted(solo["canonical_employee_ids"]) == [8812]


def test_lookup_unknown_employee_is_unresolved(client):
    client.post("/api/v1/resolve/rebuild")
    body = client.get("/api/v1/resolve/employee/424242").json()
    assert body["resolved"] is False
    assert body["canonical_employee_ids"] == []
