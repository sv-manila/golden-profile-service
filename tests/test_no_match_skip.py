"""No-match credential results are never stored in the Golden Profile.

A NO_MATCH determination (CredentialMatch::NO_MATCH -> status "2") carries no
useful cached answer — storing it just pollutes the profile and the search. The
service drops it on sync regardless of which path posted it.
"""


def test_no_match_is_not_synced(client):
    r = client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 9700, "registry": "nm-skip",
        "params_first_name": "No", "params_last_name": "MatchZ",
        "params_credential_id": "NM-1", "status": "2",
        "match_summary_status": "Invalid - ", "match": "{\"response_code\":1}",
        "check_date": "2026-06-01T00:00:00",
    })
    assert r.status_code == 201
    assert r.json()["skipped"] is True
    assert r.json()["id"] is None
    # Nothing stored -> nothing to find.
    body = client.post("/api/v1/search/general",
                       json={"params_first_name": "No", "params_last_name": "MatchZ"}).json()
    assert body["credential_matches"] == []


def test_valid_is_still_synced(client):
    r = client.post("/api/v1/credential-matches", json={
        "cami_employee_id": 9701, "registry": "nm-ok",
        "params_first_name": "Yes", "params_last_name": "MatchZ",
        "params_credential_id": "OK-1", "status": "VALID",
        "match_summary_status": "Valid", "match": "{}", "check_date": "2026-06-01T00:00:00",
    })
    body = r.json()
    assert body["skipped"] is False
    assert body["id"] is not None


def test_bulk_drops_no_match_keeps_valid(client):
    r = client.post("/api/v1/credential-matches/bulk", json={"items": [
        {"cami_employee_id": 9702, "registry": "nm-b", "params_credential_id": "B1",
         "status": "2", "match": "{}", "check_date": "2026-06-01T00:00:00"},
        {"cami_employee_id": 9702, "registry": "nm-b", "params_credential_id": "B2",
         "status": "VALID", "match_summary_status": "Valid", "match": "{}",
         "check_date": "2026-06-01T00:00:00"},
    ]})
    assert r.status_code in (200, 201)
    # Only the valid one is stored.
    assert r.json()["count"] == 1
