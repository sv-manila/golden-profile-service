"""Fuzzy name-variant SUGGESTIONS — review-only, never an auto-merge.

Surfaces employees with a same-last-name + variant-first-name who are NOT already
strong-id linked, as candidates for a human to confirm. Records already merged by
a strong key are excluded (they are not suggestions). Two different people who
share a name are surfaced too — the human decides; the system never merges them.
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


def _suggest(client, first, last):
    return client.post("/api/v1/resolve/suggestions",
                       json={"params_first_name": first, "params_last_name": last}).json()


def test_prefix_variant_is_suggested(client):
    # Same person likely, but no shared strong id -> a suggestion, not a merge.
    _cm(client, emp=8830, registry="sug-a", cred="RJ1", first="Robert", last="Jonez")
    _cm(client, emp=8831, registry="sug-b", cred="RJ2", first="Rob", last="Jonez")
    ids = [s["cami_employee_id"] for s in _suggest(client, "Robert", "Jonez")["suggestions"]]
    assert 8831 in ids
    assert 8830 not in ids  # the query's own record is never suggested back


def test_already_strong_linked_not_suggested(client):
    # Kathy & Katherine Smithx share an NPI -> already merged -> NOT a suggestion.
    _cm(client, emp=8832, registry="sug-c", cred="SK1", first="Kathy", last="Smithx", npi="1930000001")
    _cm(client, emp=8833, registry="sug-d", cred="SK2", first="Katherine", last="Smithx", npi="1930000001")
    ids = [s["cami_employee_id"] for s in _suggest(client, "Kathy", "Smithx")["suggestions"]]
    assert 8833 not in ids


def test_different_last_name_not_suggested(client):
    _cm(client, emp=8834, registry="sug-e", cred="Z1", first="Zed", last="Alphaz")
    _cm(client, emp=8835, registry="sug-f", cred="Z2", first="Zed", last="Betaz")
    ids = [s["cami_employee_id"] for s in _suggest(client, "Zed", "Alphaz")["suggestions"]]
    assert 8835 not in ids


def test_suggestion_carries_score_and_reason(client):
    _cm(client, emp=8836, registry="sug-g", cred="M1", first="Maria", last="Santosz")
    _cm(client, emp=8837, registry="sug-h", cred="M2", first="M", last="Santosz")
    sug = _suggest(client, "Maria", "Santosz")["suggestions"]
    hit = [s for s in sug if s["cami_employee_id"] == 8837]
    assert hit and 0 < hit[0]["score"] <= 1 and hit[0]["reason"]
