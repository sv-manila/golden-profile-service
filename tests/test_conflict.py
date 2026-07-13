"""Conflict flagging in the general (name-based) search.

Artifact promise ("two sources disagree"): when the same person + same registry
+ same license has contradictory validity across recent snapshots, keep the most
trusted (newest) answer, but flag the conflict and expose the disagreeing rows —
never quietly pick one.
"""


def _post_match(client, *, emp, first, last, registry, cred, status, summary, check_date):
    r = client.post("/api/v1/credential-matches", json={
        "cami_employee_id": emp, "registry": registry,
        "params_first_name": first, "params_last_name": last,
        "params_credential_id": cred, "params_license_type": "RN",
        "match_summary_status": summary, "status": status,
        "match": "{\"response_code\":2}", "check_date": check_date,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_general_search_flags_conflicting_status(client):
    first, last, emp, reg = "Cora", "ConflictA", 9600, "conf-a-ny"
    # Older snapshot says INVALID, newer says VALID — same registry + license.
    old_id = _post_match(client, emp=emp, first=first, last=last, registry=reg,
                         cred="NY-900", status="1", summary="Invalid - Expired",
                         check_date="2025-01-01T00:00:00")
    new_id = _post_match(client, emp=emp, first=first, last=last, registry=reg,
                         cred="NY-900", status="VALID", summary="Valid",
                         check_date="2026-06-01T00:00:00")

    body = client.post("/api/v1/search/general",
                       json={"params_first_name": first, "params_last_name": last}).json()
    matches = [m for m in body["credential_matches"] if m["registry"] == reg]
    assert len(matches) == 1
    winner = matches[0]
    # Newest wins and is reported valid.
    assert winner["id"] == new_id
    assert winner["has_conflict"] is True
    # The disagreeing older snapshot is exposed, not dropped.
    assert len(winner["conflicts"]) == 1
    assert winner["conflicts"][0]["id"] == old_id
    assert winner["conflicts"][0]["valid"] is False


def test_general_search_no_conflict_when_snapshots_agree(client):
    first, last, emp, reg = "Cora", "ConflictB", 9601, "conf-b-ny"
    # Two snapshots, same VALID determination — re-verification, not a conflict.
    _post_match(client, emp=emp, first=first, last=last, registry=reg,
                cred="NY-901", status="VALID", summary="Valid",
                check_date="2025-01-01T00:00:00")
    _post_match(client, emp=emp, first=first, last=last, registry=reg,
                cred="NY-901", status="VALID", summary="Valid",
                check_date="2026-06-01T00:00:00")

    body = client.post("/api/v1/search/general",
                       json={"params_first_name": first, "params_last_name": last}).json()
    matches = [m for m in body["credential_matches"] if m["registry"] == reg]
    assert len(matches) == 1
    assert matches[0]["has_conflict"] is False
    assert matches[0]["conflicts"] == []


def test_general_search_different_registries_are_not_a_conflict(client):
    """Different registries legitimately differ (different scope) — not a conflict."""
    first, last, emp = "Cora", "ConflictC", 9602
    _post_match(client, emp=emp, first=first, last=last, registry="conf-c-ny",
                cred="NY-902", status="VALID", summary="Valid",
                check_date="2026-06-01T00:00:00")
    _post_match(client, emp=emp, first=first, last=last, registry="conf-c-ca",
                cred="CA-902", status="1", summary="Invalid - Expired",
                check_date="2026-06-01T00:00:00")

    body = client.post("/api/v1/search/general",
                       json={"params_first_name": first, "params_last_name": last}).json()
    for m in body["credential_matches"]:
        if m["registry"] in ("conf-c-ny", "conf-c-ca"):
            assert m["has_conflict"] is False
